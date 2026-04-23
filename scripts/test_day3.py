"""
Day 3 interactive test — full push-to-talk voice loop.

Run:  .venv/bin/python scripts/test_day3.py

Controls:
  Hold Ctrl+Space  → speak
  Release          → Nova thinks and responds
  Ctrl+C           → quit

NOTE: macOS requires Accessibility permission for global hotkeys.
  System Settings → Privacy & Security → Accessibility → add Terminal.app
"""
from __future__ import annotations

import asyncio
import sys
import time

sys.path.insert(0, ".")

import ollama

from config.settings import get_settings
from nova.agent.orchestrator import Orchestrator
from nova.agent.tool_registry import ToolRegistry
from nova.approval.manager import ApprovalManager
from nova.engines.research import GetNewsTool, WebSearchTool
from nova.memory.store import MemoryStore
from nova.tools.clipboard import GetClipboardTool, SetClipboardTool
from nova.tools.notes import ListNotesTool, ReadNoteTool, WriteNoteTool
from nova.tools.screenshot import ScreenshotTool
from nova.voice.pipeline import VoicePipeline
from nova.voice.tts import MacOSTTS


def check_ollama(host: str, model: str) -> None:
    try:
        client = ollama.Client(host=host)
        models = [m["name"] for m in client.list().get("models", [])]
    except Exception as e:
        print(f"ERROR: Ollama unreachable at {host}\n  → Run: ollama serve\n  {e}")
        sys.exit(1)
    base = model.split(":")[0]
    if not any(m.startswith(base) for m in models):
        print(f"ERROR: Model '{model}' not found.\n  → Run: ollama pull {model}")
        sys.exit(1)


def build_registry(settings) -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(WebSearchTool(max_results=settings.research.get("max_results", 5)))
    reg.register(GetNewsTool(feed_urls=settings.research.get("news_feeds", [])))
    reg.register(ScreenshotTool(save_dir=settings.data_dir / "screenshots"))
    reg.register(WriteNoteTool(notes_dir=settings.notes_dir))
    reg.register(ReadNoteTool(notes_dir=settings.notes_dir))
    reg.register(ListNotesTool(notes_dir=settings.notes_dir))
    reg.register(GetClipboardTool())
    reg.register(SetClipboardTool())
    return reg


def main() -> None:
    settings = get_settings()
    settings.ensure_dirs()

    model = settings.model.get("name", "qwen2.5:72b")
    print(f"Checking Ollama ({model})…")
    check_ollama(settings.ollama_host, model)
    print("  ✓ Ollama ready\n")

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

    # Quick TTS smoke-test so we know audio output works before the full loop
    tts = MacOSTTS(**{k: v for k, v in settings.voice.get("tts", {}).get("macos_say", {}).items()})
    print("Testing TTS… (you should hear Nova's voice)")
    tts.speak("Nova voice pipeline ready.")
    print("  ✓ TTS OK\n")

    pipeline = VoicePipeline(
        settings=settings,
        orchestrator=orchestrator,
        session_id=session_id,
    )

    def on_state(state: str) -> None:
        icons = {"idle": "○", "recording": "● REC", "thinking": "◌ ...", "speaking": "▶"}
        print(f"\r  [{icons.get(state, state)}]          ", end="", flush=True)

    def on_transcript(text: str) -> None:
        print(f"\n\nYou:  {text}")
        print("Nova: ", end="", flush=True)

    def on_chunk(chunk: str) -> None:
        print(chunk, end="", flush=True)

    def on_done(text: str) -> None:
        print()  # newline after streamed response

    pipeline.on_state_change = on_state
    pipeline.on_transcript = on_transcript
    pipeline.on_response_chunk = on_chunk
    pipeline.on_response_done = on_done

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Nova voice loop active.")
    print("  Hold Ctrl+Space to speak. Release to send.")
    print("  Ctrl+C to quit.")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    print("  NOTE: If hotkey does nothing, grant Accessibility permission:")
    print("  System Settings → Privacy & Security → Accessibility → Terminal\n")

    pipeline.start()
    print("  [○]  Waiting…", end="", flush=True)

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n\nGoodbye.")
        pipeline.stop()


if __name__ == "__main__":
    main()
