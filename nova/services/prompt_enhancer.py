"""
Nova Prompt Enhancer — uses a fast local LLM to turn a raw user image/sketch/drawing
request into a rich, accurate Stable Diffusion prompt.

Pipeline:
  user request  →  PromptEnhancer (fast LLM)  →  detailed SD prompt  →  ImageGenService

The enhancer understands:
  • Anime / manga characters (Nami, Luffy, Naruto…)
  • Real-world subjects (portraits, landscapes, animals…)
  • Art styles (pencil sketch, watercolor, oil painting, pixel art…)
  • Scene composition requests ("sitting by a window", "in a sunset")
  • Negative directives ("make her fierce", "realistic", "detailed")
"""
from __future__ import annotations

import asyncio
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

# ── System prompt for the enhancer model ─────────────────────────────────────

_ENHANCER_SYSTEM = """\
You are an expert Stable Diffusion prompt engineer. Your ONLY job is to convert a \
user's image request into a single, highly detailed Stable Diffusion prompt that will \
produce an accurate, beautiful result.

Rules:
1. Output ONLY the prompt — no explanation, no code, no extra text, no markdown, \
   no "Here is the prompt:", no thinking tags, no quotes around the prompt.
1b. If the request includes a "User's latest message" / "Extracted subject" / "Recent thread" / \
   "Web image search" block, those define subject and follow-ups (e.g. which character, what "her" means). \
   Do NOT replace them with a random unrelated name (e.g. a generic Western name) when the user named \
   a character, scene, or prior topic. **Preserve the exact subject** given in those blocks.
2. CRITICAL — CHARACTER IDENTITY: The subject's FULL NAME and source/series MUST be \
   the very first tokens in the prompt. Examples:
   • "Nami, One Piece anime character, …"
   • "Thomas Shelby, Cillian Murphy, Peaky Blinders, …"
   • "Naruto Uzumaki, Naruto Shippuden anime, …"
   Never bury the name inside the prompt — it must come FIRST so the model can \
   identify who to draw accurately.
3. For live-action TV/film characters: ALWAYS include the actor's real name right \
   after the character name (e.g. "Thomas Shelby, Cillian Murphy"). \
   This is essential for accurate face generation.
4. Include all of: physical appearance (hair color/style, eye color, skin tone, \
   face shape), clothing/accessories, pose/expression, setting/background, \
   lighting, art style, quality tags.
5. For anime/manga characters: include canonical look with exact hair colour, \
   eye colour, outfit details, accessories, and signature items. \
   End with "official [series] anime art style, highly detailed, vibrant colors, 8k".
6. For photorealistic/portrait requests: add "photorealistic, DSLR photo, \
   sharp focus, cinematic lighting, 8k ultra HD".
7. For sketches/drawings: add "detailed pencil sketch, fine linework, \
   graphite on white paper, masterpiece".
8. For watercolor/oil painting: add matching painterly descriptors.
9. NEVER include "text", "watermark", "signature", or "low quality".
10. Keep the prompt under 180 words.
11. Respond with the prompt **on a single line**, comma-separated tokens. No line breaks \
    inside the prompt itself.
"""

_ENHANCER_USER_TEMPLATE = "User request: {request}\n\nWrite the Stable Diffusion prompt:"


# ── Async enhancer function ───────────────────────────────────────────────────

async def enhance_image_prompt(
    raw_request: str,
    ollama_host: str = "http://localhost:11434",
    fast_model: str  = "llama3.2:3b",
    mini_model: str  = "phi:2.7b",
    timeout: float   = 12.0,
) -> str:
    """
    Call the fast LLM to generate a detailed SD prompt from *raw_request*.

    Falls back to the mini model if the fast model times out, and ultimately
    returns the raw request unchanged if both calls fail.
    """
    import httpx

    models_to_try = [fast_model, mini_model]
    payload_base = {
        "stream": False,
        "options": {
            "temperature": 0.4,
            "top_p": 0.9,
            "num_predict": 200,
        },
    }

    for model in models_to_try:
        payload = {
            **payload_base,
            "model": model,
            "system": _ENHANCER_SYSTEM,
            "prompt": _ENHANCER_USER_TEMPLATE.format(request=raw_request),
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{ollama_host}/api/generate",
                    json=payload,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    enhanced = (data.get("response") or "").strip()
                    if enhanced and len(enhanced) > 20:
                        logger.info(
                            "[PromptEnhancer] %s → '%s...'",
                            model,
                            enhanced[:60],
                        )
                        return _clean_enhanced_prompt(enhanced)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[PromptEnhancer] %s failed: %s", model, exc)

    # Both models failed — return original request
    logger.warning("[PromptEnhancer] both models failed, using raw request")
    return raw_request


def _clean_enhanced_prompt(text: str) -> str:
    """Strip any accidental markdown, quotes, prefix explanations, or <think> blocks."""
    import re

    # Strip <think>…</think> blocks that reasoning models sometimes include
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Remove any leftover opening/closing think tags
    text = re.sub(r"</?think>", "", text, flags=re.IGNORECASE)

    # Remove fenced code blocks (keep the inner content)
    code_fence = re.search(r"```[a-zA-Z]*\n?(.*?)```", text, flags=re.DOTALL)
    if code_fence:
        text = code_fence.group(1)

    # Drop common LLM lead-in phrases (whole-line variants)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    cleaned: list[str] = []
    lead_ins = (
        "here is the prompt", "here's the prompt", "prompt:", "sd prompt:",
        "stable diffusion prompt:", "here's a prompt", "here is a prompt",
        "sure,", "of course,", "okay,", "alright,", "certainly,",
    )
    for ln in lines:
        low = ln.lower()
        if any(low.startswith(li) for li in lead_ins):
            # Keep anything after a colon on the same line
            if ":" in ln:
                after = ln.split(":", 1)[1].strip()
                if after:
                    cleaned.append(after)
            continue
        cleaned.append(ln)
    text = " ".join(cleaned).strip()

    # Strip stray backticks
    text = text.strip("`").strip()

    # Strip surrounding quotes
    while text and text[0] in "\"'“”‘’" and text[-1] in "\"'“”‘’":
        text = text[1:-1].strip()

    # Collapse whitespace
    text = " ".join(text.split())

    return text
