"""
Hardware detection — shared helpers for RAM, VRAM, and the unified memory
budget used by the model router and resource advisor.

The "memory budget" is a single number representing how much memory Ollama
can realistically use to load a model:

  - Apple Silicon: VRAM and RAM are the same physical pool (unified memory),
    so the budget is just total RAM. Counting VRAM separately would
    double-count.
  - Discrete GPU (NVIDIA / AMD): Ollama loads as many layers as fit in VRAM
    and spills the rest to RAM. The budget is RAM + VRAM.
  - No GPU: just RAM.

VRAM is detected by shelling out to `nvidia-smi` / `rocm-smi` so we don't
add a Python dependency for a single lookup. Failures fall back silently to
RAM-only — better to under-recommend than to over-promise.
"""
from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass

import psutil


@dataclass(frozen=True)
class MemoryBudget:
    """Unified memory budget breakdown for logging and routing decisions."""
    total_gb: float        # what the router uses as its budget
    ram_gb: float          # system RAM (always populated)
    vram_gb: float         # discrete GPU VRAM (0 on Apple Silicon / CPU-only)
    apple_silicon: bool    # unified memory architecture

    def describe(self) -> str:
        """One-line human-readable breakdown for startup logs."""
        if self.apple_silicon:
            return f"{self.ram_gb:.1f} GB unified memory (Apple Silicon)"
        if self.vram_gb > 0:
            return (
                f"{self.total_gb:.1f} GB budget "
                f"({self.ram_gb:.1f} GB RAM + {self.vram_gb:.1f} GB VRAM)"
            )
        return f"{self.ram_gb:.1f} GB RAM (no GPU detected)"


def is_apple_silicon() -> bool:
    """True on M-series Macs where RAM and VRAM share the same physical pool."""
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def nvidia_vram_gb() -> float:
    """Sum of VRAM across all NVIDIA GPUs in GB. 0 if nvidia-smi fails."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            timeout=3, stderr=subprocess.DEVNULL,
        ).decode().strip()
        # nvidia-smi reports MiB
        return sum(float(x) for x in out.splitlines() if x.strip()) / 1024
    except Exception:
        return 0.0


def amd_vram_gb() -> float:
    """Sum of VRAM across all AMD GPUs in GB. 0 if rocm-smi fails or absent."""
    try:
        out = subprocess.check_output(
            ["rocm-smi", "--showmeminfo", "vram", "--csv"],
            timeout=3, stderr=subprocess.DEVNULL,
        ).decode().strip()
        # CSV: device,vram total memory (B),vram used memory (B)
        total_bytes = 0.0
        for line in out.splitlines()[1:]:
            parts = line.split(",")
            if len(parts) >= 2:
                try:
                    total_bytes += float(parts[1])
                except ValueError:
                    continue
        return total_bytes / (1024 ** 3)
    except Exception:
        return 0.0


def total_vram_gb() -> float:
    """Combined VRAM across NVIDIA and AMD GPUs. 0 on Apple Silicon / CPU-only."""
    if is_apple_silicon():
        return 0.0  # unified memory; counting VRAM would double-count RAM
    return nvidia_vram_gb() + amd_vram_gb()


def get_memory_budget() -> MemoryBudget:
    """Probe RAM + VRAM and return the unified budget Ollama can draw on."""
    ram_gb = psutil.virtual_memory().total / (1024 ** 3)
    apple = is_apple_silicon()
    vram_gb = 0.0 if apple else (nvidia_vram_gb() + amd_vram_gb())
    total_gb = ram_gb if apple else (ram_gb + vram_gb)
    return MemoryBudget(
        total_gb=total_gb,
        ram_gb=ram_gb,
        vram_gb=vram_gb,
        apple_silicon=apple,
    )


def get_total_memory_gb() -> float:
    """Convenience: just the unified budget number, for callers that don't need the breakdown."""
    return get_memory_budget().total_gb


def safety_margin_gb(budget_gb: float) -> float:
    """Headroom to reserve for OS / app processes when sizing models.

    Scales with the budget — 2 GB is fine on a 16 GB box but tight on a
    128 GB rig that's also running a browser, IDE, and Docker.
    """
    if budget_gb <= 16:
        return 2.0
    if budget_gb <= 64:
        return 4.0
    return 8.0
