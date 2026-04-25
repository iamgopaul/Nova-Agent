"""
GAAIA headless server — no desktop UI.

Usage:
  .venv/bin/python scripts/run_server_only.py

Use this when:
  - Running GAAIA on a remote machine (accessed from iPhone / Windows)
  - CI / testing without a display
  - Developing the API layer independently of the UI
"""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

import uvicorn
from gaaia.server.main import create_app


def main() -> None:
    from config.settings import get_settings
    s = get_settings()
    host = s.server.get("host", "127.0.0.1")
    port = s.server.get("port", 8765)

    print(f"GAAIA server — http://{host}:{port}")
    print(f"  Docs:    http://{host}:{port}/docs")
    print(f"  Health:  http://{host}:{port}/health")
    print(f"  Model:   {s.model.get('name')}")

    uvicorn.run(
        create_app(),
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
