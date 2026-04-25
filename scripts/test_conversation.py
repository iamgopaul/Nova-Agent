"""Day 1 smoke test — verifies GAAIA responds in character via local Ollama."""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, ".")

import ollama

from config.settings import get_settings
from gaaia.memory.store import MemoryStore
from gaaia.agent.orchestrator import Orchestrator


def check_ollama(host: str, model: str) -> None:
    try:
        client = ollama.Client(host=host)
        models = [m["name"] for m in client.list().get("models", [])]
    except Exception as e:
        print(f"ERROR: Cannot reach Ollama at {host}")
        print(f"  → Run: ollama serve")
        print(f"  Details: {e}")
        sys.exit(1)

    available = [m for m in models if m.startswith(model.split(":")[0])]
    if not available:
        print(f"ERROR: Model '{model}' not found in Ollama.")
        print(f"  → Run: ollama pull {model}")
        print(f"  Available models: {models or 'none'}")
        sys.exit(1)

    print(f"Ollama OK — using model: {model}")


async def main() -> None:
    settings = get_settings()
    settings.ensure_dirs()

    model = settings.model.get("name", "qwen2.5:7b")
    host = settings.ollama_host
    check_ollama(host, model)

    memory = MemoryStore(settings.db_path)
    session_id = memory.get_or_create_session()
    orchestrator = Orchestrator(settings=settings, memory=memory)

    print("\nGAAIA: ", end="", flush=True)
    response = await orchestrator.run(
        user_message="Hello GAAIA. Introduce yourself in two sentences.",
        session_id=session_id,
        stream_callback=lambda chunk: print(chunk, end="", flush=True),
    )
    print("\n")
    print(f"[Session: {session_id}]")
    print(f"[Memory: {len(memory.get_recent_turns(session_id))} turn(s) stored]")


if __name__ == "__main__":
    asyncio.run(main())
