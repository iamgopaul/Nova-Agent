"""
GAAIA Document router — LLM-powered document generation.

POST /document/generate  { "prompt": "...", "format": "docx|xlsx|pdf|pptx|txt|csv", "session_id": "..." }
  → 200  appropriate MIME type  (file bytes)
  → 400  unsupported format
  → 500  generation failure

Flow:
  1. Call GAIA Core (mistral:7b) to produce structured JSON content from the user prompt.
  2. Optionally generate images per section/slide using Stable Diffusion.
  3. Pass the JSON (+images) to document_generator which formats it into the requested file type.
  4. Return the raw file bytes with the correct Content-Type + Content-Disposition headers.
"""

from __future__ import annotations

import asyncio
import json
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from gaaia.agent.orchestrator import Orchestrator
from gaaia.server.dependencies import get_orchestrator

router = APIRouter()

_SUPPORTED_FORMATS = {"docx", "xlsx", "pdf", "pptx", "txt", "csv"}

_IMAGE_KEYWORDS = (
    "image", "images", "photo", "photos", "picture", "pictures",
    "visual", "visuals", "illustration", "graphic", "graphics",
    "drawing", "drawings", "sketch", "sketches", "artwork", "artworks",
    "painted", "painting", "paintings",
)

_DRAWING_KEYWORDS = (
    "drawing", "drawings", "sketch", "sketches", "drawn", "hand-drawn",
    "hand drawn", "painted", "painting", "watercolor", "pencil",
    "illustrated", "illustration",
)

# Artistic style suffixes to alternate between for variety in documents
_DOC_ART_STYLES = [
    ", cinematic lighting, highly detailed, vibrant colors, 8k, photorealistic",
    ", detailed pencil sketch, fine linework, graphite on white paper, intricate, masterpiece",
    ", beautiful watercolor painting, soft washes, wet on wet technique, vibrant watercolor",
    ", professional concept art, artstation trending, cinematic lighting, ultra detailed, 8k",
    ", oil painting on canvas, rich textures, impasto technique, masterpiece oil painting",
    ", cinematic lighting, ultra detailed, dramatic composition, 8k, photorealistic",
]


def _wants_images(prompt: str) -> bool:
    low = prompt.lower()
    return any(kw in low for kw in _IMAGE_KEYWORDS)


def _wants_drawings(prompt: str) -> bool:
    """Return True if the user explicitly asked for drawings/sketches alongside images."""
    low = prompt.lower()
    return any(kw in low for kw in _DRAWING_KEYWORDS)


# ── LLM prompts per format ────────────────────────────────────────────────────

_PROSE_PROMPT = """\
You are a professional document writer. The user wants a {fmt} document.

Based on the user's request, produce a JSON object with this schema:
{{
  "title":    "Document title",
  "subtitle": "Optional subtitle or author",
  "sections": [
    {{
      "heading":      "Section heading",
      "paragraphs":   ["paragraph 1 text", "paragraph 2 text", ...],
      "image_prompt": "A short visual description for image generation (include ONLY when images are requested)"
    }}
  ]
}}

Rules:
- Write full, well-structured content — not placeholders.
- Use 3-6 sections appropriate to the topic.
- Each section should have 1-4 paragraphs.
- Include "image_prompt" per section ONLY if the user explicitly requests images/visuals.
- Keep image_prompt concise (15-25 words), describe the visual clearly, add style tags like "professional photography, vibrant colors, 8k".
- Return ONLY valid JSON. No markdown fences, no extra text.

User request: {prompt}
"""

_SPREADSHEET_PROMPT = """\
You are a data analyst. The user wants an Excel spreadsheet.

Based on the user's request, produce a JSON object with this schema:
{{
  "title": "Workbook title",
  "sheets": [
    {{
      "sheet_title": "Tab name (max 31 chars)",
      "headers": ["Column 1", "Column 2", ...],
      "rows": [
        ["label", 123, 456],
        ...
      ],
      "chart": {{
        "type": "bar",
        "title": "Chart title",
        "category_col": 0,
        "value_cols": [1, 2]
      }}
    }}
  ]
}}

Chart rules:
- "type" must be one of: "bar", "line", "pie", "area".  Use "bar" when unsure.
- "category_col" is the 0-based column index used as x-axis labels / pie slice names.
- "value_cols" is a list of 0-based column indices that contain numeric values to plot.
- Omit "chart" entirely if the sheet is purely a reference table with no meaningful chart.
- For a pie chart, value_cols should contain exactly one column index.

General rules:
- Use multiple sheets when the data naturally separates (e.g. monthly vs annual summary).
- Include realistic, meaningful numeric data — no placeholders like "value1".
- Provide at least 6-12 data rows per sheet.
- All rows must have the same number of values as headers.
- Numeric columns must contain numbers, not strings.
- Return ONLY valid JSON. No markdown fences, no extra text.

User request: {prompt}
"""

_SLIDES_PROMPT = """\
You are a presentation designer. The user wants a PowerPoint presentation.

Based on the user's request, produce a JSON object with this schema:
{{
  "title":    "Presentation title",
  "subtitle": "Subtitle or presenter name",
  "sections": [
    {{
      "heading":      "Slide title",
      "paragraphs":   ["bullet point 1", "bullet point 2", ...],
      "image_prompt": "A short visual description for image generation (include ONLY when images are requested)"
    }}
  ]
}}

Rules:
- Create 6-10 slides.
- Each slide should have 3-5 concise bullet points.
- Include "image_prompt" per slide ONLY if the user explicitly requests images/visuals.
- Keep image_prompt concise (15-25 words), describe the visual clearly, add style tags like "professional photography, vibrant colors, 8k".
- Return ONLY valid JSON. No markdown fences, no extra text.

User request: {prompt}
"""


def _pick_prompt(fmt: str, prompt: str) -> str:
    if fmt in ("xlsx", "csv"):
        return _SPREADSHEET_PROMPT.format(fmt=fmt.upper(), prompt=prompt)
    if fmt == "pptx":
        return _SLIDES_PROMPT.format(fmt=fmt.upper(), prompt=prompt)
    return _PROSE_PROMPT.format(fmt=fmt.upper(), prompt=prompt)


# ── Parallel image generation ─────────────────────────────────────────────────

_MAX_IMAGES = {"pptx": 8, "pdf": 8, "docx": 8, "txt": 0, "xlsx": 3, "csv": 0}

# Sequential semaphore — Stable Diffusion is NOT thread-safe for concurrent inference
# on the same model instance.  Run one image at a time.
_IMG_SEM: asyncio.Semaphore | None = None
_IMG_TIMEOUT = 360.0   # 6 minutes max per image


def _get_img_sem() -> asyncio.Semaphore:
    global _IMG_SEM
    if _IMG_SEM is None:
        _IMG_SEM = asyncio.Semaphore(1)
    return _IMG_SEM


async def _generate_images_for_content(content: dict, fmt: str) -> None:
    """
    For each section/sheet that has an "image_prompt", generate a PNG image
    (using Stable Diffusion) and attach it as "image_bytes".
    Mutates *content* in-place.

    Images are generated strictly one at a time (semaphore=1) to avoid
    concurrent access to the SD pipeline which is not thread-safe.
    Each generation is capped at _IMG_TIMEOUT seconds.
    """
    from gaaia.services.image_generator import generate_image

    max_imgs = _MAX_IMAGES.get(fmt, 0)
    if max_imgs == 0:
        return

    # Support both "sections" (pptx/docx/pdf) and "sheets" (xlsx)
    items: list[dict] = content.get("sections") or []
    if fmt == "xlsx":
        items = [s for sheet in content.get("sheets", []) for s in [sheet]]

    sem = _get_img_sem()

    async def _gen_one(item: dict, idx: int) -> None:
        prompt = item.get("image_prompt", "").strip()
        if not prompt:
            return
        async with sem:
            print(
                f"[DocRouter] Image {idx+1}: '{prompt[:70]}…'",
                flush=True,
            )
            try:
                img_bytes = await asyncio.wait_for(
                    asyncio.to_thread(
                        generate_image,
                        prompt,
                        width=512,
                        height=384,   # taller than before, better aspect ratio
                        steps=22,     # DPM++ 22 steps ≈ PNDM 40 steps in quality
                        guidance_scale=8.5,
                    ),
                    timeout=_IMG_TIMEOUT,
                )
                item["image_bytes"] = img_bytes
                print(
                    f"[DocRouter] Image {idx+1} done — {len(img_bytes)//1024} KB",
                    flush=True,
                )
            except asyncio.TimeoutError:
                print(
                    f"[DocRouter] Image {idx+1} timed out after {_IMG_TIMEOUT}s — skipping",
                    flush=True,
                )
            except Exception as exc:
                print(f"[DocRouter] Image {idx+1} failed: {exc}", flush=True)

    candidates = [it for it in items[:max_imgs] if it.get("image_prompt")]
    if not candidates:
        print(
            f"[DocRouter] No image_prompts found in {fmt.upper()} content — skipping image gen",
            flush=True,
        )
        return

    print(
        f"[DocRouter] Generating {len(candidates)} image(s) for {fmt.upper()} (sequential)…",
        flush=True,
    )
    # Run sequentially via gather — the semaphore(1) ensures only one runs at a time
    # but gather lets us launch all coroutines and wait for them together.
    await asyncio.gather(
        *[asyncio.create_task(_gen_one(it, i)) for i, it in enumerate(candidates)]
    )
    print("[DocRouter] All images done.", flush=True)


async def _apply_web_images_to_content(content: dict, web_image_urls: list[str]) -> None:
    """
    Download web image bytes from *web_image_urls* and attach them to sections in
    *content* (one URL per section, in order).  Sections that already have
    ``image_bytes`` are skipped.  Mutates *content* in-place.
    """
    sections: list[dict] = content.get("sections") or []
    if not sections or not web_image_urls:
        return

    async def _download(url: str) -> bytes | None:
        try:
            async with httpx.AsyncClient(
                timeout=20.0,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; GAAIAAgent/1.0)"},
            ) as client:
                resp = await client.get(url)
                if resp.status_code == 200 and "image" in resp.headers.get("content-type", ""):
                    return resp.content
        except Exception as exc:
            print(f"[DocRouter] Web image download failed ({url[:60]}): {exc}", flush=True)
        return None

    async def _apply_one_url(sec: dict, url: str) -> bool:
        if not url or not str(url).strip().lower().startswith("http"):
            return False
        img_bytes = await _download(url)
        if not img_bytes:
            return False
        sec["image_bytes"] = img_bytes
        sec.setdefault("image_prompt", "web image")
        print(
            f"[DocRouter] Web image applied to '{sec.get('heading', '?')}': "
            f"{len(img_bytes) // 1024} KB",
            flush=True,
        )
        return True

    applied = 0
    # Aligned with section indices (sparse placement from GAIA Core)
    if len(web_image_urls) == len(sections):
        for i, sec in enumerate(sections):
            if sec.get("image_bytes"):
                continue
            u = (web_image_urls[i] or "").strip()
            if await _apply_one_url(sec, u):
                applied += 1
    else:
        # Legacy: URLs consumed in order for the first N sections
        url_iter = iter(x for x in web_image_urls if x and str(x).strip().lower().startswith("http"))
        for sec in sections:
            if sec.get("image_bytes"):
                continue
            try:
                u = next(url_iter)
            except StopIteration:
                break
            if await _apply_one_url(sec, u):
                applied += 1

    print(f"[DocRouter] Web images applied: {applied}/{len(sections)} sections", flush=True)


async def _llm_image_placement_analysis(
    story_text: str,
    host: str,
    model: str,
    max_images: int,
) -> list[dict]:
    """
    Use GAIA Core to analyze a story and identify the best positions for images.

    Returns a list of dicts:
      {"heading_keywords": "3-5 keywords from the section", "prompt": "SD prompt …"}

    Falls back to an empty list on any error.
    """
    system = (
        f"You are a visual director for illustrated books. "
        f"Given a story, identify exactly {max_images} key visual moments "
        f"that would make the most impactful illustrations.\n\n"
        f"For each moment provide:\n"
        f"1. heading_keywords: 3-5 lowercase words from the nearest section heading or paragraph start "
        f"(used to match the correct part of the document)\n"
        f"2. prompt: a vivid, specific Stable Diffusion image prompt (25-35 words) that visually "
        f"represents this scene. Include art style, lighting, and quality tags "
        f"(e.g. 'cinematic lighting, ultra-detailed, 8k, photorealistic').\n\n"
        f"Return ONLY a JSON array — no markdown fences, no extra text:\n"
        f'[{{"heading_keywords": "cosmic birth stars", "prompt": "big bang explosion swirling nebula golden light, '
        f'cinematic 8k photorealistic space photography"}}, ...]'
    )

    truncated = story_text[:4000]

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                f"{host}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user",   "content": truncated},
                    ],
                    "stream": False,
                    "options": {"num_predict": 1000, "temperature": 0.35},
                },
            )
            resp.raise_for_status()
            raw = resp.json()["message"]["content"].strip()

        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if m:
            placements = json.loads(m.group())
            if isinstance(placements, list):
                return placements[:max_images]
    except Exception as exc:
        print(f"[DocRouter] LLM image placement analysis failed: {exc}", flush=True)

    return []


def _apply_llm_image_prompts(sections: list[dict], placements: list[dict]) -> None:
    """
    Match LLM-suggested image placements to sections by keyword search and assign
    ``image_prompt`` to sections that don't already have one.
    Mutates *sections* in-place.
    """
    for placement in placements:
        keywords = placement.get("heading_keywords", "").lower().split()
        prompt   = (placement.get("prompt") or "").strip()
        if not prompt or not keywords:
            continue

        # Try heading match first, then first-paragraph match
        matched = False
        for sec in sections:
            if sec.get("image_prompt"):
                continue  # already assigned
            heading    = sec.get("heading", "").lower()
            para_start = " ".join(sec.get("paragraphs", [])[:1]).lower()[:120]
            combined   = heading + " " + para_start
            if sum(1 for kw in keywords if kw in combined) >= 2:
                sec["image_prompt"] = prompt
                matched = True
                break

        if not matched:
            # Assign to the next section without a prompt
            for sec in sections:
                if not sec.get("image_prompt"):
                    sec["image_prompt"] = prompt
                    break


async def _llm_structure(
    host: str, model: str, fmt: str, user_prompt: str
) -> dict:
    """
    Ask the LLM to produce structured JSON content for the document.
    Falls back to a simple plain-text body on any error.
    """
    system_prompt = _pick_prompt(fmt, user_prompt)

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{host}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "stream": False,
                    "options": {"num_predict": 2000, "temperature": 0.4},
                },
            )
            resp.raise_for_status()
            raw = resp.json()["message"]["content"].strip()

        # Extract the first JSON object / array from the response
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group())

    except Exception as exc:
        print(f"[DocRouter] LLM structuring failed: {exc} — using plain body", flush=True)

    # Fallback: treat raw LLM output as body text
    return {"title": "Document", "body": user_prompt}


# ── Request / endpoint ────────────────────────────────────────────────────────

class DocumentRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    format: str = Field(default="docx")
    session_id: str = Field(default="")
    # Optional: the actual assistant response from the chat — when provided, its
    # content is used directly instead of calling the LLM again, ensuring the
    # document matches exactly what was displayed in the chat.
    response: str = Field(default="")
    # Optional: web image URLs to embed in the document (one per section).
    # When provided, the document router downloads these images instead of
    # generating them with Stable Diffusion, so the doc matches the chat view.
    web_image_urls: list[str] = Field(default_factory=list)


def _derive_title_from_prompt(prompt: str) -> str:
    """
    Derive a clean, title-cased document title from the user's prompt.
    Strips common request prefixes so "Write an essay about Destiny 2" → "Destiny 2".
    """
    p = prompt.strip()
    # Strip leading action phrases
    p = re.sub(
        r"^(?:write|generate|create|make|produce|draft|give me|can you write|can you create)"
        r"\s+(?:me\s+)?(?:an?\s+)?(?:essay|document|report|article|story|summary|overview|"
        r"introduction|guide|analysis|biography|bio|paper|research\s+paper|word\s+doc|pdf)?"
        r"(?:\s+(?:about|on|for|regarding|of|describing))?\s*",
        "",
        p,
        flags=re.IGNORECASE,
    ).strip()
    # Strip trailing format specifiers
    p = re.sub(r"\s+(?:in\s+both\s+)?(?:pdf|docx?|word|excel)\s*(?:and\s+(?:pdf|docx?|word))?\.?$", "", p, flags=re.IGNORECASE).strip()
    if not p:
        return "Document"
    # Title-case
    return p[:80].title()


def _parse_markdown_tables(text: str) -> dict | None:
    """
    Extract markdown tables from *text* and return an xlsx-compatible content dict.

    Each table becomes one sheet.  Returns None if no tables are found.

    Example markdown table:
        | Month | Sales | Profit |
        |-------|-------|--------|
        | Jan   | 1000  | 200    |
    """
    # Match a markdown table: header row | separator row | 1+ data rows
    TABLE_RE = re.compile(
        r"(?:^|\n)"
        r"(\|[^\n]+\|[ \t]*\n)"           # header row
        r"(?:\|[-| :]+\|[ \t]*\n)"        # separator row (ignored)
        r"((?:\|[^\n]+\|[ \t]*\n?)+)",    # data rows
        re.MULTILINE,
    )

    def _parse_row(line: str) -> list[str]:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        return cells

    def _coerce(val: str) -> int | float | str:
        try:
            return int(val)
        except ValueError:
            pass
        try:
            return float(val.replace(",", ""))
        except ValueError:
            return val

    sheets = []
    for i, m in enumerate(TABLE_RE.finditer(text)):
        headers = _parse_row(m.group(1))
        rows    = [
            [_coerce(c) for c in _parse_row(line)]
            for line in m.group(2).splitlines()
            if line.strip()
        ]
        if not headers or not rows:
            continue

        # Detect numeric value columns for auto-chart
        numeric_cols = [
            ci for ci, _ in enumerate(headers)
            if any(isinstance(r[ci], (int, float)) for r in rows if ci < len(r))
        ]
        cat_col   = next((ci for ci, _ in enumerate(headers) if ci not in numeric_cols), 0)
        val_cols  = [c for c in numeric_cols if c != cat_col] or numeric_cols[:1]

        sheet: dict = {
            "sheet_title": f"Sheet{i + 1}",
            "headers":     headers,
            "rows":        rows,
        }
        if val_cols:
            sheet["chart"] = {
                "type":         "bar",
                "title":        f"Chart — {headers[cat_col]} vs {', '.join(headers[c] for c in val_cols if c < len(headers))}",
                "category_col": cat_col,
                "value_cols":   val_cols,
            }
        sheets.append(sheet)

    if not sheets:
        return None

    return {"title": "Data", "sheets": sheets}


def _clean_response_text(text: str) -> str:
    """
    Strip all known LLM-appended closing markers and instruction echoes from
    document response text before it is parsed into document structure.
    Applied in the document router as a safety net — catches anything that
    slipped through the chat router's cleanup.
    """
    # [DOCUMENT FORMATTING ...] instruction echo
    text = re.sub(r"\[DOCUMENT FORMATTING[^\]]*\][\s\S]*?(?=\n\n|\Z)", "", text, flags=re.IGNORECASE)
    # <<SYSTEM:...>>...<<END_SYSTEM>> echo
    text = re.sub(r"<<SYSTEM:[^>]*>>[\s\S]*?<<END_SYSTEM>>", "", text, flags=re.IGNORECASE)
    # [Internal — ...] echoes
    text = re.sub(r"\[Internal\s*[-—][^\]]*\]?", "", text, flags=re.IGNORECASE)
    # "End of Essay" / "End of Document" style markers (with or without brackets/asterisks)
    text = re.sub(
        r"\*{0,2}\[?\s*(?:End\s+of\s+(?:Essay|Document|Story|Report|Article|Section|Response|Draft|Text|Content))\s*\]?\*{0,2}\.?\s*$",
        "",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    # Orphaned [Essay], [Document] type bracket labels
    text = re.sub(r"^\s*\[\s*(?:Essay|Document|Story|Report|Draft)\s*\]\s*$", "", text, flags=re.IGNORECASE | re.MULTILINE)
    # Collapse excessive blank lines
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def _strip_markdown(text: str) -> str:
    """Remove markdown syntax while preserving the text content and line breaks."""
    # Remove fenced code blocks (```...```) — keep the code content
    text = re.sub(r"```[^\n]*\n(.*?)```", r"\1", text, flags=re.DOTALL)
    # Remove inline code
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Remove headings markers (# ## ###) but keep the heading text
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove bold/italic markers
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text)
    # Remove markdown links — keep display text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove horizontal rules
    text = re.sub(r"^[-=*]{3,}\s*$", "", text, flags=re.MULTILINE)
    # Collapse 3+ blank lines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _parse_markdown_to_structure(
    text: str,
    fmt: str,
    with_image_prompts: bool = False,
    vary_art_styles: bool = False,
) -> dict:
    """
    Convert the assistant's markdown response into the structured JSON schema
    expected by document_generator — without calling the LLM again.

    Handles:
      • Standard markdown headings  (## Heading)
      • Slide / section labels       (Slide 1: Title, Section 2 - Title)
      • Bold headings                (**Title**)
      • Numbered headings            (1. Title, 2. Title at line start)
      • Narrative headings           (Title – Time Period: body text)
      • Image bullets                (• Image: ..., - Image: ...)
      • INLINE bracket markers       ([Image: desc] anywhere in a line)
      • Text content bullets         (• Text: ...)
    """
    # ── Pre-compile all regexes ────────────────────────────────────────────────
    # Slide/chapter style labels
    _SLIDE_RE = re.compile(
        r"^(?:slide|section|part|chapter|step|topic|lesson|module|unit)\s*\d*\s*[:\-–—]\s*(.+)$",
        re.IGNORECASE,
    )
    _NUM_HEADING_RE  = re.compile(r"^\d+[.\-–:]\s+(.{4,80})$")
    _BOLD_HEADING_RE = re.compile(r"^\*{2}(.+)\*{2}$|^_{2}(.+)_{2}$")
    _IMAGE_BULLET_RE = re.compile(
        r"^[-*+•]\s*\*{0,2}[Ii](?:mage|llustration|llustrations)\*{0,2}\s*[:\-]\s*\*{0,2}\s*(.+)$"
    )
    _IMAGE_INLINE_RE = re.compile(r"\*{1,2}[Ii]mage\*{1,2}\s*[:\-]\s*(.+)")
    _TEXT_BULLET_RE  = re.compile(r"^[-*+•]\s*\*{0,2}[Tt]ext\*{0,2}\s*[:\-]\s*\*{0,2}\s*(.+)$")

    # INLINE bracket marker — matches [Image: desc], [Drawing: desc], [Illustration 3: desc]
    # ANYWHERE in a line (not anchored to line start/end).
    _INLINE_BRACKET_RE = re.compile(
        r"\[(?:Image|Drawing|Sketch|Illustration|Photo|Figure|Visual|Graphic|Picture|Painting|Artwork)"
        r"\s*\d*\s*[:\-–]\s*([^\]]+)\]",
        re.IGNORECASE,
    )

    # Narrative heading: "Title text – time period: body text" or "Title text: body text"
    # E.g. "The Creation of Earth – Around 4.5 Billion Years Ago: Earth was born..."
    # The heading part must be ≤ 100 chars before the colon and start with a capital.
    _NARRATIVE_HEADING_RE = re.compile(
        r"^([A-Z][^\n]{5,100}?)\s*:\s+([A-Z].{10,})$"
    )

    lines = text.strip().splitlines()
    title = "Document"
    sections: list[dict] = []
    current_heading  = ""
    current_paras:   list[str] = []
    current_img_desc = ""
    para_buf:        list[str] = []

    def flush_para():
        if para_buf:
            para_text = " ".join(para_buf).strip()
            if para_text:
                current_paras.append(para_text)
            para_buf.clear()

    def flush_section(force: bool = False):
        nonlocal current_img_desc
        flush_para()
        if current_heading or current_paras or (force and current_img_desc):
            sec: dict = {"heading": current_heading, "paragraphs": list(current_paras)}
            if current_img_desc:
                sec["image_prompt"] = current_img_desc
            sections.append(sec)
        current_paras.clear()
        current_img_desc = ""

    def extract_inline_images(s: str) -> tuple[str, str]:
        """
        Remove all [Image: ...] bracket markers from *s* and return
        (cleaned_text, first_image_desc_found_or_empty).
        """
        found = ""
        def _replace(m: re.Match) -> str:
            nonlocal found
            if not found:
                found = m.group(1).strip().rstrip(".,;")
            return ""
        cleaned = _INLINE_BRACKET_RE.sub(_replace, s).strip()
        # Clean up leftover double-spaces
        cleaned = re.sub(r"  +", " ", cleaned).strip()
        return cleaned, found

    for raw_line in lines:
        stripped = raw_line.strip()

        # ── Step 0: Extract INLINE bracket image markers from ANY line ─────────
        # Important: we delay assigning inline_img_desc to current_img_desc until
        # AFTER any heading flush, so the image goes to the correct section.
        stripped, inline_img_desc = extract_inline_images(stripped)

        # Skip now-empty lines
        if not stripped:
            if inline_img_desc:
                # This line was ONLY an image marker (e.g. "[Image 3: ...]").
                # The text accumulated so far belongs to a section that ends here.
                # Flush it WITH this image, then start a fresh section.
                current_img_desc = current_img_desc or inline_img_desc
                flush_section(force=True)
                # After flush, current_img_desc is cleared — next text belongs to next section.
            else:
                flush_para()
            continue

        # ── Standard markdown headings  (#, ##, ###) ──────────────────────────
        h_match = re.match(r'^#{1,6}\s+(.+)$', stripped)
        if h_match:
            flush_section()
            heading_text = h_match.group(1).strip()
            if re.match(r'^#\s', raw_line.strip()) and title == "Document":
                title = heading_text
            current_heading = heading_text
            # Image on same line as heading → belongs to this new section
            if inline_img_desc:
                current_img_desc = inline_img_desc
            continue

        # ── "Slide N: Title" and similar labels ───────────────────────────────
        sl_match = _SLIDE_RE.match(stripped)
        if sl_match:
            flush_section()
            current_heading = sl_match.group(1).strip().strip('"\'')
            if title == "Document":
                title = current_heading
            if inline_img_desc:
                current_img_desc = inline_img_desc
            continue

        # ── Explicit "Title:" line ────────────────────────────────────────────
        t_match = re.match(r'^[Tt]itle:\s*(.+)$', stripped)
        if t_match:
            title = t_match.group(1).strip()
            if inline_img_desc and not current_img_desc:
                current_img_desc = inline_img_desc
            continue

        # ── Horizontal rules ─────────────────────────────────────────────────
        if re.match(r'^[-=*]{3,}$', stripped):
            flush_section()
            current_heading = ""
            continue

        # ── Image description bullet  (• Image: ...) ─────────────────────────
        img_m = _IMAGE_BULLET_RE.match(stripped)
        if img_m:
            if not current_img_desc:
                current_img_desc = img_m.group(1).strip().rstrip(".,;")
            continue

        # ── Inline bold image label  (**Image:** ...) ─────────────────────────
        img_inline = _IMAGE_INLINE_RE.search(stripped)
        if img_inline and not current_img_desc:
            current_img_desc = img_inline.group(1).strip().rstrip(".,;")
            if inline_img_desc and not current_img_desc:
                current_img_desc = inline_img_desc
            continue

        # ── "Text: ..." content bullet — strip label, keep content ───────────
        txt_m = _TEXT_BULLET_RE.match(stripped)
        if txt_m:
            flush_para()
            current_paras.append(txt_m.group(1).strip())
            if inline_img_desc and not current_img_desc:
                current_img_desc = inline_img_desc
            continue

        # ── Bold stand-alone heading  (**Title**) ─────────────────────────────
        bold_m = _BOLD_HEADING_RE.match(stripped)
        if bold_m:
            candidate = (bold_m.group(1) or bold_m.group(2) or "").strip()
            if candidate and len(candidate) <= 100 and not re.search(r"[.!?]$", candidate):
                flush_section()
                current_heading = candidate
                if inline_img_desc:
                    current_img_desc = inline_img_desc
                continue

        # ── Regular bullet / numbered list items ─────────────────────────────
        bullet_match = (
            re.match(r'^[-*+•]\s+(.+)$', stripped) or
            re.match(r'^\d+\.\s+(.+)$', stripped)
        )
        if bullet_match:
            flush_para()
            current_paras.append(bullet_match.group(1).strip())
            if inline_img_desc and not current_img_desc:
                current_img_desc = inline_img_desc
            continue

        # ── Numbered heading at line start (short lines only) ────────────────
        num_m = _NUM_HEADING_RE.match(stripped)
        if num_m and not para_buf:
            candidate = num_m.group(1).strip()
            if not re.search(r"[.!?]$", candidate):
                flush_section()
                current_heading = candidate
                if inline_img_desc:
                    current_img_desc = inline_img_desc
                continue

        # ── Narrative heading: "Title: body text" (story / timeline format) ──
        # Catches: "The Creation of Earth – 4.5 BYA: Earth was born in a swirling..."
        # Only match at the start of a new block (para_buf empty).
        if not para_buf:
            narr_m = _NARRATIVE_HEADING_RE.match(stripped)
            if narr_m:
                heading_candidate = narr_m.group(1).strip()
                body_text = narr_m.group(2).strip()
                if len(heading_candidate) <= 120 and not re.search(r"[.!?]$", heading_candidate):
                    flush_section()
                    current_heading = heading_candidate
                    # Image on this heading line → belongs to the NEW section
                    if inline_img_desc:
                        current_img_desc = inline_img_desc
                    if body_text:
                        para_buf.append(body_text)
                    continue

        # ── Regular text ─────────────────────────────────────────────────────
        # For regular text lines, the inline image (if any) belongs to current section
        if inline_img_desc and not current_img_desc:
            current_img_desc = inline_img_desc
        para_buf.append(stripped)

    flush_section()

    if not sections:
        sections = [{"heading": "", "paragraphs": [text.strip()]}]

    # ── Enhance / auto-generate image prompts when images are requested ───────
    if with_image_prompts:
        for idx, sec in enumerate(sections):
            if sec.get("image_prompt"):
                # Already set — enhance with style-aware quality tags
                p = sec["image_prompt"]
                # Don't override prompts that already have style/quality tags
                _HAS_STYLE = (
                    "8k", "detailed", "cinematic", "linework", "watercolor",
                    "pencil", "sketch", "charcoal", "oil paint", "concept art",
                    "photorealistic", "hyperrealistic", "artstation",
                )
                if any(k in p.lower() for k in _HAS_STYLE):
                    sec["image_prompt"] = p  # already fully described — leave as-is
                elif vary_art_styles:
                    style = _DOC_ART_STYLES[idx % len(_DOC_ART_STYLES)]
                    sec["image_prompt"] = p + style
                else:
                    sec["image_prompt"] = p + ", cinematic lighting, highly detailed, vibrant colors, 8k"
                continue
            # Auto-fill from heading or first paragraph words
            heading = sec.get("heading", "").strip()
            if vary_art_styles:
                style = _DOC_ART_STYLES[idx % len(_DOC_ART_STYLES)]
            else:
                style = ", cinematic lighting, highly detailed, vibrant colors, 8k"
            if heading:
                sec["image_prompt"] = heading + style
            elif sec.get("paragraphs"):
                words = sec["paragraphs"][0].split()[:8]
                sec["image_prompt"] = " ".join(words) + style

    return {"title": title, "sections": sections}


@router.post("/generate")
async def generate_document_endpoint(
    body: DocumentRequest,
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> Response:
    """
    Generate a document:
      1a. If the assistant's response text is provided, parse it directly.
      1b. Otherwise call GAIA Core to produce structured JSON content.
      2. If images are requested and the format supports them, generate images in parallel.
      3. Format JSON (+images) into the requested file type.
      4. Return file bytes.
    """
    from gaaia.services.document_generator import generate_document

    fmt = body.format.lower().lstrip(".")
    if fmt not in _SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{fmt}'. Supported: {', '.join(sorted(_SUPPORTED_FORMATS))}",
        )

    host       = orchestrator._host        # noqa: SLF001
    core_model = orchestrator._core_model  # noqa: SLF001

    wants_imgs = _wants_images(body.prompt)
    vary_styles = wants_imgs and _wants_drawings(body.prompt)

    # Step 1 — structure the content
    # Always clean the response text before any parsing — strips closing markers,
    # echoed instructions, and other LLM-appended junk.
    clean_response = _clean_response_text(body.response) if body.response else body.response

    if clean_response and fmt == "txt":
        # Plain text: strip markdown syntax, preserve text and line breaks exactly
        print(f"[DocRouter] TXT — using assistant response directly ({len(clean_response)} chars)", flush=True)
        content = {"title": "", "body": _strip_markdown(clean_response)}
    elif clean_response and fmt == "xlsx":
        # Excel: try to pull markdown tables from the response first
        parsed = _parse_markdown_tables(clean_response)
        if parsed:
            print(f"[DocRouter] XLSX — extracted {len(parsed['sheets'])} table(s) from response", flush=True)
            content = parsed
        else:
            # No tables found — fall back to LLM structuring
            print("[DocRouter] XLSX — no markdown tables found, calling LLM…", flush=True)
            content = await _llm_structure(host, core_model, fmt, body.prompt.strip())
    elif clean_response and fmt not in ("csv",):
        print(f"[DocRouter] Using assistant response directly ({len(clean_response)} chars)", flush=True)
        content = _parse_markdown_to_structure(
            clean_response, fmt,
            with_image_prompts=wants_imgs,
            vary_art_styles=vary_styles,
        )
        # If parser defaulted to generic "Document" title, derive a better one from the prompt
        if content.get("title", "Document") == "Document" and body.prompt.strip():
            content["title"] = _derive_title_from_prompt(body.prompt.strip())
    else:
        content = await _llm_structure(host, core_model, fmt, body.prompt.strip())

    # Step 2 — generate images (if requested and format supports them)
    if wants_imgs and _MAX_IMAGES.get(fmt, 0) > 0:
        if body.web_image_urls:
            # Web images provided — download and embed instead of running Stable Diffusion.
            # This ensures the document has the same images that appear in the chat view.
            print(
                f"[DocRouter] Applying {len(body.web_image_urls)} web image(s) to {fmt.upper()}…",
                flush=True,
            )
            await _apply_web_images_to_content(content, body.web_image_urls)
        else:
            # Fallback: Stable Diffusion image generation.
            sections = content.get("sections") or content.get("sheets") or []
            sections_with_prompts = [s for s in sections if s.get("image_prompt")]

            if not sections_with_prompts and body.response and fmt not in ("xlsx", "csv"):
                # No markers found in the parsed content — ask GAIA Core to analyze
                # the story and identify the best positions for images (multi-model pipeline).
                max_imgs = _MAX_IMAGES.get(fmt, 4)
                print(
                    f"[DocRouter] No image markers found — asking GAIA Core to place {max_imgs} images…",
                    flush=True,
                )
                placements = await _llm_image_placement_analysis(
                    body.response, host, core_model, max_imgs
                )
                if placements:
                    _apply_llm_image_prompts(sections, placements)
                    print(
                        f"[DocRouter] GAIA Core placed {len(placements)} image(s) via LLM analysis",
                        flush=True,
                    )

            await _generate_images_for_content(content, fmt)

    # Step 3 — format into file (run in thread pool to avoid blocking event loop)
    try:
        file_bytes, filename, mime = await asyncio.to_thread(
            generate_document, content, fmt
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Document formatting failed: {exc}"
        ) from exc

    return Response(
        content=file_bytes,
        media_type=mime,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-GAAIA-Filename": filename,
        },
    )
