"""
/api/stats — system resource usage + last-request performance metrics.
"""
from __future__ import annotations

import platform
import subprocess
import threading
import time

from fastapi import APIRouter

from nova.services.stats_tracker import get_request_stats
from nova.services import resource_advisor

router = APIRouter()

# ── Background CPU sampler ─────────────────────────────────────────────────────
# psutil.cpu_percent(interval=None) always returns 0.0 on the very first call
# because it needs two measurements to compute a delta.  We run a background
# thread that continuously keeps a fresh reading so every API response is real.

_cpu_value: float = 0.0
_cpu_lock = threading.Lock()
_cpu_thread_started = False


def _cpu_sampler() -> None:
    global _cpu_value
    try:
        import psutil as _p
        while True:
            try:
                val = _p.cpu_percent(interval=1)   # blocks 1 s — accurate measurement
                with _cpu_lock:
                    _cpu_value = val
            except Exception:
                time.sleep(1)
    except ImportError:
        pass


def _ensure_cpu_thread() -> None:
    global _cpu_thread_started
    if not _cpu_thread_started:
        _cpu_thread_started = True
        t = threading.Thread(target=_cpu_sampler, daemon=True)
        t.start()


def _get_cpu() -> float | None:
    _ensure_cpu_thread()
    with _cpu_lock:
        return round(_cpu_value, 1) if _cpu_value is not None else None


# ── GPU / accelerator detection ───────────────────────────────────────────────

def _nvidia_gpu() -> dict | None:
    """Query NVIDIA GPU via nvidia-smi. Returns None if unavailable."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0:
            parts = [p.strip() for p in result.stdout.strip().split(",")]
            if len(parts) >= 4:
                return {
                    "type": "nvidia",
                    "utilization_percent": float(parts[0]),
                    "memory_used_mb": float(parts[1]),
                    "memory_total_mb": float(parts[2]),
                    "temperature_c": float(parts[3]),
                }
    except Exception:
        pass
    return None


def _apple_silicon_info() -> dict | None:
    """Return basic Apple Silicon chip info (no sudo required)."""
    if platform.system() != "Darwin":
        return None
    if platform.machine() not in ("arm64", "aarch64"):
        return None
    try:
        # Read chip branding from sysctl
        out = subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            text=True, timeout=2,
        ).strip()
    except Exception:
        out = "Apple Silicon"

    # Unified memory = RAM is shared between CPU and GPU,
    # so VRAM "total" equals total system RAM.
    try:
        import psutil as _p
        mem = _p.virtual_memory()
        total_mb = round(mem.total / 1_048_576)
        used_mb  = round(mem.used  / 1_048_576)
        pct      = round(mem.percent, 1)
    except Exception:
        total_mb = used_mb = 0
        pct = 0.0

    return {
        "type": "apple_silicon",
        "chip": out or "Apple Silicon",
        # Expose as VRAM-equivalent so the frontend bar renders
        "utilization_percent": pct,
        "memory_used_mb": used_mb,
        "memory_total_mb": total_mb,
        "temperature_c": None,
    }


def _system_stats() -> dict:
    try:
        import psutil

        cpu = _get_cpu()
        mem = psutil.virtual_memory()

        # Try NVIDIA first, fall back to Apple Silicon info
        gpu = _nvidia_gpu() or _apple_silicon_info()

        return {
            "cpu_percent": cpu,
            "ram_used_gb": round(mem.used  / 1_073_741_824, 2),
            "ram_total_gb": round(mem.total / 1_073_741_824, 2),
            "ram_percent": round(mem.percent, 1),
            "gpu": gpu,
        }
    except ImportError:
        return {
            "cpu_percent": None,
            "ram_used_gb": None,
            "ram_total_gb": None,
            "ram_percent": None,
            "gpu": None,
        }


@router.get("")
async def get_stats():
    req = get_request_stats()
    perf = resource_advisor.get_perf_options()
    return {
        "system": _system_stats(),
        "last_request": {
            "model": req.model,
            "tokens_generated": req.tokens_generated,
            "elapsed_seconds": req.elapsed_seconds,
            "tokens_per_second": req.tokens_per_second,
            "routed_via": req.routed_via,
            "status": req.status,
        },
        "perf_profile": resource_advisor.get_full_profile(),
    }
