"""
Shared factory — builds the full Nova runtime from settings.
Used by both the desktop entry point and the FastAPI server lifespan.
"""
from __future__ import annotations

from config.settings import Settings
from nova.agent.orchestrator import Orchestrator
from nova.agent.tool_registry import ToolRegistry
from nova.approval.manager import ApprovalManager
from nova.engines.communication import DraftEmailTool, DraftMessageTool
from nova.engines.dev import GitStatusTool, ListFilesTool, ReadFileTool, SearchCodeTool
from nova.engines.media import (
    FindMovieTool,
    GetNowPlayingTool,
    PauseMusicTool,
    PlayMusicTool,
    PlayYouTubeTool,
)
from nova.engines.video_analyzer import AnalyzeVideoTool
from nova.engines.research import GetNewsTool, WebSearchTool
from nova.memory.store import MemoryStore
from nova.tools.clipboard import GetClipboardTool, SetClipboardTool
from nova.tools.notes import ListNotesTool, ReadNoteTool, WriteNoteTool
from nova.tools.screenshot import ScreenshotTool
from nova.tools.weather import WeatherTool


def build_registry(settings: Settings) -> ToolRegistry:
    registry = ToolRegistry()

    # Research
    registry.register(WebSearchTool(max_results=settings.research.get("max_results", 5)))
    registry.register(GetNewsTool(feed_urls=settings.research.get("news_feeds", [])))
    registry.register(WeatherTool())

    # System tools
    registry.register(ScreenshotTool(save_dir=settings.data_dir / "screenshots"))
    registry.register(WriteNoteTool(notes_dir=settings.notes_dir))
    registry.register(ReadNoteTool(notes_dir=settings.notes_dir))
    registry.register(ListNotesTool(notes_dir=settings.notes_dir))
    registry.register(GetClipboardTool())
    registry.register(SetClipboardTool())

    # Communication
    registry.register(DraftEmailTool())
    registry.register(DraftMessageTool())

    # Media
    registry.register(PlayMusicTool())
    registry.register(PauseMusicTool())
    registry.register(GetNowPlayingTool())
    registry.register(PlayYouTubeTool())
    registry.register(FindMovieTool(tmdb_api_key=settings.tmdb_api_key))
    registry.register(AnalyzeVideoTool())

    # Dev
    dev_cfg = settings.dev
    registry.register(ReadFileTool())
    registry.register(ListFilesTool(include_extensions=dev_cfg.get("include_extensions")))
    registry.register(GitStatusTool())
    registry.register(SearchCodeTool())

    return registry


def build_nova(settings: Settings) -> tuple[MemoryStore, Orchestrator, ApprovalManager]:
    """
    Construct and return (memory, orchestrator, approval_manager).
    All three are long-lived singletons — create once, reuse everywhere.
    """
    settings.ensure_dirs()
    memory   = MemoryStore(settings.db_path)
    registry = build_registry(settings)
    approval = ApprovalManager(settings.approval)
    orchestrator = Orchestrator(
        settings=settings,
        memory=memory,
        tool_registry=registry,
        approval_manager=approval,
    )
    return memory, orchestrator, approval
