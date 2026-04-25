from __future__ import annotations

import threading
import re

import numpy as np


class WhisperSTT:
    """
    Local speech-to-text using faster-whisper.
    The model is loaded once at construction and kept resident in memory.
    On M4 Max: base.en transcribes a 5s clip in ~150-200ms on CPU/int8.
    """

    def __init__(
        self,
        model_size: str = "base.en",
        device: str = "cpu",
        compute_type: str = "int8",
        beam_size: int = 1,
        vad_filter: bool = False,
        language: str | None = None,
        initial_prompt: str | None = None,
    ) -> None:
        from faster_whisper import WhisperModel

        if model_size.endswith(".en") and language and language.lower() not in {"en", "english"}:
            # English-only checkpoints cannot transcribe other languages.
            model_size = model_size.replace(".en", "")

        self._beam_size = beam_size
        self._vad_filter = vad_filter
        self._language = None if not language or language.lower() in {"auto", "none"} else language
        self._initial_prompt = initial_prompt.strip() if initial_prompt else None

        print(f"  Loading Whisper '{model_size}' ({device}/{compute_type})…", flush=True)
        print("  First run may take a few minutes while model files download. Please wait.", flush=True)

        loading_done = threading.Event()

        def _progress_logger() -> None:
            elapsed = 0
            while not loading_done.wait(timeout=5.0):
                elapsed += 5
                print(f"    still loading Whisper… {elapsed}s", flush=True)

        progress_thread = threading.Thread(target=_progress_logger, daemon=True)
        progress_thread.start()

        try:
            self._model = WhisperModel(model_size, device=device, compute_type=compute_type)
        except Exception as exc:
            if device.lower() == "mps":
                print(f"  MPS init failed ({exc}). Falling back to cpu/int8…", flush=True)
                self._model = WhisperModel(model_size, device="cpu", compute_type="int8")
            else:
                raise
        finally:
            loading_done.set()
            progress_thread.join(timeout=0.2)

        print("  Whisper ready.")

    def warmup(self) -> None:
        """Run a silent clip through the model to trigger JIT compilation."""
        silence = np.zeros(16000, dtype=np.float32)  # 1 second of silence
        list(
            self._model.transcribe(
                silence,
                language=self._language,
                vad_filter=True,
                initial_prompt=self._initial_prompt,
            )[0]
        )

    def set_initial_prompt(self, prompt: str | None) -> None:
        """Update the runtime transcription hint text used by subsequent turns."""
        self._initial_prompt = (prompt or "").strip() or None

    def transcribe(
        self,
        pcm_bytes: bytes,
        sample_rate: int = 16000,
        language_override: str | None = None,
        fast_mode: bool = False,
    ) -> str:
        """
        Transcribe raw int16 PCM bytes to text.
        Returns empty string if audio is too short or silent.
        """
        if not pcm_bytes or len(pcm_bytes) < 2048:
            return ""

        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        audio = self._normalize_audio(audio)

        language = language_override if language_override is not None else self._language
        beam = 1 if fast_mode else self._beam_size
        use_vad = False if fast_mode else self._vad_filter

        text = self._decode(
            audio,
            beam_size=beam,
            vad_filter=use_vad,
            language=language,
        )
        if text and self._looks_like_cjk(text) and language != "en":
            # If Whisper drifts into another script, retry as English once.
            text = self._decode(audio, beam_size=beam, vad_filter=use_vad, language="en")
        if text:
            return text

        # Fallback pass: permissive decode for quiet/noisy captures.
        # If language auto-detection struggled, retry in English which helps
        # with Caribbean Creole/English code-switching in many cases.
        if fast_mode:
            # One extra quick retry with auto language can recover short
            # Caribbean-accent interruption words (e.g., "wait", "stahp").
            if language is not None:
                return self._decode(audio, beam_size=1, vad_filter=False, language=None)
            return ""
        return self._decode(audio, beam_size=1, vad_filter=False, language="en")

    @staticmethod
    def _looks_like_cjk(text: str) -> bool:
        if not text:
            return False
        return bool(re.search(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", text))

    def _normalize_audio(self, audio: np.ndarray) -> np.ndarray:
        """Apply gentle gain normalization to help low-volume speech."""
        if audio.size == 0:
            return audio
        rms = float(np.sqrt(np.mean(audio ** 2)) + 1e-8)
        target_rms = 0.06
        if rms < target_rms:
            gain = min(8.0, target_rms / rms)
            audio = np.clip(audio * gain, -1.0, 1.0)
        return audio

    def _decode(
        self,
        audio: np.ndarray,
        beam_size: int,
        vad_filter: bool,
        language: str | None,
    ) -> str:
        segments, _ = self._model.transcribe(
            audio,
            language=language,
            beam_size=beam_size,
            vad_filter=vad_filter,
            vad_parameters={"min_silence_duration_ms": 300},
            initial_prompt=self._initial_prompt,
        )
        return " ".join(seg.text for seg in segments).strip()
