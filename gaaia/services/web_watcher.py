"""
gaaia/services/web_watcher.py
────────────────────────────
Background service that periodically searches the web for user-defined watch
topics and stores the summarized results back in the watched_topics table.

Each user can configure their own topics (presets + custom) in Settings ▸ Web
Watch.  The scheduler runs every `interval_seconds` (default 1 hour) and
processes all currently-enabled topics across all accounts.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gaaia.memory.store import MemoryStore

_DIVIDER = "─" * 52


async def _ddg_search(query: str, max_results: int = 6) -> list[dict]:
    """Return DuckDuckGo results as {title, body, href} dicts."""
    try:
        try:
            from ddgs import DDGS  # new package name
        except ImportError:
            from duckduckgo_search import DDGS  # legacy fallback

        results: list[dict] = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                title = (r.get("title") or "").strip()
                body  = (r.get("body")  or "").strip()
                href  = (r.get("href")  or "").strip()
                if href and (title or body):
                    results.append({"title": title, "body": body[:300], "href": href})
        return results
    except Exception:
        return []


async def fetch_topic(memory: MemoryStore, topic: dict) -> None:
    """Fetch fresh web results for a single topic and persist them."""
    topic_id = topic["id"]
    label     = topic["label"]
    query     = topic["query"]
    start     = time.time()

    results = await _ddg_search(query)
    elapsed = time.time() - start

    result_payload = json.dumps(
        {
            "label": label,
            "query": query,
            "fetched_at": datetime.utcnow().isoformat(),
            "items": results,
        }
    )
    memory.update_watched_topic_result(topic_id, result_payload)
    print(
        f"[WebWatcher] '{label}' → {len(results)} results in {elapsed:.1f}s",
        flush=True,
    )


class WatcherScheduler:
    """
    Runs one fetch-pass per interval (default 60 min) across every enabled topic.
    Mirrors the KnowledgeFeedScheduler pattern so shutdown is clean.
    """

    def __init__(self, memory: MemoryStore, interval_seconds: int = 3600) -> None:
        self._memory   = memory
        self._interval = interval_seconds
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="gaaia-web-watcher")
        mins = self._interval // 60
        print(f"┌{_DIVIDER}┐", flush=True)
        print(f"│  🔎  Web Watcher — scheduler active                │", flush=True)
        print(
            f"│      Checking every {mins} min{'':>{max(0,35-len(str(mins)))}}│",
            flush=True,
        )
        print(f"└{_DIVIDER}┘", flush=True)

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            print("[WebWatcher] Scheduler stopped.", flush=True)

    async def _loop(self) -> None:
        # Brief startup delay so the main server is fully initialised
        await asyncio.sleep(15)
        while True:
            try:
                await self._run_all()
            except Exception as exc:
                print(f"[WebWatcher] Loop error: {exc}", flush=True)
            try:
                await asyncio.sleep(self._interval)
            except asyncio.CancelledError:
                break

    async def _run_all(self) -> None:
        topics = self._memory.list_all_enabled_topics()
        if not topics:
            return
        print(
            f"[WebWatcher] Refreshing {len(topics)} topic(s)…",
            flush=True,
        )
        for topic in topics:
            try:
                await fetch_topic(self._memory, topic)
            except Exception as exc:
                print(
                    f"[WebWatcher] Failed '{topic.get('label')}': {exc}",
                    flush=True,
                )
