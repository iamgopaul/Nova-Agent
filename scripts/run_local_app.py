from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

# Load .env into os.environ early so all subprocesses and modules inherit it
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
except ImportError:
    pass

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend"
BACKEND_CMD = [sys.executable, "scripts/run_server_only.py"]
# On Windows, pnpm is pnpm.cmd — subprocess.Popen will not find it without
# either shell=True or the absolute path. shutil.which resolves the .cmd shim.
_PNPM = shutil.which("pnpm") or "pnpm"
FRONTEND_CMD = [_PNPM, "run", "dev"]


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
            print("[GAAIA] Backend did not become healthy on 127.0.0.1:8765 in time.", flush=True)
            return 1

        frontend_env = os.environ.copy()
        _base = (frontend_env.get("GAAIA_API_BASE") or "http://127.0.0.1:8765").strip().rstrip("/")
        if _base.lower().endswith("/api"):
            _base = _base[:-4].rstrip("/")
        frontend_env["GAAIA_API_BASE"] = _base or "http://127.0.0.1:8765"
        frontend = subprocess.Popen(FRONTEND_CMD, cwd=FRONTEND_DIR, env=frontend_env)

        # Keep process alive while the web frontend runs.
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
