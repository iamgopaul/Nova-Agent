"""
Nova desktop entry point.

Usage:  .venv/bin/python scripts/run_desktop.py

Starts the customtkinter UI + FastAPI server (background thread).
"""
from __future__ import annotations

import sys
import threading

sys.path.insert(0, ".")


def _start_api_server() -> None:
    try:
        import uvicorn
        from nova.server.main import create_app
        uvicorn.run(
            create_app(),
            host="127.0.0.1",
            port=8765,
            log_level="error",
            access_log=False,
        )
    except Exception:
        pass  # server not built yet, or port already in use — fine


def main() -> None:
    import ollama
    from config.settings import get_settings
    from nova.bootstrap import build_nova

    settings = get_settings()
    model = settings.model.get("name", "qwen2.5:72b")

    # ── Preflight ────────────────────────────────────────────────────
    try:
        client = ollama.Client(host=settings.ollama_host)
        response = client.list()
        # ollama>=0.3 returns a ListResponse Pydantic model; older returns a dict
        model_list = getattr(response, "models", None) or response.get("models", [])
        names = [getattr(m, "model", None) or m.get("name", "") for m in model_list]
        if not any(m.startswith(model.split(":")[0]) for m in names):
            print(f"ERROR: Model '{model}' not found.\n  → Run: ollama pull {model}")
            sys.exit(1)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"ERROR: Cannot reach Ollama ({exc}).\n  → Run: ollama serve")
        sys.exit(1)

    # ── Bootstrap ────────────────────────────────────────────────────
    memory, orchestrator, _ = build_nova(settings)
    session = memory.get_or_create_session()

    # Load Whisper / VoicePipeline BEFORE tkinter initialises Cocoa frameworks.
    # macOS blocks fork() after Cocoa is loaded; CTranslate2 (Whisper) needs fork.
    from nova.voice.pipeline import VoicePipeline
    print(f"Nova starting — model: {model}")
    pipeline = VoicePipeline(
        settings=settings,
        orchestrator=orchestrator,
        session_id=session,
    )

    threading.Thread(target=_start_api_server, daemon=True).start()

    # Import NovaApp only NOW — after Whisper is loaded — so Cocoa initialises last.
    # macOS blocks fork() after Cocoa loads; CTranslate2 (Whisper) needs fork().
    from nova.desktop.app import NovaApp
    NovaApp(
        settings=settings,
        orchestrator=orchestrator,
        session_id=session,
        pipeline=pipeline,
    ).run()


if __name__ == "__main__":
    main()
