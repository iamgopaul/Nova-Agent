"""
Response acceleration caches (in-process, not durable across backend restarts).

* LLM cache: reuses the same assistant text for identical (model, messages) when
  the request is safe to replay (no live search, no tools, etc.).
* Search snippet cache: short TTL for identical web article-snippet fetches.
"""
from __future__ import annotations

import copy
import hashlib
import json
import threading
import time
from collections import OrderedDict
from typing import Any

from config.settings import Settings

# Search snippet cache: singleton, lazy-init from Settings
_s_snippet: Any = False
_s_lock = threading.Lock()


def looks_like_meta_instruction_waste(text: str) -> bool:
    """
    Heuristic: responses that re-hash system instructions or analyse "guidelines" as if the user
    pasted them — we should not cache or promote these. Keeps a bad one-off from replaying for 15 min.
    """
    t = (text or "").lower().strip()
    if len(t) < 100:
        return False
    needles = (
        "in this text, you",
        "in this text you've",
        "you've provided a detailed set of guidelines",
        "guidelines for an assistant named",
        "these instructions cover",
        "in summary, the guidelines",
        "the guidelines emphasize",
        "this detailed set of instructions",
        "as an ai assistant, your",
    )
    return any(n in t for n in needles) and (
        "guideline" in t
        or "instruction" in t
        or "rules for" in t
        or "operating mode" in t
    )


class LLMResponseCache:
    """Thread-safe hash-keyed text cache for Ollama chat (no tool rounds)."""

    def __init__(
        self,
        max_entries: int = 400,
        ttl: float = 900.0,
        max_value_chars: int = 120_000,
    ) -> None:
        self._max = max(1, int(max_entries))
        self._ttl = max(30.0, float(ttl))
        self._max_value_chars = int(max_value_chars)
        self._lock = threading.Lock()
        # key -> (expiry, text)
        self._data: OrderedDict[str, tuple[float, str]] = OrderedDict()

    @staticmethod
    def make_key(model: str, messages: list[dict[str, Any]]) -> str:
        h = hashlib.sha256()
        h.update((model or "").encode("utf-8"))
        h.update(b"\0")
        h.update(
            json.dumps(
                messages,
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8"),
        )
        return h.hexdigest()

    def get(self, model: str, messages: list[dict[str, Any]]) -> str | None:
        k = self.make_key(model, messages)
        now = time.time()
        with self._lock:
            if k not in self._data:
                return None
            exp, val = self._data[k]
            if exp <= now or len(val) > self._max_value_chars:
                del self._data[k]
                return None
            self._data.move_to_end(k)
            return val

    def set(self, model: str, messages: list[dict[str, Any]], text: str) -> None:
        if not text or len(text) > self._max_value_chars:
            return
        if looks_like_meta_instruction_waste(text):
            return
        k = self.make_key(model, messages)
        until = time.time() + self._ttl
        with self._lock:
            while len(self._data) >= self._max:
                self._data.popitem(last=False)
            self._data[k] = (until, text)
            self._data.move_to_end(k)


def build_llm_cache(settings: Settings) -> LLMResponseCache | None:
    cfg = settings.response_cache
    if not cfg or not bool(cfg.get("enabled", True)):
        return None
    llm = cfg.get("llm", {}) or {}
    return LLMResponseCache(
        max_entries=int(llm.get("max_entries", 400)),
        ttl=float(llm.get("ttl_seconds", 900)),
        max_value_chars=int(llm.get("max_response_chars", 120_000)),
    )


class TTLCache:
    """
    Thread-safe max-size + time-to-live cache for any JSON-style objects.
    Values for mutable types are deep-copied on get/set to avoid aliasing.
    """

    def __init__(self, max_entries: int, ttl: float) -> None:
        self._max = max(1, int(max_entries))
        self._ttl = max(1.0, float(ttl))
        self._lock = threading.Lock()
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        now = time.time()
        with self._lock:
            if key not in self._data:
                return None
            exp, val = self._data[key]
            if exp <= now:
                del self._data[key]
                return None
            self._data.move_to_end(key)
            if isinstance(val, (list, dict)):
                return copy.deepcopy(val)
            return val

    def set(self, key: str, value: Any) -> None:
        until = time.time() + self._ttl
        to_store = copy.deepcopy(value) if isinstance(value, (list, dict)) else value
        with self._lock:
            while len(self._data) >= self._max:
                self._data.popitem(last=False)
            self._data[key] = (until, to_store)
            self._data.move_to_end(key)


def get_search_snippet_cache() -> TTLCache | None:
    global _s_snippet
    with _s_lock:
        if _s_snippet is not False:
            return _s_snippet
        try:
            from config.settings import get_settings

            rc = get_settings().response_cache
        except Exception:
            _s_snippet = None
            return None
        if not rc or not bool(rc.get("enabled", True)):
            _s_snippet = None
            return None
        sn = rc.get("search_snippets", {}) or {}
        _s_snippet = TTLCache(
            max_entries=int(sn.get("max_entries", 200)),
            ttl=float(sn.get("ttl_seconds", 120)),
        )
        return _s_snippet
