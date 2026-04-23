from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend"
BACKEND_CMD = [sys.executable, "scripts/run_server_only.py"]
FRONTEND_CMD = ["npm", "run", "dev:desktop"]


def _wait_for_port(host: str, port: int, timeout_s: float = 8.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.3)
            if sock.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.2)
    return False


def main() -> int:
    backend: subprocess.Popen | None = None
    frontend: subprocess.Popen | None = None

    try:
        backend = subprocess.Popen(BACKEND_CMD, cwd=ROOT)

        # Allow up to 90 s — Kokoro pre-warm + Knowledge Feed first fetch can take 15–30 s
        if not _wait_for_port("127.0.0.1", 8765, timeout_s=90.0):
            if backend.poll() is not None:
                return backend.returncode or 1
            print("[Nova] Backend did not become healthy on 127.0.0.1:8765 in time.", flush=True)
            return 1

        frontend_env = os.environ.copy()
        frontend_env.setdefault("NOVA_API_BASE", "http://127.0.0.1:8765")
        frontend = subprocess.Popen(FRONTEND_CMD, cwd=FRONTEND_DIR, env=frontend_env)

        # Keep process alive while desktop frontend runs.
        return frontend.wait()
    except KeyboardInterrupt:
        return 130
    finally:
        for proc in (frontend, backend):
            if proc and proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
        for proc in (frontend, backend):
            if proc and proc.poll() is None:
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
