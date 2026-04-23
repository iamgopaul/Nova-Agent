from __future__ import annotations

import subprocess
import webbrowser

import requests

from nova.tools.base import BaseTool, ToolResult

_TMDB_BASE = "https://api.themoviedb.org/3"


# ── Apple Music ───────────────────────────────────────────────────────

def _applescript(script: str) -> tuple[int, str, str]:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


class PlayMusicTool(BaseTool):
    name = "play_music"
    description = (
        "Search and play a song, artist, or album in Apple Music. "
        "Searches the local library first, then Apple Music catalogue."
    )

    def schema(self) -> dict:
        return self._schema(
            {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Song title, artist, or album to play.",
                    }
                },
                "required": ["query"],
            }
        )

    async def run(self, query: str) -> ToolResult:
        script = f"""
tell application "Music"
    activate
    set searchResults to search first library playlist for "{query}"
    if searchResults is not {{}} then
        play first item of searchResults
        set t to first item of searchResults
        return (name of t) & " — " & (artist of t)
    else
        return "not_found"
    end if
end tell
"""
        code, out, err = _applescript(script)
        if code != 0:
            return ToolResult(content=f"Apple Music error: {err}", error=err)
        if out == "not_found":
            return ToolResult(content=f"No results for '{query}' in your library.")
        return ToolResult(content=f"Now playing: {out}", metadata={"track": out})


class PauseMusicTool(BaseTool):
    name = "pause_music"
    description = "Pause or resume Apple Music playback."

    def schema(self) -> dict:
        return self._schema(
            {"type": "object", "properties": {}, "required": []}
        )

    async def run(self) -> ToolResult:
        code, out, err = _applescript('tell application "Music" to playpause')
        if code != 0:
            return ToolResult(content=f"Error: {err}", error=err)
        return ToolResult(content="Playback toggled.")


class GetNowPlayingTool(BaseTool):
    name = "get_now_playing"
    description = "Get the currently playing track in Apple Music."

    def schema(self) -> dict:
        return self._schema(
            {"type": "object", "properties": {}, "required": []}
        )

    async def run(self) -> ToolResult:
        script = """
tell application "Music"
    if player state is playing then
        return (name of current track) & " — " & (artist of current track) ¬
            & " (" & (album of current track) & ")"
    else
        return "nothing_playing"
    end if
end tell
"""
        code, out, err = _applescript(script)
        if code != 0:
            return ToolResult(content=f"Error: {err}", error=err)
        if out == "nothing_playing":
            return ToolResult(content="Nothing is playing right now.")
        return ToolResult(content=f"Now playing: {out}", metadata={"track": out})


# ── YouTube ───────────────────────────────────────────────────────────

class PlayYouTubeTool(BaseTool):
    name = "play_youtube"
    description = (
        "Search YouTube for a video and open it in the default browser. "
        "Use for music videos, tutorials, trailers, or any YouTube content."
    )

    def schema(self) -> dict:
        return self._schema(
            {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query for YouTube.",
                    }
                },
                "required": ["query"],
            }
        )

    async def run(self, query: str) -> ToolResult:
        try:
            import yt_dlp

            opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
                "skip_download": True,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"ytsearch1:{query}", download=False)
                entries = (info or {}).get("entries", [])

            if not entries:
                return ToolResult(content="No YouTube results found.")

            video = entries[0]
            url   = video.get("url") or f"https://www.youtube.com/watch?v={video.get('id', '')}"
            title = video.get("title", query)

            subprocess.Popen(["open", url])
            return ToolResult(
                content=f"Opening: {title}",
                metadata={"url": url, "title": title},
            )

        except ImportError:
            # yt-dlp not available — fall back to browser search
            url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
            subprocess.Popen(["open", url])
            return ToolResult(content=f"Opened YouTube search for: {query}")

        except Exception as exc:
            return ToolResult(content=f"YouTube search failed: {exc}", error=str(exc))


# ── Movie / series finder ─────────────────────────────────────────────

class FindMovieTool(BaseTool):
    name = "find_movie"
    description = (
        "Find where to watch a movie or TV series. Returns streaming "
        "availability, ratings, and overview. Uses TMDB if an API key is "
        "configured, otherwise falls back to a web search."
    )

    def __init__(self, tmdb_api_key: str = "") -> None:
        self._key = tmdb_api_key

    def schema(self) -> dict:
        return self._schema(
            {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Movie or series title to look up.",
                    },
                    "media_type": {
                        "type": "string",
                        "description": "Type of media to search for.",
                        "enum": ["movie", "tv", "any"],
                    },
                },
                "required": ["title"],
            }
        )

    async def run(self, title: str, media_type: str = "any") -> ToolResult:
        if self._key:
            return self._tmdb_lookup(title, media_type)
        return self._ddg_fallback(title)

    def _tmdb_lookup(self, title: str, media_type: str) -> ToolResult:
        try:
            search_type = "multi" if media_type == "any" else media_type
            resp = requests.get(
                f"{_TMDB_BASE}/search/{search_type}",
                params={"api_key": self._key, "query": title},
                timeout=8,
            )
            results = resp.json().get("results", [])
            if not results:
                return ToolResult(content=f"No results found for '{title}'.")

            item    = results[0]
            kind    = item.get("media_type", media_type)
            name    = item.get("title") or item.get("name", title)
            year    = (item.get("release_date") or item.get("first_air_date") or "")[:4]
            rating  = item.get("vote_average", 0)
            overview = item.get("overview", "No overview available.")[:300]
            item_id  = item["id"]

            # Streaming providers
            provider_endpoint = "movie" if kind == "movie" else "tv"
            prov_resp = requests.get(
                f"{_TMDB_BASE}/{provider_endpoint}/{item_id}/watch/providers",
                params={"api_key": self._key},
                timeout=8,
            )
            providers = prov_resp.json().get("results", {})
            us = providers.get("US", {})
            flatrate = [p["provider_name"] for p in us.get("flatrate", [])]
            rent     = [p["provider_name"] for p in us.get("rent", [])]

            lines = [f"**{name}** ({year}) — {rating:.1f}/10"]
            lines.append(overview)
            if flatrate:
                lines.append(f"Stream on: {', '.join(flatrate)}")
            if rent:
                lines.append(f"Rent/buy on: {', '.join(rent)}")
            if not flatrate and not rent:
                lines.append("No streaming data available for your region.")

            return ToolResult(
                content="\n".join(lines),
                metadata={"id": item_id, "type": kind},
            )

        except Exception as exc:
            return self._ddg_fallback(title)

    def _ddg_fallback(self, title: str) -> ToolResult:
        try:
            try:
                from ddgs import DDGS  # type: ignore
            except ImportError:
                from duckduckgo_search import DDGS  # type: ignore
            query   = f"where to watch {title} streaming 2024 2025"
            results = list(DDGS().text(query, max_results=4))
            if not results:
                return ToolResult(content=f"No streaming info found for '{title}'.")
            parts = [
                f"**{r.get('title','')}**\n{r.get('body','')}"
                for r in results
            ]
            return ToolResult(content="\n\n".join(parts))
        except Exception as exc:
            return ToolResult(
                content=f"Search failed: {exc}", error=str(exc)
            )
