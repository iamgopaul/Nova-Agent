"""
Day 6 verification — Domain engines + bootstrap registration.

Usage:
  .venv/bin/python scripts/test_day6.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, ".")


def test_imports() -> None:
    print("── Import checks ─────────────────────────────────────────────")
    from nova.engines.communication import DraftEmailTool, DraftMessageTool
    print("  ✓ engines.communication")

    from nova.engines.media import (
        FindMovieTool, GetNowPlayingTool, PauseMusicTool,
        PlayMusicTool, PlayYouTubeTool,
    )
    print("  ✓ engines.media")

    from nova.engines.dev import (
        GitStatusTool, ListFilesTool, ReadFileTool, SearchCodeTool,
    )
    print("  ✓ engines.dev")

    from nova.bootstrap import build_registry
    from config.settings import get_settings
    settings = get_settings()
    registry = build_registry(settings)
    names = sorted(registry._tools.keys())  # type: ignore[attr-defined]
    print(f"  ✓ bootstrap registered {len(names)} tools:")
    for n in names:
        print(f"      • {n}")

    expected = {
        "search_web", "get_news", "take_screenshot",
        "write_note", "read_note", "list_notes",
        "get_clipboard", "set_clipboard",
        "draft_email", "draft_message",
        "play_music", "pause_music", "get_now_playing",
        "play_youtube", "find_movie",
        "read_file", "list_files", "git_status", "search_code",
    }
    missing = expected - set(names)
    assert not missing, f"Missing tools: {missing}"
    print(f"  ✓ all {len(expected)} expected tools present")


async def test_draft_message() -> None:
    print("\n── DraftMessageTool ──────────────────────────────────────────")
    from nova.engines.communication import DraftMessageTool
    tool = DraftMessageTool()
    result = await tool.run(
        recipient="Alice",
        context="Confirm tomorrow's 9 AM meeting",
        tone="professional",
    )
    print(f"  content: {result.content[:120]}")
    assert "Alice" in result.content
    print("  ✓ DraftMessageTool returned composed prompt")


async def test_read_file() -> None:
    print("\n── ReadFileTool ──────────────────────────────────────────────")
    from nova.engines.dev import ReadFileTool
    import os
    tool = ReadFileTool()
    # Read this script itself
    path = os.path.abspath(__file__)
    result = await tool.run(path=path)
    assert "test_read_file" in result.content
    print(f"  ✓ ReadFileTool read {len(result.content)} chars from {path}")


async def test_list_files() -> None:
    print("\n── ListFilesTool ─────────────────────────────────────────────")
    from nova.engines.dev import ListFilesTool
    tool = ListFilesTool()
    result = await tool.run(path=".", max_depth=2)
    assert "nova/" in result.content or "config" in result.content
    lines = result.content.splitlines()
    print(f"  ✓ ListFilesTool returned {len(lines)} lines")
    for line in lines[:8]:
        print(f"      {line}")


async def test_git_status() -> None:
    print("\n── GitStatusTool ─────────────────────────────────────────────")
    from nova.engines.dev import GitStatusTool
    tool = GitStatusTool()
    result = await tool.run(path=".")
    print(f"  content: {result.content[:200]}")
    # Either shows git output or "not a git repo" — both are valid
    print("  ✓ GitStatusTool completed")


async def test_search_code() -> None:
    print("\n── SearchCodeTool ────────────────────────────────────────────")
    from nova.engines.dev import SearchCodeTool
    tool = SearchCodeTool()
    result = await tool.run(pattern="BaseTool", path=".", file_type="py")
    print(f"  content preview: {result.content[:200]}")
    assert result.error is None
    print("  ✓ SearchCodeTool completed")


async def test_get_now_playing() -> None:
    print("\n── GetNowPlayingTool ─────────────────────────────────────────")
    from nova.engines.media import GetNowPlayingTool
    tool = GetNowPlayingTool()
    result = await tool.run()
    print(f"  content: {result.content}")
    print("  ✓ GetNowPlayingTool completed (Music may not be open — that's fine)")


async def test_find_movie_fallback() -> None:
    print("\n── FindMovieTool (DDG fallback) ──────────────────────────────")
    from nova.engines.media import FindMovieTool
    tool = FindMovieTool(tmdb_api_key="")  # force DDG fallback
    result = await tool.run(title="Inception")
    print(f"  content preview: {result.content[:200]}")
    print("  ✓ FindMovieTool completed")


async def main() -> None:
    test_imports()
    await test_draft_message()
    await test_read_file()
    await test_list_files()
    await test_git_status()
    await test_search_code()
    await test_get_now_playing()
    await test_find_movie_fallback()
    print("\n══ Day 6 checks passed ══════════════════════════════════════\n")


if __name__ == "__main__":
    asyncio.run(main())
