from __future__ import annotations

import os
import re
import subprocess
import tempfile
import threading


# ── Shared helpers ────────────────────────────────────────────────────────────

_CLEANUP = re.compile(
    r"(\*+|`+|#{1,6}\s?|"
    r"\[([^\]]+)\]\([^\)]+\)|"
    r"https?://\S+|"
    r"^\s*[-•]\s)",
    re.MULTILINE,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _clean(text: str) -> str:
    text = _CLEANUP.sub(lambda m: m.group(2) if m.group(2) else " ", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def _split_sentences(text: str) -> list[str]:
    text = _clean(text)
    return [p.strip() for p in _SENTENCE_SPLIT.split(text) if p.strip()]


# ── macOS say ─────────────────────────────────────────────────────────────────

class MacOSTTS:
    """Built-in macOS `say` — zero setup, zero cost, works fully offline."""

    def __init__(self, voice: str = "Flo (English (UK))", rate: int = 175) -> None:
        self._voice = self._resolve_voice(voice)
        self._rate = str(rate)
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._stop_requested = threading.Event()

    @staticmethod
    def _available_voices() -> set[str]:
        try:
            out = subprocess.run(
                ["say", "-v", "?"],
                capture_output=True,
                text=True,
                check=False,
            ).stdout
            voices: set[str] = set()
            for line in out.splitlines():
                if not line.strip():
                    continue
                name = line.split()[0]
                if name:
                    voices.add(name)
            return voices
        except Exception:
            return set()

    def _resolve_voice(self, requested: str) -> str:
        voices = self._available_voices()
        if not voices:
            return requested
        if requested in voices:
            return requested
        short = requested.split("(")[0].strip()
        if short in voices:
            print(f"[Nova] macOS voice '{requested}' not found — using '{short}'.")
            return short
        if "Samantha" in voices:
            print(f"[Nova] macOS voice '{requested}' not found — using 'Samantha'.")
            return "Samantha"
        fallback = sorted(voices)[0]
        print(f"[Nova] macOS voice '{requested}' not found — using '{fallback}'.")
        return fallback

    def speak(self, text: str) -> None:
        self._stop_requested.clear()
        self._speak_once(text)

    def _speak_once(self, text: str) -> None:
        text = _clean(text)
        if not text:
            return
        with self._lock:
            if self._stop_requested.is_set():
                return
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
            proc = subprocess.Popen(
                ["say", "-v", self._voice, "-r", self._rate, text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._proc = proc
        code = proc.wait()
        if code != 0 and not self._stop_requested.is_set():
            # Retry once with default voice in case the configured voice is invalid.
            proc = subprocess.Popen(
                ["say", "-r", self._rate, text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            with self._lock:
                self._proc = proc
            proc.wait()
        with self._lock:
            if self._proc is proc:
                self._proc = None

    def speak_streaming(self, text: str) -> None:
        self._stop_requested.clear()
        for sentence in _split_sentences(text):
            if self._stop_requested.is_set():
                break
            self._speak_once(sentence)

    def stop(self) -> None:
        self._stop_requested.set()
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
                self._proc = None


# ── Kokoro ────────────────────────────────────────────────────────────────────

class KokoroTTS:
    """
    Kokoro v0.23 local neural TTS — free, offline, high quality.
    Falls back to MacOSTTS if kokoro is not installed or fails.
    """

    SAMPLE_RATE = 24000

    def __init__(
        self,
        voice: str = "bf_emma",
        speed: float = 1.0,
        lang_code: str = "b",
        fallback: "MacOSTTS | None" = None,
    ) -> None:
        self._voice = voice
        self._speed = speed
        self._fallback = fallback or MacOSTTS()
        self._pipeline = None
        self._stop_requested = threading.Event()

        try:
            from kokoro import KPipeline
            self._pipeline = KPipeline(lang_code=lang_code, repo_id="hexgrad/Kokoro-82M")
            print(f"[Nova] Kokoro TTS ready — voice: {voice}")
        except Exception as exc:
            print(f"[Nova] Kokoro init failed: {exc} — using macOS say.")

    def speak(self, text: str) -> None:
        self._stop_requested.clear()
        self._speak_once(text)

    def _speak_once(self, text: str) -> None:
        text = _clean(text)
        if not text:
            return
        if self._stop_requested.is_set():
            return
        if not self._pipeline:
            self._fallback.speak(text)
            return
        try:
            import sounddevice as sd
            generator = self._pipeline(text, voice=self._voice, speed=self._speed)
            for _, _, audio in generator:
                if self._stop_requested.is_set():
                    sd.stop()
                    return
                sd.play(audio, samplerate=self.SAMPLE_RATE)
                sd.wait()
        except Exception as exc:
            print(f"[Nova] Kokoro error: {exc} — falling back to say.")
            self._fallback.speak(text)

    def speak_streaming(self, text: str) -> None:
        self._stop_requested.clear()
        for sentence in _split_sentences(text):
            if self._stop_requested.is_set():
                break
            self._speak_once(sentence)

    def stop(self) -> None:
        self._stop_requested.set()
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass
        self._fallback.stop()


# ── ElevenLabs ────────────────────────────────────────────────────────────────

class ElevenLabsTTS:
    """
    ElevenLabs neural TTS — natural, expressive, low-latency.
    Falls back to MacOSTTS automatically if the API key is missing or the
    request fails.
    """

    def __init__(
        self,
        api_key: str,
        voice_id: str = "XB0fDUnXU5powFXDhCwa",
        voice_name: str | None = None,
        model_id: str = "eleven_turbo_v2_5",
        stability: float = 0.5,
        similarity_boost: float = 0.85,
        playback_volume: float = 0.45,
        fallback: MacOSTTS | None = None,
    ) -> None:
        self._api_key = api_key
        self._voice_id = voice_id
        self._voice_name = voice_name.strip() if voice_name else None
        self._model_id = model_id
        self._stability = stability
        self._similarity_boost = similarity_boost
        self._playback_volume = str(playback_volume)
        self._fallback = fallback or MacOSTTS()
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._client = None
        self._stop_requested = threading.Event()

        if api_key:
            try:
                from elevenlabs.client import ElevenLabs
                self._client = ElevenLabs(api_key=api_key)
                self._voice_id = self._resolve_voice_id(self._voice_name, self._voice_id)
            except Exception as exc:
                print(f"[Nova] ElevenLabs init failed: {exc} — using macOS say.")

    def _resolve_voice_id(self, preferred_name: str | None, fallback_voice_id: str) -> str:
        if not preferred_name or not self._client:
            return fallback_voice_id
        try:
            voices = self._client.voices.get_all()
            voice_list = getattr(voices, "voices", None) or []
            for voice in voice_list:
                name = (getattr(voice, "name", "") or "").strip().lower()
                if name == preferred_name.lower():
                    resolved = getattr(voice, "voice_id", "") or fallback_voice_id
                    print(f"[Nova] ElevenLabs voice set to '{preferred_name}'.")
                    return resolved
            print(
                f"[Nova] ElevenLabs voice '{preferred_name}' not found — using configured voice ID."
            )
            return fallback_voice_id
        except Exception as exc:
            print(
                f"[Nova] Failed to resolve ElevenLabs voice '{preferred_name}': {exc} — using configured voice ID."
            )
            return fallback_voice_id

    def speak(self, text: str) -> None:
        self._stop_requested.clear()
        self._speak_once(text)

    def _speak_once(self, text: str) -> None:
        text = _clean(text)
        if not text:
            return
        if self._stop_requested.is_set():
            return
        if not self._client:
            self._fallback.speak(text)
            return
        try:
            self._speak_elevenlabs(text)
        except Exception as exc:
            print(f"[Nova] ElevenLabs error: {exc} — falling back to say.")
            self._fallback.speak(text)

    def _speak_elevenlabs(self, text: str) -> None:
        audio_gen = self._client.text_to_speech.convert(
            text=text,
            voice_id=self._voice_id,
            model_id=self._model_id,
            voice_settings={
                "stability": self._stability,
                "similarity_boost": self._similarity_boost,
            },
        )
        audio_bytes = b"".join(audio_gen)

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(audio_bytes)
            path = f.name

        try:
            with self._lock:
                if self._stop_requested.is_set():
                    return
                proc = subprocess.Popen(
                    ["afplay", "-v", self._playback_volume, path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self._proc = proc
            proc.wait()
            with self._lock:
                if self._proc is proc:
                    self._proc = None
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def speak_streaming(self, text: str) -> None:
        """Speak sentence-by-sentence for low time-to-first-word."""
        self._stop_requested.clear()
        for sentence in _split_sentences(text):
            if self._stop_requested.is_set():
                break
            self._speak_once(sentence)

    def stop(self) -> None:
        self._stop_requested.set()
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
                self._proc = None
        self._fallback.stop()


# ── Factory ───────────────────────────────────────────────────────────────────

def create_tts(settings) -> "KokoroTTS | ElevenLabsTTS | MacOSTTS":
    """
    Build the right TTS engine from settings.
    Returns ElevenLabsTTS (with MacOSTTS fallback) if engine=elevenlabs and
    an API key is present; otherwise returns MacOSTTS directly.
    """
    tts_cfg = settings.voice.get("tts", {})
    engine = tts_cfg.get("engine", "macos_say")
    macos_cfg = tts_cfg.get("macos_say", {})
    macos = MacOSTTS(
        voice=macos_cfg.get("voice", "Flo (English (UK))"),
        rate=macos_cfg.get("rate", 175),
    )

    if engine == "kokoro":
        kok_cfg = tts_cfg.get("kokoro", {})
        return KokoroTTS(
            voice=kok_cfg.get("voice", "bf_isabella"),
            speed=kok_cfg.get("speed", 1.0),
            lang_code=kok_cfg.get("lang_code", "b"),
            fallback=macos,
        )

    if engine == "elevenlabs":
        el_cfg = tts_cfg.get("elevenlabs", {})
        api_key = getattr(settings, "elevenlabs_api_key", "") or ""
        if not api_key:
            print("[Nova] No ELEVENLABS_API_KEY found — using macOS say.")
            return macos
        return ElevenLabsTTS(
            api_key=api_key,
            voice_id=el_cfg.get("voice_id", "XB0fDUnXU5powFXDhCwa"),
            voice_name=el_cfg.get("voice_name"),
            model_id=el_cfg.get("model_id", "eleven_turbo_v2_5"),
            stability=el_cfg.get("stability", 0.5),
            similarity_boost=el_cfg.get("similarity_boost", 0.85),
            playback_volume=el_cfg.get("playback_volume", 0.45),
            fallback=macos,
        )

    return macos
