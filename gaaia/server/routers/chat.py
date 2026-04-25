from __future__ import annotations

import asyncio
import json
import re
import threading
from typing import Sequence

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from gaaia.agent.orchestrator import Orchestrator
from gaaia.attachments import build_attachment_context
from gaaia.engines.research import fetch_web_images, fetch_article_snippets, fetch_weather_data
from gaaia.memory.store import MemoryStore
from gaaia.services.location import is_vague_weather_location_phrase, resolve_weather_location
from gaaia.services.camera_buffer import get_live_prefix_for_prompt
from gaaia.services import stats_tracker
from gaaia.services.prompt_enhancer import enhance_image_prompt
from gaaia.server.dependencies import get_current_user, get_memory, get_orchestrator
from gaaia.memory.models import User
from gaaia.server.schemas import ChatRequest

router = APIRouter()

# ── Response-quality helpers ──────────────────────────────────────────────────

# Patterns that mean the LLM is echoing its system prompt instead of replying.
# Checked in real-time during streaming; the stream is suppressed and a safe
# fallback is emitted when any of these appear in the first ~300 chars.
_ECHO_ABORT_PATTERNS: list[re.Pattern] = [
    re.compile(r"Here'?s? a detailed breakdown of the instruction", re.IGNORECASE),
    re.compile(r"GAAIA is presented as Isabella", re.IGNORECASE),
    re.compile(r"1\.\s+GAAIA Identity:", re.IGNORECASE),
    re.compile(r"# GAIA\s*[-—]\s*AI Chief of Staff", re.IGNORECASE),
    re.compile(r"# Generation Capabilities\s*[-—]", re.IGNORECASE),
    re.compile(r"CRITICAL:.*LIVE generation pipelines", re.IGNORECASE | re.DOTALL),
    re.compile(r"You are GAIA.*You are not a chatbot", re.IGNORECASE | re.DOTALL),
    re.compile(r"# Identity\s*\nYou are GAIA", re.IGNORECASE),
    re.compile(r"When it comes to generating responses", re.IGNORECASE),
    re.compile(r"here are a few guidelines (?:that )?might help", re.IGNORECASE),
    re.compile(r"You are GAIA — a real person named Isabella", re.IGNORECASE),
    re.compile(r"Not an AI assistant\. Not a chatbot", re.IGNORECASE),
    re.compile(r"1\.\s*Be conversational:?", re.IGNORECASE),
    re.compile(r"2\.\s*Keep it concise:?", re.IGNORECASE),
    re.compile(r"6\.\s*Use the user'?s? location:?", re.IGNORECASE),
    re.compile(r"7\.\s*Stay updated:?", re.IGNORECASE),
    re.compile(r"ideally under \d+\s+words each", re.IGNORECASE),
    # LLM role-playing the user ("You: Hey there! …" at response start)
    re.compile(r"^You:\s+\w", re.IGNORECASE),
    # LLM regurgitating a web-search result or unrelated article as the opening
    re.compile(r"^(You|User):\s+Hey\s+there", re.IGNORECASE),
    # Model "summarises" the system prompt as if the user had pasted it
    re.compile(
        r"It looks like you'?(?:ve| have) shared.+(?:guidelines|set of (?:the )?rules|instructions for)",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(r"conversational AI named GAAIA.+(?:guidelines|These guidelines|various aspects)", re.IGNORECASE | re.DOTALL),
    re.compile(r"By following these rules, GAAIA aims to provide", re.IGNORECASE),
]

# SD quality tags — used to detect when the LLM leaks an image prompt into its text.
_SD_TAG_RE = re.compile(
    r"\b("
    r"photorealistic|8k\s+ultra\s+hd|sharp\s+focus|cinematic\s+lighting|"
    r"highly\s+detailed|official\s+\w[\w\s]*art\s+style|masterpiece|best\s+quality|"
    r"vibrant\s+colou?rs?|ultra\s+hd|dslr\s+photo|4k|8k|hdr|"
    r"line\s+art|anime\s+art\s+style|official\s+.*anime|"
    r"detailed\s+pencil|pencil\s+sketch|fine\s+linework|graphite|"
    r"oil\s+painting|watercolou?r|concept\s+art|digital\s+painting"
    r")\b",
    re.IGNORECASE,
)

# Inline [Image: …] / [Image N: …] / [Image Generated] / [Generated Image] markers
# the LLM puts in image responses — must be stripped from visible chat text.
_INLINE_IMG_MARKER_RE = re.compile(
    r"\[(?:"
    r"Image\s*\d*\s*:"          # [Image: ...] / [Image 1: ...]
    r"|Image\s+Generated"       # [Image Generated]
    r"|Generated\s+Image"       # [Generated Image]
    r"|AI[- ]?Generated\s+Image"# [AI-Generated Image]
    r"|Image\s+Ready"           # [Image Ready]
    r"|Image\s+Complete"        # [Image Complete]
    r"|Image\s+Created"         # [Image Created]
    r"|Image\s*\d*"             # [Image] / [Image 1]
    r")[^\]]*\]",
    re.IGNORECASE,
)

# Terse/generic one-word confirmations the model sometimes produces for image/doc gen.
_TERSE_CONFIRM_RE = re.compile(
    r"^(?:confirmed\.?|sure\.?|got\s*it\.?|done\.?|ok(?:ay)?\.?|understood\.?|"
    r"acknowledged\.?|noted\.?|absolutely\.?|certainly\.?|of\s*course\.?|"
    r"will\s*do\.?|on\s*it\.?)$",
    re.IGNORECASE,
)

# Trailing manual-document-creation instruction paragraphs that the LLM appends even
# though the app generates the file automatically.  Everything from the match onwards
# is stripped from the response text (and therefore from the document content).
_DOC_INSTRUCTIONS_TAIL_RE = re.compile(
    r"\n*(?:"
    r"(?:---+\s*)?"                        # optional horizontal rule before the section
    r"(?:\*{1,2})?Document\s+Generation(?:\*{1,2})?\b|"  # "Document Generation" heading
    r"(?:\*{1,2})?How\s+to\s+(?:Generate|Create|Save|Export|Download)\b[^\n]*(?:PDF|Word|document|docx|file)[^\n]*(?:\*{1,2})?|"
    r"To (?:generate|create|export|convert|save|download|produce|make)\b[^\n]*"
    r"(?:PDF|Word|document|docx|file|format|Word document|Google Doc)[^\n]*|"
    r"Here(?:'?s| are)(?: the| some)? (?:steps?|instructions?|guide|ways?)\b|"
    r"You can (?:follow|use these|save|export|convert|copy)\b|"
    r"Simply (?:copy|paste|open|save|select)\b|"
    r"Alternatively,? you can\b|"
    r"(?:To )?(?:download|save|export|share) (?:this|the) (?:document|essay|file|text)\b|"
    r"(?:Using|With)\s+(?:Microsoft\s+)?(?:Word|Google\s+Docs|LibreOffice)\b|"
    # LLM closing markers — must NEVER appear in user-visible content or documents
    r"\[End\s+of\s+(?:Essay|Document|Story|Report|Article|Section|Text|Response|Draft|Content)\]|"
    r"\[Internal\s*[-—]|"                  # echoed internal instruction block
    r"Save\s+the\s+current\s+(?:essay|document|draft|text)\b|"
    r"Create\s+a\s+(?:Word|Google\s+Docs?|PDF)\s+(?:document|outline)\b"
    r")[\s\S]*$",
    re.IGNORECASE,
)

# LLM image-refusal patterns — fired even though the generation pipeline is live.
# Detected post-stream so the full refusal text can be swapped for a clean reply.
_IMAGE_REFUSAL_RE = re.compile(
    r"("
    r"not able to generate visual content|"
    r"cannot create.*images?|"
    r"don'?t have the ability to.*generate|"
    r"I can'?t.*generate.*images?|"
    r"here'?s a link to a fan art|"
    r"I'?m unable to.*generate|"
    r"as an? (text-based )?AI.*I.*cannot.*visual|"
    r"unable to.*create.*images?|"
    r"I'?m not able to create|"
    r"providing a description instead|"
    r"suggest.*using.*tool|"
    r"recommend.*external.*software"
    r")",
    re.IGNORECASE | re.DOTALL,
)

# Colour / colorize follow-up patterns
# e.g. "give her colour", "add color", "colorize it", "make it colorful"
_IMAGE_COLOUR_FOLLOWUP_RE = re.compile(
    r"\b("
    r"give\s+(it|her|him|them)\s+colou?r|"
    r"add\s+colou?rs?|"
    r"colou?rize|"
    r"make\s+it\s+colou?rful|"
    r"in\s+colou?r|"
    r"with\s+colou?r|"
    r"colou?red\s+version|"
    r"add\s+some\s+colou?r|"
    r"make\s+(her|him|it|them)\s+colou?rful"
    r")\b",
    re.IGNORECASE,
)

# Image variation / edit follow-up patterns
# e.g. "make the background blue", "now make her smile", "same image but at night"
_IMAGE_VARIATION_RE = re.compile(
    r"\b("
    r"same\s+(image|picture|photo|style)\s+but\b|"
    r"(change|make)\s+(it|the|her|him|them)\b|"
    r"now\s+(make|change|add|remove|turn)\b|"
    r"but\s+(now|this\s+time|instead|with)\b|"
    r"keep\s+the\s+same\b|"
    r"keep\s+it\s+the\s+same\b|"
    r"edit\s+(it|the\s+image)\b|"
    r"modify\s+(it|the\s+image)\b|"
    r"update\s+the\s+image\b|"
    r"redo\s+it\b|"
    r"regenerate\s+it\b|"
    r"this\s+time\s+(make|add|remove|with|in)\b"
    r")\b",
    re.IGNORECASE,
)


def _is_image_variation_request(message: str, has_prior_image: bool) -> bool:
    """Return True if *message* is a follow-up edit to a previously generated image."""
    if not has_prior_image:
        return False
    return bool(_IMAGE_VARIATION_RE.search(message or ""))


# ── Visual / web-results request detection ───────────────────────────────────
_VISUAL_SHOW_RE = re.compile(
    r"\b("
    # ── Explicit visual requests ────────────────────────────────────────────
    r"show\s+(me|us)\b|"
    r"how\s+does\s+(he|she|it|they|this|that)\s+look|"
    r"what\s+does\s+(he|she|it|they|.{2,30}?)\s+look\s+like|"
    r"can\s+you\s+show(\s+me)?|"
    r"let\s+me\s+see|"
    r"show\s+(some\s+)?images?\b|"
    r"show\s+(some\s+)?photos?\b|"
    r"show\s+(some\s+)?pictures?\b|"
    r"images?\s+of\b|"
    r"images?\s+from\b|"
    r"photos?\s+of\b|"
    r"photos?\s+from\b|"
    r"pictures?\s+of\b|"
    r"pictures?\s+from\b|"
    r"find\s+(me\s+)?(images?|photos?|pictures?)\b|"
    r"search\s+(for\s+)?(images?|photos?|pictures?)\b|"
    r"articles?\s+(about|on)\b|"
    r"find\s+(me\s+)?articles?\b|"
    r"show\s+(me\s+)?(news|articles?)\b|"
    r"pull\s+(up\s+)?(images?|articles?|results?)\b|"
    # ── "I want to see / can I see / let me see" ────────────────────────────
    r"(?:can\s+i|i\s+(?:want|wanna|would\s+like)\s+to)\s+see\b|"
    r"show\s+(?:me\s+)?(?:a\s+)?(?:photo|picture|pic|image)s?\s+(?:of|for)\b|"
    r"what\s+(?:do|does)\s+(?:he|she|they|.{2,40}?)\s+(?:look\s+like|resemble)\b|"
    # ── Research / person queries — always benefit from web images + articles ─
    r"who\s+is\b|"
    r"who\s+was\b|"
    r"who\s+are\b|"
    r"tell\s+me\s+about\b|"
    r"expand\s+on\b|"
    r"more\s+about\b|"
    r"research\s+(?:on\s+)?\b|"
    r"(?:give\s+me\s+)?(?:some\s+)?(?:more\s+)?(?:info(?:rmation)?|details?)\s+(?:on|about)\b|"
    r"what\s+(?:do\s+you\s+know|can\s+you\s+tell\s+me)\s+about\b|"
    r"(?:can\s+you\s+)?(?:look\s+up|search\s+(?:up|for))\b|"
    r"who\s+(?:exactly\s+)?is\s+(?:he|she|they|this|that)\b"
    r")\b",
    re.IGNORECASE,
)

# Proper noun extractor — find first multi-word title-case phrase in a string.
_PROPER_NOUN_RE = re.compile(
    r"(?:^|[.!?\n]\s*)"          # start or after sentence boundary
    r"(?:On\s+\w+\s+\d+,?\s+\d{4},?\s+)?"   # optional date prefix
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4})"  # 2–5 title-case words
    r"\s+(?:is\b|serves?\b|was\b|has\b|are\b|were\b|currently\b)"
)


def _is_visual_show_request(text: str) -> bool:
    return bool(_VISUAL_SHOW_RE.search(text or ""))


# Follow-up clicks send: Regarding your previous response:\n"…"\n\n<actual question>
_CONTEXTUAL_REPLY_PREFIX_RE = re.compile(
    r"(?is)^Regarding\s+your\s+previous\s+response:\s*\"[^\"]*\"\s*\n\s*\n",
)


def _user_message_for_web_results(raw: str) -> str:
    """Strip suggestion wrapper so visual / research intent matches the real question."""
    s = (raw or "").strip()
    s = _CONTEXTUAL_REPLY_PREFIX_RE.sub("", s, count=1).strip()
    return s


def _normalize_web_image_query(q: str) -> str:
    """
    Tighten conversational fragments into image-search-friendly queries.
    E.g. 'who Tony Stark is' → 'Tony Stark', 'who is Tony Stark' → 'Tony Stark'.
    """
    q = (q or "").strip().strip("?!.").strip()
    if not q:
        return q
    m = re.match(r"(?i)^who\s+(?:is|was|are)\s+(.{2,100})$", q)
    if m:
        inner = m.group(1).strip().rstrip("?.!")
        if inner and not re.match(r"^(he|she|they|this|that)$", inner, re.I):
            return inner[:100]
    m = re.match(r"(?i)^who\s+(.+?)\s+is$", q)
    if m:
        return m.group(1).strip()[:100]
    m = re.match(r"(?i)^who\s+(.+?)\s+(was|are)$", q)
    if m:
        return m.group(1).strip()[:100]
    return q[:120]


def _build_visual_query(user_message: str, ai_response: str) -> str:
    """
    Derive a web-search query (images + articles) from *user_message* and the
    most recent *ai_response*.  Handles explicit visual requests AND research /
    person queries.  No LLM required — pure regex heuristics.
    """
    msg = (user_message or "").strip()

    # ── 1. Strip the "[LIVE WEATHER DATA …]" injection so it doesn't pollute ──
    msg_clean = re.sub(r"\[LIVE WEATHER DATA[^\]]*\]", "", msg).strip()

    # ── 2c. "can you show me who Tony Stark is?" → entity name ────────────────
    m = re.search(
        r"(?i)\b(?:can\s+you\s+)?show\s+me\s+who\s+(.+?)\s+is\b",
        msg_clean,
    )
    if m:
        subj = m.group(1).strip(" .?!")
        if len(subj) >= 2:
            return subj

    # ── 2a. "show/find me images/photos/pictures of X" ───────────────────────
    m = re.search(
        r"\b(?:show|find|get|search|display|pull)\s+(?:me\s+|us\s+)?"
        r"(?:some\s+)?(?:images?|photos?|pictures?|videos?|clips?|articles?)\s+"
        r"(?:of|about|on|for)\s+(.{4,80}?)(?:\s*[.?!,]?\s*$)",
        msg_clean, re.IGNORECASE,
    )
    if m:
        subject = m.group(1).strip(" .?!")
        if not re.match(r"^(him|her|it|them|the|a|an|this|that|me)$", subject, re.IGNORECASE):
            return subject

    # ── 2b. "show me X" / "show me the prime minister" (bare show, no media noun) ──
    m = re.search(
        r"\b(?:show\s+(?:me|us)|can\s+i\s+see|(?:i\s+(?:want|wanna|would\s+like)\s+to)\s+see)\s+"
        r"(?:a\s+|the\s+)?(?:photo\s+of\s+|picture\s+of\s+|image\s+of\s+)?(.{3,80}?)(?:\s*[?!.,]?\s*$)",
        msg_clean, re.IGNORECASE,
    )
    if m:
        subject = m.group(1).strip(" .?!")
        # Skip if it's an explicit AI-generation request (has art/generation words)
        _gen_words = re.compile(
            r"\b(draw(?:ing)?|paint(?:ing)?|art(?:work)?|illustration|sketch|render|generat|creat)\b",
            re.IGNORECASE,
        )
        if not _gen_words.search(subject) and not re.match(
            r"^(him|her|it|them|the|a|an|this|that|me|nothing)$", subject, re.IGNORECASE
        ):
            return subject

    # ── 3. "who is / who was / who are X" ────────────────────────────────────
    m = re.search(
        r"\bwho\s+(?:is|was|are)\s+(?:the\s+)?(.{3,80}?)(?:\s*[?!.,]?\s*$)",
        msg_clean, re.IGNORECASE,
    )
    if m:
        subject = m.group(1).strip(" .?!")
        if not re.match(
            r"^(he|she|it|they|him|her|them|this|that|a|an|the)$",
            subject, re.IGNORECASE,
        ):
            return subject

    # ── 4. "tell me about X" / "more about X" / "expand on X" ───────────────
    m = re.search(
        r"\b(?:tell\s+me\s+about|more\s+about|expand\s+on|"
        r"research\s+(?:on\s+)?|"
        r"give\s+me\s+(?:(?:some|more)\s+)?(?:info(?:rmation)?|details?)\s+(?:on|about)|"
        r"what\s+(?:do\s+you\s+know|can\s+you\s+tell\s+me)\s+about|"
        r"(?:look\s+up|search\s+(?:up\s+)?for))\s+(.{3,80}?)(?:\s*[?!.,]?\s*$)",
        msg_clean, re.IGNORECASE,
    )
    if m:
        subject = m.group(m.lastindex).strip(" .?!")
        if not re.match(r"^(him|her|it|them|the|a|an|this|that)$", subject, re.IGNORECASE):
            return subject

    # ── 5. "what does X look like" / "how does X look" ───────────────────────
    for pat in (
        r"\bwhat\s+does\s+(.{3,50}?)\s+look\s+like",
        r"\bhow\s+does\s+(.{3,50}?)\s+look",
    ):
        m = re.search(pat, msg_clean, re.IGNORECASE)
        if m:
            subject = m.group(1).strip()
            if not re.match(r"^(he|she|it|they|this|that)$", subject, re.IGNORECASE):
                return subject
            break  # pronoun — fall through to context extraction

    # ── 6. Pronoun / vague reference → resolve from the AI response ──────────
    has_pronoun = bool(re.search(r"\b(he|she|it|they|him|her|them|this person)\b", msg_clean, re.IGNORECASE))
    has_vague   = bool(re.search(r"\b(who|they)\b", msg_clean, re.IGNORECASE))
    if (has_pronoun or has_vague) and ai_response:
        m = _PROPER_NOUN_RE.search(ai_response)
        if m:
            return m.group(1).strip()
        # Fallback: first cluster of capitalised words in the opening line
        first_line = ai_response.split("\n")[0][:400]
        caps = re.findall(r"\b[A-Z][a-z]{2,}\b", first_line)
        if len(caps) >= 2:
            return " ".join(caps[:3])

    # ── 7. "articles / news / information about X" ───────────────────────────
    m = re.search(
        r"\b(?:articles?|news|information)\s+(?:about|on|regarding)\s+(.{4,80}?)(?:\s*[.?!]?\s*$)",
        msg_clean, re.IGNORECASE,
    )
    if m:
        return m.group(1).strip(" .?!")

    # ── 8. Subject is already quoted / named explicitly with no pattern ───────
    #    e.g. "Imran Khan" alone, or a sentence that IS the subject
    #    Extract first title-case name phrase as a last resort.
    caps_in_msg = re.findall(r"\b[A-Z][a-z]{1,}\b", msg_clean)
    if len(caps_in_msg) >= 2:
        # Avoid returning pure noise like "GAAIA" alone
        candidate = " ".join(caps_in_msg[:3])
        noise = re.compile(
            r"^(GAAIA|Hey|Hi|Hello|Please|Can|Could|Would|Should|Tell|Show|Find|"
            r"Give|What|Who|How|When|Where|Why|Which|Is|Are|Was|Were|Do|Does|Did)\b",
            re.IGNORECASE,
        )
        if not noise.match(candidate):
            return candidate

    # ── 9. Strip common filler words and return whatever remains ──────────────
    cleaned = re.sub(
        r"\b(show\s+(me|us)|can\s+you\s+show(\s+me)?|let\s+me\s+see"
        r"|how\s+does\s+(he|she|it|they|this|that)\s+look"
        r"|what\s+does\s+\S+\s+look\s+like"
        r"|who\s+is|who\s+was|tell\s+me\s+about|more\s+about|expand\s+on"
        r"|please|now|for\s+me|hey\s+nova|nova|hi\s+nova)\b",
        "", msg_clean, flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" .?!")
    return cleaned or msg_clean


# ── Weather widget detection ──────────────────────────────────────────────────
_WEATHER_WIDGET_RE = re.compile(
    r"("
    # "what's/whats/how's the weather [like] [today]"
    r"(?:what'?s?|how'?s?|whats)\s+(?:the\s+)?(?:weather|forecast|temp(?:erature)?)(?:\s+like)?|"
    # "what's the forecast for today / this week"
    r"(?:what'?s?|whats)\s+(?:the\s+)?forecast\b|"
    # "weather today / now / tonight / in …"
    r"weather\s+(?:today|now|tonight|this\s+week|tomorrow|forecast|report|in|for|like)\b|"
    # "today's weather / current weather / live weather"
    r"(?:today'?s?|tomorrow'?s?|current|live)\s+(?:weather|forecast)\b|"
    # "forecast for today / tomorrow"
    r"forecast\s+for\s+(?:today|tomorrow|this\s+week)\b|"
    r"(?:will|is)\s+it\s+(?:rain|snow|sunny|hot|cold|warm)\b|"
    r"chance\s+of\s+rain\b|"
    r"weather\s+forecast\b|"
    r"what'?s?\s+(?:the\s+)?(?:temp(?:erature)?|high|low)\s+(?:today|tomorrow|this\s+week)?"
    r")",
    re.IGNORECASE,
)

# ── Clock widget detection ────────────────────────────────────────────────────
_CLOCK_WIDGET_RE = re.compile(
    r"\b("
    r"what(?:'?s|\s+is)\s+(?:the\s+)?(?:current\s+)?time\b|"
    r"show\s+(?:me\s+)?(?:a\s+)?(?:live\s+)?clock\b|"
    r"live\s+clock\b|"
    r"what\s+time\s+is\s+it\b|"
    r"current\s+time\b|"
    r"clock\s+(?:widget|in\s+(?:the\s+)?chat)\b"
    r")\b",
    re.IGNORECASE,
)


def _is_weather_widget_request(text: str) -> bool:
    return bool(_WEATHER_WIDGET_RE.search(text or ""))


def _is_clock_widget_request(text: str) -> bool:
    return bool(_CLOCK_WIDGET_RE.search(text or ""))


def _extract_weather_location(text: str) -> str:
    """Extract an explicit location from a weather query (e.g. 'weather in London')."""
    for pat in (
        r"\b(?:weather|forecast|temperature|temp)\s+(?:in|for|at)\s+(.{2,60}?)(?:\s*[?!.,]?\s*$)",
        r"\bin\s+(.{2,60}?)\s+(?:today|tomorrow|this\s+week|forecast|weather)\b",
        r"\bhow'?s?\s+(?:the\s+)?weather\s+(?:like\s+)?in\s+(.{2,60}?)(?:\s*[?!.,]?\s*$)",
    ):
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip(" .?!")
            if re.match(
                r"^(it|there|here|today|now|like|the|outside)$",
                candidate,
                re.IGNORECASE,
            ):
                continue
            if is_vague_weather_location_phrase(candidate):
                continue
            return candidate
    return ""


def _echo_fallback_reply(user_message: str) -> str:
    """When we suppress a meta-instruction echo, use a line that fits a tiny greeting."""
    u = (user_message or "").strip()
    u = re.sub(r"\[LIVE WEATHER DATA[^\]]*\]\s*", "", u, flags=re.IGNORECASE)
    u = re.sub(r"\[Live [^\]]+\]\s*", "", u, flags=re.IGNORECASE)
    u = (u or "").split("\n\n", 1)[-1].strip()[:200]
    core = re.sub(r"[!?.,'\"]+", " ", (u or "").lower())
    core = re.sub(r"\s+", " ", core).strip()
    if re.match(
        r"^(hey\s+nova|hi\s+nova|hello\s+nova|hi(\s+there)?|hello(\s+there)?|"
        r"hey(\s+there)?|yo|sup|hiya|nova|hey)$",
        core,
    ) or re.match(
        r"^hey\s*nova$|^hi$|^hello$",
        core,
    ):
        return "Hey! Good to see you — what's on your mind today?"
    return "Sure! Let me sort that out for you."


def _is_prompt_meta_narration(text: str) -> bool:
    """
    Model pretends the user *shared* or *pasted* private instructions, then
    narrates or summarises them — e.g. 'It looks like you've shared guidelines…'.
    """
    if not (text or "").strip():
        return False
    low = text[:3500].lower()
    if "it looks like you" in low and "shared" in low and "guideline" in low:
        return True
    if "it looks like you" in low and "shared" in low and "nova" in low and (
        "voice and tone" in low or "operating mode" in low or "conversational" in low
    ):
        return True
    if "these guidelines" in low and "ensure that nova" in low:
        return True
    if "conversational ai named nova" in low and "guideline" in low and len(text) < 3000:
        return True
    if "by following these rules" in low and "nova" in low and "real person" in low:
        return True
    if "how do i implement this in my project" in low and "guideline" in low:
        return True
    return False


def _is_echo_corrupt(text: str) -> bool:
    """Return True if *text* looks like the LLM echoing its system prompt or role-playing."""
    if not (text or "").strip():
        return False
    if _is_prompt_meta_narration(text):
        return True
    probe = text[:2500]
    return any(p.search(probe) for p in _ECHO_ABORT_PATTERNS)


def _looks_like_image_tutorial(text: str) -> bool:
    """
    True when the model answered an image-generation request with a how-to / guide instead
    of a short confirmation. Used to replace with a one-liner; the real image still generates.
    """
    t = (text or "").strip()
    if not t:
        return False
    low = t.lower()
    # Fast paths — catch guides early (incl. mid-stream) with short min length
    if re.search(r"(?i)step[-\s]by[-\s]step", t) and len(t) >= 25:
        return True
    if re.search(
        r"(?i)here('?s| is)\s+(?:a |the |my )?"
        r"(?:(?:quick |simple |brief |detailed )?)(?:step[- ]by[- ]step |)"
        r"(?:guide|walkthrough|tutorial|overview|instructions?)\b",
        t,
    ) and len(t) >= 20:
        return True
    if re.search(
        r"(?i)guide\s+on\s+how\s+to\s+(?:create|make|draw|build)",
        t,
    ):
        return True
    if re.search(
        r"(?i)(?:adobe|)\s*photoshop|\bgimp\b|image editing software|"
        r"trace and recreate|reference image to trace|pre-?made templates",
        t,
    ) and re.search(
        r"(?i)(open |select |search for a high-quality|use the reference|on a new layer|brush tool)",
        t,
    ):
        return True
    if len(t) < 100:
        return False
    if re.search(r"(?i)\bstep\s*\d+[\s:.)—-]", t):
        return True
    if re.search(
        r"(?i)here('?s| is)\s+(?:a |the |my )?(?:quick |simple |brief )?"
        r"(?:(?:step[- ]by[- ]step|detailed)\s+)?(?:guide|walkthrough|tutorial|overview)\b",
        t,
    ):
        return True
    if re.search(
        r"(?i)how to\s+(?:create|make|generate|produce|get)\s+(?:an?\s+)?"
        r"(?:image|picture|photo|artwork|illustration)\b",
        t,
    ) and not re.search(r"(?i)generating (?:it|that|your) now", low):
        if any(
            s in low
            for s in (
                "midjourney",
                "dall-e",
                "dalle",
                "photoshop",
                "illustrator",
                "canva",
                "comfyui",
                "invokeai",
                "figma",
                "procreate",
            )
        ):
            return True
    if re.search(r"(?i)^#+\s*(?:how|steps?|guide|tutorial)\b", t, re.M):
        return True
    # "1." then blank line then "Open your…" (numbered list not on same line as text)
    if re.search(r"(?i)\d+\s*\.?\s*\n+\s*open your", t) or re.search(
        r"(?i)search for a high-quality reference image", t
    ):
        return True
    num_lines = len(re.findall(r"(?m)^\s*\d+[\).]\s+\S", t))
    if num_lines >= 3 and any(
        w in low
        for w in (
            " open ",
            " select ",
            " choose ",
            " click ",
            " download ",
            " install ",
            " layer ",
            " brush ",
        )
    ):
        return True
    return False


def _strip_response_artifacts(text: str) -> str:
    """
    Clean up common LLM response artifacts:
      1. Inline [Image N: …] document markers (not valid in chat)
      2. Trailing SD-prompt paragraphs leaked after a short confirmation sentence.
      3. Echoed internal system instruction blocks.
      4. Essay / document end markers the LLM appends as closers.
    """
    # Remove [Image: …] / [Image 1: …] markers
    text = _INLINE_IMG_MARKER_RE.sub("", text).strip()
    # Strip echoed [DOCUMENT FORMATTING …] instruction blocks (the new style)
    text = re.sub(r"\[DOCUMENT FORMATTING[^\]]*\][\s\S]*?(?=\n\n|\Z)", "", text, flags=re.IGNORECASE).strip()
    # Strip echoed <<SYSTEM:...>> instruction blocks (old style)
    text = re.sub(r"<<SYSTEM:[^>]*>>[\s\S]*?<<END_SYSTEM>>", "", text, flags=re.IGNORECASE).strip()
    # Strip [Internal — ...] echoes (any length, greedy to end-of-bracket or line)
    text = re.sub(r"\[Internal\s*[-—][^\]]*\]?", "", text, flags=re.IGNORECASE).strip()
    # Strip all essay / document closing markers (with or without brackets, with optional asterisks)
    text = re.sub(
        r"\*{0,2}\[?\s*(?:End\s+of\s+(?:Essay|Document|Story|Report|Article|Section|Response|Draft|Text|Content))\s*\]?\*{0,2}\.?\s*$",
        "",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    ).strip()
    # Also strip trailing bracket-only lines like "[Document]" or "[Essay]"
    text = re.sub(r"\[\s*(?:Essay|Document|Story|Report|Draft)\s*\]\s*$", "", text, flags=re.IGNORECASE | re.MULTILINE).strip()
    # Collapse any double-spaces left by removal
    text = re.sub(r"  +", " ", text)
    # Strip trailing SD-prompt paragraphs
    text = _strip_sd_leakage(text)
    return text.strip()


def _strip_sd_leakage(text: str) -> str:
    """
    Remove trailing paragraphs that are Stable Diffusion prompts leaked into
    the chat response.  A paragraph is SD leakage when it:
      • contains ≥3 SD quality tags, AND
      • has a comma-density of >20% (comma-separated descriptor lists).
    Also handles prompts joined with a single \\n rather than a blank line.
    Only trailing sections are stripped so real content is never touched.
    """
    # Split on blank lines OR a single newline immediately followed by a
    # run of comma-separated descriptor words (the SD prompt pattern).
    paragraphs = re.split(r"\n{1,2}", text.strip())
    while paragraphs:
        last = paragraphs[-1].strip()
        if not last:
            paragraphs.pop()
            continue
        tag_hits = len(_SD_TAG_RE.findall(last))
        comma_density = last.count(",") / max(len(last.split()), 1)
        last_l = last.lower()
        if tag_hits >= 3 and comma_density > 0.20:
            paragraphs.pop()
        # Single-line or paragraph-long leaked SD "prompt soup" (character + style tags, 8k, etc.)
        elif (
            len(last) > 100
            and last.count(",") >= 6
            and comma_density > 0.10
            and any(
                k in last_l
                for k in (
                    "8k",
                    "4k",
                    "anime",
                    "art style",
                    "digital painting",
                    "illustration",
                    "masterpiece",
                )
            )
        ):
            paragraphs.pop()
        else:
            break
    return "\n\n".join(p for p in paragraphs if p.strip()).strip()


_SUGGESTION_SYSTEM_PROMPT = """\
You generate short follow-up suggestions for a chat assistant app.

You are given both what the user asked and what the assistant answered. Suggestions must be the **natural next steps** for *this* exchange — tied to the same topic, scope, and intent.

Rules:
- Exactly 3 suggestions. Each under 10 words.
- **Ground in the user question and the assistant reply** — not generic filler ("Tell me more", "Make it shorter", "What else?") unless the reply is truly too thin to be more specific.
- Write from the user's perspective (e.g. "Add a section on Quebec" not "The user may want Quebec").
- NEVER suggest reading aloud, listening, or speaking — the read-aloud button is already in the UI.
- **Never** suggest opening Photoshop, GIMP, "tracing", "tutorials" on how to draw, or any DIY art-software workflow — the app generates images; users are not hand-drawing in external tools.
- If the assistant **just generated an AI image** (user asked to create/draw/generate a picture), prefer actionable chip text the app can run: e.g. "Download this image as PNG", "Try a different art style", "Make a wider landscape version" — not software tutorials.
- If the topic is visual (fashion, places, food, people, design, art, style, decor, nature, travel) and it is **not** only a raw image-generation request, you may still include a line starting with "Show me photos of" or "Search for images of" for reference browsing.
- Return ONLY a valid JSON array of 3 strings, no other text.

Example (essay about South Beach Miami):
["Show me photos of South Beach in summer", "Add a section on the Art Deco district", "Make it longer with more detail"]

Example (factual help):
["What if we change the API schema?", "Show a minimal code example", "What breaks in production?"]

Example (fashion / style topic):
["Show me photos of this style", "Search for images of the outfit", "Where can I buy similar pieces?"]

Example (AI just generated a character or scene image):
["Download this image as PNG", "Regenerate with a darker mood", "Add a second character to the scene"]
"""


class SuggestionsRequest(BaseModel):
    user_message: str
    assistant_response: str


@router.post("/suggestions")
async def generate_suggestions(
    body: SuggestionsRequest,
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> dict:
    """
    Use GAIA Spark (llama3.2:3b) to generate 3 contextual follow-up suggestions
    based on the actual assistant response. Falls back to [] on any error.
    """
    if _is_echo_corrupt(body.assistant_response) or _is_prompt_meta_narration(
        body.assistant_response
    ):
        return {"suggestions": []}

    # Cap context to avoid long prompts for the small router model
    response_snippet = body.assistant_response.strip()[:2000]
    user_snippet = body.user_message.strip()[:500]

    messages = [
        {"role": "system", "content": _SUGGESTION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"User asked: {user_snippet}\n\n"
                f"Assistant responded: {response_snippet}\n\n"
                "Generate 3 follow-up suggestions."
            ),
        },
    ]

    host = orchestrator._host  # noqa: SLF001
    fast_model = orchestrator._fast_model  # noqa: SLF001 — GAIA Spark

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                f"{host}/api/chat",
                json={
                    "model": fast_model,
                    "messages": messages,
                    "stream": False,
                    "options": {"num_predict": 120, "temperature": 0.7},
                },
            )
            resp.raise_for_status()
            content = resp.json()["message"]["content"].strip()

        # Extract JSON array from the response
        m = re.search(r'\[.*?\]', content, re.DOTALL)
        if not m:
            return {"suggestions": []}

        raw = json.loads(m.group())
        suggestions = [str(s).strip() for s in raw if str(s).strip()][:3]
        return {"suggestions": suggestions}

    except Exception:
        return {"suggestions": []}


class FormatRequest(BaseModel):
    content: str


def _looks_like_musical_or_structured_block(text: str) -> bool:
    """
    Chord progressions, key names, lead-sheet section labels — not chatty outro/intro.
    Keeps the last line of a response (e.g. 'G Major - … (Fade out)') in the body
    with normal styling instead of muted outro.
    """
    t = text.strip()
    if not t:
        return False
    if re.search(r"\b[A-G](?:#|b)?\s+(?:Major|minor)\b", t, re.I):
        return True
    if len(re.findall(r"\s-\s", t)) >= 2:
        return True
    if re.search(
        r"\([^)]*\b(?:Verse|Chorus|Bridge|Intro|Outro|Ending|Fade|Instrumental|Hook|Refrain)\b[^)]*\)",
        t,
        re.I,
    ):
        return True
    return False


def _normalize_merged_sections(
    intro: str, body: str, outro: str, full_content: str
) -> dict:
    """
    Re-merge lead-sheet / chord text misclassified as intro or outro into body.
    Matches normalizeResponseSections in message-bubble.tsx.
    """
    t_i = (intro or "").strip()
    t_o = (outro or "").strip()
    t_b = ((body or full_content).strip() or (full_content or "").strip() or full_content) or ""
    if t_i and _looks_like_musical_or_structured_block(t_i):
        t_b = f"{t_i}\n\n{t_b}" if t_b else t_i
        t_i = ""
    if t_o and _looks_like_musical_or_structured_block(t_o):
        t_b = f"{t_b}\n\n{t_o}" if t_b else t_o
        t_o = ""
    if not t_i and not t_o:
        return {"intro": "", "body": t_b or full_content, "outro": ""}
    return {"intro": t_i, "body": t_b, "outro": t_o}


def _is_short_prose(paragraph: str) -> bool:
    """
    Returns True if *paragraph* looks like a short conversational remark
    (intro preamble or outro closing) rather than substantive content.
    Mirrors the isShortProse() helper in message-bubble.tsx.
    """
    t = paragraph.strip()
    if not t:
        return False
    if _looks_like_musical_or_structured_block(t):
        return False
    # Code blocks, headings, lists, tables — never an intro/outro
    if t.startswith(("```", "#", "- ", "* ", "|")) or re.match(r"^\d+\.", t):
        return False
    lines = [ln for ln in t.splitlines() if ln.strip()]
    return len(lines) <= 3 and len(t) <= 220


def _split_response_sections(content: str) -> dict:
    """
    Deterministically split an assistant response into intro / body / outro.

    Algorithm mirrors splitResponseSections() in message-bubble.tsx so both
    sides always produce identical results without any LLM call — eliminating
    the risk of the formatter echoing its own system prompt.
    """
    paras = [p for p in re.split(r"\n{2,}", content.strip()) if p.strip()]

    if len(paras) <= 1:
        return {"intro": "", "body": content, "outro": ""}

    intro_end    = 0
    outro_start  = len(paras)
    last_idx     = len(paras) - 1

    # At most one short-prose paragraph becomes the intro (only if body remains)
    if _is_short_prose(paras[0]) and len(paras) > 1:
        intro_end = 1

    # At most one short-prose paragraph becomes the outro (only if body remains)
    if last_idx > intro_end and _is_short_prose(paras[last_idx]):
        outro_start = last_idx

    intro = "\n\n".join(paras[:intro_end])       if intro_end > 0           else ""
    outro = "\n\n".join(paras[outro_start:])      if outro_start < len(paras) else ""
    body  = "\n\n".join(paras[intro_end:outro_start])

    if not intro and not outro:
        return {"intro": "", "body": content, "outro": ""}

    return _normalize_merged_sections(
        intro, body or content, outro, content
    )


@router.post("/format")
async def format_response(body: FormatRequest) -> dict:
    """
    Split an assistant response into intro / body / outro using a fast,
    deterministic heuristic — no LLM call, no risk of echoing prompt text.
    """
    return _split_response_sections(body.content)


# ── Music generation intent detection ────────────────────────────────────────

# Exact-substring keywords (kept for specificity)
_MUSIC_GEN_KEYWORDS: Sequence[str] = (
    "background music",
    "lo-fi beat",
    "hip hop beat",
    "hip-hop beat",
    "jazz beat",
    "jazz track",
    "electronic beat",
    "chill beat",
    "trap beat",
    "drum beat",
    "piano music",
    "piano intro",
    "piano version",
    "piano melody",
    "piano riff",
    "piano cover",
    "guitar music",
    "guitar riff",
    "guitar intro",
    "ambient music",
    "relaxing music",
    "musicgen",
)

# Regex pattern 1: verb + anything + music noun (gap widened to 80 chars to
# handle long song names, e.g. "generate the piano coldplay sky full of stars intro music")
_MUSIC_GEN_RE = re.compile(
    r"\b(generate|create|make|produce|compose|build|give\s+me)\b"
    r".{0,80}"
    r"\b(beat|beats|music|track|tracks|instrumental|melody|tune|song|composition|rhythm|jingle|audio)\b",
    re.IGNORECASE,
)

# Regex pattern 2: "play/generate/create ... [song/artist] ... on/with piano/guitar/etc."
_MUSIC_INSTRUMENT_RE = re.compile(
    r"\b(generate|create|make|produce|compose|play|give\s+me)\b"
    r".{0,80}"
    r"\b(piano|guitar|violin|cello|drums|bass|synth|keyboard|flute|saxophone|trumpet)\b",
    re.IGNORECASE,
)

# Regex pattern 3: "... intro/outro/riff/solo ... music/audio/sound"
_MUSIC_PART_RE = re.compile(
    r"\b(intro|outro|riff|solo|bridge|chorus|verse|hook)\b"
    r".{0,60}"
    r"\b(music|audio|sound|melody|track|song)\b"
    r"|\b(music|audio|sound|melody|track)\b"
    r".{0,30}"
    r"\b(intro|outro|riff|solo|bridge|chorus)\b",
    re.IGNORECASE,
)


def _is_music_gen_request(text: str) -> bool:
    lowered = (text or "").lower().strip()
    if any(kw in lowered for kw in _MUSIC_GEN_KEYWORDS):
        return True
    if _MUSIC_GEN_RE.search(text or ""):
        return True
    if _MUSIC_INSTRUMENT_RE.search(text or ""):
        return True
    if _MUSIC_PART_RE.search(text or ""):
        return True
    return False


# Mapping of well-known song/artist keywords → evocative MusicGen descriptions
# MusicGen cannot reproduce copyrighted songs but can generate original music
# inspired by the style/mood description.
_SONG_STYLE_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"sky full of stars|coldplay.*piano|piano.*coldplay", re.I),
     "atmospheric electronic piano, Coldplay-style, dreamy evolving melody, ethereal synth pads, emotional buildup, 120 BPM"),
    (re.compile(r"bohemian rhapsody|queen.*piano|piano.*queen", re.I),
     "dramatic piano ballad, operatic, Queen-style, powerful build, classical meets rock"),
    (re.compile(r"clair de lune|debussy|classical piano", re.I),
     "romantic classical piano, Debussy-style, gentle flowing arpeggios, soft dynamics"),
    (re.compile(r"river flows|yiruma|korean piano", re.I),
     "soft emotional piano, contemporary classical, gentle flowing melody, peaceful and melancholic"),
    (re.compile(r"interstellar|hans zimmer|cinematic", re.I),
     "cinematic piano and strings, Hans Zimmer-style, slow build, epic emotional swell"),
    (re.compile(r"lofi|lo-fi|lo fi|study music|chill hop", re.I),
     "lo-fi hip hop beat, soft piano chords, warm vinyl crackle, relaxing, 85 BPM"),
    (re.compile(r"jazz", re.I),
     "smooth jazz piano, walking bass, brushed drums, warm and mellow, late-night jazz club"),
    (re.compile(r"hip.?hop|rap beat|trap", re.I),
     "modern hip hop beat, 808 bass, trap hi-hats, melodic piano sample, 140 BPM"),
]


def _extract_music_prompt(user_message: str) -> str:
    """
    Convert the user's music request into a clean MusicGen prompt.

    For song-inspired requests (e.g. 'generate Coldplay sky full of stars piano intro'),
    returns a detailed stylistic description instead of the raw user text, since
    MusicGen generates original music and cannot reproduce copyrighted songs.
    """
    import re as _re

    msg = user_message.strip()

    # Check for known song/artist patterns first — return evocative style description
    for pattern, style_desc in _SONG_STYLE_MAP:
        if pattern.search(msg):
            # Extract any extra style hints from the message (e.g. "intro", "slow", "fast")
            extras = []
            if _re.search(r"\bintro\b", msg, _re.I):
                extras.append("opening intro")
            if _re.search(r"\bslow\b|\bsoftly\b|\bgentle\b", msg, _re.I):
                extras.append("slow and gentle")
            if _re.search(r"\bfast\b|\bupbeat\b|\benergetic\b", msg, _re.I):
                extras.append("energetic upbeat")
            suffix = ", " + ", ".join(extras) if extras else ""
            return style_desc + suffix

    # Strip conversational filler to get the core music description
    patterns = [
        r"^(hey\s+nova[,\.]?\s*)",
        r"^(can\s+you\s+)",
        r"^(please\s+)",
        r"^(i\s+want\s+(you\s+to\s+)?)",
        r"^(i'd\s+like\s+(you\s+to\s+)?)",
        r"^(generate\s+(me\s+)?(a\s+|the\s+)?)",
        r"^(make\s+(me\s+)?(a\s+)?)",
        r"^(create\s+(me\s+)?(a\s+)?)",
        r"^(give\s+me\s+(a\s+)?)",
        r"^(produce\s+(me\s+)?(a\s+)?)",
        r"^(compose\s+(me\s+)?(a\s+)?)",
        r"^(play\s+(me\s+)?(a\s+)?)",
    ]
    for pattern in patterns:
        msg = _re.sub(pattern, "", msg, flags=_re.IGNORECASE).strip()

    # Strip trailing noise
    msg = _re.sub(r"\s*(for me|please|now|quickly|asap|audio|sound)\s*$", "", msg, flags=_re.IGNORECASE).strip()

    return msg or user_message.strip()


# Music-descriptor words used to score sentences in the LLM response
_MUSIC_SCORE_WORDS: frozenset[str] = frozenset({
    # instruments
    "piano", "guitar", "drums", "bass", "synth", "violin", "cello",
    "trumpet", "saxophone", "flute", "organ", "ukulele", "harp", "sitar",
    "keyboard", "strings", "brass", "woodwind",
    # tempo / rhythm
    "bpm", "tempo", "beat", "rhythm", "upbeat", "groove",
    # mood / texture
    "atmospheric", "dreamy", "melancholic", "emotional", "energetic",
    "relaxing", "peaceful", "epic", "dark", "bright", "uplifting",
    "soothing", "intense", "mellow", "haunting", "ethereal", "cinematic",
    # style / genre
    "jazz", "lofi", "lo-fi", "hip-hop", "classical", "electronic",
    "ambient", "rock", "pop", "folk", "orchestral", "acoustic",
    # musical structure
    "melody", "chord", "arpeggios", "progression", "riff", "solo",
    "harmony", "layers", "instrumental", "motif", "hook",
})

# Conversational filler to strip from the start of a response sentence
_MUSIC_RESPONSE_FILLER = re.compile(
    r"^(sure[,!]?\s*|here\s*(is|are|'s|s)\s*(a\s*|an\s*|the\s*)?|"
    r"i('ll|'m going to|'m about to|will)\s+(generate|create|produce|compose|make)\s*(a\s*|an\s*|the\s*)?|"
    r"generating\s*(a\s*|an\s*|the\s*)?|"
    r"here\s+you\s+go[,!]?\s*|"
    r"okay[,!]?\s*|alright[,!]?\s*)",
    re.IGNORECASE,
)


def _refine_music_prompt_from_response(response: str, fallback: str) -> str:
    """
    Extract the best MusicGen prompt from GAAIA's actual response text.

    Looks for the sentence most loaded with musical descriptors — tempo,
    instrument names, mood words, genre tags, etc. — and returns it
    stripped of conversational filler.  Falls back to *fallback* if the
    response contains no useful musical descriptions.
    """
    import re as _re

    # Split into sentences (period / exclamation / newline)
    sentences = _re.split(r"(?<=[.!?])\s+|\n+", response.strip())

    best_sentence = ""
    best_score    = 0

    for sent in sentences:
        words = _re.findall(r"[a-z]+", sent.lower())
        score = sum(1 for w in words if w in _MUSIC_SCORE_WORDS)
        # Extra weight for BPM numbers (e.g. "120 BPM", "80bpm")
        if _re.search(r"\d+\s*bpm", sent, _re.I):
            score += 3
        if score > best_score:
            best_score    = score
            best_sentence = sent

    if best_score < 2:
        # Not enough music description in the response — keep the original prompt
        return fallback

    # Strip leading conversational filler
    refined = _MUSIC_RESPONSE_FILLER.sub("", best_sentence).strip()
    # Strip leading/trailing markdown and punctuation noise
    refined = re.sub(r"^[*_`#>\-•]+|[*_`#>\-•]+$", "", refined).strip()

    return refined if len(refined) > 8 else fallback


# ── Image generation intent detection ────────────────────────────────────────

# Exact-substring keywords (kept for specificity)
_IMAGE_GEN_KEYWORDS: Sequence[str] = (
    "stable diffusion",
    "text to image",
    "text-to-image",
    "illustrate",
    "design a logo",
)

# Pattern A — verb-first: "generate/create/draw/make/… [words] image/photo/…"
# Tempered repeat: the span between the verb and "image" must not pass through
# a document request (or "create a word document" is mis-read as "create" + "images" later).
_IMAGE_GEN_RE = re.compile(
    # "show" is intentionally excluded here — "show me a photo/picture of X" is a
    # web-image-search request (handled by _VISUAL_SHOW_RE), not an AI generation request.
    r"\b(generate|create|make|draw|paint|produce|design|render|give\s+me|imagine|visualize|depict)\b"
    r"(?:(?!word\s+document|word\s+doc|write\s+an?\s+essay|essay\s+on|term\s+paper|create\s+.*\s+document|make\s+.*\s+document).){0,70}"
    r"\b(image|images|art|artwork|illustration|poster|logo|visual|graphic|painting|drawing|sketch|portrait|landscape|wallpaper|render)\b",
    re.IGNORECASE,
)

# Pattern B — noun-first: "the/a/an image of …", "a photo of …", "a portrait of …"
# Catches: "the image of Nami", "a picture of a dragon", "portrait of a warrior"
_IMAGE_NOUN_FIRST_RE = re.compile(
    r"\b(an?\s+|the\s+)?(image|photo|picture|pic|portrait|illustration|artwork|drawing|sketch|painting|wallpaper)\s+"
    r"(of|depicting|showing|featuring|with)\b",
    re.IGNORECASE,
)

# Pattern C — character / scene render: "X anime character", "anime version of X", etc.
_IMAGE_ANIME_RE = re.compile(
    r"\b(anime|manga|cartoon|animated)\s+(character|version|style|art|drawing|image|picture|portrait)\b"
    r"|\b(character|version|style|art)\s+of\b",
    re.IGNORECASE,
)

# Pattern D — bare draw/sketch/paint with a subject but no art noun
# Catches: "draw me luffy", "sketch nami", "paint a dragon", "draw goku"
_IMAGE_BARE_VERB_RE = re.compile(
    r"^(draw|sketch|paint)\s+(me\s+)?\w",
    re.IGNORECASE,
)


def _is_document_essay_with_embedded_images_request(text: str) -> bool:
    """
    True when the user is mainly asking for an essay / Word (or similar) where
    images are meant to *illustrate the document* (and match inside the file),
    not a separate chat-side Stable Diffusion image.

    Prevents _IMAGE_GEN_RE from matching: "create a word document" + "include
    images" (the verb "create" applies to the document, not to a stand-alone image).
    """
    t = (text or "").lower()
    has_longform_doc = bool(
        re.search(
            r"(?i)\b("
            r"write\s+an?\s+essay|write\s+.*\s+essay|essay\s+on|"
            r"word\s+document|word\s+doc\b|\bdocx\b|"
            r"create\s+.*\bword\b|create\s+.*\s+document|"
            r"make\s+.*\s+document|"
            r"term\s+paper|report|thesis|"
            r"powerpoint|pptx|presentation"
            r")\b",
            t,
        )
    )
    has_embedded_illustration_intent = bool(
        re.search(
            r"(?i)(include|with|add|embed).{0,80}?\b(images?|photos?|pictures?|illustrations?)\b|"
            r"\b(images?|photos?|pictures?)\s+from\s+(?:online|the\s+web|google|the\s+internet|search)\b|"
            r"same\s+images?\b|"
            r"images?\s+in\s+the\s+(?:word|doc|document|file)\b|"
            r"illustrat.{0,40}?\b(essay|document|word|docx|paper|file)\b|"
            r"from\s+online\s+or\s+generated",
            t,
        )
    )
    if has_longform_doc and has_embedded_illustration_intent:
        return True
    return False


def _wants_web_for_doc_images(text: str) -> bool:
    """
    True when the user explicitly asks for images *from the web/online* in their
    document (as opposed to AI-generated / Stable Diffusion images).
    """
    t = (text or "").lower()
    return bool(re.search(
        r"\b(from\s+online|from\s+the\s+web|from\s+the\s+internet|from\s+google|"
        r"online\s+images?|web\s+images?|internet\s+images?|"
        r"images?\s+from\s+(?:online|the\s+web|google|internet|search)|"
        r"online\s+or\s+generated|from\s+online\s+or)\b",
        t,
    ))


def _extract_essay_topic(user_message: str) -> str:
    """Extract the main essay subject as a short phrase for image search queries."""
    t = (user_message or "").strip()
    # Patterns: "essay on/about/of X", "write about X", "write an essay about/of X"
    for pat in (
        r"essay\s+(?:on|about|of|regarding)\s+(.+?)(?:\s*[.,]|\s+include|\s+with|\s+and\s+create|$)",
        r"write\s+(?:about|on)\s+(.+?)(?:\s*[.,]|\s+include|\s+with|\s+and\s+create|$)",
        r"(?:write|make|create|compose)\s+(?:me\s+)?(?:a\s+|an\s+)?(?:\w+\s+){0,4}?(?:essay|paper|report|article)\s+(?:for\s+me\s+)?(?:about|on|of|regarding)\s+(.+?)(?:\s*[.,]|\s+include|\s+with|\s+and\s+create|$)",
    ):
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            topic = m.group(m.lastindex or 1).strip().rstrip(".,;")
            if topic:
                return " ".join(topic.split()[:10])
    return ""


def _parse_essay_for_sections(text: str) -> list[dict]:
    """
    Parse essay markdown text into a list of {"heading", "text"} dicts (up to 6).
    Splits on ## / ### headings; falls back to bold or numbered headings.
    """
    heading_re = re.compile(r"^#{1,3}\s+(.+)$", re.MULTILINE)
    parts = heading_re.split(text)
    sections: list[dict] = []

    if len(parts) >= 3:
        for i in range(1, len(parts) - 1, 2):
            heading = parts[i].strip()
            body_text = parts[i + 1].strip() if i + 1 < len(parts) else ""
            paras = [p.strip() for p in body_text.split("\n\n") if p.strip()]
            sections.append({
                "heading": heading,
                # Join all paragraphs so the full section text appears in the chat view
                "text": "\n\n".join(paras)[:2000],
            })
            if len(sections) >= 6:
                break
    else:
        # Try bold headings: **Heading**
        bold_re = re.compile(r"^\*{2}(.+)\*{2}\s*$", re.MULTILINE)
        parts2 = bold_re.split(text)
        if len(parts2) >= 3:
            for i in range(1, len(parts2) - 1, 2):
                heading = parts2[i].strip()
                body_text = parts2[i + 1].strip() if i + 1 < len(parts2) else ""
                paras = [p.strip() for p in body_text.split("\n\n") if p.strip()]
                sections.append({
                    "heading": heading,
                    "text": "\n\n".join(paras)[:2000],
                })
                if len(sections) >= 6:
                    break

    if not sections:
        sections = [{"heading": "Content", "text": text[:500].strip()}]
    return sections


async def _llm_essay_image_placements(
    essay_text: str,
    section_headings: list[str],
    use_web: bool,
    ollama_host: str,
    core_model: str,
    max_images: int | None = None,
) -> list[dict]:
    """
    Ask GAIA Core (Ollama) to *after* the essay is written — decide which sections
    deserve an image and the exact search query (web) or SD prompt (generated).

    Returns a list of dicts, each like:
      {"section_index": int, "search_query": str}   # when use_web
      {"section_index": int, "image_prompt": str}  # when not use_web
    On failure, returns an empty list (caller may fall back to heuristics).
    """
    n = len(section_headings)
    if n < 1:
        return []
    # Target: one image per section, capped by caller or 6 total.
    # GAIA Core's prompt already tells it to skip bare intros/conclusions,
    # so the LLM naturally won't fill every slot — we just give it room to.
    _cap = max_images if isinstance(max_images, int) else 6
    _cap = max(1, min(6, _cap))
    k = min(_cap, n)

    outline = "\n".join(
        f"  {i}: {h}" for i, h in enumerate(section_headings) if h.strip()
    )
    user_payload = f"""The essay was split into these sections (0-based indices):

{outline}

--- FULL ESSAY TEXT ---
{essay_text[:4000]}

Read the whole essay, then list which section indices should get one illustration each.
You may choose up to {k} sections (not every section). Prefer the most visual, place-specific, or event-rich
sections. Skip a bare "Introduction" or "Conclusion" if they add little visual value unless
the content there is very concrete and photographable.
"""

    if use_web:
        system = f"""You are GAIA Core — a visual layout assistant. Your job is to choose
where real web photographs should appear in a published essay.

For each section you select, you must return:
- "section_index": integer, must be between 0 and {n - 1}
- "search_query": 6-14 words in English for an image search engine. Be specific
  (landmarks, beach names, neighborhood, festival names, "Art Deco district Miami" etc.).

Return ONLY a valid JSON array (no markdown fences, no extra keys), for example:
[{{"section_index": 1, "search_query": "Lummus Park Beach Miami white sand summer"}}, ...]
"""
    else:
        system = f"""You are GAIA Core — a visual layout assistant. Your job is to choose
where generated illustrations should appear in a published essay.

For each section you select, you must return:
- "section_index": integer, must be between 0 and {n - 1}
- "image_prompt": 28-40 words, a vivid Stable Diffusion prompt. Include art direction and
  quality tags: photorealistic or editorial photography, 8k, natural lighting, South Florida
  context when relevant.

Return ONLY a valid JSON array (no markdown fences, no extra keys), for example:
[{{"section_index": 1, "image_prompt": "Lifeguard tower on white sand, turquoise ocean, Miami…"}}, ...]
"""

    try:
        async with httpx.AsyncClient(timeout=55.0) as client:
            resp = await client.post(
                f"{ollama_host.rstrip('/')}/api/chat",
                json={
                    "model": core_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_payload},
                    ],
                    "stream": False,
                    "options": {"num_predict": 1200, "temperature": 0.3},
                },
            )
            resp.raise_for_status()
            raw = resp.json()["message"]["content"].strip()
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if not m:
            return []
        out = json.loads(m.group())
        if not isinstance(out, list):
            return []
        cleaned: list[dict] = []
        seen: set[int] = set()
        for item in out:
            if not isinstance(item, dict):
                continue
            try:
                si = int(item.get("section_index", -1))
            except (TypeError, ValueError):
                continue
            if si < 0 or si >= n or si in seen:
                continue
            if use_web:
                q = (item.get("search_query") or "").strip()
                if len(q) < 4:
                    continue
                cleaned.append({"section_index": si, "search_query": q[:200]})
            else:
                p = (item.get("image_prompt") or "").strip()
                if len(p) < 10:
                    continue
                cleaned.append({"section_index": si, "image_prompt": p[:800]})
            seen.add(si)
        return cleaned[:k]
    except Exception as exc:
        print(f"[Chat] GAIA Core essay image placement failed: {exc}", flush=True)
        return []


def _is_web_image_browse_request(text: str) -> bool:
    """
    User wants to *see* images from the web (search, gallery), not to run the
    text-to-image generator.  Must be checked before _is_image_gen_request
    so phrases like "show me an image of Nami" don't match _IMAGE_NOUN_FIRST_RE.
    """
    t = (text or "").lower().strip()
    if not t:
        return False
    # Clear generation: create/draw an image, etc.
    if re.search(
        r"(?i)\b(generate|create|make|render|illustrate)\b"
        r".{0,20}\b(a|an|the|some|me|new|original|custom|another)?\s*"
        r"(image|photo|picture|pic|portrait|artwork|illustration|drawing|sketch)\b",
        t,
    ):
        return False
    if re.search(
        r"(?i)\b(draw|sketch|paint|illustrate)\s+(me\s+)?(a|an|her|him|it|this|that|the|my)\b",
        t,
    ):
        return False
    if _IMAGE_BARE_VERB_RE.search(t):
        return False
    if re.search(
        r"(?i)\b(show|find|search|look\s+up|pull\s+up|can\s+you\s+show|let\s+me\s+see)\b",
        t,
    ) and re.search(r"(?i)\b(images?|photos?|pictures?|pics?)\b", t):
        return True
    if re.search(
        r"(?i)show me (a|an|the|some) (image|photo|picture|pic)\b",
        t,
    ) and not re.search(r"(?i)\b(generate|draw|create|sketch|paint|make|render|illustrate)\b", t):
        return True
    return False


def _is_image_gen_request(text: str) -> bool:
    if _is_web_image_browse_request(text):
        return False
    if _is_document_essay_with_embedded_images_request(text):
        return False
    lowered = (text or "").lower().strip()
    if any(kw in lowered for kw in _IMAGE_GEN_KEYWORDS):
        return True
    if _IMAGE_GEN_RE.search(text or ""):
        return True
    if _IMAGE_NOUN_FIRST_RE.search(text or ""):
        return True
    if _IMAGE_ANIME_RE.search(text or ""):
        return True
    if _IMAGE_BARE_VERB_RE.search(lowered):
        return True
    if _IMAGE_COLOUR_FOLLOWUP_RE.search(text or ""):
        return True
    return False


_VAGUE_IMAGE_WORDS = frozenset({
    "image", "photo", "picture", "pic", "art", "drawing", "painting",
    "random image", "an image", "a photo", "a picture", "a painting",
    "random", "something", "anything", "cool image", "cool photo",
    "random art", "some art", "art work", "artwork",
})


def _extract_image_prompt(user_message: str) -> str:
    """Extract a clean image generation prompt from the user's message.

    Strips conversational filler and verb/noun wrappers to leave the
    subject/scene description that should be sent to the image generator.
    Returns empty string only for truly content-free requests.
    """
    msg = user_message.strip()

    # Strip leading address / politeness
    leading = [
        r"^(hey\s+nova[,\.]?\s*)",
        r"^(can\s+you\s+(please\s+)?)",
        r"^(please\s+)",
        r"^(i\s+want\s+(you\s+to\s+)?)",
        r"^(i\s+need\s+(you\s+to\s+)?)",
        r"^(i'd\s+like\s+(you\s+to\s+)?)",
        r"^(nova[,\.]?\s+)",
    ]
    for pat in leading:
        msg = re.sub(pat, "", msg, flags=re.IGNORECASE).strip()

    # Strip generation verb + optional article: "generate a", "create an", "draw me a", etc.
    verb_strip = (
        r"^(generate|create|make|draw|paint|produce|design|render|show|imagine|"
        r"visualize|depict|give\s+me)\s+(me\s+)?(an?\s+|the\s+)?"
    )
    msg = re.sub(verb_strip, "", msg, flags=re.IGNORECASE).strip()

    # Strip pure noun wrappers: "image of", "photo of", "picture of", "a portrait of"
    # BUT keep "anime image of X" → the subject is "anime character X"
    noun_wrap = r"^(an?\s+|the\s+)?(image|photo|picture|pic|portrait|illustration|artwork|drawing|sketch|painting|wallpaper)\s+(of|depicting|showing|featuring)\s+"
    msg = re.sub(noun_wrap, "", msg, flags=re.IGNORECASE).strip()

    # Strip trailing filler
    msg = re.sub(r"\s*(for me|please|now|quickly|asap|thanks)\s*[\.\!]*$", "", msg, flags=re.IGNORECASE).strip()

    # Remove trailing punctuation
    msg = msg.rstrip(".,!?").strip()

    if not msg or msg.lower() in _VAGUE_IMAGE_WORDS:
        return ""

    # ── Known character enrichment ────────────────────────────────────────────
    # For recognised anime/game/fiction characters, replace the plain name with
    # a detailed, accurate description so Stable Diffusion renders them correctly.
    _CHAR_DB: list[tuple[str, str]] = [
        # ── Live-action / TV / Film (actor name included for SD face accuracy) ──
        (r"\bthomas\s+shelby\b|\bshelby\b.*peaky|peaky.*\bshelby\b",
         "Thomas Shelby, Cillian Murphy, Peaky Blinders, "
         "sharp cheekbones, piercing blue eyes, slicked-back dark undercut hair, "
         "tailored charcoal three-piece suit, flat cap, cigarette between fingers, "
         "cold intimidating expression, 1920s Birmingham alley, moody noir lighting, "
         "cinematic, photorealistic, sharp focus, 8k ultra HD"),
        (r"\bwalter\s+white\b|\bheisenberg\b",
         "Walter White Heisenberg, Bryan Cranston, Breaking Bad, "
         "bald head, salt-and-pepper goatee, intense brown eyes, "
         "black pork-pie hat, black jacket, holding chemistry flask, "
         "New Mexico desert background, harsh sunlight, "
         "photorealistic, cinematic lighting, sharp focus, 8k"),
        (r"\bjohn\s+wick\b",
         "John Wick, Keanu Reeves, sharp jawline, short dark hair, "
         "perfectly fitted black tactical suit and tie, "
         "holding a pistol with both hands, neon-lit rainy city background, "
         "intense focused gaze, cinematic action shot, "
         "photorealistic, dramatic lighting, 8k ultra HD"),
        (r"\btony\s+stark\b|\biron\s+man\b",
         "Tony Stark Iron Man, Robert Downey Jr, "
         "arc reactor glowing in chest, goatee, confident smirk, "
         "sleek black turtleneck or Iron Man suit, "
         "photorealistic, cinematic Marvel lighting, 8k"),
        (r"\bjonathan\s+wick\b|\bwick\b",
         "John Wick, Keanu Reeves, all-black tactical suit, "
         "cinematic neon-lit environment, photorealistic, 8k"),

        # ── One Piece ──────────────────────────────────────────────────────────
        (r"\bnami\b.*one.?piece|one.?piece.*\bnami\b|\bnami\b.*pirate|\bnami\b.*straw.?hat",
         "Nami, One Piece anime character, "
         "long bright orange wavy hair, large expressive brown eyes, warm tan skin, "
         "curvy hourglass figure, "
         "wearing orange strappy crop top, white cargo shorts, "
         "Log Pose bracelet on left wrist, pinwheel tattoo on left shoulder, "
         "confident charming smile, stylish pose, "
         "official One Piece anime art style, full color vibrant illustration, "
         "digital painting, vivid warm colors, 8k"),
        (r"\bluffy\b.*one.?piece|one.?piece.*\bluffy\b|\bmonkey.*luffy\b",
         "Monkey D. Luffy, One Piece anime character, "
         "messy short black hair, large black eyes, scar under left eye, "
         "iconic red vest open on chest, blue shorts, straw hat on head, "
         "wide cheerful grin, dynamic pose, "
         "official One Piece anime art style, highly detailed, vibrant colors, 8k"),
        (r"\bzoro\b.*one.?piece|one.?piece.*\bzoro\b|\broronoa",
         "Roronoa Zoro, One Piece anime character, "
         "short green hair, muscular build, three swords at hip, "
         "white shirt, black pants, green haramaki, "
         "serious stoic expression, "
         "official One Piece anime art style, highly detailed, 8k"),
        (r"\bsanji\b.*one.?piece|one.?piece.*\bsanji\b",
         "Sanji, One Piece anime character, "
         "curly blonde hair covering right eye, slim tall build, "
         "black suit, dark tie, cigarette, suave expression, "
         "official One Piece anime art style, highly detailed, 8k"),
        (r"\brobin\b.*one.?piece|one.?piece.*\brobin\b|\bnico.?robin\b",
         "Nico Robin, One Piece anime character, "
         "long straight dark hair, tall slim figure, calm mysterious expression, "
         "purple outfit, reading a book, "
         "official One Piece anime art style, highly detailed, 8k"),

        # ── Naruto ─────────────────────────────────────────────────────────────
        (r"\bnaruto\b.*uzumaki|\buzumaki.*naruto\b|\bnaruto\s+uzumaki\b",
         "Naruto Uzumaki, Naruto Shippuden anime character, "
         "spiky bright blonde hair, blue eyes, three whisker marks on each cheek, "
         "orange and black ninja jumpsuit, leaf village headband, "
         "confident determined expression, dynamic fighting pose, "
         "official Naruto anime art style, highly detailed, vibrant colors, 8k"),
        (r"\bsasuke\b.*naruto|naruto.*\bsasuke\b|\bsasuke\s+uchiha\b",
         "Sasuke Uchiha, Naruto anime character, "
         "dark spiky hair, pale skin, dark eyes with Sharingan, "
         "dark blue shirt, white shorts, sword on back, "
         "cold serious expression, "
         "official Naruto anime art style, highly detailed, 8k"),
        (r"\bsakura\b.*naruto|naruto.*\bsakura\b|\bsakura\s+haruno\b",
         "Sakura Haruno, Naruto anime character, "
         "short pink hair, green eyes, red Chinese dress, "
         "leaf village headband, determined expression, "
         "official Naruto anime art style, highly detailed, 8k"),
        (r"\bkakashi\b.*naruto|naruto.*\bkakashi\b",
         "Kakashi Hatake, Naruto anime character, "
         "silver-gray hair spiked upward, dark eye and Sharingan eye, "
         "mask covering lower face, ANBU flak jacket, headband over eye, "
         "cool relaxed expression, "
         "official Naruto anime art style, highly detailed, 8k"),

        # ── Attack on Titan ────────────────────────────────────────────────────
        (r"\beren\b.*titan|titan.*\beren\b|\beren\s+yeager\b",
         "Eren Yeager, Attack on Titan anime character, "
         "dark brown hair tied back in bun, teal-green eyes, "
         "Survey Corps uniform with white shirt, green hooded cape, ODM gear, "
         "intense determined expression, "
         "official Attack on Titan art style, highly detailed, 8k"),
        (r"\bmikasa\b.*titan|titan.*\bmikasa\b|\bmikasa\s+ackerman\b",
         "Mikasa Ackerman, Attack on Titan anime character, "
         "short straight black hair, grey eyes, athletic muscular build, "
         "Survey Corps uniform, red scarf around neck, ODM gear, "
         "fierce determined expression, "
         "official Attack on Titan art style, highly detailed, 8k"),

        # ── Demon Slayer ───────────────────────────────────────────────────────
        (r"\btanjiro\b.*demon|demon.*\btanjiro\b|\btanjiro\s+kamado\b",
         "Tanjiro Kamado, Demon Slayer anime character, "
         "dark red-black hair in bun, burgundy eyes, "
         "green and black checkered haori, katana with flame blade, "
         "scar on forehead, kind determined face, "
         "official Demon Slayer kimetsu no yaiba art style, highly detailed, vibrant, 8k"),
        (r"\bnezuko\b.*demon|demon.*\bnezuko\b|\bnezuko\s+kamado\b",
         "Nezuko Kamado, Demon Slayer anime character, "
         "long dark hair with pink ends tied in low ponytail, "
         "bamboo muzzle in mouth, pink kimono with hemp-leaf pattern, "
         "black and pink striped tabi socks, demonic eyes with slit pupils, "
         "official Demon Slayer art style, highly detailed, 8k"),

        # ── Dragon Ball ────────────────────────────────────────────────────────
        (r"\bgoku\b.*dragon.?ball|dragon.?ball.*\bgoku\b|\bson\s*goku\b",
         "Son Goku, Dragon Ball Z anime character, "
         "spiky black hair standing on end, muscular physique, "
         "orange and blue gi uniform, white boots, power pole, "
         "confident wide smile, energy aura around body, "
         "official Dragon Ball Z anime art style, highly detailed, vibrant colors, 8k"),
        (r"\bvegeta\b.*dragon.?ball|dragon.?ball.*\bvegeta\b",
         "Vegeta, Dragon Ball Z anime character, "
         "upright flame-shaped black hair, muscular build, "
         "blue and white Saiyan battle armor, gloves and boots, "
         "proud arrogant expression, arms crossed, "
         "official Dragon Ball Z art style, highly detailed, 8k"),

        # ── Jujutsu Kaisen ─────────────────────────────────────────────────────
        (r"\bgojo\b.*jujutsu|jujutsu.*\bgojo\b|\bsatoru\s+gojo\b",
         "Satoru Gojo, Jujutsu Kaisen anime character, "
         "spiky white hair, striking blue infinity eyes, tall athletic build, "
         "black blindfold or sunglasses, black jujutsu uniform, "
         "charismatic confident expression, "
         "official Jujutsu Kaisen art style, highly detailed, 8k"),
        (r"\byuji\b.*jujutsu|jujutsu.*\byuji\b|\bitadori\b",
         "Yuji Itadori, Jujutsu Kaisen anime character, "
         "spiky pink hair, brown eyes, athletic build, "
         "black jujutsu uniform, pink tattoo markings on face, "
         "energetic fighting expression, "
         "official Jujutsu Kaisen art style, highly detailed, 8k"),
    ]

    msg_lower = msg.lower()
    for pattern, enriched_desc in _CHAR_DB:
        if re.search(pattern, msg_lower, re.IGNORECASE):
            return enriched_desc

    # ── Transform abstract / data-viz requests into paintable SD scenes ──────
    # Words like "timeline", "chart", "graph", "diagram", "map", "infographic"
    # can't literally be rendered by Stable Diffusion — convert them to a
    # rich illustrative scene that *depicts* the underlying topic instead.
    _ABSTRACT_VIZ_RE = re.compile(
        r"\b(timeline|timelines|time\s+line|chart|graph|diagram|infographic"
        r"|flowchart|map|table|data|statistics|comparison)\b",
        re.IGNORECASE,
    )
    if _ABSTRACT_VIZ_RE.search(msg):
        # Extract the subject — strip the abstract noun so we get the real topic
        topic = re.sub(_ABSTRACT_VIZ_RE, "", msg).strip(" .,;:oftheaAn\t")
        # Common topic patterns → ONE focused paintable scene (not a collage)
        # Keep scenes simple and specific — SD struggles with too many competing subjects
        # ORDER MATTERS: more specific patterns first
        _TOPIC_SCENES = [
            (r"dinosaur|prehistoric|paleontol|jurassic|cretaceous|triassic",
             "cinematic wide-angle photo of a T-Rex in a lush Cretaceous jungle, "
             "golden hour light filtering through giant ferns, mist in the background, "
             "highly detailed, photorealistic, 8k, no text, no borders"),
            (r"earth.*creat|creation.*earth|formation.*earth|earth.*form",
             "dramatic NASA-style illustration of the young Earth 4.5 billion years ago, "
             "molten lava surface, early atmosphere glowing orange, asteroids in background, "
             "space view, stunning cosmic art, photorealistic, ultra detailed, 8k"),
            (r"earth|planet|geology|geological",
             "breathtaking aerial view of Earth from space showing continents and oceans, "
             "dramatic sunlight hitting the atmosphere, thin blue atmosphere halo, "
             "NASA photography style, ultra detailed, photorealistic, 8k"),
            (r"human.*evol|evol.*human|homo|sapien|hominid",
             "cinematic museum diorama showing early Homo sapiens around a campfire at night, "
             "cave paintings on stone wall behind them, dramatic torchlight, "
             "ultra detailed, photorealistic, 8k"),
            (r"civiliz|ancient.*histor|histor.*ancient",
             "grand panoramic view of ancient Rome at its peak — Colosseum, Forum, crowds, "
             "golden afternoon light, dramatic sky, photorealistic architectural illustration, 8k"),
            (r"univers|cosmos|space|galaxy|nebula|astro|big.?bang",
             "breathtaking NASA Hubble-style photo of a swirling galaxy and nebula, "
             "deep space, stars, vivid colours of gas clouds, ultra detailed, photorealistic, 8k"),
            (r"evolution|life.*earth|biology|species",
             "stunning underwater scene of the ancient Cambrian ocean, "
             "colourful alien-looking sea creatures, shafts of light from above, "
             "photorealistic, cinematic, ultra detailed, 8k"),
        ]
        combined_text = (topic + " " + msg).lower()
        for pattern, scene in _TOPIC_SCENES:
            if re.search(pattern, combined_text, re.IGNORECASE):
                return scene
        # Generic fallback — create an artistic collage of the topic
        if topic:
            return (
                f"artistic scientific illustration and collage depicting {topic}, "
                "highly detailed museum-quality educational infographic style, "
                "vibrant colors, cinematic lighting, 8k ultra HD"
            )
        return (
            "artistic scientific illustration and collage, museum-quality "
            "educational style, vibrant colors, cinematic lighting, 8k"
        )

    return msg


def _build_enhance_image_user_payload(
    raw_extract: str,
    current_message: str,
    recent_turns: list[dict],
    web_titles: str = "",
) -> str:
    """
    One text block for the image prompt enhancer: it must know the *latest* user
    intent plus *recent* names/subjects (so "her" / "the same" resolve to Nami,
    not a random name). Optional web image captions add style/series context.
    """
    parts: list[str] = [
        "User's latest message:\n",
        (current_message or "").strip() + "\n\n",
        "Extracted subject to draw (highest priority — keep this identity):\n",
        raw_extract.strip() + "\n",
    ]
    if recent_turns:
        snips: list[str] = []
        for turn in recent_turns[-10:]:
            c = (turn.get("content") or "").strip()
            if not c:
                continue
            c = re.sub(r"\s+", " ", c)[:300]
            role = turn.get("role", "user")
            if role == "user":
                snips.append(f"- User: {c}")
            else:
                snips.append(f"- Assistant: {c[:240]}")
        if snips:
            parts.append(
                "\nRecent thread (resolve pronouns, character names, and follow-up intent):\n"
                + "\n".join(snips) + "\n"
            )
    if web_titles:
        parts.append(
            "\nWeb image search captions (use for look/series alignment; do not copy watermarks):\n"
            f"{web_titles}\n"
        )
    return "".join(parts)


async def _web_titles_for_image_enhance(query: str, count: int = 4) -> str:
    if not (query or "").strip():
        return ""
    try:
        imgs = await asyncio.wait_for(fetch_web_images((query or "").strip(), count=count), timeout=3.5)
    except (asyncio.TimeoutError, Exception):
        return ""
    if not imgs:
        return ""
    titles: list[str] = []
    for im in imgs[:4]:
        ti = (im.get("title") or "").strip()
        if ti and len(ti) > 2:
            titles.append(ti[:140])
    return " | ".join(titles) if titles else ""


async def _first_web_image_url(query: str) -> str:
    """Return the first direct image URL from a web image search, or '' on failure."""
    if not (query or "").strip():
        return ""
    try:
        imgs = await asyncio.wait_for(fetch_web_images(query.strip(), count=3), timeout=4.0)
        for im in imgs:
            url = (im.get("image_url") or im.get("thumbnail_url") or "").strip()
            if url and url.startswith("http"):
                return url
    except Exception:
        pass
    return ""


# ── Multi-image count detection ───────────────────────────────────────────────

_MULTI_IMAGE_COUNT_RE = re.compile(
    r"\b(generate|generated|create|make|draw|produce|show|include|with|add)\s+"
    r"(?P<count>[2-9]|ten|two|three|four|five|six|seven|eight|nine|"
    r"multiple|several|a\s+few|a\s+couple(\s+of)?|some)\s+"
    r"(?:different\s+|generated\s+|ai\s+generated\s+)?"
    r"(images|photos|pictures|illustrations|artworks|drawings)\b",
    re.IGNORECASE,
)

_WORD_TO_INT = {
    "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 4,  # cap at 4
    "multiple": 3, "several": 3, "a few": 3, "a couple": 2,
    "a couple of": 2, "some": 3,
}

_MAX_MULTI_IMAGES = 4  # hard cap to avoid GPU OOM


def _extract_image_count(text: str) -> int:
    """Return how many images the user wants to generate (1-4)."""
    m = _MULTI_IMAGE_COUNT_RE.search(text or "")
    if not m:
        return 1
    raw = m.group("count").strip().lower()
    if raw.isdigit():
        return min(int(raw), _MAX_MULTI_IMAGES)
    return _WORD_TO_INT.get(raw, 2)


# ── Story-mode detection (interleaved paragraph + visual) ────────────────────

_STORY_VISUAL_RE = re.compile(
    r"\b(story|tell\s+(me\s+)?a\s+story|write\s+(me\s+)?a\s+story|create\s+(me\s+)?a\s+story"
    r"|narrative|tale|journey\s+through|timeline|history\s+of|history\s+about"
    r"|progression|evolution\s+of|write\s+about|describe\s+the|tell\s+me\s+about"
    r"|walkthrough|breakdown|explainer)\b",
    re.IGNORECASE,
)

_STORY_IMAGE_KEYWORDS = frozenset({
    "image", "images", "photo", "picture", "pictures", "visual", "visuals",
    "drawing", "drawings", "sketch", "sketches", "illustration", "illustrations",
    "painting", "paintings", "artwork", "art", "diagram", "diagrams",
    "show me", "include images", "include drawings", "include visuals",
    "with images", "with drawings", "with pictures",
})


def _is_story_with_visuals(text: str) -> bool:
    """Return True when the user asks for a narrative/story AND wants visuals."""
    low = (text or "").lower()
    has_story = bool(_STORY_VISUAL_RE.search(text or ""))
    has_visuals = any(kw in low for kw in _STORY_IMAGE_KEYWORDS)
    return has_story and has_visuals


def _is_inline_composed_visual_request(text: str) -> bool:
    """
    True when the user asks for a substantive write-up and explicitly wants
    visuals embedded in that response (not as a separate trailing gallery).
    """
    t = (text or "").strip().lower()
    if not t:
        return False
    has_longform = bool(re.search(
        r"\b(essay|article|report|paper|story|narrative|write\s+about|"
        r"explain|guide|walk\s+me\s+through|breakdown|compare|overview)\b",
        t,
    ))
    has_visual_embed = bool(re.search(
        r"\b(include|with|add|embed)\b.{0,60}\b(images?|photos?|pictures?|"
        r"illustrations?|charts?|graphs?|diagrams?)\b",
        t,
    ))
    return has_longform and has_visual_embed


def _requested_visual_source_mode(text: str) -> str:
    """
    Return one of: "generated", "web", "both".
    """
    t = (text or "").lower()
    wants_web = bool(re.search(
        r"\b(online|web|internet|google|search)\b", t
    ))
    wants_generated = bool(re.search(
        r"\b(generated|generate|ai\s*generated|create|draw|illustrate|render)\b",
        t,
    ))
    if wants_web and wants_generated:
        return "both"
    if wants_web:
        return "web"
    return "generated"


def _build_story_sections(response: str, user_message: str) -> list[dict]:
    """
    Parse the LLM response into story sections, each with paragraph text and
    a visual prompt derived from that paragraph's actual content + any inline
    image marker description.

    Returns a list of:
      {"heading": str, "text": str, "image_prompt": str, "visual_type": str}
    """
    import json as _json
    from gaaia.server.routers.document import (
        _parse_markdown_to_structure,
        _wants_drawings,
        _DOC_ART_STYLES,
    )

    vary = _wants_drawings(user_message)
    content = _parse_markdown_to_structure(
        response, "story",
        with_image_prompts=True,  # kept for forward compat
        vary_art_styles=vary,
    )

    _STYLE_NAMES = ["image", "sketch", "watercolor", "concept_art", "oil_painting", "image"]

    sections = []
    for idx, sec in enumerate(content.get("sections", [])):
        paragraphs = sec.get("paragraphs", [])
        heading    = sec.get("heading", "").strip()

        # Skip sections that have no actual paragraph text (they're artifact flushes
        # from standalone [Image N:] markers — those images are already captured in
        # the preceding section with text).
        paragraph_text = "\n\n".join(p for p in paragraphs if p.strip())
        if not paragraph_text:
            continue

        image_prompt   = sec.get("image_prompt", "").strip()

        # Enrich an existing image_prompt with paragraph context if it's very short
        if image_prompt and paragraph_text and len(image_prompt) < 60:
            # Inject heading + first sentence of paragraph for better accuracy
            first_sentence = paragraph_text.split(".")[0].strip()[:80]
            if first_sentence and first_sentence.lower() not in image_prompt.lower():
                image_prompt = f"{image_prompt}, depicting {first_sentence}"

        # If no image_prompt was extracted, derive a rich one from the paragraph text
        if not image_prompt and paragraph_text:
            # Build a descriptive prompt: heading (if any) + first 20 words of paragraph
            base = heading if heading else ""
            para_words = paragraph_text.split()
            # Take up to 20 words from the paragraph for richer context
            context = " ".join(para_words[:20])
            if base:
                subject = f"{base} — {context}"
            else:
                subject = context
            style_sfx = ", cinematic lighting, highly detailed, vibrant colors, 8k ultra HD"
            image_prompt = subject + style_sfx

        # Determine visual_type from the prompt style suffix
        visual_type = "image"
        if vary:
            visual_type = _STYLE_NAMES[idx % len(_STYLE_NAMES)]
        low_p = image_prompt.lower()
        if any(k in low_p for k in ("sketch", "linework", "pencil", "charcoal")):
            visual_type = "sketch"
        elif any(k in low_p for k in ("watercolor", "watercolour")):
            visual_type = "watercolor"
        elif any(k in low_p for k in ("oil painting", "oil on canvas")):
            visual_type = "oil_painting"
        elif any(k in low_p for k in ("concept art", "artstation")):
            visual_type = "concept_art"
        elif any(k in low_p for k in ("pixel art", "8-bit")):
            visual_type = "pixel_art"

        sections.append({
            "heading":      heading,
            "text":         paragraph_text,
            "image_prompt": image_prompt,
            "visual_type":  visual_type,
        })

    return sections


# ── Chart / graph generation intent detection ────────────────────────────────

_CHART_GEN_KEYWORDS = frozenset({
    "bar chart", "pie chart", "line chart", "line graph", "area chart",
    "scatter plot", "scatter chart", "scatter graph",
    "histogram", "chart", "graph", "plot", "data visualization",
    "visualize this", "visualise this", "visualize the data", "visualise the data",
    # NOTE: "timeline" is intentionally excluded — it routes to Mermaid instead
})

_CHART_GEN_RE = re.compile(
    r"\b(generate|create|make|draw|plot|show|build|produce|display|visualize|visualise)\b"
    r".{0,60}"
    r"\b(chart|graph|plot|histogram|diagram|visualization|bar chart|pie chart|line chart"
    r"|line graph|scatter|area chart)\b",
    re.IGNORECASE,
)

_MERMAID_DIAGRAM_RE = re.compile(
    r"\b(flowchart|flow chart|flow diagram|sequence diagram|entity.relationship|er diagram"
    r"|class diagram|state diagram|gantt chart|mind map|architecture diagram"
    r"|timelines?|time.?lines?|chronolog(?:y|ies)?|milestone(?:s)?|chronolog\w*"
    r"|create.*diagram|draw.*diagram|make.*diagram|generate.*diagram"
    r"|create.*timelines?|show.*timelines?|make.*timelines?|generate.*timelines?)",
    re.IGNORECASE,
)


def _is_chart_request(text: str) -> bool:
    low = (text or "").lower()
    if any(kw in low for kw in _CHART_GEN_KEYWORDS):
        return True
    return bool(_CHART_GEN_RE.search(text or ""))


def _is_mermaid_request(text: str) -> bool:
    return bool(_MERMAID_DIAGRAM_RE.search(text or ""))


_CHART_JSON_RE = re.compile(
    r"```(?:json|chart)?\s*\n(\{[^`]+?\})\s*\n```",
    re.DOTALL | re.IGNORECASE,
)


def _extract_chart_spec(response: str) -> dict | None:
    """
    Extract the first JSON block from the LLM response that looks like a chart spec.
    Returns None if no valid chart spec is found.
    """
    import json as _json
    for m in _CHART_JSON_RE.finditer(response or ""):
        try:
            obj = _json.loads(m.group(1))
            # Must have a type and either datasets, rows, events, or labels
            if obj.get("type") and (
                obj.get("datasets") or obj.get("rows")
                or obj.get("events") or obj.get("labels")
            ):
                return obj
        except Exception:
            continue
    return None


# ── Document generation intent detection ─────────────────────────────────────

_DOC_FORMAT_SIGNALS: list[tuple[str, list[str]]] = [
    ("xlsx", [
        "excel", "spreadsheet", "xlsx", "xls",
        "create a table", "make a table", "budget spreadsheet",
        "budget tracker", "expense tracker", "income tracker",
    ]),
    ("csv", [
        "csv file", "csv data", "comma separated", "export as csv",
        "save as csv", "export data as csv",
    ]),
    ("pptx", [
        "presentation", "powerpoint", "pptx", "slides", "slide deck",
        "create a deck", "make a deck", "create slides", "make slides",
    ]),
    ("pdf", [
        "pdf", "export as pdf", "generate a pdf", "create a pdf",
        "save as pdf", "pdf version", "pdf document",
    ]),
    ("txt", [
        "text file", "txt file", "plain text", "save as txt",
        "write to a file",
    ]),
    # docx is the fallback for all other document keywords
    ("docx", [
        "word document", "word doc", "word file", "docx", "doc file",
        "create a document", "make a document", "write a document",
        "create a report", "make a report", "write a report",
        "write a letter", "write a proposal", "write an essay as a file",
        "write a contract", "create a contract",
        "in word", "as word", "export as word", "save as word",
        "generate a word", "create a word",
    ]),
]

# Extra DOCX patterns for natural-language phrasings the signal list can't cover,
# e.g. "put it in a word and a pdf", "a word and pdf", "pdf and word".
_DOCX_FLEXIBLE_RE = re.compile(
    r"\b("
    r"word\s+(?:doc(?:ument)?|file|format|version)\b|"     # "word doc", "word document"
    r"(?:in|as|make|create|generate|save|export)\s+(?:a\s+)?word\b|"  # "in a word", "as word", etc.
    r"(?:a|the)\s+word\s+(?:and|or|&)\b|"                 # "a word and", "the word or"
    r"\bword\s+(?:and|or|&)\s+(?:a\s+)?(?:pdf|pptx|xlsx|csv|txt)\b|"  # "word and pdf"
    r"\b(?:pdf|pptx|xlsx|csv|txt)\s+(?:and|or|&)\s+(?:a\s+)?word\b"   # "pdf and word"
    r")",
    re.IGNORECASE,
)


def _detect_doc_formats(text: str) -> list[str]:
    """Return all detected document format keys (may be multiple, e.g. ['docx', 'pdf'])."""
    lowered = (text or "").lower().strip()
    found: list[str] = []
    for fmt, signals in _DOC_FORMAT_SIGNALS:
        if any(sig in lowered for sig in signals):
            found.append(fmt)
    # Also check the flexible DOCX regex for natural-language variations
    # e.g. "put it in a word and a pdf" → "a word and" matches → add docx
    if "docx" not in found and _DOCX_FLEXIBLE_RE.search(text or ""):
        found.append("docx")
    return found


def _detect_doc_format(text: str) -> str | None:
    """Return the first detected document format key, or None (legacy single-format helper)."""
    results = _detect_doc_formats(text)
    return results[0] if results else None


# ── Camera visual signals ─────────────────────────────────────────────────────

_CHAT_VISUAL_SIGNALS = (
    "camera",
    "what do you see",
    "look at",
    "watch me",
    "look at this",
    "what am i",
    "which finger",
    "which fingers",
    "how many fingers",
    "finger",
    "fingers",
    "hand",
    "hands",
    "right hand",
    "left hand",
    "what am i holding",
    "holding up",
    "background",
    "behind me",
    "gesture",
    "gestures",
    "wave",
    "waving",
    "point",
    "pointing",
)


def _should_include_camera_context(text: str) -> bool:
    lowered = (text or "").lower().strip()
    if not lowered:
        return False
    if any(signal in lowered for signal in _CHAT_VISUAL_SIGNALS):
        return True
    return bool(re.search(r"\b(can|do)\s+you\s+see\b", lowered))


@router.post("")
async def chat(
    request: Request,
    orchestrator: Orchestrator = Depends(get_orchestrator),
    memory: MemoryStore = Depends(get_memory),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """
    Stream a GAAIA response as Server-Sent Events.

    Each event is a JSON object:
      {"type": "text",  "content": "<chunk>"}
      {"type": "done",  "content": ""}
      {"type": "error", "content": "<message>"}

    Client example:
      const es = new EventSource('/chat');   // or use fetch + ReadableStream
    """
    body = await _parse_chat_request(request)
    try:
        session_id = memory.get_or_create_session(body.session_id, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    # Detect generation intents early — used to emit SSE side-car events after the LLM response
    _music_prompt: str | None = (
        _extract_music_prompt(body.message) if _is_music_gen_request(body.message) else None
    )
    _is_essay_mode: bool = _is_document_essay_with_embedded_images_request(body.message)
    _wants_story: bool = (
        _is_story_with_visuals(body.message)
        or _is_inline_composed_visual_request(body.message)
    )
    _visual_source_mode: str = _requested_visual_source_mode(body.message)
    _requested_inline_image_count: int = (
        _extract_image_count(body.message)
        if _MULTI_IMAGE_COUNT_RE.search(body.message or "")
        else 0
    )

    # Standalone image generation is only for direct image requests.
    # Composed long-form requests (story/essay with visuals) are planned inline.
    _raw_image_prompt: str | None = (
        _extract_image_prompt(body.message)
        if (_is_image_gen_request(body.message) and not (_is_essay_mode or _wants_story))
        else None
    )
    _image_count: int = _extract_image_count(body.message) if _raw_image_prompt else 1

    # ── Kick off LLM-based prompt enhancement in parallel with LLM response ──
    # Load recent history + a quick web image lookup *before* the enhancer so the
    # model knows "her" / "same as before" and typical online depictions, without
    # random name substitution. (Adds ~0–3s web fetch; runs alongside the main path.)
    _enhance_task: asyncio.Task[str] | None = None
    if _raw_image_prompt:
        _ollama_host = getattr(orchestrator, "_host", "http://localhost:11434")
        _fast_model  = getattr(orchestrator, "_fast_model",  "llama3.2:3b")
        _mini_model  = getattr(orchestrator, "_mini_model",  "phi:2.7b")
        _recent_for_enh = memory.get_recent_turns(session_id, 16, user_id=current_user.id)
        _q_web = _normalize_web_image_query(_raw_image_prompt) or _raw_image_prompt
        _web_hint = await _web_titles_for_image_enhance(_q_web)
        if not _web_hint and (body.message or "").strip():
            _q2 = _normalize_web_image_query(
                re.sub(r"\[LIVE WEATHER DATA[^\]]*\]", "", body.message, flags=re.I)
            ) or (body.message or "").strip()[:200]
            if _q2 and _q2.lower() != _q_web.lower():
                _web_hint = await _web_titles_for_image_enhance(_q2, count=3)
        _enhance_payload = _build_enhance_image_user_payload(
            _raw_image_prompt,
            body.message or "",
            list(_recent_for_enh),
            web_titles=_web_hint,
        )
        _enhance_task = asyncio.create_task(
            enhance_image_prompt(
                _enhance_payload,
                ollama_host=_ollama_host,
                fast_model=_fast_model,
                mini_model=_mini_model,
                timeout=18.0,
            )
        )
        print(
            f"[Chat] Image prompt enhancer started (context+web) raw='{_raw_image_prompt[:50]}...'",
            flush=True,
        )
    _image_prompt: str | None = _raw_image_prompt  # will be replaced when task resolves

    # ── Variation / consistency detection ────────────────────────────────────
    # Check recent history for a prior image gen request in this session
    _prior_image_turns = memory.get_recent_turns(session_id, 6, user_id=current_user.id) if _raw_image_prompt else []
    _had_prior_image_gen = any(
        turn.get("role") == "user" and _is_image_gen_request(turn.get("content", ""))
        for turn in _prior_image_turns
    )
    _is_variation: bool = _raw_image_prompt is not None and _is_image_variation_request(
        body.message, _had_prior_image_gen
    )

    # Kick off web reference image fetch in parallel (only for fresh, non-variation generations)
    _ref_image_task: asyncio.Task[str] | None = None
    if _raw_image_prompt and not _is_variation:
        _ref_q = _normalize_web_image_query(_raw_image_prompt) or _raw_image_prompt
        _ref_image_task = asyncio.create_task(_first_web_image_url(_ref_q))

    _wants_chart:        bool = _is_chart_request(body.message)
    _wants_mermaid:      bool = _is_mermaid_request(body.message)
    _web_intent_msg:     str = _user_message_for_web_results(body.message)
    # Don't show a web-results panel when the request is for AI image generation —
    # the SD pipeline handles that path. Also suppress when it's an illustrated essay
    # (images appear inline via story_sections instead).
    _wants_web_results:  bool = (
        not bool(_raw_image_prompt)
        and (
            _is_visual_show_request(_web_intent_msg)
            or _is_web_image_browse_request(_web_intent_msg)
        )
    )
    _wants_weather:      bool = _is_weather_widget_request(body.message)
    _wants_clock:        bool = _is_clock_widget_request(body.message)
    # Multiple formats can be requested in one message (e.g. "word doc and a pdf")
    _doc_formats: list[str] = _detect_doc_formats(body.message)
    # Essay + images mode: suppress text streaming so the user sees the completed
    # illustrated essay (with images inline) all at once instead of text first then images.

    # ── Weather: start fetching immediately so data is ready before the LLM ────
    # Priority: explicit place in message → app user_home_location → memory "I live in…" →
    # IP from location_context → "" (wttr uses request IP — often wrong for hosted backends / VPNs).
    _weather_task: asyncio.Task[dict | None] | None = None
    _weather_prefetched: dict | None = None  # set inside run_orchestrator before LLM
    if _wants_weather:
        _loc_ctx = getattr(request.app.state, "location_context", "") or ""
        _settings = getattr(request.app.state, "settings", None)
        _app_home = (getattr(_settings, "app", None) or {}).get("user_home_location", "")
        if not isinstance(_app_home, str):
            _app_home = str(_app_home or "")
        _explicit = _extract_weather_location(body.message)
        _w_loc = resolve_weather_location(
            _explicit,
            memory_location_fact=memory.get_fact_value("location", ""),
            app_home_location=(_app_home or "").strip(),
            server_location_context=_loc_ctx,
        )
        _weather_task = asyncio.create_task(fetch_weather_data(_w_loc))
        print(
            f"[Chat] Weather fetch started for "
            f"'{(_w_loc or 'ip-auto')}' (explicit='{_explicit or '-'}' app_home={bool(_app_home.strip())})",
            flush=True,
        )

    queue: asyncio.Queue[dict | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def emit_status(content: str) -> None:
        loop.call_soon_threadsafe(
            queue.put_nowait,
            {"type": "status", "content": content},
        )

    emit_status("Reading your request")

    attachment_context = ""
    if body.attachments:
        emit_status("Analyzing attachments")
        if any(att.content_type.startswith("image/") for att in body.attachments):
            emit_status("Preparing image analysis")
        attachment_context = await build_attachment_context(
            body.attachments,
            request.app.state.settings,
            progress_callback=lambda step: emit_status(_attachment_status_label(step)),
        )

    user_message = _compose_user_message(body.message, attachment_context)

    # ── Colour / colorize follow-up: detect "give her colour", "add color", etc. ──
    # When the user asks to colourize something without naming a new subject,
    # look back through recent history to find the last image request and reuse
    # its subject as the base for a colourful re-generation.
    if _raw_image_prompt is None and _IMAGE_COLOUR_FOLLOWUP_RE.search(body.message or ""):
        recent_turns = memory.get_recent_turns(session_id, 10, user_id=current_user.id)
        _last_img_subject: str = ""
        for turn in reversed(recent_turns):
            if turn.get("role") == "user":
                msg_text = turn.get("content", "")
                if _is_image_gen_request(msg_text):
                    _last_img_subject = msg_text.strip()
                    break
        if _last_img_subject:
            _raw_image_prompt = f"colorful, vibrant, fully colored: {_last_img_subject}"
            _image_prompt = _raw_image_prompt
            _ollama_host = getattr(orchestrator, "_host", "http://localhost:11434")
            _fast_model  = getattr(orchestrator, "_fast_model",  "llama3.2:3b")
            _mini_model  = getattr(orchestrator, "_mini_model",  "phi:2.7b")
            _q_col = _normalize_web_image_query(_last_img_subject) or _last_img_subject
            _web_col = await _web_titles_for_image_enhance(_q_col, count=3)
            _col_payload = _build_enhance_image_user_payload(
                _raw_image_prompt,
                body.message or "",
                list(recent_turns),
                web_titles=_web_col,
            )
            _enhance_task = asyncio.create_task(
                enhance_image_prompt(
                    _col_payload,
                    ollama_host=_ollama_host,
                    fast_model=_fast_model,
                    mini_model=_mini_model,
                    timeout=18.0,
                )
            )
            print(
                f"[Chat] Colour follow-up detected — reusing subject: '{_last_img_subject[:60]}'",
                flush=True,
            )

    wants_camera_context = _should_include_camera_context(body.message)
    live_prefix = get_live_prefix_for_prompt(session_id, "") if wants_camera_context else ""
    if live_prefix:
        user_message = f"{live_prefix}\n\n{user_message}"

    emit_status("Preparing response plan")

    # ── Stats tracking ────────────────────────────────────────────────────────
    _req_start = stats_tracker.request_started(
        model=body.model_key or "auto",
        routed_via="pending",
    )
    _total_chars = 0
    _response_parts: list[str] = []   # accumulate full assistant response for doc generation
    _stream_aborted = False            # set when we detect a corrupt/echo response mid-stream
    # Once the model emits the first text token, the heartbeat must stop pinging
    # "Composing response" (otherwise the UI looks like a second re-compose).
    _stream_has_content = threading.Event()

    def on_chunk(chunk: str) -> None:
        nonlocal _total_chars, _stream_aborted
        # Essay+images: we buffer the LLM in memory and do not stream tokens; if we
        # set _stream_has_content on the first token, the heartbeat stops while the
        # model is still writing — nothing enters the SSE queue for minutes → idle
        # timeout. Only mark "has streamed" once we are past essay mode.
        if chunk and not _stream_has_content.is_set() and not _is_essay_mode:
            _stream_has_content.set()
        _total_chars += len(chunk)
        _response_parts.append(chunk)
        stats_tracker.token_generated(_req_start, len(chunk))

        # Real-time corruption / refusal / image-tutorial detection
        if not _stream_aborted and _total_chars >= 64:
            accumulated = "".join(_response_parts)
            is_corrupt = _is_echo_corrupt(accumulated)
            is_refusal = bool(
                (_image_prompt or _raw_image_prompt)
                and _IMAGE_REFUSAL_RE.search(accumulated)
            )
            is_img_tutorial = bool(
                (_image_prompt or _raw_image_prompt)
                and _looks_like_image_tutorial(accumulated)
            )
            if is_corrupt or is_refusal or is_img_tutorial:
                _stream_aborted = True
                if is_refusal:
                    label = "image refusal"
                elif is_img_tutorial:
                    label = "image tutorial (guide instead of generate)"
                else:
                    label = "system-prompt echo"
                print(
                    f"[Chat] ⚠ {label} detected mid-stream — suppressing output",
                    flush=True,
                )
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {"type": "replace", "content": ""},
                )
                return  # stop forwarding this and subsequent chunks

        if _stream_aborted:
            return  # suppress remaining chunks

        # In essay+images mode we hold the text until images are ready, then release
        # everything at once via story_sections.  Text is still accumulated in
        # _response_parts for doc generation; we just don't stream it to the UI yet.
        if _is_essay_mode:
            return

        loop.call_soon_threadsafe(
            queue.put_nowait,
            {"type": "text", "content": chunk},
        )

    async def run_orchestrator() -> None:
        # _image_prompt / _weather_prefetched live in the enclosing scope;
        # we reassign both here so we must declare them nonlocal.
        nonlocal _image_prompt, _weather_prefetched

        # ── Pre-fetch weather data before the LLM so the response is accurate ──
        # The task was started the moment the request arrived.  We give it up to
        # 5 s to resolve; if it does we inject a one-line weather summary into the
        # user message so the LLM can quote real temperatures/conditions.
        # The widget SSE event is sent after the LLM regardless.
        effective_user_message = user_message
        # Nudge the model: image gen is automatic — users want the picture, not a how-to.
        if _raw_image_prompt:
            effective_user_message += (
                "\n\n[Internal — image generation: The app renders this image automatically. "
                "Reply with exactly ONE natural, friendly sentence mentioning what you are "
                "generating (e.g. 'Sure! Generating your image of X now ✨'). "
                "Never say just 'Confirmed' or 'Sure' alone. "
                "Do not give step-by-step instructions, software tutorials, or guides.]"
            )
        # Nudge the model: document generation is automatic — do NOT tell the user how to
        # manually save/export files. Just write the requested content.
        if _doc_formats:
            fmt_list = " and ".join(f.upper() for f in _doc_formats)
            effective_user_message += (
                f"\n\n[DOCUMENT FORMATTING — follow exactly]\n"
                f"The {fmt_list} file(s) are created automatically. Write ONLY the document content.\n"
                f"FORMAT RULES:\n"
                f"Line 1 must be: # <descriptive title here>  (example: # The Rise of Artificial Intelligence)\n"
                f"Each major section must start with: ## <Section Name>\n"
                f"Write at least 5 sections. Each section needs 3-5 full paragraphs of polished prose.\n"
                f"END RULE: Your response ends with the last paragraph of content. "
                f"Do not write any closing line, marker, label, or bracket after the final paragraph. "
                f"The words 'End of Essay', 'End of Document', '[Internal', or any similar marker must NEVER appear."
            )
        if _wants_weather and _weather_task is not None:
            try:
                emit_status("Fetching live weather data")
                _weather_prefetched = await asyncio.wait_for(
                    asyncio.shield(_weather_task), timeout=5.0
                )
                if _weather_prefetched:
                    w = _weather_prefetched
                    _forecast_str = ", ".join(
                        f"{'Today' if i == 0 else ('Tomorrow' if i == 1 else 'Day 3')}: "
                        f"{d['desc']} {d['max_f']}°F/{d['min_f']}°F "
                        f"({d['max_c']}°C/{d['min_c']}°C)"
                        for i, d in enumerate(w.get("forecast", [])[:3])
                    )
                    effective_user_message += (
                        f"\n\n[LIVE WEATHER DATA — {w['location']}: "
                        f"{w['desc']}, {w['temp_f']}°F ({w['temp_c']}°C), "
                        f"feels like {w['feels_like_f']}°F ({w['feels_like_c']}°C), "
                        f"humidity {w['humidity']}%, "
                        f"wind {w['wind_mph']} mph ({w['wind_kmph']} km/h) {w['wind_dir']}, "
                        f"UV index {w['uv_index']}. "
                        f"3-day forecast: {_forecast_str}. "
                        f"Use this REAL live data in your response — do NOT say "
                        f"'weather not available' or similar.]"
                    )
                    print(
                        f"[Chat] Weather injected: {w['location']} "
                        f"{w['temp_f']}°F {w['desc']}",
                        flush=True,
                    )
            except (asyncio.TimeoutError, Exception) as _we:
                print(f"[Chat] Weather pre-fetch failed/timed out: {_we}", flush=True)

        # ── Heartbeat — prevents the SSE idle timer from firing on slow starts ──
        # When the user sends a long message (e.g. quoting a previous response),
        # Ollama can take 30–90+ seconds to warm up and produce the first token.
        # During that window NOTHING enters the SSE queue, so the 90 s idle timer
        # fires a false "took too long" error.  This task keeps the queue alive by
        # emitting a "Composing response" status ping every 12s **only while no
        # text has been streamed yet**; as soon as `on_chunk` sets
        # `_stream_has_content`, we stop pinging (otherwise the UI repeats
        # "Composing response" over an already visible answer).
        _heartbeat_done = asyncio.Event()

        async def _heartbeat() -> None:
            _step = 0
            _labels = (
                [
                    "Writing your illustrated essay…",
                    "Still writing the essay…",
                    "Almost finished writing…",
                ]
                if _is_essay_mode
                else ["Composing response", "Still working on it…", "Composing response"]
            )
            try:
                while not _heartbeat_done.is_set() and not _stream_has_content.is_set():
                    # 12s window, in 1s steps so we exit within ~1s of first token
                    for _ in range(12):
                        if _heartbeat_done.is_set() or _stream_has_content.is_set():
                            return
                        await asyncio.sleep(1.0)
                    if not _heartbeat_done.is_set() and not _stream_has_content.is_set():
                        emit_status(_labels[_step % len(_labels)])
                        _step += 1
            except asyncio.CancelledError:
                pass

        _heartbeat_task = asyncio.create_task(_heartbeat())

        if _is_essay_mode:
            emit_status("Writing your illustrated essay…")

        try:
            await orchestrator.run(
                user_message=effective_user_message,
                session_id=session_id,
                stream_callback=on_chunk,
                status_callback=emit_status,
                mode=body.mode,
                model_key=body.model_key,
            )
            stats_tracker.request_finished(_req_start, _total_chars)
            full_response = "".join(_response_parts).strip()

            # ── Post-stream response cleaning ──────────────────────────────────

            # 0) Entire output is system-meta (matched late) — user already saw the junk
            if not _stream_aborted and _is_echo_corrupt(full_response):
                print(
                    "[Chat] ⚠ system-prompt echo in full output — replacing",
                    flush=True,
                )
                if _image_prompt or _raw_image_prompt:
                    full_response = "On it! Generating your image now ✨"
                elif _music_prompt:
                    full_response = "Generating the track for you now 🎵"
                elif _doc_formats:
                    full_response = "Preparing your document now 📄"
                else:
                    full_response = _echo_fallback_reply(body.message)
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {"type": "replace", "content": full_response},
                )

            # 1) Mid-stream abort (echo / image refusal) — only partial text reached the client
            elif _stream_aborted:
                if _image_prompt or _raw_image_prompt:
                    full_response = "On it! Generating your image now ✨"
                elif _music_prompt:
                    full_response = "Generating the track for you now 🎵"
                elif _doc_formats:
                    full_response = "Preparing your document now 📄"
                else:
                    full_response = _echo_fallback_reply(body.message)
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {"type": "replace", "content": full_response},
                )

            # 2) Detect LLM image refusal (e.g. "I'm not able to generate visual content")
            #    even though the image pipeline is live.  Replace the whole response with
            #    a short clean confirmation — the image_generate event fires regardless.
            elif (_image_prompt or _raw_image_prompt) and _IMAGE_REFUSAL_RE.search(full_response):
                subject_hint = (
                    (_image_prompt or _raw_image_prompt or "").split(",")[0].strip()
                )
                full_response = f"On it! Generating your image of {subject_hint} now ✨"
                print(
                    "[Chat] ⚠ LLM image refusal detected — replaced with clean confirmation",
                    flush=True,
                )
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {"type": "replace", "content": full_response},
                )

            # 3) Strip SD-prompt leakage and [Image: …] markers from chat text.
            #    This runs for ALL non-aborted, non-refusal responses because the
            #    LLM sometimes adds [Image: …] markers or SD descriptions even for
            #    non-generation replies.
            else:
                cleaned = _strip_response_artifacts(full_response)
                if cleaned != full_response:
                    print(
                        "[Chat] Response artifacts stripped (SD leakage / image markers)",
                        flush=True,
                    )
                    full_response = cleaned
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        {"type": "replace", "content": full_response},
                    )

                # 3b) Image request answered with a how-to / tutorial — replace; pipeline still runs.
                if (_image_prompt or _raw_image_prompt) and _looks_like_image_tutorial(
                    full_response
                ):
                    subj = (
                        (_image_prompt or _raw_image_prompt or "")
                        .split(",")[0]
                        .strip()[:60]
                    )
                    full_response = (
                        f"Sure! Generating your image of {subj} now ✨"
                        if subj
                        else "Sure! Generating your image now ✨"
                    )
                    print(
                        "[Chat] ⚠ Image tutorial-style reply replaced with short confirmation",
                        flush=True,
                    )
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        {"type": "replace", "content": full_response},
                    )

                # 3c) Image gen — terse/generic one-word confirmation ("Confirmed.", "Sure.", etc.)
                #     Replace with a descriptive one-liner that mentions what's being generated.
                elif (_image_prompt or _raw_image_prompt) and _TERSE_CONFIRM_RE.match(
                    full_response.strip()
                ):
                    subj = (
                        (_image_prompt or _raw_image_prompt or "")
                        .split(",")[0]
                        .strip()[:80]
                    )
                    full_response = (
                        f"Sure! Generating your image of {subj} now ✨"
                        if subj
                        else "Sure! Generating your image now ✨"
                    )
                    print(
                        "[Chat] ⚠ Terse image confirmation replaced with descriptive one-liner",
                        flush=True,
                    )
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        {"type": "replace", "content": full_response},
                    )

                # 3d) Doc gen — strip trailing instructions / end markers UNCONDITIONALLY.
                if _doc_formats:
                    stripped_doc = _strip_response_artifacts(
                        _DOC_INSTRUCTIONS_TAIL_RE.sub("", full_response)
                    ).strip()
                    full_response = stripped_doc
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        {"type": "replace", "content": full_response},
                    )

            # Emit generation side-car events AFTER the text response
            if _music_prompt:
                # Refine the music prompt using what GAAIA actually described in her
                # response — this ensures the audio matches the text (e.g. tempo,
                # instruments, mood) rather than just the raw user request.
                refined_music_prompt = _refine_music_prompt_from_response(
                    full_response, _music_prompt
                )
                print(
                    f"[Chat] Music prompt: '{_music_prompt}' → refined: '{refined_music_prompt}'",
                    flush=True,
                )
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {"type": "music_generate", "content": refined_music_prompt},
                )
            if _image_prompt:
                # Resolve the LLM-enhanced prompt (runs concurrently with LLM response)
                if _enhance_task is not None:
                    try:
                        _image_prompt = await asyncio.wait_for(
                            asyncio.shield(_enhance_task), timeout=6.0
                        )
                        print(
                            f"[Chat] Enhanced prompt: '{_image_prompt[:80]}...'",
                            flush=True,
                        )
                    except (asyncio.TimeoutError, Exception) as _e:
                        print(
                            f"[Chat] Prompt enhancer timed out/failed ({_e}), "
                            "using raw prompt",
                            flush=True,
                        )
                        _image_prompt = _raw_image_prompt or _image_prompt

                # Resolve web reference image URL (if we started a fetch earlier)
                _ref_image_url: str = ""
                if _ref_image_task is not None:
                    try:
                        _ref_image_url = await asyncio.wait_for(
                            asyncio.shield(_ref_image_task), timeout=3.0
                        )
                        if _ref_image_url:
                            print(f"[Chat] Web ref image: {_ref_image_url[:80]}", flush=True)
                    except (asyncio.TimeoutError, Exception):
                        pass

                # Emit one event per requested image; each carries the same enhanced prompt.
                for _img_idx in range(_image_count):
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        {
                            "type": "image_generate",
                            "content": _image_prompt,
                            "index": _img_idx,
                            "total": _image_count,
                            "session_id": session_id,
                            "is_variation": _is_variation,
                            "ref_image_url": _ref_image_url,
                        },
                    )

            if _wants_story:
                _story_sections = _build_story_sections(full_response, body.message)
                if _requested_inline_image_count > 0 and len(_story_sections) > 0:
                    # Keep the full written story, but cap visual slots to what the
                    # user asked for (e.g., "include 4 images").
                    for i, sec in enumerate(_story_sections):
                        if i >= _requested_inline_image_count:
                            sec["image_prompt"] = ""
                            sec.pop("imageUrl", None)

                # Enhance each section's image prompt with the LLM enhancer (concurrently)
                if _story_sections:
                    _ollama_host = getattr(orchestrator, "_host", "http://localhost:11434")
                    _fast_model  = getattr(orchestrator, "_fast_model",  "llama3.2:3b")
                    _mini_model  = getattr(orchestrator, "_mini_model",  "phi:2.7b")
                    _section_tasks = [
                        asyncio.create_task(
                            enhance_image_prompt(
                                s["image_prompt"],
                                ollama_host=_ollama_host,
                                fast_model=_fast_model,
                                mini_model=_mini_model,
                                timeout=10.0,
                            )
                        ) if s.get("image_prompt") else None
                        for s in _story_sections
                    ]
                    try:
                        enhanced_prompts = await asyncio.gather(
                            *[t for t in _section_tasks if t is not None],
                            return_exceptions=True,
                        )
                        ep_iter = iter(enhanced_prompts)
                        for sec, task in zip(_story_sections, _section_tasks):
                            if task is not None:
                                result = next(ep_iter)
                                if isinstance(result, str) and len(result) > 10:
                                    sec["image_prompt"] = result
                    except Exception as _se:
                        print(f"[Chat] Story prompt enhancement failed: {_se}", flush=True)

                    # When the user asks for online/web images (or both), fetch real
                    # web images per section and attach them inline.
                    if _visual_source_mode in {"web", "both"}:
                        emit_status("Finding web images…")

                        async def _fetch_story_web(section: dict) -> str:
                            heading = str(section.get("heading") or "").strip()
                            text = str(section.get("text") or "").strip()
                            lead = " ".join(text.split()[:14])
                            query = _normalize_web_image_query(
                                f"{heading} {lead}".strip()
                            )
                            if not query:
                                return ""
                            try:
                                imgs = await asyncio.wait_for(fetch_web_images(query, count=4), timeout=10.0)
                            except Exception:
                                return ""
                            for img in imgs:
                                url = img.get("image_url") or img.get("thumbnail_url")
                                if isinstance(url, str) and url.startswith("http"):
                                    return url
                            return ""

                        _urls = await asyncio.gather(
                            *[_fetch_story_web(s) for s in _story_sections],
                            return_exceptions=True,
                        )
                        for sec, u in zip(_story_sections, _urls):
                            if isinstance(u, str) and u:
                                sec["imageUrl"] = u
                                if _visual_source_mode == "web":
                                    sec["image_prompt"] = ""

                if len(_story_sections) >= 2:
                    import json as _story_json
                    print(
                        f"[Chat] Story mode: {len(_story_sections)} sections with visuals",
                        flush=True,
                    )
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        {
                            "type": "story_sections",
                            "content": _story_json.dumps(_story_sections),
                        },
                    )

            if _wants_chart:
                # Try to extract a chart spec from the LLM's JSON block
                _chart_spec = _extract_chart_spec(full_response)
                if _chart_spec:
                    import json as _json
                    print(
                        f"[Chat] Chart detected: type={_chart_spec.get('type')} "
                        f"labels={len(_chart_spec.get('labels') or _chart_spec.get('rows', []))}",
                        flush=True,
                    )
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        {"type": "chart_generate", "content": _json.dumps(_chart_spec)},
                    )
                else:
                    print("[Chat] Chart request but no JSON spec found in response", flush=True)

            if _wants_mermaid:
                # Extract ```mermaid code block from the response
                _mermaid_m = re.search(
                    r"```mermaid\s*\n(.*?)```", full_response, re.DOTALL | re.IGNORECASE
                )
                if _mermaid_m:
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        {"type": "mermaid_generate", "content": _mermaid_m.group(1).strip()},
                    )

            # ── Essay + Document + Images pipeline ───────────────────────────────
            # 1. Parse the essay into sections
            # 2. GAIA Core (middle model) reads the essay and picks section indices +
            #    search_query (web) or image_prompt (SD)
            # 3. Fetch web images / queue SD prompts only for those sections
            # 4. Emit story_sections + optional web_image_urls aligned by section index
            _doc_essay_web_images: list[str] = []  # parallel to sections; "" = no image
            import json as _ej
            if _is_essay_mode:
                _essay_topic = _extract_essay_topic(body.message) or "South Beach Miami"
                _essay_sections = _parse_essay_for_sections(full_response)
                _use_web_imgs = _wants_web_for_doc_images(body.message)
                _nc_host = getattr(orchestrator, "_host", "http://localhost:11434")
                _nc_model = getattr(orchestrator, "_core_model", "mistral:7b")
                _sd_by_index: dict[int, str] = {}
                _doc_essay_web_images = [""] * len(_essay_sections)

                async def _fetch_one_web(q: str) -> str:
                    q = (q or "").strip()[:120]
                    if len(q) < 3:
                        return ""
                    try:
                        imgs = await asyncio.wait_for(
                            fetch_web_images(q, count=4),
                            timeout=10.0,
                        )
                        for img in imgs:
                            url = img.get("image_url") or img.get("thumbnail_url")
                            if url and str(url).startswith("http"):
                                return url
                    except Exception:
                        pass
                    return ""

                async def _fallback_fetch_all_web() -> list[str]:
                    """Heuristic one image per section when GAIA Core placement fails."""

                    async def _one(h: str, topic: str) -> str:
                        skip = {"introduction", "conclusion", "summary", "overview"}
                        q = (
                            f"{h} {topic}"
                            if h.lower() not in skip
                            else topic
                        )
                        return await _fetch_one_web(q)

                    _coros = [_one(s["heading"], _essay_topic) for s in _essay_sections]
                    _got = await asyncio.gather(*_coros, return_exceptions=True)
                    return [u if isinstance(u, str) else "" for u in _got]

                if _essay_sections:
                    emit_status("GAIA Core: choosing where to place images…")
                    _placements = await _llm_essay_image_placements(
                        full_response,
                        [s["heading"] for s in _essay_sections],
                        _use_web_imgs,
                        _nc_host,
                        _nc_model,
                        max_images=(_requested_inline_image_count or None),
                    )
                    print(
                        f"[Chat] GAIA Core essay placements: {len(_placements)} "
                        f"(web={_use_web_imgs})",
                        flush=True,
                    )

                    emit_status(
                        "Finding web images…"
                        if _use_web_imgs
                        else "Preparing illustrations…"
                    )

                    nsec = len(_essay_sections)
                    if _placements:
                        if _use_web_imgs:
                            _idx_sq: list[tuple[int, str]] = []
                            for p in _placements:
                                si = int(p.get("section_index", -1))
                                if 0 <= si < nsec:
                                    _idx_sq.append((si, (p.get("search_query") or "").strip()))
                            if _idx_sq:
                                _urls = await asyncio.gather(
                                    *[_fetch_one_web(q) for _, q in _idx_sq],
                                    return_exceptions=True,
                                )
                                for (si, _), u in zip(_idx_sq, _urls):
                                    if isinstance(u, str) and u:
                                        _doc_essay_web_images[si] = u
                        else:
                            for p in _placements:
                                si = int(p.get("section_index", -1))
                                if 0 <= si < nsec and (p.get("image_prompt") or "").strip():
                                    _sd_by_index[si] = p["image_prompt"].strip()[:800]
                    else:
                        # GAIA Core returned nothing usable — fall back to heuristics
                        if _use_web_imgs:
                            _doc_essay_web_images = await _fallback_fetch_all_web()
                        else:
                            for i in range(nsec):
                                _sd_by_index[i] = (
                                    f"{_essay_sections[i]['heading']}, {_essay_topic}, "
                                    "editorial photography, vibrant, 8k"
                                )

                    if _use_web_imgs and _placements and not any(_doc_essay_web_images):
                        _doc_essay_web_images = await _fallback_fetch_all_web()

                # Build story_sections for inline chat display
                _story_for_essay: list[dict] = []
                for _si, _sec in enumerate(_essay_sections):
                    _web_url = (
                        _doc_essay_web_images[_si]
                        if _si < len(_doc_essay_web_images)
                        else ""
                    )
                    _sd_prompt = _sd_by_index.get(_si, "")
                    _item: dict = {
                        "heading": _sec["heading"],
                        "text": _sec["text"],
                        "image_prompt": (
                            ""
                            if _web_url
                            else (
                                _sd_prompt
                                if _sd_prompt
                                else ""
                            )
                        ),
                        "visual_type": "image",
                    }
                    if _web_url:
                        _item["imageUrl"] = _web_url
                    _story_for_essay.append(_item)

                if _story_for_essay:
                    emit_status("Assembling your illustrated essay…")
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        {"type": "story_sections", "content": _ej.dumps(_story_for_essay)},
                    )
                    print(
                        f"[Chat] Essay story_sections emitted: {len(_story_for_essay)} sections",
                        flush=True,
                    )
                    # First user-visible payload for essay — stop the "writing essay" heartbeat.
                    _stream_has_content.set()

            if _is_essay_mode and not _stream_has_content.is_set():
                # Parsed no sections or nothing to show; still stop the heartbeat.
                _stream_has_content.set()

            for _doc_fmt in _doc_formats:
                _doc_evt: dict = {
                    "type": "doc_generate",
                    # content = "format|user_message"
                    # response = actual assistant reply — document router uses this
                    #   directly instead of calling LLM again, so the doc matches the chat.
                    "content": f"{_doc_fmt}|{body.message.strip()}",
                    "response": full_response,
                }
                if _doc_essay_web_images and any(
                    u and str(u).strip().lower().startswith("http")
                    for u in _doc_essay_web_images
                ):
                    # Index-aligned with parsed doc sections (sparse OK — empty = no image)
                    _doc_evt["web_images"] = _ej.dumps(_doc_essay_web_images)
                loop.call_soon_threadsafe(queue.put_nowait, _doc_evt)

            # ── Weather widget ───────────────────────────────────────────────────
            # _weather_prefetched was already resolved before the LLM ran.
            # If it arrived in time, we inject it now; otherwise try one last
            # short wait in case the pre-fetch timed out and is still pending.
            if _wants_weather:
                import json as _wj
                _w_data = _weather_prefetched
                if _w_data is None and _weather_task is not None:
                    try:
                        _w_data = await asyncio.wait_for(
                            asyncio.shield(_weather_task), timeout=4.0
                        )
                    except (asyncio.TimeoutError, Exception) as _we:
                        print(f"[Chat] Weather last-chance fetch failed: {_we}", flush=True)
                if _w_data:
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        {"type": "weather_data", "content": _wj.dumps(_w_data)},
                    )
                    print(
                        f"[Chat] Weather widget sent for {_w_data.get('location')}",
                        flush=True,
                    )
                else:
                    print("[Chat] Weather data unavailable — widget skipped", flush=True)

            # ── Live clock widget ────────────────────────────────────────────────
            if _wants_clock:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {"type": "clock_widget", "content": ""},
                )

            # ── Web results (images + articles) for visual show requests ────────
            # Skip generic web_results panel for essay+images requests — images are
            # already shown inline via story_sections and embedded in the document.
            if _wants_web_results and not _is_essay_mode and not _wants_story:
                import json as _wj
                _raw_vq = _build_visual_query(_web_intent_msg, full_response)
                _visual_query = _normalize_web_image_query(_raw_vq) or _raw_vq
                if _visual_query:
                    print(
                        f"[Chat] Visual search query: '{_visual_query[:80]}' "
                        f"(raw: '{_raw_vq[:60]}')",
                        flush=True,
                    )
                    try:
                        _images_task = asyncio.create_task(
                            fetch_web_images(_visual_query, count=6)
                        )
                        _articles_task = asyncio.create_task(
                            fetch_article_snippets(_visual_query, count=4)
                        )
                        # Hard cap: never let the combined web-results fetch
                        # block the stream for more than 12 seconds.
                        _web_imgs, _web_arts = await asyncio.wait_for(
                            asyncio.gather(
                                _images_task, _articles_task,
                                return_exceptions=True,
                            ),
                            timeout=12.0,
                        )
                        _web_imgs   = _web_imgs   if isinstance(_web_imgs,   list) else []
                        _web_arts   = _web_arts   if isinstance(_web_arts,   list) else []
                        # Second pass: some providers return nothing for awkward phrasing.
                        if not _web_imgs and not _web_arts and _visual_query != _raw_vq:
                            _web_imgs = await fetch_web_images(_raw_vq, count=6)
                            _web_imgs = _web_imgs if isinstance(_web_imgs, list) else []
                        if not _web_imgs and not _web_arts:
                            _alt = f"{_visual_query} photo"
                            _web_imgs = await fetch_web_images(_alt, count=6)
                            _web_imgs = _web_imgs if isinstance(_web_imgs, list) else []
                        # Always emit so the client can show the panel + fallback links
                        # even when previews are empty (network / rate limits).
                        loop.call_soon_threadsafe(
                            queue.put_nowait,
                            {
                                "type": "web_results",
                                "content": _wj.dumps({
                                    "query":    _visual_query,
                                    "images":   _web_imgs,
                                    "articles": _web_arts,
                                }),
                            },
                        )
                        print(
                            f"[Chat] Web results: {len(_web_imgs)} images, "
                            f"{len(_web_arts)} articles",
                            flush=True,
                        )
                    except Exception as _we:
                        print(f"[Chat] Web results fetch failed: {_we}", flush=True)
        except Exception as exc:
            stats_tracker.request_finished(_req_start, _total_chars, error=True)
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"type": "error", "content": str(exc)},
            )
        finally:
            # Stop the heartbeat as soon as the orchestrator exits (success or error).
            _heartbeat_done.set()
            _heartbeat_task.cancel()
            loop.call_soon_threadsafe(queue.put_nowait, None)

    asyncio.create_task(run_orchestrator())

    async def stream():
        # Global watchdog: if the backend produces no output for 120 seconds
        # (after the heartbeat pings every 12 s the real ceiling is model hang),
        # or the total stream exceeds 300 seconds, abort with a friendly error.
        # Essay+web-image pipelines can run several minutes; keepalive is via
        # heartbeat (pre-stream) + status events; this is a last-resort ceiling.
        _IDLE_TIMEOUT = 180.0
        _TOTAL_TIMEOUT = 600.0
        import time as _time
        _stream_start = _time.monotonic()
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=_IDLE_TIMEOUT)
            except asyncio.TimeoutError:
                yield _sse({
                    "type": "replace",
                    "content": "Sorry, this is taking too long to process. The request may be too complex or the model is overloaded. Please try again.",
                })
                yield _sse({"type": "done", "content": ""})
                break
            if item is None:
                yield _sse({"type": "done", "content": ""})
                break
            yield _sse(item)
            if _time.monotonic() - _stream_start > _TOTAL_TIMEOUT:
                yield _sse({"type": "done", "content": ""})
                break

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Session-Id": session_id,
        },
    )


async def _parse_chat_request(request: Request) -> ChatRequest:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid chat request body.") from exc

    raw_model_key = str(payload.get("model_key") or "").strip().lower()
    if raw_model_key in {"", "auto", "default", "basic", "swift"}:
        payload["model_key"] = None

    return ChatRequest.model_validate(payload)


def _compose_user_message(message: str, attachment_context: str) -> str:
    text = message.strip()
    if not attachment_context:
        return text

    attachment_block = (
        "Attached file context:\n"
        f"{attachment_context.strip()}"
    )
    if text:
        return f"{text}\n\n{attachment_block}"
    return f"Please review the attached files and images and summarize what you find.\n\n{attachment_block}"


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _attachment_status_label(raw_step: str) -> str:
    step = (raw_step or "").lower()
    if step.startswith("start "):
        return "Preparing image"
    if step.startswith("image prepared"):
        return "Image loaded"
    if "vision summary pass" in step:
        return "Understanding image contents"
    if "vision text pass" in step:
        return "Reading visible text (vision)"
    if "ocr pass" in step:
        return "Running OCR"
    if "ocr skipped" in step:
        return "OCR skipped"
    if "scoring and formatting" in step:
        return "Combining analysis results"
    if step.startswith("done in"):
        return "Image analysis complete"
    if "vision model unavailable" in step:
        return "Vision model not available"
    if "analysis failed" in step:
        return "Image analysis failed"
    # Non-image statuses are already human-readable (zip/text/pdf steps); keep them as-is.
    return raw_step or "Working"
