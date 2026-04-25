"""
gaaia/services/knowledge_feed.py
────────────────────────────────
Background knowledge feed — automatically fetches trending news and web content
on a schedule and stores summaries in GAAIA's fact store, so she always has fresh
context even before the user asks.

This is NOT model training/fine-tuning.  It is RAG (Retrieval-Augmented Generation):
live web content is fetched, summarised, and injected into prompts at query time.
The model weights never change — but GAAIA's working knowledge is always current.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime

from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from gaaia.memory.store import MemoryStore

# ── RSS feeds to crawl ─────────────────────────────────────────────────────────
_DEFAULT_FEEDS: list[str] = [
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://feeds.reuters.com/reuters/topNews",
    "https://hnrss.org/frontpage",
    "https://rss.cnn.com/rss/money_news_international.rss",
    "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
]

# ── DuckDuckGo trending topics to auto-fetch ───────────────────────────────────
_TRENDING_QUERIES: list[str] = [
    "trending news today",
    "latest technology news 2026",
    "world news today",
    "sports news today",
]

_USER_AGENT = "GAAIA-KnowledgeFeed/1.0 (+https://gaaia.co)"


def _parse_rss_titles(xml: str, max_items: int = 8) -> list[str]:
    """Extract <title> text from RSS XML without an XML library dependency."""
    import re
    items: list[str] = []
    # Skip the channel-level <title>
    in_item = False
    for line in xml.splitlines():
        stripped = line.strip()
        if "<item>" in stripped:
            in_item = True
        if in_item:
            m = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", stripped)
            if m:
                title = m.group(1).strip()
                if title and len(title) > 8:
                    items.append(title)
                    if len(items) >= max_items:
                        break
    return items


async def _fetch_rss_headlines(feeds: list[str]) -> list[str]:
    """Fetch headlines from all configured RSS feeds concurrently."""
    headlines: list[str] = []
    async with httpx.AsyncClient(timeout=8.0, headers={"User-Agent": _USER_AGENT}) as client:
        tasks = [client.get(url) for url in feeds]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        for resp in responses:
            if isinstance(resp, Exception):
                continue
            try:
                headlines.extend(_parse_rss_titles(resp.text))
            except Exception:
                continue
    return headlines


async def _ddg_snippet_search(query: str, max_results: int = 5) -> list[str]:
    """Run a DuckDuckGo instant-answer search and return text snippets."""
    try:
        try:
            from ddgs import DDGS  # type: ignore  # new package name
        except ImportError:
            from duckduckgo_search import DDGS  # type: ignore  # legacy fallback
        results: list[str] = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                body = (r.get("body") or "").strip()
                title = (r.get("title") or "").strip()
                if body:
                    results.append(f"{title}: {body}" if title else body)
        return results
    except Exception:
        return []


def _build_knowledge_summary(
    headlines: list[str],
    snippets: list[str],
    fetched_at: str,
) -> str:
    """Combine headlines and snippets into a single knowledge block."""
    parts: list[str] = [f"[Auto-fetched knowledge — {fetched_at}]"]

    if headlines:
        parts.append("Current headlines: " + " | ".join(headlines[:12]))

    if snippets:
        parts.append("Web context: " + " | ".join(s[:200] for s in snippets[:6]))

    return "\n".join(parts)


_DIVIDER = "─" * 52

async def run_knowledge_fetch(memory: MemoryStore, feeds: list[str] | None = None) -> None:
    """
    Fetch fresh knowledge from the web and store it in GAAIA's fact store.
    Called by the scheduler on startup and every N minutes.
    """
    feeds = feeds or _DEFAULT_FEEDS
    fetched_at = datetime.now().strftime("%A %B %-d %Y, %-I:%M %p")
    start = time.time()

    print(f"\n┌{_DIVIDER}┐", flush=True)
    print(f"│  🌐  Knowledge Feed — starting fetch                │", flush=True)
    print(f"│      {fetched_at:<46}│", flush=True)
    print(f"└{_DIVIDER}┘", flush=True)

    headlines = await _fetch_rss_headlines(feeds)

    snippet_tasks = [_ddg_snippet_search(q, max_results=3) for q in _TRENDING_QUERIES]
    snippet_results = await asyncio.gather(*snippet_tasks, return_exceptions=True)
    snippets: list[str] = []
    for r in snippet_results:
        if isinstance(r, list):
            snippets.extend(r)

    elapsed = time.time() - start

    if not headlines and not snippets:
        print(f"┌{_DIVIDER}┐", flush=True)
        print(f"│  ⚠️   Knowledge Feed — no content (network down?)   │", flush=True)
        print(f"│      Elapsed: {elapsed:.1f}s{' ' * (44 - len(f'{elapsed:.1f}s'))}│", flush=True)
        print(f"└{_DIVIDER}┘\n", flush=True)
        return

    summary = _build_knowledge_summary(headlines, snippets, fetched_at)

    try:
        memory.save_fact("live_knowledge_feed", summary, source="auto-feed")
        memory.save_fact("live_knowledge_fetched_at", fetched_at, source="auto-feed")
        print(f"┌{_DIVIDER}┐", flush=True)
        print(f"│  ✅  Knowledge Feed — fetch complete                │", flush=True)
        print(f"│      {len(headlines)} headlines  •  {len(snippets)} web snippets  •  {elapsed:.1f}s{' ' * max(0, 27 - len(f'{len(headlines)} headlines  •  {len(snippets)} web snippets  •  {elapsed:.1f}s'))}│", flush=True)
        print(f"└{_DIVIDER}┘\n", flush=True)
    except Exception as exc:
        print(f"┌{_DIVIDER}┐", flush=True)
        print(f"│  ❌  Knowledge Feed — save failed: {str(exc)[:20]:<20}│", flush=True)
        print(f"└{_DIVIDER}┘\n", flush=True)


class KnowledgeFeedScheduler:
    """
    Runs run_knowledge_fetch() on startup and then every `interval_seconds`.
    Designed to run as a background asyncio task inside the FastAPI lifespan.
    """

    def __init__(
        self,
        memory: MemoryStore,
        interval_seconds: int = 3600,
        feeds: list[str] | None = None,
    ) -> None:
        self._memory = memory
        self._interval = interval_seconds
        self._feeds = feeds
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="gaaia-knowledge-feed")
        mins = self._interval // 60
        print(f"┌{_DIVIDER}┐", flush=True)
        print(f"│  🔄  Knowledge Feed — scheduler active             │", flush=True)
        print(f"│      Refreshing every {mins} min  •  first fetch starting now {'':>{max(0,16-len(str(mins)))}}│", flush=True)
        print(f"└{_DIVIDER}┘", flush=True)

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            print(f"\n[KnowledgeFeed] Scheduler stopped.", flush=True)

    async def _loop(self) -> None:
        # Fetch immediately on startup (don't wait an hour for the first update)
        try:
            await run_knowledge_fetch(self._memory, self._feeds)
        except Exception as exc:
            print(f"[KnowledgeFeed] Startup fetch error: {exc}", flush=True)

        while True:
            try:
                await asyncio.sleep(self._interval)
                await run_knowledge_fetch(self._memory, self._feeds)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                print(f"[KnowledgeFeed] Scheduled fetch error: {exc}", flush=True)
                # Back off slightly on error, then continue
                await asyncio.sleep(60)
