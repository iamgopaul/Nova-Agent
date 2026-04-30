from __future__ import annotations

import re

from gaaia.memory.store import MemoryStore

# Patterns that indicate a stored message is a leaked format/system prompt rather
# than a real assistant reply.  These end up in gaaia.db when the old LLM-based
# /chat/format endpoint echoed its own instructions back as the response.
# We scrub them from both the LLM context window and the UI history feed.
_CORRUPT_PATTERNS: list[re.Pattern] = [
    # ── Old formatting-endpoint leakage ───────────────────────────────────────
    re.compile(r"Reproduce ALL text verbatim", re.IGNORECASE),
    re.compile(r"Return ONLY a single valid JSON object with keys .intro", re.IGNORECASE),
    re.compile(r"Never shorten,?\s+paraphrase,?\s+omit", re.IGNORECASE),
    re.compile(r"Here's the breakdown of your request", re.IGNORECASE),
    re.compile(r"'intro': ONLY an explicit conversational opening", re.IGNORECASE),
    re.compile(r'"outro" must ONLY contain text', re.IGNORECASE),

    # ── System-prompt / identity echo ─────────────────────────────────────────
    # Matches when the LLM echoes the system-prompt instructions as its reply
    re.compile(r"Here'?s? a detailed breakdown of the instruction", re.IGNORECASE),
    re.compile(r"GAAIA is presented as Isabella", re.IGNORECASE),
    re.compile(r"GAAIA Identity:.*GAAIA is presented as", re.IGNORECASE | re.DOTALL),
    re.compile(r"1\.\s+GAAIA Identity:", re.IGNORECASE),
    re.compile(r"Generative Capabilities:.*GAAIA can research", re.IGNORECASE | re.DOTALL),
    re.compile(r"You are GAIA.*You are not a chatbot.*You are an operator", re.IGNORECASE | re.DOTALL),
    re.compile(r"# GAIA — AI Chief of Staff", re.IGNORECASE),
    re.compile(r"# Generation Capabilities — ABSOLUTE OVERRIDE", re.IGNORECASE),
    re.compile(r"CRITICAL:.*LIVE generation pipelines", re.IGNORECASE),
    re.compile(r"When it comes to generating responses", re.IGNORECASE),
    re.compile(r"You are GAIA — a real person named Isabella", re.IGNORECASE),
    re.compile(r"1\.\s*Be conversational:?", re.IGNORECASE),
    re.compile(r"7\.\s*Stay updated:?", re.IGNORECASE),
    re.compile(
        r"It looks like you'?(?:ve| have) shared.+(?:guidelines|set of (?:the )?rules)",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(r"By following these rules, GAAIA aims to", re.IGNORECASE),
    re.compile(r"conversational AI named GAAIA.*guidelines|guidelines.*conversational AI named GAAIA", re.IGNORECASE | re.DOTALL),
]


def _is_corrupt(content: str) -> bool:
    """Return True if the message content looks like a leaked formatting prompt."""
    return any(p.search(content) for p in _CORRUPT_PATTERNS)


class ContextBuilder:
    def __init__(
        self,
        store: MemoryStore,
        max_turns: int = 20,
        max_facts: int = 10,
    ) -> None:
        self._store = store
        self._max_turns = max_turns
        self._max_facts = max_facts

    def build(self, session_id: str) -> dict:
        messages = self._store.get_recent_turns(session_id, self._max_turns)
        facts = self._store.get_facts()[: self._max_facts]
        primary_user = self._store.get_fact_value("user_name", "").strip()
        display_user = self._store.get_fact_value("user_display_name", "").strip()
        last_speaker = self._store.get_fact_value("last_speaker", "").strip()

        # Truncate long messages before injecting into the LLM context window.
        # Essays and research papers can be 8000+ words; including them in full
        # blows the context budget and crowds out recent turns the model needs.
        # The stored database content is never modified — only the LLM view is capped.
        _USER_LIMIT = 600    # internal-tag-heavy messages can be long; keep essential text
        _ASST_LIMIT = 1200   # enough for the model to reference what it said without overflow
        _TRUNCATE_SUFFIX = " […]"

        def _trim(role: str, content: str) -> str:
            limit = _USER_LIMIT if role == "user" else _ASST_LIMIT
            if len(content) <= limit:
                return content
            return content[:limit].rsplit(" ", 1)[0] + _TRUNCATE_SUFFIX

        chat_messages = [
            {"role": message["role"], "content": _trim(message["role"], message["content"])}
            for message in messages
            if not _is_corrupt(message.get("content", ""))
        ]

        injected_facts = ""
        context_lines: list[str] = []
        if display_user:
            context_lines.append(
                f"- preferred_address_name: {display_user} "
                f"(always use this exact form when addressing the user by name)"
            )
        if primary_user:
            if display_user:
                context_lines.append(
                    f"- enrolled_full_name: {primary_user} "
                    f"(internal identity only — do not use for greetings; use preferred_address_name)"
                )
            else:
                context_lines.append(f"- primary_user: {primary_user}")
        if last_speaker:
            context_lines.append(f"- last_speaker: {last_speaker}")
        if facts:
            lines = "\n".join(f"- {f['key']}: {f['value']}" for f in facts)
            context_lines.append(lines)

        if context_lines:
            injected_facts = f"\n\n## What I know about you\n" + "\n".join(context_lines)

        return {"messages": chat_messages, "injected_facts": injected_facts}
