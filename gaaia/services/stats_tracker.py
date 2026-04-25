"""
Global stats tracker for GAAIA.

Tracks per-request metrics (model, tokens, speed, latency) and exposes
them for the /api/stats endpoint. Thread-safe; updated from the streaming
callback in the chat router.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class RequestStats:
    model: str = ""
    tokens_generated: int = 0
    elapsed_seconds: float = 0.0
    tokens_per_second: float = 0.0
    routed_via: str = ""          # e.g. "llm-router" | "keyword" | "direct"
    status: str = "idle"          # "idle" | "streaming" | "done" | "error"


_stats = RequestStats()
_lock = threading.Lock()


def request_started(model: str, routed_via: str = "") -> float:
    """Call when a request begins. Returns a monotonic start timestamp."""
    with _lock:
        _stats.model = model
        _stats.tokens_generated = 0
        _stats.elapsed_seconds = 0.0
        _stats.tokens_per_second = 0.0
        _stats.routed_via = routed_via
        _stats.status = "streaming"
    return time.monotonic()


def token_generated(start_time: float, char_count: int = 0) -> None:
    """
    Call each time a text chunk arrives from the model.
    `char_count` is the length of the chunk in characters; tokens are
    estimated at 1 token ≈ 4 characters (standard heuristic).
    """
    est_tokens = max(1, char_count // 4) if char_count else 1
    with _lock:
        _stats.tokens_generated += est_tokens
        elapsed = time.monotonic() - start_time
        _stats.elapsed_seconds = elapsed
        if elapsed > 0:
            _stats.tokens_per_second = round(_stats.tokens_generated / elapsed, 1)


def request_finished(start_time: float, total_chars: int, error: bool = False) -> None:
    """Call when a request completes (success or error)."""
    with _lock:
        elapsed = time.monotonic() - start_time
        _stats.elapsed_seconds = round(elapsed, 2)
        # If no tokens were counted (e.g. very short responses), estimate from chars
        if _stats.tokens_generated == 0 and total_chars:
            _stats.tokens_generated = max(1, total_chars // 4)
        if elapsed > 0:
            _stats.tokens_per_second = round(_stats.tokens_generated / elapsed, 1)
        _stats.status = "error" if error else "done"


def get_request_stats() -> RequestStats:
    with _lock:
        return RequestStats(
            model=_stats.model,
            tokens_generated=_stats.tokens_generated,
            elapsed_seconds=_stats.elapsed_seconds,
            tokens_per_second=_stats.tokens_per_second,
            routed_via=_stats.routed_via,
            status=_stats.status,
        )
