"""
MusicGen service — uses HuggingFace Transformers' built-in MusicGen implementation
(facebook/musicgen-small) to generate instrumental beats from text prompts.

No audiocraft dependency needed — `transformers` is already installed.
Model is downloaded from HuggingFace on first use (~1.9 GB) and cached.
"""

from __future__ import annotations

import io
import logging
import threading
import wave

logger = logging.getLogger(__name__)

_model = None
_processor = None
_lock = threading.Lock()

_MODEL_ID = "facebook/musicgen-small"
_SAMPLE_RATE = 32000  # MusicGen-small output sample rate


def _load() -> None:
    global _model, _processor
    try:
        import torch  # noqa: F401 — ensure torch is available first
        from transformers import AutoProcessor, MusicgenForConditionalGeneration
    except ImportError as exc:
        raise RuntimeError(
            "transformers and/or torch are not installed.\n"
            "Run: pip install transformers torch torchaudio"
        ) from exc

    print(f"[MusicGen] Loading {_MODEL_ID} (first use — downloading if not cached)…", flush=True)
    _processor = AutoProcessor.from_pretrained(_MODEL_ID)
    _model = MusicgenForConditionalGeneration.from_pretrained(_MODEL_ID)
    print("[MusicGen] Model ready.", flush=True)


def _get() -> tuple:
    global _model, _processor
    if _model is None:
        with _lock:
            if _model is None:
                _load()
    return _model, _processor


def generate_music(prompt: str, duration: int = 15) -> bytes:
    """
    Generate instrumental music from a text description and return raw WAV bytes.

    Parameters
    ----------
    prompt   : natural-language description (e.g. "chill lo-fi hip-hop beat, soft piano")
    duration : target length in seconds (clamped 5–30)
    """
    import numpy as np
    import torch

    duration = max(5, min(30, duration))
    model, processor = _get()

    # MusicGen generates at 50 tokens/second; num tokens ≈ duration × 50
    max_new_tokens = int(duration * 50)

    print(f"[MusicGen] Generating: '{prompt[:80]}' ({duration}s, ~{max_new_tokens} tokens)…", flush=True)

    inputs = processor(text=[prompt], padding=True, return_tensors="pt")

    with torch.no_grad():
        audio_values = model.generate(**inputs, max_new_tokens=max_new_tokens)

    # audio_values: [batch, channels, samples]
    audio: np.ndarray = audio_values[0, 0].cpu().numpy()   # shape: [samples]

    # Normalise and convert to int16 PCM
    audio = np.clip(audio, -1.0, 1.0)
    audio_int16 = (audio * 32767).astype(np.int16)

    sample_rate: int = model.config.audio_encoder.sampling_rate

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)          # 16-bit PCM
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())

    wav_bytes = buf.getvalue()
    print(f"[MusicGen] Done — {len(wav_bytes) // 1024} KB WAV @ {sample_rate} Hz", flush=True)
    return wav_bytes
