"""
/api/stats — system resource usage + last-request performance metrics.
"""
from __future__ import annotations

from fastapi import APIRouter

from nova.services.stats_tracker import get_request_stats
from nova.services import resource_advisor

router = APIRouter()


def _system_stats() -> dict:
    try:
        import psutil

        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()

        gpu: dict | None = None
        try:
            import subprocess, json as _json
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
                    gpu = {
                        "utilization_percent": float(parts[0]),
                        "memory_used_mb": float(parts[1]),
                        "memory_total_mb": float(parts[2]),
                        "temperature_c": float(parts[3]),
                    }
        except Exception:
            gpu = None

        return {
            "cpu_percent": round(cpu, 1),
            "ram_used_gb": round(mem.used / 1_073_741_824, 2),
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
