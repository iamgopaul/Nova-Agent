from __future__ import annotations

import asyncio
import hashlib
import os
import re
from urllib.parse import urlparse, quote_plus

import feedparser
import httpx
from ddgs import DDGS

from nova.services.response_cache import get_search_snippet_cache
from nova.tools.base import BaseTool, ToolResult


# ── Brave Search API helper ───────────────────────────────────────────────────
# Primary search tier — typically responds in 200–600 ms with high-quality results.
# Requires BRAVE_SEARCH_API_KEY in the environment.  Falls back to DDG if absent.

_BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


def _brave_api_key() -> str:
    """
    Read the Brave API key lazily at call time so that .env loading order doesn't matter.
    Prefers the Settings object (pydantic-settings loads .env); falls back to os.environ.
    """
    try:
        from config.settings import get_settings
        key = get_settings().brave_search_api_key.strip()
        if key:
            return key
    except Exception:
        pass
    return os.getenv("BRAVE_SEARCH_API_KEY", "").strip()


async def _brave_search(query: str, count: int = 10, timeout: float = 5.0) -> list[dict]:
    """
    Call the Brave Search API.
    Returns results in the same shape as DDGS output: {title, body, href}.
    Returns [] if the key is missing, the request fails, or times out.
    """
    api_key = _brave_api_key()
    if not api_key:
        return []
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    }
    params = {"q": query, "count": count, "search_lang": "en", "safesearch": "moderate"}
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(_BRAVE_SEARCH_URL, headers=headers, params=params)
            if resp.status_code != 200:
                return []
            data = resp.json()
    except Exception:
        return []

    results: list[dict] = []
    for item in (data.get("web", {}).get("results") or []):
        title = (item.get("title") or "").strip()
        body  = (item.get("description") or "").strip()
        href  = (item.get("url") or "").strip()
        if not href:
            continue
        if not (title or body):
            continue
        results.append({"title": title, "body": body, "href": href})

    return results


# ── Fast DuckDuckGo instant-answer helper ─────────────────────────────────────
# Second-tier — hits DDG's JSON API directly (100–500 ms).
# Falls back to the full DDGS.text() scraper if the instant API has no data.

async def _ddg_instant(query: str, timeout: float = 4.0) -> list[dict]:
    """
    Call the DuckDuckGo Instant Answers API.
    Returns a list of result dicts compatible with DDGS.text() output
    (keys: title, body, href).  Returns [] on timeout or error.
    """
    url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1&skip_disambig=1"
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "Nova-AI/1.0"})
            if resp.status_code != 200:
                return []
            data = resp.json()
    except Exception:
        return []

    results: list[dict] = []

    # Primary abstract (Wikipedia-style answer)
    abstract = (data.get("AbstractText") or "").strip()
    if abstract:
        results.append({
            "title": data.get("Heading") or query,
            "body":  abstract,
            "href":  data.get("AbstractURL") or data.get("AbstractSource") or "",
        })

    # Definition
    definition = (data.get("Definition") or "").strip()
    if definition:
        results.append({
            "title": f"Definition: {query}",
            "body":  definition,
            "href":  data.get("DefinitionURL") or "",
        })

    # Infobox rows (e.g. "Prime Minister: Keith Rowley")
    infobox = data.get("Infobox") or {}
    for item in (infobox.get("content") or [])[:6]:
        label = (item.get("label") or "").strip()
        value = (item.get("value") or "").strip()
        if label and value:
            results.append({
                "title": label,
                "body":  value,
                "href":  data.get("AbstractURL") or "",
            })

    # Related topic blurbs (often Wikipedia links — keep; skip duckduckgo.com disambiguation stubs)
    for topic in _ddg_flatten_related_topic_nodes(data.get("RelatedTopics") or [])[:6]:
        text = (topic.get("Text") or "").strip()
        href = (topic.get("FirstURL") or topic.get("FirstUrl") or "").strip()
        if not text or not href:
            continue
        if _is_non_article_aggregator_url(href):
            continue
        results.append({"title": text[:100], "body": text, "href": href})

    return results

# ── Source credibility ────────────────────────────────────────────────────────

# Domains that carry editorial standards, fact-checking, or peer review.
# Results from these are labelled [trusted] and sorted first.
_TRUSTED_DOMAINS: frozenset[str] = frozenset({
    # Wire services / broadcasters
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "npr.org",
    "pbs.org", "theguardian.com", "bloomberg.com", "ft.com",
    "economist.com", "wsj.com", "nytimes.com", "washingtonpost.com",
    "theatlantic.com", "time.com", "forbes.com", "businessinsider.com",
    # Science / health
    "nature.com", "science.org", "nejm.org", "thelancet.com",
    "bmj.com", "who.int", "cdc.gov", "nih.gov", "pubmed.ncbi.nlm.nih.gov",
    "sciencedirect.com", "arxiv.org", "scholar.google.com",
    # Tech / factual reference
    "techcrunch.com", "wired.com", "arstechnica.com", "theverge.com",
    "wikipedia.org", "britannica.com", "snopes.com", "factcheck.org",
    "politifact.com", "fullfact.org", "gov.uk", "usa.gov",
    # Sports official/reference
    "espncricinfo.com", "icc-cricket.com", "cricbuzz.com",
})

# Domains with a documented history of publishing misinformation.
# Results from these are dropped entirely.
_BLOCKED_DOMAINS: frozenset[str] = frozenset({
    "naturalnews.com", "infowars.com", "breitbart.com", "beforeitsnews.com",
    "worldnewsdailyreport.com", "empirenews.net", "thelastlineofdefense.org",
    "abcnews.com.co", "cbsnews.com.co", "nbc.com.co",
    "theonion.com",  # satire — fine to read, not to cite as fact
    "clickhole.com", "babylonbee.com",  # satire
    "yournewswire.com", "newspunch.com", "neonnettle.com",
    "globalresearch.ca", "veteranstoday.com", "zerohedge.com",
    "activistpost.com", "collectiveevolution.com",
})


def _root_domain(url: str) -> str:
    """Extract the registrable domain from a URL."""
    try:
        host = urlparse(url).netloc.lower().lstrip("www.")
        return host
    except Exception:
        return ""


def _is_non_article_aggregator_url(url: str) -> bool:
    """DuckDuckGo /c/ topic pages look like real rows but are search stubs, not sources."""
    d = _root_domain(url)
    if d == "duck.co" or d.endswith(".duck.co"):
        return True
    if d == "duckduckgo.com" or d.endswith(".duckduckgo.com"):
        return True
    return False


def _ellipsize_for_preview(text: str, max_len: int = 220) -> str:
    """Cap snippet length on a word/sentence break so the UI does not end on 'Disney-ow'."""
    t = (text or "").replace("\n", " ").strip()
    if len(t) <= max_len:
        return t
    cut = t[: max_len + 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    body = (cut or t[:max_len]).rstrip(" ,;–-")
    if not body:
        body = t[:max_len]
    return f"{body}\u2026"


_QUERY_STOPWORDS: frozenset[str] = frozenset(
    "the and for with from about that this your have been are was not you all any will can "
    "how why who what when where which into tell this these those them out our over more some "
    "such than only each their most also good best very much many few more less here there "
    "able just like know does did done being been going".split()
)


def _significant_query_tokens(query: str) -> list[str]:
    return [
        t for t in re.findall(r"[a-z0-9]{3,}", (query or "").lower())
        if t not in _QUERY_STOPWORDS
    ]


def _article_snippet_matches_query(query: str, title: str, body: str) -> bool:
    """
    Reject disambiguation tangents (e.g. 'Hollywood Records artists') when the user
    asked about a specific person. Requires query terms to actually appear in the text.
    """
    terms = _significant_query_tokens(query)
    if not terms:
        return True
    text = f"{title} {body}".lower()
    n = len(terms)
    hits = sum(1 for t in terms if t in text)
    if n <= 2:
        return hits == n
    need = max(2, (2 * n + 2) // 3)  # ~2/3 of 3+ word queries
    return hits >= need


def _article_snippet_cache_key(query: str, count: int) -> str:
    """Stable key for snippet cache: query string + requested result count."""
    q = (query or "").strip()
    digest = hashlib.sha256(f"{q}\n{int(count)}".encode("utf-8")).hexdigest()
    return f"ns:article_snips:{digest}"


def _ddg_flatten_related_topic_nodes(raw) -> list[dict]:
    """DuckDuckGo RelatedTopics may be nested ['Topics' → …]. Return leaf {Text, FirstURL} dicts."""
    out: list[dict] = []
    if not raw:
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("Topics"), list):
            out.extend(_ddg_flatten_related_topic_nodes(item["Topics"]))
            continue
        text = (item.get("Text") or item.get("text") or "").strip()
        href = (item.get("FirstURL") or item.get("FirstUrl") or "").strip()
        if text and href:
            out.append({"Text": text, "FirstURL": href})
    return out


def _score_result(url: str) -> int:
    """Return 2 for trusted, 0 for neutral, -1 for blocked."""
    domain = _root_domain(url)
    if any(domain == d or domain.endswith("." + d) for d in _TRUSTED_DOMAINS):
        return 2
    if any(domain == d or domain.endswith("." + d) for d in _BLOCKED_DOMAINS):
        return -1
    return 0


def _label(score: int) -> str:
    return "[trusted source] " if score == 2 else ""


# ── Live weather helper ───────────────────────────────────────────────────────

async def fetch_weather_data(location: str, timeout: float = 7.0) -> dict | None:
    """
    Fetch current weather + 3-day forecast from wttr.in (no API key required).
    Returns a normalized flat dict on success, None on error.

    Dict keys:
      location, temp_c, temp_f, feels_like_c, feels_like_f,
      code (WMO weather code), desc, humidity, wind_mph, wind_kmph,
      wind_dir, uv_index, visibility_km, precip_mm, obs_time,
      forecast: [{date, max_c, min_c, max_f, min_f, code, desc}]  × 3
    """
    encoded = quote_plus(location.strip())
    url = f"https://wttr.in/{encoded}?format=j1"
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "Nova-AI/1.0"})
            if resp.status_code != 200:
                return None
            data = resp.json()
    except Exception:
        return None

    return _normalize_wttr(data)


def _normalize_wttr(data: dict) -> dict:
    cc   = (data.get("current_condition") or [{}])[0]
    area = (data.get("nearest_area")      or [{}])[0]
    raw  = data.get("weather") or []

    city   = (area.get("areaName") or [{}])[0].get("value", "")
    region = (area.get("region")   or [{}])[0].get("value", "")
    location = ", ".join(p for p in [city, region] if p)

    forecast: list[dict] = []
    for day in raw[:3]:
        hourly = day.get("hourly") or []
        # wttr.in hourly steps are at times 0/300/600/900/1200/1500/1800/2100
        # Find the entry closest to noon (time = 1200)
        midday = next(
            (h for h in hourly if str(h.get("time", "0")).zfill(4).startswith("12")),
            hourly[len(hourly) // 2] if hourly else {},
        )
        forecast.append({
            "date":  day.get("date", ""),
            "max_c": day.get("maxtempC", ""),
            "min_c": day.get("mintempC", ""),
            "max_f": day.get("maxtempF", ""),
            "min_f": day.get("mintempF", ""),
            "code":  str(midday.get("weatherCode") or "113"),
            "desc":  (midday.get("weatherDesc") or [{}])[0].get("value", ""),
        })

    return {
        "location":      location,
        "temp_c":        cc.get("temp_C", ""),
        "temp_f":        cc.get("temp_F", ""),
        "feels_like_c":  cc.get("FeelsLikeC", ""),
        "feels_like_f":  cc.get("FeelsLikeF", ""),
        "code":          str(cc.get("weatherCode", "113")),
        "desc":          (cc.get("weatherDesc") or [{}])[0].get("value", "Unknown"),
        "humidity":      cc.get("humidity", ""),
        "wind_mph":      cc.get("windspeedMiles", ""),
        "wind_kmph":     cc.get("windspeedKmph", ""),
        "wind_dir":      cc.get("winddir16Point", ""),
        "uv_index":      cc.get("uvIndex", ""),
        "visibility_km": cc.get("visibility", ""),
        "precip_mm":     cc.get("precipMM", "0.0"),
        "obs_time":      cc.get("localObsDateTime") or cc.get("observation_time", ""),
        "forecast":      forecast,
    }


# ── Image search helpers ──────────────────────────────────────────────────────

_BRAVE_IMAGE_SEARCH_URL = "https://api.search.brave.com/res/v1/images/search"


async def _brave_image_search(query: str, count: int = 6, timeout: float = 5.0) -> list[dict]:
    """
    Brave Image Search API.
    Returns list of {title, image_url, thumbnail_url, source_url}.
    """
    api_key = _brave_api_key()
    if not api_key:
        return []
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    }
    params = {"q": query, "count": count, "search_lang": "en", "safesearch": "moderate"}
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(_BRAVE_IMAGE_SEARCH_URL, headers=headers, params=params)
            if resp.status_code != 200:
                return []
            data = resp.json()
    except Exception:
        return []

    results: list[dict] = []
    for item in data.get("results", []):
        thumbnail = item.get("thumbnail") or {}
        props = item.get("properties") or {}
        img_url = props.get("url", "") or thumbnail.get("src", "")
        thumb_url = thumbnail.get("src", "") or img_url
        src_url = item.get("url", "")
        if img_url:
            results.append({
                "title": item.get("title", ""),
                "image_url": img_url,
                "thumbnail_url": thumb_url,
                "source_url": src_url,
            })
    return results


async def _ddg_image_search(query: str, max_results: int = 6) -> list[dict]:
    """DuckDuckGo image search fallback."""
    try:
        raw = await asyncio.wait_for(
            asyncio.to_thread(lambda: list(DDGS().images(query, max_results=max_results))),
            timeout=8.0,
        )
    except Exception:
        return []
    results: list[dict] = []
    for item in raw:
        img_url = item.get("image") or item.get("url", "")
        thumb_url = item.get("thumbnail") or img_url
        if img_url:
            results.append({
                "title": item.get("title", ""),
                "image_url": img_url,
                "thumbnail_url": thumb_url,
                "source_url": item.get("url", ""),
            })
    return results


async def fetch_web_images(query: str, count: int = 6) -> list[dict]:
    """
    Fetch web images for *query*. Tries Brave first, DDG as fallback.
    Returns list of {title, image_url, thumbnail_url, source_url}.
    """
    images = await _brave_image_search(query, count=count)
    if not images:
        images = await _ddg_image_search(query, max_results=count)
    return images


async def fetch_article_snippets(query: str, count: int = 4) -> list[dict]:
    """
    Fetch top article snippets for *query* using the same Brave/DDG pipeline
    as WebSearchTool but returned as plain dicts {title, description, url, source}.
    """
    snip_cache = get_search_snippet_cache()
    cache_key: str | None = None
    if snip_cache is not None:
        cache_key = _article_snippet_cache_key(query, count)
        hit = snip_cache.get(cache_key)
        if hit is not None:
            return hit

    raw: list[dict] = []
    if _brave_api_key():
        raw = await _brave_search(query, count=count * 2, timeout=5.0)
    if not raw:
        raw = await _ddg_instant(query, timeout=4.0)
    if not raw:
        try:
            raw = await asyncio.wait_for(
                asyncio.to_thread(lambda: list(DDGS().text(query, max_results=count * 2))),
                timeout=6.0,
            )
        except Exception:
            pass

    articles: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        url = (item.get("href") or item.get("url") or "").strip()
        if not url or url in seen:
            continue
        if _is_non_article_aggregator_url(url):
            continue
        title = (item.get("title") or "").strip()
        body = (item.get("body") or item.get("snippet") or "").strip()
        if not _article_snippet_matches_query(query, title, body):
            continue
        seen.add(url)
        domain = _root_domain(url)
        if _score_result(url) < 0:
            continue
        articles.append({
            "title": title,
            "description": _ellipsize_for_preview(body, 220),
            "url": url,
            "source": domain,
        })
        if len(articles) >= count:
            break
    if snip_cache is not None and cache_key is not None:
        snip_cache.set(cache_key, articles)
    return articles


# ── Tools ─────────────────────────────────────────────────────────────────────

class WebSearchTool(BaseTool):
    name = "search_web"
    description = (
        "Search the web for current events, facts, technical documentation, "
        "companies, prices, or anything requiring up-to-date information. "
        "Uses Brave Search when available (fast, high-quality); falls back to "
        "DuckDuckGo automatically. Results are ranked by source credibility — "
        "trusted outlets (Reuters, BBC, AP, Wikipedia, etc.) appear first. "
        "Known misinformation sites are filtered out automatically. "
        "Always cite sources in your answer and note when information comes "
        "from a single source that hasn't been corroborated."
    )

    def __init__(self, max_results: int = 8) -> None:
        self._max = max_results

    def schema(self) -> dict:
        return self._schema(
            {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query.",
                    }
                },
                "required": ["query"],
            }
        )

    async def run(self, query: str) -> ToolResult:
        raw: list[dict] = []

        # ── Tier 1: Brave Search API (fast, high-quality) ─────────────────────
        if _brave_api_key():
            raw = await _brave_search(query, count=self._max * 2, timeout=5.0)

        # ── Tier 2: DuckDuckGo Instant Answers API (100–500 ms) ───────────────
        if not raw:
            raw = await _ddg_instant(query, timeout=4.0)

        # ── Tier 3: DDGS full-text scraper (slowest, most comprehensive) ──────
        if not raw:
            try:
                raw = await asyncio.wait_for(
                    asyncio.to_thread(
                        lambda: list(DDGS().text(query, max_results=self._max * 2))
                    ),
                    timeout=8.0,
                )
            except asyncio.TimeoutError:
                return ToolResult(
                    content="Web search timed out — all search backends failed to respond.",
                    error="timeout",
                )
            except Exception as exc:
                return ToolResult(content=f"Search unavailable: {exc}", error=str(exc))

        if not raw:
            return ToolResult(content="No results found.")

        # Score and filter
        scored = []
        for r in raw:
            href = (r.get("href") or "").strip()
            if not href:
                continue
            score = _score_result(href)
            if score == -1:
                continue  # blocked — drop silently
            scored.append((score, r))

        # Trusted first, then neutral; cap at self._max
        scored.sort(key=lambda x: x[0], reverse=True)
        scored = scored[: self._max]

        if not scored:
            return ToolResult(content="No credible results found for that query.")

        parts = []
        for score, r in scored:
            title = r.get("title", "")
            body = r.get("body", "")
            href = r.get("href", "")
            label = _label(score)
            parts.append(f"{label}**{title}**\n{body}\nSource: {href}")

        return ToolResult(content="\n\n---\n\n".join(parts))


class GetNewsTool(BaseTool):
    name = "get_news"
    description = (
        "Fetch the latest news headlines from trusted RSS feeds "
        "(BBC, Reuters, AP, Hacker News). Optionally filter by topic keyword."
    )

    def __init__(self, feed_urls: list[str]) -> None:
        self._feeds = feed_urls

    def schema(self) -> dict:
        return self._schema(
            {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": (
                            "Optional topic filter, e.g. 'AI', 'markets', "
                            "'tech'. Leave empty for top headlines."
                        ),
                    }
                },
                "required": [],
            }
        )

    async def run(self, topic: str = "") -> ToolResult:
        headlines: list[str] = []
        topic_lower = topic.lower()

        for url in self._feeds[:4]:
            try:
                feed = await asyncio.wait_for(
                    asyncio.to_thread(feedparser.parse, url),
                    timeout=8.0,
                )
                source = feed.feed.get("title", url)
                for entry in feed.entries[:6]:
                    title = entry.get("title", "").strip()
                    summary = entry.get("summary", "").strip()[:200]
                    if topic_lower and (
                        topic_lower not in title.lower()
                        and topic_lower not in summary.lower()
                    ):
                        continue
                    headlines.append(f"[{source}] {title}\n{summary}")
            except Exception:
                continue

        if not headlines:
            msg = f"No headlines found" + (f" for '{topic}'" if topic else "") + "."
            return ToolResult(content=msg)

        return ToolResult(content="\n\n".join(headlines[:12]))
