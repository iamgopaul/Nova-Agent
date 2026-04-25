from __future__ import annotations

import asyncio
import re
import threading
import time
from collections.abc import Callable
from typing import Literal

from config.settings import Settings
from gaaia.agent.orchestrator import Orchestrator
from gaaia.approval.manager import ApprovalRequest
from gaaia.voice.audio_io import AudioRecorder
from gaaia.voice.hotkey import PTTListener
from gaaia.services.speaker_identity import SpeakerIdentityStore
from gaaia.voice.speaker_focus import SpeakerFocusManager
from gaaia.voice.stt import WhisperSTT
from gaaia.voice.tts import create_tts

State = Literal["idle", "recording", "thinking", "speaking"]


class VoicePipeline:
    """
    The complete push-to-talk voice loop:

      [hold hotkey] → record mic → STT → Orchestrator → TTS → [speak]

    Callbacks (all optional, all called from a background thread):
      on_state_change(state: str)  — 'idle' | 'recording' | 'thinking' | 'speaking'
      on_transcript(text: str)     — what the user said
      on_response_chunk(text: str) — streamed response token
      on_response_done(text: str)  — complete response after TTS begins
    """

    def __init__(
        self,
        settings: Settings,
        orchestrator: Orchestrator,
        session_id: str,
        approval_callback: Callable[[ApprovalRequest], bool] | None = None,
    ) -> None:
        voice = settings.voice
        stt_cfg = voice.get("stt", {})
        audio_cfg = voice.get("audio", {})
        hotkey_cfg = voice.get("hotkey", {})

        self._orchestrator = orchestrator
        self._session_id = session_id
        self._approval_callback = approval_callback

        self._recorder = AudioRecorder(
            sample_rate=audio_cfg.get("sample_rate", 16000),
        )
        self._sample_rate = audio_cfg.get("sample_rate", 16000)
        self._stt = WhisperSTT(
            model_size=stt_cfg.get("model_size", "base.en"),
            device=stt_cfg.get("device", "cpu"),
            compute_type=stt_cfg.get("compute_type", "int8"),
            beam_size=stt_cfg.get("beam_size", 1),
            vad_filter=stt_cfg.get("vad_filter", False),
            language=stt_cfg.get("language", None),
            initial_prompt=stt_cfg.get("initial_prompt", None),
        )
        self._tts = create_tts(settings)
        self._hotkey = PTTListener(
            hotkey_str=hotkey_cfg.get("push_to_talk", "<ctrl>+<space>"),
        )
        self._activation_sound = audio_cfg.get("activation_sound", True)
        self._silence_threshold_db = audio_cfg.get("silence_threshold_db", -38.0)
        self._silence_duration_s = audio_cfg.get("silence_duration_s", 0.9)
        self._min_speech_duration_s = audio_cfg.get("min_speech_duration_s", 0.35)
        self._pre_speech_timeout_s = audio_cfg.get("pre_speech_timeout_s", 4.0)
        self._max_turn_duration_s = audio_cfg.get("max_turn_duration_s", 12.0)
        self._voice_mode = voice.get("mode", "fast")
        self._allow_barge_in = voice.get("allow_barge_in", True)
        self._interrupt_on_any_speech = voice.get("interrupt_on_any_speech", True)
        focus_cfg = voice.get("speaker_focus", {})
        self._require_wake_word = focus_cfg.get("require_wake_word", True)
        self._wake_words = [
            w.strip().lower() for w in focus_cfg.get("wake_words", ["gaaia"]) if str(w).strip()
        ]
        self._speaker_focus = SpeakerFocusManager(
            profile_path=settings.data_dir / "voice_profile.json",
            enabled=focus_cfg.get("voice_lock_enabled", True),
            similarity_threshold=float(focus_cfg.get("similarity_threshold", 0.68)),
            enrollment_samples=int(focus_cfg.get("enrollment_samples", 3)),
            sample_rate=audio_cfg.get("sample_rate", 16000),
        )
        self._speaker_identity = SpeakerIdentityStore(
            profile_path=settings.data_dir / "speaker_profiles.json",
            enabled=bool(focus_cfg.get("remember_speakers", True)),
            similarity_threshold=float(focus_cfg.get("multi_speaker_similarity_threshold", 0.76)),
            sample_rate=int(audio_cfg.get("sample_rate", 16000)),
            auto_create_unknown=bool(focus_cfg.get("auto_create_unknown_speakers", False)),
        )
        self._last_wakeword_hint_ts = 0.0
        self._last_voice_lock_hint_ts = 0.0
        self._last_identity_prompt_ts = 0.0
        self._voice_mismatch_count = 0
        self._awaiting_identity = False

        # Callbacks — wired by the desktop app
        self.on_state_change: Callable[[State], None] | None = None
        self.on_status: Callable[[str], None] | None = None
        self.on_transcript: Callable[[str], None] | None = None
        self.on_response_chunk: Callable[[str], None] | None = None
        self.on_response_done: Callable[[str], None] | None = None
        self.on_conversation_end: Callable[[], None] | None = None
        self.on_error: Callable[[str], None] | None = None

        self._busy = threading.Lock()
        self._conversation_stop = threading.Event()
        self._conversation_thread: threading.Thread | None = None

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        """Start listening for the push-to-talk hotkey. Non-blocking."""
        self._stt.warmup()
        try:
            self._hotkey.start(
                on_activate=self._on_key_pressed,
                on_deactivate=self._on_key_released,
            )
        except Exception as exc:
            print(
                f"\n[GAIA] Hotkey listener failed to start: {exc}\n"
                "  Text input still works.\n"
                "  For voice: System Settings → Privacy & Security → Accessibility → add Terminal\n"
            )

    def stop(self) -> None:
        self.stop_live_conversation()
        self._hotkey.stop()
        self._tts.stop()

    def start_live_conversation(self) -> None:
        """Start hands-free turn-taking until stop_live_conversation() is called."""
        if self._conversation_thread and self._conversation_thread.is_alive():
            return
        self._conversation_stop.clear()
        self._conversation_thread = threading.Thread(
            target=self._live_conversation_loop,
            daemon=True,
        )
        self._conversation_thread.start()

    def stop_live_conversation(self) -> None:
        """Stop hands-free conversation and any active TTS playback."""
        self._conversation_stop.set()
        self._tts.stop()

    # ── Hotkey handlers ───────────────────────────────────────────────

    def _on_key_pressed(self) -> None:
        if not self._busy.acquire(blocking=False):
            return  # already processing a turn
        self._tts.stop()
        self._set_state("recording")
        if self._activation_sound:
            AudioRecorder.play_system_sound("Tink")
        self._recorder.start()

    def _on_key_released(self) -> None:
        if self._activation_sound:
            AudioRecorder.play_system_sound("Pop")
        pcm = self._recorder.stop()

        try:
            self._process(pcm)
        finally:
            self._busy.release()
            self._set_state("idle")

    _STOP_RE = re.compile(
        r"^\s*(shut\s+up|stop(\s+talking|\s+speaking)?|be\s+quiet|quiet|silence|shush|enough|ok+ay?\s+stop|wait(\s+please)?|pause|hold\s+on)\s*[.!]?\s*$",
        re.IGNORECASE,
    )
    _INTERRUPT_RE = re.compile(
        r"\b(stop|stahp|shut\s+up|be\s+quiet|quiet|silence|shush|wait|weyt|hold\s+on|hold\s+up|pause|hang\s+on|enough|nough|cut\s+it|zip\s+it|hush|not\s+now|give\s+me\s+a\s+sec|one\s+sec|one\s+second)\b",
        re.IGNORECASE,
    )
    _ENROLL_RE = re.compile(
        r"\b(?:learn|train|enroll)(?:\s+my)?\s+voice\b|\bvoice\s+lock\s+on\b",
        re.IGNORECASE,
    )
    _FORGET_RE = re.compile(
        r"\b(?:forget|reset|clear|remove)\s+(?:my\s+)?voice\b|\bvoice\s+lock\s+off\b",
        re.IGNORECASE,
    )

    # ── Processing ────────────────────────────────────────────────────

    def _process(self, pcm: bytes) -> None:
        if not pcm:
            if self.on_status:
                self.on_status("No audio captured")
            return

        if self._awaiting_identity:
            self._handle_identity_reply(pcm)
            return

        if self.on_status:
            self.on_status("Transcribing")
        self._set_state("thinking")
        transcript = self._stt.transcribe(pcm)
        if not transcript:
            if self._is_live_mode():
                if self.on_status:
                    self.on_status("No speech detected")
                return
            if self.on_error:
                self.on_error("I didn't catch that. Try speaking a bit louder or closer to the mic.")
            return

        speaker_label = self._identify_speaker(pcm, transcript)
        if speaker_label is None:
            return

        transcript = self._prefix_speaker(transcript, speaker_label)

        accepted, cleaned_transcript = self._filter_for_wake_word(transcript)
        if not accepted:
            # Ignore ambient/background speech that doesn't address GAAIA.
            return
        transcript = cleaned_transcript or transcript

        if self._FORGET_RE.search(transcript):
            removed = self._speaker_focus.clear_profile()
            if removed:
                self._local_reply("Voice lock disabled. I forgot your saved voice profile.")
            else:
                self._local_reply("I couldn't clear the voice profile just now.")
            return

        if self._ENROLL_RE.search(transcript):
            if not self._speaker_focus.enabled:
                self._local_reply("Voice lock is off in settings right now.")
                return
            self._speaker_focus.start_enrollment()
            self._local_reply(
                "Got it. Voice training started. Say three short commands with 'GAIA' at the start."
            )
            return

        if self._speaker_focus.is_enrolling:
            done, remaining = self._speaker_focus.add_enrollment_sample(pcm)
            if done:
                self._local_reply("Perfect. Voice lock is now on and tuned to you.")
            elif remaining > 0:
                self._local_reply(f"Nice. {remaining} more sample{'s' if remaining != 1 else ''}.")
            else:
                self._local_reply("That sample was too short. Try again.")
            return

        if self._speaker_focus.has_profile:
            matched, _ = self._speaker_focus.verify(pcm)
            if not matched:
                self._voice_mismatch_count += 1
                # Fail-safe: don't permanently lock out the user on noisy captures.
                if self._voice_mismatch_count >= 3:
                    self._voice_mismatch_count = 0
                    if self.on_error:
                        self.on_error("Voice lock was uncertain, so I allowed this turn. Say 'GAAIA learn my voice' to retrain.")
                else:
                    now = time.time()
                    if self.on_error and (now - self._last_voice_lock_hint_ts) > 6.0:
                        self._last_voice_lock_hint_ts = now
                        self.on_error("Voice lock active: I only respond to your enrolled voice.")
                    return
            else:
                self._voice_mismatch_count = 0

        if self._STOP_RE.match(transcript):
            self._tts.stop()
            self._set_state("idle")
            return

        if self.on_transcript:
            self.on_transcript(transcript)

        response_chunks: list[str] = []

        def collect(chunk: str) -> None:
            response_chunks.append(chunk)
            if self.on_response_chunk:
                self.on_response_chunk(chunk)

        # asyncio.run() is safe here — we're in a plain daemon thread
        try:
            response = asyncio.run(
                self._orchestrator.run(
                    user_message=transcript,
                    session_id=self._session_id,
                    stream_callback=collect,
                    approval_callback=self._approval_callback,
                    mode=self._voice_mode,
                )
            )
        except Exception as exc:
            if self.on_error:
                self.on_error(f"Voice response failed: {exc}")
            return

        if self.on_response_done:
            self.on_response_done(response)

        if self._is_live_mode() and self._allow_barge_in:
            self._set_state("recording")
        else:
            self._set_state("speaking")
        self._speak_with_barge_in(response)

    def _live_conversation_loop(self) -> None:
        """Record -> transcribe -> respond -> speak in a continuous loop."""
        try:
            while not self._conversation_stop.is_set():
                if not self._busy.acquire(blocking=False):
                    continue
                try:
                    if self.on_status:
                        self.on_status("Requesting microphone")
                    self._set_state("recording")
                    if self.on_status:
                        self.on_status("Capturing audio")
                    pcm = self._recorder.record_until_silence(
                        threshold_db=self._silence_threshold_db,
                        silence_duration_s=self._silence_duration_s,
                        min_speech_duration_s=self._min_speech_duration_s,
                        pre_speech_timeout_s=self._pre_speech_timeout_s,
                        max_duration_s=self._max_turn_duration_s,
                        stop_event=self._conversation_stop,
                    )
                    if self._conversation_stop.is_set():
                        break
                    if self.on_status:
                        self.on_status("Sending audio to GAAIA")
                    self._process(pcm)
                finally:
                    self._busy.release()
        except Exception as exc:
            if self.on_error:
                self.on_error(f"Live voice mode failed: {exc}")

        self._set_state("idle")

    def _identify_speaker(self, pcm: bytes, transcript: str) -> str | None:
        if not self._speaker_identity.enabled:
            return None

        try:
            speaker_name, confidence, declared = self._speaker_identity.identify(pcm, transcript)
        except Exception:
            return None

        if speaker_name:
            reference = self._speaker_identity.reference_name(speaker_name)
            self._remember_speaker(speaker_name, display_name=reference, primary=declared)
            return reference

        now = time.time()
        if (now - self._last_identity_prompt_ts) > 8.0:
            self._last_identity_prompt_ts = now
            self._awaiting_identity = True
            known_name = self._known_user_name()
            if known_name:
                self._local_reply(f"I don't think that's {known_name}. Who am I speaking with?")
            else:
                self._local_reply("I don't recognize that voice yet. Who am I speaking with?")
        return None

    def _handle_identity_reply(self, pcm: bytes) -> None:
        self._set_state("thinking")
        transcript = self._stt.transcribe(pcm)
        if not transcript:
            self._local_reply("I missed that. Please say your name once more.")
            return

        name = None
        try:
            name = self._speaker_identity.learn_identity(pcm, transcript, fallback_text=transcript)
        except Exception:
            name = None

        if not name:
            self._local_reply("Please say your name as 'I'm ...' or 'My name is ...'.")
            return

        self._awaiting_identity = False
        reference = self._speaker_identity.reference_name(name)
        self._remember_speaker(name, display_name=reference, primary=True)
        self._local_reply(f"Got it, {reference}. I'll remember you.")

    def _remember_speaker(self, name: str, display_name: str | None = None, primary: bool = False) -> None:
        try:
            memory = self._orchestrator.memory
        except Exception:
            memory = None
        if memory is None:
            return

        try:
            if primary or not memory.get_fact_value("user_name", "").strip():
                memory.save_fact("user_name", name, source="voice-id")
            if display_name:
                memory.save_fact("user_display_name", display_name, source="voice-id")
            memory.save_fact("last_speaker", name, source="voice-id")
        except Exception:
            pass

    def _known_user_name(self) -> str:
        try:
            memory = self._orchestrator.memory
        except Exception:
            return ""
        try:
            return memory.get_fact_value("user_name", "").strip()
        except Exception:
            return ""

    @staticmethod
    def _prefix_speaker(transcript: str, speaker_label: str) -> str:
        cleaned = transcript.strip()
        if not cleaned:
            return cleaned
        return f"[Speaker: {speaker_label}] {cleaned}"

    # ── Helpers ───────────────────────────────────────────────────────

    def _set_state(self, state: State) -> None:
        if self.on_state_change:
            self.on_state_change(state)

    def _filter_for_wake_word(self, transcript: str) -> tuple[bool, str]:
        """Return (accepted, cleaned_transcript) based on wake-word policy."""
        text = transcript.strip()
        if not text:
            return False, ""
        if not self._require_wake_word:
            return True, text

        for wake in self._wake_words:
            # Accept wake word anywhere in the phrase, not only at the start.
            pattern = rf"\b(?:hey\s+)?{re.escape(wake)}\b[,:\-]?\s*"
            if re.search(pattern, text, flags=re.IGNORECASE):
                cleaned = re.sub(pattern, "", text, count=1, flags=re.IGNORECASE).strip(" ,:-")
                # If only wake word is spoken, ignore gracefully.
                if not cleaned:
                    return False, ""
                return True, cleaned

        # Wake-word mode is active: rate-limit the hint to avoid transcript spam.
        now = time.time()
        if self.on_error and (now - self._last_wakeword_hint_ts) > 6.0:
            self._last_wakeword_hint_ts = now
            self.on_error("Say 'GAIA' in your request so I know it's for me.")
        return False, ""

    def _speak_with_barge_in(self, response: str) -> None:
        """Speak assistant text and allow spoken interruption commands while talking."""
        if not response:
            return

        # In non-live modes, keep simple blocking TTS behavior.
        is_live_mode = (
            self._conversation_thread is not None
            and self._conversation_thread.is_alive()
            and not self._conversation_stop.is_set()
        )
        if not is_live_mode or not self._allow_barge_in:
            self._tts.speak_streaming(response)
            return

        done = threading.Event()

        def run_tts() -> None:
            try:
                self._tts.speak_streaming(response)
            finally:
                done.set()

        def run_listener() -> None:
            # Use an independent recorder while TTS is active so interruption
            # detection runs concurrently and can preempt speech quickly.
            listener = AudioRecorder(sample_rate=self._sample_rate)
            speech_miss_count = 0
            started_at = time.monotonic()
            baseline_dbfs: float | None = None
            while not done.is_set() and not self._conversation_stop.is_set():
                try:
                    pcm = listener.record_until_silence(
                        threshold_db=min(-45.0, self._silence_threshold_db),
                        silence_duration_s=0.25,
                        min_speech_duration_s=0.12,
                        pre_speech_timeout_s=0.80,
                        max_duration_s=1.80,
                        stop_event=done,
                    )
                except Exception as exc:
                    if self.on_error:
                        self.on_error(f"Barge-in listener error: {exc}")
                    continue
                if done.is_set() or not pcm:
                    continue

                dbfs = self._pcm_dbfs(pcm)
                if baseline_dbfs is None:
                    baseline_dbfs = dbfs
                elif (time.monotonic() - started_at) < 1.5:
                    # Adapt quickly at the start while GAAIA playback dominates input.
                    baseline_dbfs = 0.85 * baseline_dbfs + 0.15 * dbfs

                # Hard fail-safe: if user speech clearly dominates playback energy,
                # interrupt immediately without waiting for ASR keywords.
                if (
                    self._interrupt_on_any_speech
                    and baseline_dbfs is not None
                    and dbfs > max(-42.0, baseline_dbfs + 2.0)
                ):
                    self._tts.stop()
                    done.set()
                    if self.on_response_done:
                        self.on_response_done("Got you. I'm listening.")
                    self._set_state("recording")
                    break

                # Force a very fast, English-biased decode path for interruption words.
                heard = self._stt.transcribe(
                    pcm,
                    language_override="en",
                    fast_mode=True,
                )
                if not heard:
                    heard = self._stt.transcribe(pcm, language_override=None, fast_mode=True)
                if not heard:
                    if self._interrupt_on_any_speech and self._is_strong_speech(pcm):
                        speech_miss_count += 1
                        if speech_miss_count >= 2:
                            self._tts.stop()
                            done.set()
                            if self.on_response_done:
                                self.on_response_done("Got you. I'm listening.")
                            self._set_state("recording")
                            break
                    continue

                speech_miss_count = 0

                if self._INTERRUPT_RE.search(heard):
                    self._tts.stop()
                    done.set()
                    if self.on_transcript:
                        self.on_transcript(heard)
                    if self.on_response_done:
                        self.on_response_done("Okay. I stopped. Go ahead.")
                    # Immediately reflect that GAAIA is listening again.
                    self._set_state("recording")
                    break

                # Fallback: if user starts talking while GAAIA is speaking,
                # treat that as a barge-in unless it looks like speaker echo.
                if self._interrupt_on_any_speech and not self._looks_like_echo(heard, response):
                    self._tts.stop()
                    done.set()
                    if self.on_transcript:
                        self.on_transcript(heard)
                    if self.on_response_done:
                        self.on_response_done("Got you. I'm listening.")
                    self._set_state("recording")
                    break

        speaker = threading.Thread(target=run_tts, daemon=True)
        listener = threading.Thread(target=run_listener, daemon=True)
        speaker.start()
        listener.start()

        # Keep listener alive for the full speaking window so interruption works
        # even on long responses.
        while speaker.is_alive() and not self._conversation_stop.is_set():
            speaker.join(timeout=0.1)
        done.set()
        listener.join(timeout=0.8)

    def _local_reply(self, text: str) -> None:
        """Reply without calling the model (used for local voice-control commands)."""
        if self.on_response_done:
            self.on_response_done(text)
        self._set_state("speaking")
        self._speak_with_barge_in(text)

    def _is_live_mode(self) -> bool:
        return (
            self._conversation_thread is not None
            and self._conversation_thread.is_alive()
            and not self._conversation_stop.is_set()
        )

    def _is_strong_speech(self, pcm: bytes) -> bool:
        if not pcm:
            return False
        # Estimate voiced interruption energy quickly from PCM bytes.
        import numpy as np

        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        if samples.size == 0:
            return False
        duration_s = samples.size / float(self._sample_rate)
        dbfs = self._pcm_dbfs(pcm)
        return duration_s >= 0.10 and dbfs > -44.0

    @staticmethod
    def _pcm_dbfs(pcm: bytes) -> float:
        import numpy as np

        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        if samples.size == 0:
            return -120.0
        rms = float(np.sqrt(np.mean(samples ** 2)) + 1e-12)
        return 20.0 * np.log10(rms)

    @staticmethod
    def _looks_like_echo(heard: str, current_response: str) -> bool:
        """Heuristic: ignore transcripts that are likely GAAIA's own playback."""
        heard_l = re.sub(r"\s+", " ", heard.lower()).strip()
        resp_l = re.sub(r"\s+", " ", current_response.lower()).strip()
        if not heard_l or not resp_l:
            return False
        if heard_l in resp_l:
            return True

        h_words = [w for w in re.findall(r"[a-z']+", heard_l) if len(w) > 1]
        if not h_words:
            return False
        r_words = set(re.findall(r"[a-z']+", resp_l))
        overlap = sum(1 for w in h_words if w in r_words)
        ratio = overlap / max(1, len(h_words))
        if len(h_words) <= 3:
            return ratio >= 0.5
        return ratio >= 0.7
