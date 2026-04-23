"""
Day 2 smoke test — verifies the full tool loop:
  search_web, take_screenshot, write_note, get_clipboard, get_news
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

import ollama

from config.settings import get_settings
from nova.agent.orchestrator import Orchestrator
from nova.agent.tool_registry import ToolRegistry
from nova.approval.manager import ApprovalManager, ApprovalRequest
from nova.engines.research import GetNewsTool, WebSearchTool
from nova.memory.store import MemoryStore
from nova.tools.clipboard import GetClipboardTool, SetClipboardTool
from nova.tools.notes import ListNotesTool, ReadNoteTool, WriteNoteTool
from nova.tools.screenshot import ScreenshotTool


def check_ollama(host: str, model: str) -> None:
    try:
        client = ollama.Client(host=host)
        models = [m["name"] for m in client.list().get("models", [])]
    except Exception as e:
        print(f"ERROR: Cannot reach Ollama at {host}\n  → Run: ollama serve\n  {e}")
        sys.exit(1)
    base = model.split(":")[0]
    if not any(m.startswith(base) for m in models):
        print(f"ERROR: Model '{model}' not found.\n  → Run: ollama pull {model}")
        sys.exit(1)
    print(f"Ollama OK — model: {model}")


def cli_approval(request: ApprovalRequest) -> bool:
    """Simple terminal approval prompt used during Day 2 testing."""
    print(f"\n  [APPROVAL] {request.description}")
    print(f"  Tool: {request.tool_name} | Risk: {request.risk_level}")
    ans = input("  Allow? (y/n): ").strip().lower()
    return ans == "y"


def build_registry(settings) -> ToolRegistry:
    registry = ToolRegistry()
    screenshots_dir = settings.data_dir / "screenshots"
    notes_dir = settings.notes_dir
    feed_urls = settings.research.get("news_feeds", [])
    max_results = settings.research.get("max_results", 5)

    registry.register(WebSearchTool(max_results=max_results))
    registry.register(GetNewsTool(feed_urls=feed_urls))
    registry.register(ScreenshotTool(save_dir=screenshots_dir))
    registry.register(WriteNoteTool(notes_dir=notes_dir))
    registry.register(ReadNoteTool(notes_dir=notes_dir))
    registry.register(ListNotesTool(notes_dir=notes_dir))
    registry.register(GetClipboardTool())
    registry.register(SetClipboardTool())
    return registry


async def run_test(prompt: str, label: str, orchestrator: Orchestrator, session_id: str) -> None:
    print(f"\n{'─'*60}")
    print(f"TEST: {label}")
    print(f"You: {prompt}")
    print(f"Nova: ", end="", flush=True)
    await orchestrator.run(
        user_message=prompt,
        session_id=session_id,
        stream_callback=lambda c: print(c, end="", flush=True),
        approval_callback=cli_approval,
    )
    print()


async def main() -> None:
    settings = get_settings()
    settings.ensure_dirs()

    model = settings.model.get("name", "qwen2.5:72b")
    check_ollama(settings.ollama_host, model)

    memory = MemoryStore(settings.db_path)
    session_id = memory.get_or_create_session()
    registry = build_registry(settings)
    approval = ApprovalManager(settings.approval)
    orchestrator = Orchestrator(
        settings=settings,
        memory=memory,
        tool_registry=registry,
        approval_manager=approval,
    )

    print(f"\nTools registered: {[t['function']['name'] for t in registry.get_all_schemas()]}")

    # Test 1: web search (auto-approved)
    await run_test(
        "Search the web for the latest news about AI models released this week.",
        "Web search (auto)",
        orchestrator, session_id,
    )

    # Test 2: screenshot (auto-approved)
    await run_test(
        "Take a screenshot of my screen.",
        "Screenshot (auto)",
        orchestrator, session_id,
    )

    # Test 3: write note (requires confirmation)
    await run_test(
        "Save a note titled 'Nova Day 2 Test' with the content: Tool system is working.",
        "Write note (confirm)",
        orchestrator, session_id,
    )

    # Test 4: news briefing (auto-approved)
    await run_test(
        "Give me a quick news briefing on technology.",
        "News briefing (auto)",
        orchestrator, session_id,
    )

    print(f"\n{'─'*60}")
    print(f"Day 2 complete. Session: {session_id}")
    print(f"Memory: {len(memory.get_recent_turns(session_id))} turns stored.")


if __name__ == "__main__":
    asyncio.run(main())
