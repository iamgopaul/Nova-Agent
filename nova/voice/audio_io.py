from __future__ import annotations

import subprocess
import threading
from threading import Event

import numpy as np
import sounddevice as sd
import soundfile as sf


class AudioRecorder:
    """
    Mic recorder with two modes:
      PTT  — start() / stop() for push-to-talk.
      VAD  — record_until_silence() for hands-free conversation.
    """

    def __init__(self, sample_rate: int = 16000, channels: int = 1) -> None:
        self._sr = sample_rate
        self._ch = channels
        self._frames: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._stream: sd.InputStream | None = None

    # ── PTT mode ──────────────────────────────────────────────────────

    def start(self) -> None:
        with self._lock:
            self._frames = []
        self._stream = sd.InputStream(
            samplerate=self._sr,
            channels=self._ch,
            dtype="int16",
            blocksize=1024,
            callback=self._callback,
        )
        self._stream.start()

    def _callback(self, indata: np.ndarray, frames: int, time, status) -> None:
        with self._lock:
            self._frames.append(indata.copy())

    def stop(self) -> bytes:
        """Stop recording and return raw int16 PCM bytes."""
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        with self._lock:
            if not self._frames:
                return b""
            return np.concatenate(self._frames, axis=0).tobytes()

    # ── VAD mode ──────────────────────────────────────────────────────

    def record_until_silence(
        self,
        threshold_db: float = -38.0,
        silence_duration_s: float = 1.2,
        min_speech_duration_s: float = 0.35,
        pre_speech_timeout_s: float = 4.0,
        max_duration_s: float = 30.0,
        stop_event: Event | None = None,
        return_audio_if_threshold_missed: bool = True,
    ) -> bytes:
        """
        Record until the mic goes quiet for silence_duration_s seconds.
        Returns raw int16 PCM bytes. Used for hands-free conversation mode.
        """
        blocksize = 1024
        blocks_for_silence = int(silence_duration_s * self._sr / blocksize)
        blocks_for_min_speech = max(1, int(min_speech_duration_s * self._sr / blocksize))
        blocks_for_pre_speech = max(1, int(pre_speech_timeout_s * self._sr / blocksize))
        max_blocks = int(max_duration_s * self._sr / blocksize)

        all_frames: list[np.ndarray] = []
        silent_blocks = [0]
        speech_blocks = [0]
        total_blocks = [0]
        speech_started = [False]
        done = threading.Event()
        lock = threading.Lock()

        def callback(indata: np.ndarray, frames: int, time, status) -> None:
            with lock:
                all_frames.append(indata.copy())
                # Convert to dBFS (0 dB = max int16). Thresholds like -38 dB
                # only make sense on normalized full-scale audio.
                audio = indata.astype(np.float32) / 32768.0
                rms = np.sqrt(np.mean(audio ** 2))
                db = 20.0 * np.log10(rms + 1e-12)
                if db >= threshold_db:
                    speech_started[0] = True
                    speech_blocks[0] += 1
                    silent_blocks[0] = 0
                else:
                    if speech_started[0]:
                        silent_blocks[0] += 1
                total_blocks[0] += 1
                if (
                    (
                        speech_started[0]
                        and speech_blocks[0] >= blocks_for_min_speech
                        and silent_blocks[0] >= blocks_for_silence
                    )
                    or (not speech_started[0] and total_blocks[0] >= blocks_for_pre_speech)
                    or total_blocks[0] >= max_blocks
                ):
                    done.set()

        stream = sd.InputStream(
            samplerate=self._sr,
            channels=self._ch,
            dtype="int16",
            blocksize=blocksize,
            callback=callback,
        )
        stream.start()
        while not done.wait(timeout=0.1):
            if stop_event and stop_event.is_set():
                break
        stream.stop()
        stream.close()

        with lock:
            if not all_frames:
                return b""
            if not speech_started[0] and not return_audio_if_threshold_missed:
                return b""
            return np.concatenate(all_frames, axis=0).tobytes()

    # ── Playback helpers ──────────────────────────────────────────────

    @staticmethod
    def play_file(path: str) -> None:
        data, sr = sf.read(path, dtype="float32")
        sd.play(data, sr)
        sd.wait()

    @staticmethod
    def play_system_sound(name: str = "Tink") -> None:
        """
        Play a built-in macOS sound non-blocking.
        Common names: Tink, Pop, Glass, Basso, Hero, Purr, Sosumi.
        """
        path = f"/System/Library/Sounds/{name}.aiff"
        subprocess.Popen(
            ["afplay", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
