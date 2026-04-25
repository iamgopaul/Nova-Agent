"""
MusicGen service — uses HuggingFace Transformers' built-in MusicGen implementation
(facebook/musicgen-small) to generate instrumental beats from text prompts.

No audiocraft dependency — `transformers` is used with optional `torch` / `torchaudio`
(see `pip install -e ".[musicgen]"`).

Model is downloaded from HuggingFace on first use (~1.9 GB) and cached.

Quality notes
-------------
MusicGen-small emits audio at 32 kHz via EnCodec with a 50 Hz frame rate — each
generation step produces exactly 20 ms of audio across 4 parallel codebooks.
`duration * 50` tokens therefore yields (approximately) `duration` seconds of
audio, but the encoder occasionally drops the last few frames, so we add a
small safety budget and then trim to exact length on the way out.

On Apple Silicon, MPS can run out of memory for long clips; we default to a
shorter target length, clear MPS cache after use, and retry on CPU with a
further limited duration when a recoverable failure is detected.
"""

from __future__ import annotations

import gc
import io
import logging
import os
import threading
import wave

logger = logging.getLogger(__name__)

_model = None
_processor = None
_lock = threading.Lock()
_current_device: str = "cpu"

_MODEL_ID = "facebook/musicgen-small"
_FRAMES_PER_SECOND = 50   # EnCodec emits exactly 50 Hz for musicgen-small
_SAFETY_FRAMES = 25       # extra ~0.5 s so we can trim to a clean length
# Shorter first clip on MPS/CPU to reduce OOM; full cap remains 5–30s.
_MPS_MAX_DURATION = 15
_CPU_RETRY_DURATION = 10


def _teardown() -> None:
    global _model, _processor, _current_device
    _model = None
    _processor = None
    _current_device = "cpu"
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            torch.mps.empty_cache()
    except Exception:  # noqa: BLE001
        pass


def _resolve_device(explicit: str | None = None) -> str:
    import torch
    v = (explicit or os.environ.get("GAAIA_MUSIC_DEVICE") or "auto").strip().lower()
    if v == "auto":
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    if v == "mps" and (not hasattr(torch.backends, "mps") or not torch.backends.mps.is_available()):
        logger.warning("[MusicGen] MPS not available, using CPU.", flush=True)
        return "cpu"
    if v == "cuda" and not torch.cuda.is_available():
        logger.warning("[MusicGen] CUDA not available, using CPU.", flush=True)
        return "cpu"
    if v in ("cpu", "mps", "cuda"):
        return v
    logger.warning("[MusicGen] Invalid GAAIA_MUSIC_DEVICE %r; using CPU.", v)
    return "cpu"


def _load_model() -> None:
    global _model, _processor, _current_device
    try:
        import torch  # noqa: F401 — ensure torch is available first
        from transformers import AutoProcessor, MusicgenForConditionalGeneration
    except ImportError as exc:
        raise RuntimeError(
            "transformers and/or torch are not installed.\n"
            "Run: pip install -e \".[musicgen]\"   # or: pip install transformers torch torchaudio"
        ) from exc

    print(f"[MusicGen] Loading {_MODEL_ID} (first use — downloading if not cached)…", flush=True)
    _processor = AutoProcessor.from_pretrained(_MODEL_ID)
    _model = MusicgenForConditionalGeneration.from_pretrained(_MODEL_ID)

    target = _resolve_device()
    _current_device = target
    _model.to(target)
    _model.eval()
    if target == "cuda":
        print("[MusicGen] Running on CUDA.", flush=True)
    elif target == "mps":
        print("[MusicGen] Running on MPS (Apple Silicon).", flush=True)
    else:
        print("[MusicGen] Running on CPU.", flush=True)

    print("[MusicGen] Model ready.", flush=True)


def _get() -> tuple:
    global _model, _processor
    if _model is None:
        with _lock:
            if _model is None:
                _load_model()
    return _model, _processor


def _load_cpu_only() -> None:
    """Replace the loaded model with a CPU copy (e.g. after MPS OOM)."""
    global _model, _processor, _current_device
    with _lock:
        _teardown()
        try:
            from transformers import AutoProcessor, MusicgenForConditionalGeneration
        except ImportError as exc:
            raise RuntimeError(
                "transformers and/or torch are not installed.\n"
                "Run: pip install -e \".[musicgen]\""
            ) from exc
        print("[MusicGen] Loading model on CPU (retry path)…", flush=True)
        _processor = AutoProcessor.from_pretrained(_MODEL_ID)
        _model = MusicgenForConditionalGeneration.from_pretrained(_MODEL_ID)
        _model.to("cpu")
        _model.eval()
        _current_device = "cpu"
    print("[MusicGen] Model ready (CPU).", flush=True)


def _should_retry_on_cpu(exc: BaseException) -> bool:
    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
        return False
    try:
        import torch
        if isinstance(exc, torch.cuda.OutOfMemoryError):
            return True
    except Exception:  # noqa: BLE001
        pass
    msg = str(exc).lower()
    if "not installed" in msg and "transform" in msg:
        return False
    if "import" in type(exc).__name__.lower() and "error" in type(exc).__name__.lower():
        return False
    return any(
        s in msg
        for s in (
            "out of memory",
            "mps backend out of memory",
            "knmpsoutofmemory",
            "mps: allocation",
            "not currently implemented for the mps",
            "mps for op",
        )
    )


def _normalize_prompt(prompt: str) -> str:
    """
    Clean up a prompt so MusicGen sees a tight musical description rather than
    conversational fluff. Strips leading verbs like "generate/make/play", chat
    emojis, trailing punctuation, and collapses whitespace.
    """
    if not prompt:
        return "uplifting instrumental groove, smooth drums, warm bass"
    p = prompt.strip()
    for lead in (
        "generate", "create", "make", "produce", "compose", "write",
        "play", "give me", "build", "can you", "please",
    ):
        if p.lower().startswith(lead):
            p = p[len(lead):].lstrip(" ,:-")
    p = p.rstrip(" ?.,!")
    p = " ".join(p.split())
    return p or "uplifting instrumental groove, smooth drums, warm bass"


def _generate_wav_bytes_inner(prompt: str, duration: int) -> bytes:
    import numpy as np
    import torch

    clean_prompt = _normalize_prompt(prompt)
    model, processor = _get()
    if model is None or processor is None:
        raise RuntimeError("MusicGen model did not load.")

    target_frames = duration * _FRAMES_PER_SECOND
    max_new_tokens = target_frames + _SAFETY_FRAMES
    print(
        f"[MusicGen] Generating: '{clean_prompt[:90]}' "
        f"({duration}s, budget={max_new_tokens} tokens) on {_current_device}…",
        flush=True,
    )

    inputs = processor(text=[clean_prompt], padding=True, return_tensors="pt")
    try:
        device = next(model.parameters()).device
        inputs = {k: v.to(device) if hasattr(v, "to") else v for k, v in inputs.items()}
    except Exception:  # noqa: BLE001
        pass

    with torch.no_grad():
        audio_values = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            guidance_scale=3.0,
            temperature=1.0,
        )

    dev = next(model.parameters()).device
    if dev.type == "mps":
        try:
            torch.mps.synchronize()
        except Exception:  # noqa: BLE001
            pass
        try:
            torch.mps.empty_cache()
        except Exception:  # noqa: BLE001
            pass
    if torch.cuda.is_available():
        try:
            torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001
            pass

    audio: np.ndarray = audio_values[0, 0].detach().cpu().numpy()
    sample_rate: int = model.config.audio_encoder.sampling_rate
    target_samples = int(duration * sample_rate)
    if audio.shape[0] > target_samples:
        audio = audio[:target_samples]
    elif audio.shape[0] < target_samples:
        pad = np.zeros(target_samples - audio.shape[0], dtype=audio.dtype)
        audio = np.concatenate([audio, pad])

    peak = float(np.max(np.abs(audio))) or 1.0
    if peak > 0:
        audio = (audio / peak) * 0.9
    audio = np.clip(audio, -1.0, 1.0)
    audio_int16 = (audio * 32767).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())

    wav_bytes = buf.getvalue()
    actual_sec = len(audio_int16) / sample_rate
    print(
        f"[MusicGen] Done — {len(wav_bytes) // 1024} KB WAV @ {sample_rate} Hz, {actual_sec:.2f}s",
        flush=True,
    )
    return wav_bytes


def generate_music(prompt: str, duration: int = 12) -> bytes:
    """
    Generate instrumental music from a text description and return raw WAV bytes.

    Parameters
    ----------
    prompt   : natural-language description (e.g. "chill lo-fi hip-hop beat, soft piano")
    duration : target length in seconds (clamped 5–30). Shorter clips are more
               reliable on GPU/MPS. Default 12s balances quality and memory use.
    """
    duration = max(5, min(30, int(duration)))
    # Shorter default helps before first load; after load, _current_device is set.
    if _resolve_device() == "mps" or _current_device == "mps":
        duration = min(duration, _MPS_MAX_DURATION)

    try:
        return _generate_wav_bytes_inner(prompt, duration)
    except Exception as first:
        if not _should_retry_on_cpu(first):
            raise
        d2 = max(5, min(duration, _CPU_RETRY_DURATION))
        if _current_device == "cpu":
            logger.warning(
                "[MusicGen] Retrying on CPU with shorter %ss clip after: %s",
                d2,
                first,
            )
            return _generate_wav_bytes_inner(prompt, d2)
        logger.warning(
            "[MusicGen] First attempt failed (%s); moving model to CPU, %ss clip.",
            first,
            d2,
        )
        _load_cpu_only()
        return _generate_wav_bytes_inner(prompt, d2)
