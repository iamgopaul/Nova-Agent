from __future__ import annotations

import re
from collections import Counter

from nova.memory.store import MemoryStore

# Common English stop-words we don't want in the vocabulary
_STOP = frozenset(
    "a an the is are was were be been being have has had do does did "
    "will would could should may might must shall can it its it's "
    "i me my we our you your he him his she her they them their "
    "this that these those what which who when where how why "
    "and or but not no yes so if then at in on of to for with "
    "about as by from up out into over after before just also "
    "there here some any all one two said like get go know think "
    "want need make see look tell said going got yeah okay".split()
)

# Min character length and frequency to include in the vocabulary
_MIN_WORD_LEN = 4
_MIN_FREQ = 2


def _extract_tokens(text: str) -> list[str]:
    """Pull meaningful words from a block of text."""
    words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9'\-]{2,}\b", text)
    return [w.lower() for w in words if w.lower() not in _STOP and len(w) >= _MIN_WORD_LEN]


def _extract_proper_nouns(text: str) -> list[str]:
    """Pull capitalised tokens (names, places, brands) from mid-sentence."""
    tokens = re.findall(r"(?<![.!?]\s)(?<!\n)\b([A-Z][a-z]{2,}(?:\s[A-Z][a-z]{2,})*)\b", text)
    return [t for t in tokens if t.lower() not in _STOP]


def build_whisper_prompt(memory: MemoryStore) -> str:
    """
    Build a personalised Whisper initial_prompt from stored facts and
    conversation history.  Updates after every turn so Whisper gets
    progressively better at recognising the user's vocabulary.
    """
    # ── User facts ────────────────────────────────────────────────────
    facts = {f["key"]: f["value"] for f in memory.get_facts()}
    display_name = facts.get("user_display_name", "").strip()
    legal_name = facts.get("user_name", "").strip()
    # How the user asked to be called beats full legal/enrolled name for STT biasing.
    name = display_name or legal_name
    role = facts.get("user_role", "")
    workplace = facts.get("workplace", "")
    prefs = facts.get("preference", "")

    # ── Vocabulary mined from all conversation history ────────────────
    freq: Counter = Counter()
    proper_freq: Counter = Counter()

    sessions = memory.list_sessions()
    for s in sessions[:30]:  # last 30 sessions is plenty
        turns = memory.get_recent_turns(s["id"], n=40)
        for t in turns:
            if t["role"] != "user":
                continue
            freq.update(_extract_tokens(t["content"]))
            for pn in _extract_proper_nouns(t["content"]):
                proper_freq[pn] += 1

    # Top frequent common words (min 2 occurrences)
    top_words = [w for w, c in freq.most_common(30) if c >= _MIN_FREQ]
    # All proper nouns seen more than once
    top_proper = [p for p, c in proper_freq.most_common(20) if c >= 1]

    # If we already know the user's name, suppress conflicting variants that
    # start with the same first name but differ from the confirmed full name.
    if name:
        canonical = " ".join(name.split()).strip().lower()
        first = canonical.split()[0] if canonical else ""
        if first:
            filtered: list[str] = []
            for token in top_proper:
                normalized = " ".join(token.split()).strip().lower()
                if normalized == canonical:
                    filtered.append(token)
                    continue
                if normalized.startswith(first + " "):
                    continue
                filtered.append(token)
            top_proper = filtered

    # ── Build prompt as a short vocabulary list, NOT as instructions ──────
    # Whisper uses initial_prompt as prior *transcription* context, so the
    # best format is a compact list of names/terms it should recognise, not
    # imperative sentences that it will hallucinate back verbatim.
    terms: list[str] = []

    if name:
        terms.append(name)
        if role:
            terms.append(role)
        if workplace:
            terms.append(workplace)

    # Add proper nouns the user has used before (capped to avoid length blowup)
    terms.extend(top_proper[:10])

    if not terms:
        return ""

    return ", ".join(terms) + "."


def compose_stt_prompt(
    base_prompt: str,
    accent_hint: str | None = None,
    custom_terms: list[str] | None = None,
) -> str:
    """
    Compose a short, factual Whisper initial_prompt.

    Whisper treats initial_prompt as prior transcription context — NOT as
    instructions.  Any imperative sentence (e.g. "If the speaker spells...")
    will be hallucinated verbatim when audio is short or quiet.  Keep this
    strictly factual: names, proper nouns, terms to recognise.
    """
    prompt = (base_prompt or "").strip()
    pieces: list[str] = [prompt] if prompt else []

    cleaned_terms = [t.strip() for t in (custom_terms or []) if str(t).strip()]
    if cleaned_terms:
        # List the terms as a comma-separated sequence so Whisper learns to
        # recognise the spelling/pronunciation, not an instruction to follow.
        pieces.append(", ".join(cleaned_terms) + ".")

    # accent_hint: intentionally omitted — Whisper cannot follow instructions;
    # language is set via the `language` parameter instead.

    prompt_text = " ".join(pieces).strip()
    if not prompt_text:
        # Minimal neutral seed — short enough to not bleed into transcription.
        prompt_text = "Josh Gopaul."

    # Cap to ~200 characters (≈ 50 tokens) to avoid hallucination of the prompt itself.
    if len(prompt_text) > 200:
        prompt_text = prompt_text[:200].rsplit(" ", 1)[0]

    return prompt_text


def refresh_stt_prompt(
    memory: MemoryStore,
    stt,
    custom_terms: list[str] | None = None,
) -> None:
    """Rebuild and inject a fresh vocabulary hint into a live WhisperSTT instance."""
    if stt is None:
        return
    base_prompt = build_whisper_prompt(memory)
    prompt = compose_stt_prompt(base_prompt, custom_terms=custom_terms)
    stt.set_initial_prompt(prompt)
