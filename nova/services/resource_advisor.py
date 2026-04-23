"""
ResourceAdvisor — compute optimal Ollama inference parameters
based on available system hardware (CPU cores, RAM, GPU VRAM).

RAM pressure levels:
  ok        — plenty of RAM, use full models and large contexts
  moderate  — RAM is tightening; reduce batch/context, prefer smaller models
  critical  — very low RAM; force smallest safe model, enable mmap paging,
              shorten keep_alive so models unload fast

Key Ollama options we tune:
  num_gpu    — GPU layers to offload (999 = use all available VRAM)
  num_thread — CPU threads for inference (physical cores − 1)
  num_batch  — prompt-eval batch size (larger = faster TTFT, more RAM)
  num_ctx    — KV-cache context length (largest single RAM consumer)
  use_mmap   — memory-mapped model files: OS can page weights in/out,
               allowing models bigger than free RAM to run without crashing
  mlock      — when False, the OS may swap model pages under pressure
               (True would pin everything in RAM — dangerous when low)
"""
from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Literal

import psutil


RamPressure = Literal["ok", "moderate", "critical"]
ModelTier   = Literal["full", "mid", "light"]   # which size models to prefer


@dataclass
class PerfProfile:
    num_gpu:     int        # 999 = max VRAM, 0 = CPU-only
    num_thread:  int        # CPU threads
    num_batch:   int        # prompt-eval batch size
    num_ctx:     int        # default context length
    use_mmap:    bool       # memory-mapped model files
    mlock:       bool       # pin model in RAM (False = allow swapping)
    keep_alive:  str        # how long Ollama keeps a model loaded ("5m", "20m", "-1")
    ram_pressure: RamPressure
    model_tier:  ModelTier
    description: str        # human-readable label for the stats bar


_profile: PerfProfile | None = None
_lock = threading.Lock()
_REFRESH_INTERVAL = 30   # seconds — refresh more often to react to RAM changes


# ── Hardware detection ────────────────────────────────────────────────────────

def _nvidia_vram_gb() -> float:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            timeout=3, stderr=subprocess.DEVNULL,
        ).decode().strip()
        return sum(float(x) for x in out.splitlines() if x.strip()) / 1024
    except Exception:
        return 0.0


def _is_apple_silicon() -> bool:
    try:
        return subprocess.check_output(["uname", "-m"], timeout=2).decode().strip() == "arm64"
    except Exception:
        return False


# ── Profile computation ───────────────────────────────────────────────────────

def _compute_profile() -> PerfProfile:
    vm              = psutil.virtual_memory()
    cpu_count       = os.cpu_count() or 4
    total_ram_gb    = vm.total    / (1024 ** 3)
    avail_ram_gb    = vm.available / (1024 ** 3)
    ram_used_pct    = vm.percent
    vram_gb         = _nvidia_vram_gb()
    apple           = _is_apple_silicon()

    # ── RAM pressure ─────────────────────────────────────────────────────────
    if avail_ram_gb < 1.5 or ram_used_pct >= 90:
        ram_pressure: RamPressure = "critical"
    elif avail_ram_gb < 4.0 or ram_used_pct >= 75:
        ram_pressure = "moderate"
    else:
        ram_pressure = "ok"

    # ── Model tier recommendation ─────────────────────────────────────────────
    # Tells the orchestrator which size class to prefer.
    if ram_pressure == "critical":
        model_tier: ModelTier = "light"    # 1–3 B params
    elif ram_pressure == "moderate":
        model_tier = "mid"                 # 4–8 B params
    else:
        model_tier = "full"                # no restriction

    # ── GPU layers ────────────────────────────────────────────────────────────
    if apple:
        num_gpu = 999   # Metal / unified memory — offload everything
    elif vram_gb >= 16:
        num_gpu = 999
    elif vram_gb >= 8:
        num_gpu = 40
    elif vram_gb >= 4:
        num_gpu = 20
    else:
        num_gpu = 0     # CPU-only

    # Under critical RAM and no dedicated GPU, reduce layers to save unified/shared memory
    if ram_pressure == "critical" and num_gpu > 0 and not apple:
        num_gpu = min(num_gpu, 16)

    # ── CPU threads ───────────────────────────────────────────────────────────
    num_thread = max(1, cpu_count - 1)

    # ── Batch size ────────────────────────────────────────────────────────────
    # Aggressively reduce under memory pressure — batch is a large contiguous alloc.
    if ram_pressure == "critical":
        num_batch = 128
    elif ram_pressure == "moderate":
        num_batch = 256
    elif avail_ram_gb >= 24:
        num_batch = 2048
    elif avail_ram_gb >= 12:
        num_batch = 1024
    else:
        num_batch = 512

    # ── Context length ────────────────────────────────────────────────────────
    # KV cache is proportional to num_ctx — the single biggest RAM consumer.
    if ram_pressure == "critical":
        num_ctx = 1024   # absolute minimum — saves ~500 MB on 7B models
    elif ram_pressure == "moderate":
        num_ctx = 2048
    else:
        num_ctx = 4096   # comfortable default

    # ── Memory mapping & locking ──────────────────────────────────────────────
    # use_mmap=True: model weights are read from disk via mmap pages.
    # When RAM is short the OS can silently evict cold pages without crashing.
    # mlock=False: let the OS swap pages out under pressure.
    # mlock=True would pin everything — great for speed, fatal when RAM is low.
    use_mmap = True            # always safe and beneficial
    mlock    = (ram_pressure == "ok")  # only pin in RAM when we have enough

    # ── Keep-alive ────────────────────────────────────────────────────────────
    # Short keep_alive frees VRAM/RAM sooner when not in use.
    if ram_pressure == "critical":
        keep_alive = "2m"   # unload very quickly to reclaim RAM
    elif ram_pressure == "moderate":
        keep_alive = "5m"
    else:
        keep_alive = "20m"  # comfortable; avoids reload delays

    # ── Description ──────────────────────────────────────────────────────────
    pressure_label = {"ok": "✓ OK", "moderate": "⚠ Moderate", "critical": "⚠ Low RAM"}[ram_pressure]
    gpu_label = "GPU: max" if num_gpu >= 999 else (f"GPU: {num_gpu}L" if num_gpu > 0 else "CPU only")
    desc = (
        f"RAM {pressure_label} ({avail_ram_gb:.1f} GB free) | "
        f"{gpu_label} | Threads: {num_thread} | Batch: {num_batch} | ctx: {num_ctx}"
    )

    return PerfProfile(
        num_gpu=num_gpu,
        num_thread=num_thread,
        num_batch=num_batch,
        num_ctx=num_ctx,
        use_mmap=use_mmap,
        mlock=mlock,
        keep_alive=keep_alive,
        ram_pressure=ram_pressure,
        model_tier=model_tier,
        description=desc,
    )


def _refresh_loop() -> None:
    while True:
        time.sleep(_REFRESH_INTERVAL)
        try:
            new = _compute_profile()
            with _lock:
                global _profile
                _profile = new
        except Exception:
            pass


# ── Public API ────────────────────────────────────────────────────────────────

def initialize() -> None:
    """
    Probe hardware, compute the initial profile, and start the background
    refresh thread. Call once at application startup (main.py lifespan).
    """
    global _profile
    _profile = _compute_profile()

    ram_gb   = psutil.virtual_memory().total / (1024 ** 3)
    vram_gb  = _nvidia_vram_gb()
    apple    = _is_apple_silicon()
    gpu_info = "Apple Silicon (Metal)" if apple else (
        f"{vram_gb:.1f} GB VRAM" if vram_gb else "no GPU"
    )
    print(
        f"[ResourceAdvisor] Hardware: {os.cpu_count()} CPU cores, "
        f"{ram_gb:.1f} GB RAM, {gpu_info}\n"
        f"[ResourceAdvisor] Profile → {_profile.description}",
        flush=True,
    )
    if _profile.ram_pressure != "ok":
        print(
            f"[ResourceAdvisor] ⚠  RAM pressure: {_profile.ram_pressure} — "
            f"model tier capped to '{_profile.model_tier}', "
            f"ctx={_profile.num_ctx}, mmap=on, mlock=off, keep_alive={_profile.keep_alive}",
            flush=True,
        )

    t = threading.Thread(target=_refresh_loop, daemon=True, name="resource-advisor")
    t.start()


def get_perf_options() -> dict:
    """
    Return an Ollama options dict with hardware-tuned values.
    Includes memory-safety flags (use_mmap, mlock) when RAM is constrained.
    """
    with _lock:
        p = _profile
    if p is None:
        p = _compute_profile()

    return {
        "num_gpu":    p.num_gpu,
        "num_thread": p.num_thread,
        "num_batch":  p.num_batch,
        "num_ctx":    p.num_ctx,
        "use_mmap":   p.use_mmap,
        "mlock":      p.mlock,
    }


def get_keep_alive() -> str:
    """Return the recommended keep_alive string for the current RAM pressure."""
    with _lock:
        p = _profile
    return p.keep_alive if p else "20m"


def get_ram_pressure() -> RamPressure:
    with _lock:
        p = _profile
    return p.ram_pressure if p else "ok"


def get_model_tier() -> ModelTier:
    """
    Recommended model size class given current RAM.
    'full' = no restriction, 'mid' = prefer ≤8B, 'light' = prefer ≤3B.
    """
    with _lock:
        p = _profile
    return p.model_tier if p else "full"


def get_profile_description() -> str:
    with _lock:
        p = _profile
    return p.description if p else "Profiling…"


def get_full_profile() -> dict:
    """Full profile dict for the stats API."""
    with _lock:
        p = _profile
    if p is None:
        return {}
    return {
        "description":  p.description,
        "ram_pressure": p.ram_pressure,
        "model_tier":   p.model_tier,
        "num_gpu":      p.num_gpu,
        "num_thread":   p.num_thread,
        "num_batch":    p.num_batch,
        "num_ctx":      p.num_ctx,
        "use_mmap":     p.use_mmap,
        "mlock":        p.mlock,
        "keep_alive":   p.keep_alive,
    }
