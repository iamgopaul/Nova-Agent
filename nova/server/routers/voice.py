from __future__ import annotations

import asyncio
import io
import json
import os
import re
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from nova.agent.orchestrator import Orchestrator
from nova.memory.store import MemoryStore
from nova.memory.models import User
from nova.server.dependencies import get_memory, get_optional_user, get_orchestrator
from nova.server.schemas import VoiceResponse
from nova.services.body_detector import pick_frame_best_hands
from nova.services.camera_context import (
    SCENE_UNAVAILABLE,
    camera_who_line,
    hands_ground_truth_block,
)
from nova.services.camera_vision import describe_scene_frame
from nova.services.frame_detection import summarize_detections_for_voice
from nova.services.camera_buffer import get_live_prefix_for_prompt
from nova.services.video_camera import jpeg_frames_from_video_bytes
from nova.services.speaker_identity import SpeakerIdentityStore, extract_declared_name
from nova.services.voice_personalization import compose_stt_prompt, build_whisper_prompt, refresh_stt_prompt
from nova.voice.stt import WhisperSTT

router = APIRouter()


@router.get("/ping")
def voice_router_ping() -> dict:
    """Lightweight health check — confirms the voice router is mounted (debug 404s)."""
    return {"router": "voice", "status": "ok"}

# STT instance — created on first request, kept for the process lifetime
_stt: WhisperSTT | None = None
_kokoro_pipeline = None
_speaker_identity: SpeakerIdentityStore | None = None
_tts_executor = ThreadPoolExecutor(max_workers=2)
_voice_active_until: dict[str, float] = {}
_voice_active_lock = threading.Lock()
# Maps session_id → set of speaker_labels that Nova explicitly asked to introduce themselves.
# A name is only saved when the speaker was in this set on the *previous* turn.
_identity_prompted_sessions: dict[str, set[str]] = {}
_identity_prompt_lock = threading.Lock()


def _require_local_request(request: Request) -> None:
    client_host = (request.client.host if request.client else "") or ""
    if client_host not in {"127.0.0.1", "::1", "localhost"} and not client_host.startswith("::ffff:127.0.0.1"):
        raise HTTPException(status_code=403, detail="Voice identity features are local-only.")


class VoiceSpeakRequest(BaseModel):
    text: str


class VoiceEnrollResponse(BaseModel):
    name: str
    enrolled: bool


_SPEECH_CLEAN_RE = re.compile(
    r"(\*+|`+|#{1,6}\s?|"
    r"\[([^\]]+)\]\([^\)]+\)|"
    r"https?://\S+|"
    r"^\s*[-•]\s)",
    re.MULTILINE,
)


def _wake_word_settings(request: Request) -> tuple[bool, list[str], float]:
    focus_cfg = request.app.state.settings.voice.get("speaker_focus", {})
    require = bool(focus_cfg.get("require_wake_word", False))
    wake_words = [
        str(word).strip().lower()
        for word in focus_cfg.get("wake_words", ["nova", "hey nova"])
        if str(word).strip()
    ]
    active_seconds = float(focus_cfg.get("wake_active_seconds", 45.0))
    return require, wake_words, max(5.0, active_seconds)


def _stt_terms_with_wake_words(base_terms: list[str], wake_words: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for t in [*(base_terms or []), *(wake_words or []), "Nova", "hey nova"]:
        s = str(t).strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def _normalize_wake_homophones(transcript: str) -> str:
    """
    Patch common STT wake-word homophones at the start of an utterance.
    Example: "pain over" -> "hey nova".
    """
    text = (transcript or "").strip()
    if not text:
        return text
    start_map = (
        r"^(\s*)(pain over|payn over|pane over|hey no va|hey n ova|a nova|ay nova)\b[:,.!?\s-]*",
    )
    for pat in start_map:
        if re.search(pat, text, re.IGNORECASE):
            text = re.sub(pat, r"\1hey nova ", text, count=1, flags=re.IGNORECASE).strip()
            break
    return re.sub(r"\s{2,}", " ", text).strip()


def _strip_wake_word(text: str, wake_words: list[str]) -> tuple[bool, str]:
    cleaned = text.strip()
    matched = False
    for wake in wake_words:
        pattern = re.compile(rf"\b{re.escape(wake)}\b[:,.!?\s-]*", re.IGNORECASE)
        if pattern.search(cleaned):
            matched = True
            cleaned = pattern.sub("", cleaned).strip()
    return matched, cleaned


def _is_voice_active(session_id: str, now: float) -> bool:
    with _voice_active_lock:
        expiry = _voice_active_until.get(session_id, 0.0)
        if now >= expiry:
            _voice_active_until.pop(session_id, None)
            return False
        return True


def _touch_voice_active(session_id: str, now: float, active_seconds: float) -> None:
    with _voice_active_lock:
        _voice_active_until[session_id] = now + active_seconds


def _nova_asked_this_speaker(session_id: str, speaker_label: str | None) -> bool:
    """Return True if Nova asked *this* speaker to introduce themselves last turn."""
    key = speaker_label or "_anonymous_"
    with _identity_prompt_lock:
        return key in _identity_prompted_sessions.get(session_id, set())


def _mark_identity_asked(session_id: str, speaker_label: str | None) -> None:
    """Record that Nova just asked this speaker to introduce themselves."""
    key = speaker_label or "_anonymous_"
    with _identity_prompt_lock:
        _identity_prompted_sessions.setdefault(session_id, set()).add(key)


def _clear_identity_asked(session_id: str, speaker_label: str | None) -> None:
    """Clear the pending intro prompt once the speaker has responded with a name."""
    key = speaker_label or "_anonymous_"
    with _identity_prompt_lock:
        _identity_prompted_sessions.get(session_id, set()).discard(key)


def _should_append_identity_prompt(
    session_id: str,
    *,
    known_user: str,
    declared_name: str | None,
    speaker_label: str | None,
    voice_confidence: float,
    speaker_identity: SpeakerIdentityStore,
) -> bool:
    """
    Append a 'who are you?' prompt ONLY when no identity is known for this speaker.
    Once we already asked this exact speaker, don't repeat until they respond.
    """
    # If we already have an enrolled user (and this voice matches), no prompt needed.
    if known_user.strip():
        return False
    # If the user is giving their name right now, no prompt needed.
    if declared_name:
        return False
    # Don't repeat if we already asked this speaker on the previous turn.
    if _nova_asked_this_speaker(session_id, speaker_label):
        return False
    band = speaker_identity.confidence_band(speaker_label, voice_confidence)
    if band != "low":
        return False
    return True


def _clean_spoken_text(text: str) -> str:
    cleaned = _SPEECH_CLEAN_RE.sub(lambda m: m.group(2) if m.group(2) else " ", text)
    cleaned = re.sub(r"\s*&\s*", " and ", cleaned)
    cleaned = re.sub(r"\b@\b", " at ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    if len(cleaned) > 1200:
        cleaned = cleaned[:1200].rstrip() + "..."
    return cleaned


def _convert_with_ffmpeg(data: bytes) -> bytes | None:
    with tempfile.NamedTemporaryFile(suffix=".input", delete=False) as input_file:
        input_path = input_file.name
        input_file.write(data)

    with tempfile.NamedTemporaryFile(suffix=".pcm", delete=False) as output_file:
        output_path = output_file.name

    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                input_path,
                "-ac",
                "1",
                "-ar",
                "16000",
                "-f",
                "s16le",
                output_path,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return None
        return Path(output_path).read_bytes()
    except Exception:
        return None
    finally:
        try:
            os.unlink(input_path)
        except OSError:
            pass
        try:
            os.unlink(output_path)
        except OSError:
            pass


def _synthesize_macos_say(settings, text: str) -> tuple[bytes, str]:
    tts_cfg = settings.voice.get("tts", {})
    macos_cfg = tts_cfg.get("macos_say", {})
    voice = macos_cfg.get("voice", "Samantha")
    short_voice = str(voice).split("(")[0].strip() or "Samantha"
    rate = str(macos_cfg.get("rate", 175))

    with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as tmp:
        output_path = tmp.name
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
        wav_path = tmp_wav.name

    try:
        proc = subprocess.run(
            ["say", "-v", short_voice, "-r", rate, "-o", output_path, text],
            capture_output=True,
            text=True,
            check=False,
        )

        if proc.returncode != 0:
            proc = subprocess.run(
                ["say", "-r", rate, "-o", output_path, text],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                raise RuntimeError((proc.stderr or "macOS say failed").strip())

        convert = subprocess.run(
            ["afconvert", "-f", "WAVE", "-d", "LEI16", output_path, wav_path],
            capture_output=True,
            text=True,
            check=False,
        )
        if convert.returncode == 0:
            with open(wav_path, "rb") as f:
                return f.read(), "audio/wav"

        # Last-resort fallback: return original audio if WAV conversion fails.
        with open(output_path, "rb") as f:
            return f.read(), "audio/aiff"
    finally:
        try:
            os.unlink(output_path)
        except OSError:
            pass
        try:
            os.unlink(wav_path)
        except OSError:
            pass


def _get_kokoro_pipeline(settings):
    global _kokoro_pipeline
    if _kokoro_pipeline is None:
        tts_cfg = settings.voice.get("tts", {})
        kok_cfg = tts_cfg.get("kokoro", {})
        lang_code = kok_cfg.get("lang_code", "b")
        voice = kok_cfg.get("voice", "bf_isabella")
        from kokoro import KPipeline
        _kokoro_pipeline = KPipeline(lang_code=lang_code)
        print(f"[Nova] Kokoro TTS ready — voice: {voice}")
    return _kokoro_pipeline


def warmup_kokoro_inference(settings) -> None:
    """
    Load Kokoro and run one short inference to pre-compile the compute graph.
    Must be called from a worker thread (not the asyncio loop) since pipeline()
    is synchronous and can take several seconds on first call.
    """
    try:
        tts_cfg = settings.voice.get("tts", {})
        kok_cfg = tts_cfg.get("kokoro", {})
        voice   = kok_cfg.get("voice", "bf_isabella")
        speed   = float(kok_cfg.get("speed", 1.0))
        pipeline = _get_kokoro_pipeline(settings)
        # Consume the generator fully — this triggers JIT / graph compilation.
        for _ in pipeline("Hi.", voice=voice, speed=speed):
            pass
        print("[Nova] Kokoro inference graph warm — first Read Aloud will be instant.", flush=True)
    except Exception as exc:
        print(f"[Nova] Kokoro inference warm-up failed (non-fatal): {exc}", flush=True)


def _synthesize_kokoro(settings, text: str) -> tuple[bytes, str]:
    tts_cfg = settings.voice.get("tts", {})
    kok_cfg = tts_cfg.get("kokoro", {})
    voice = kok_cfg.get("voice", "bf_isabella")
    speed = kok_cfg.get("speed", 1.0)
    pipeline = _get_kokoro_pipeline(settings)

    chunks = []
    for _, _, audio in pipeline(text, voice=voice, speed=speed):
        chunks.append(audio)

    if not chunks:
        raise RuntimeError("Kokoro produced no audio")

    buf = io.BytesIO()
    sf.write(buf, np.concatenate(chunks), 24000, format="WAV")
    return buf.getvalue(), "audio/wav"


_SENTENCE_RE = re.compile(r'(?<=[.!?])\s+')

# Stream split: sentence/paragraph only — *not* commas.  Comma-splitting
# created tiny fragments, worse prosody, mispronunciations at boundaries, and
# more WAV handoffs (gaps on the client).  Word highlight in the UI is decoupled.
_CHUNK_RE = re.compile(r'(?<=[.!?])\s+|\n+')

# After sentence split, only break up very long lines for first-byte latency.
_MAX_TTS_CHUNK_CHARS = 120


def _split_long_clause(clause: str, max_chars: int = _MAX_TTS_CHUNK_CHARS) -> list[str]:
    """
    Split a clause that exceeds *max_chars* into smaller pieces at word boundaries.
    Short clauses (≤ max_chars) are returned unchanged in a one-element list.
    Chunks are kept ≥ 15 chars to avoid excessively short audio fragments.
    """
    if len(clause) <= max_chars:
        return [clause]
    words = clause.split()
    results: list[str] = []
    current: list[str] = []
    current_len = 0
    for word in words:
        # +1 for the space between words
        projected = current_len + (1 if current else 0) + len(word)
        if projected > max_chars and len(current) >= 2:
            results.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len = projected
    if current:
        results.append(" ".join(current))
    if not results:
        return [clause]
    return results


_TTS_STREAM_CLEAN_RE = re.compile(
    r"(\*+|`+|#{1,6}\s?|"
    r"\[([^\]]+)\]\([^\)]+\)|"
    r"https?://\S+|"
    r"^\s*[-•]\s)",
    re.MULTILINE,
)


def _clean_text_for_tts_stream(text: str, max_chars: int = 8000) -> str:
    """Like _clean_spoken_text but PRESERVES newlines so _CHUNK_RE can split there."""
    # Strip markdown markers (same regex as _clean_spoken_text)
    cleaned = _TTS_STREAM_CLEAN_RE.sub(lambda m: m.group(2) if m.group(2) else " ", text)
    # Avoid Kokoro glitches on these symbols
    cleaned = re.sub(r"\s*&\s*", " and ", cleaned)
    cleaned = re.sub(r"\b@\b", " at ", cleaned)
    # Collapse runs of spaces (but NOT newlines)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    # Collapse 3+ newlines to two newlines (keep paragraph breaks)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars].rstrip() + "..."
    return cleaned


def _sentence_wav_chunks(settings, text: str):
    """Yield WAV bytes for each clause/line — enables low-latency streaming with accurate word sync."""
    tts_cfg = settings.voice.get("tts", {})
    kok_cfg = tts_cfg.get("kokoro", {})
    voice = kok_cfg.get("voice", "bf_isabella")
    speed = kok_cfg.get("speed", 1.0)
    pipeline = _get_kokoro_pipeline(settings)

    # Split at clause boundaries, then further break any long clause at word
    # boundaries so the first synthesis chunk is short and arrives quickly.
    raw_clauses = [s.strip() for s in _CHUNK_RE.split(text) if s.strip()]
    sentences: list[str] = []
    for clause in raw_clauses:
        sentences.extend(_split_long_clause(clause))
    if not sentences:
        return

    # Kokoro's pipeline() can yield several audio arrays per *text* unit (e.g. per
    # sentence).  Concatenate them into **one** WAV per sentence fragment so
    # prosody stays coherent and the browser does not schedule dozens of
    # micro-buffers (which caused audible gaps and uneven pronunciation).
    for sentence in sentences:
        parts: list[np.ndarray] = []
        for _, _, audio in pipeline(sentence, voice=voice, speed=speed):
            if audio is None:
                continue
            a = np.asarray(audio, dtype=np.float32).ravel()
            if a.size:
                parts.append(a)
        if not parts:
            continue
        merged = np.concatenate(parts) if len(parts) > 1 else parts[0]
        buf = io.BytesIO()
        sf.write(buf, merged, 24000, format="WAV")
        data = buf.getvalue()
        # 4-byte little-endian length prefix so the client can frame chunks
        yield len(data).to_bytes(4, "little") + data


def _get_stt(request: Request) -> WhisperSTT:
    global _stt
    if _stt is None:
        cfg = request.app.state.settings.voice.get("stt", {})
        personalization_enabled = bool(cfg.get("personalization", True))
        custom_terms = cfg.get("custom_terms") or []
        if not isinstance(custom_terms, list):
            custom_terms = []
        _require_wake_word, wake_words, _wake_active_seconds = _wake_word_settings(request)
        custom_terms = _stt_terms_with_wake_words(custom_terms, wake_words)
        base_prompt = ""
        if personalization_enabled:
            try:
                memory: MemoryStore | None = getattr(request.app.state, "memory", None)
                if memory is not None:
                    base_prompt = build_whisper_prompt(memory)
            except Exception:
                pass
        initial_prompt = compose_stt_prompt(base_prompt, custom_terms=custom_terms)

        _stt = WhisperSTT(
            model_size=cfg.get("model_size", "base.en"),
            device=cfg.get("device", "cpu"),
            compute_type=cfg.get("compute_type", "int8"),
            beam_size=cfg.get("beam_size", 1),
            vad_filter=cfg.get("vad_filter", False),
            language=cfg.get("language"),
            initial_prompt=initial_prompt,
        )
    return _stt


def _resolve_voice_id(request: Request, preferred_name: str | None, fallback_voice_id: str) -> str:
    if not preferred_name:
        return fallback_voice_id
    try:
        from elevenlabs.client import ElevenLabs

        settings = request.app.state.settings
        client = ElevenLabs(api_key=settings.elevenlabs_api_key)
        voices = client.voices.get_all()
        voice_list = getattr(voices, "voices", None) or []
        for voice in voice_list:
            name = (getattr(voice, "name", "") or "").strip().lower()
            if name == preferred_name.strip().lower():
                return getattr(voice, "voice_id", fallback_voice_id) or fallback_voice_id
    except Exception:
        return fallback_voice_id
    return fallback_voice_id


def _get_speaker_identity(request: Request) -> SpeakerIdentityStore:
    global _speaker_identity
    if _speaker_identity is None:
        settings = request.app.state.settings
        voice_cfg = settings.voice
        focus_cfg = voice_cfg.get("speaker_focus", {})
        audio_cfg = voice_cfg.get("audio", {})
        auto_unknown = bool(focus_cfg.get("auto_create_unknown_speakers", False))
        if bool(focus_cfg.get("ask_identify_on_new_speaker", False)):
            auto_unknown = True
        _speaker_identity = SpeakerIdentityStore(
            profile_path=settings.data_dir / "speaker_profiles.json",
            enabled=bool(focus_cfg.get("remember_speakers", True)),
            similarity_threshold=float(focus_cfg.get("multi_speaker_similarity_threshold", 0.76)),
            sample_rate=int(audio_cfg.get("sample_rate", 16000)),
            auto_create_unknown=auto_unknown,
            embedding_backend=str(focus_cfg.get("embedding_backend", "ecapa")),
            max_embeddings_per_profile=int(focus_cfg.get("max_embeddings_per_profile", 12)),
        )
    return _speaker_identity


@router.post("/enroll", response_model=VoiceEnrollResponse)
async def enroll_voice(
    request: Request,
    audio: UploadFile = File(..., description="Voice sample used to enroll speaker identity"),
    name: str = Form(..., description="Speaker name to remember"),
    memory: MemoryStore = Depends(get_memory),
) -> VoiceEnrollResponse:
    _require_local_request(request)
    raw = await audio.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty audio file.")

    cleaned_name = name.strip()
    if not cleaned_name:
        raise HTTPException(status_code=400, detail="Name is required.")

    pcm = _to_pcm(raw, audio.filename or "")
    speaker_identity = _get_speaker_identity(request)
    enrolled_name = speaker_identity.learn_identity(pcm, cleaned_name, fallback_text=cleaned_name)
    if not enrolled_name:
        raise HTTPException(status_code=422, detail="Could not learn a voice identity from that sample.")

    try:
        memory.save_fact("user_name", enrolled_name, source="voice-enroll")
        memory.save_fact("last_speaker", enrolled_name, source="voice-enroll")
    except Exception:
        pass

    return VoiceEnrollResponse(name=enrolled_name, enrolled=True)


_ENROLL_INTENT_RE = re.compile(
    r"\b(enroll|register|save|remember|learn|train)\b.{0,32}\b(me|my|user|face|voice|identity|profile)\b|"
    r"\b(enroll me|register me|save me|remember me|learn me)\b",
    re.IGNORECASE,
)

def _should_include_camera_context(text: str) -> bool:
    lowered = (text or "").lower()
    visual_signals = (
        "see me", "camera", "look at", "look again", "showing", "what do you see",
        "what am i", "how many fingers", "which finger", "which fingers", "finger", "fingers", "hands", "right hand", "left hand",
        "my hand", "your hand", "feet", "body", "nose",
        "eyes", "ears", "object", "objects", "what is in", "what's in", "what am i holding",
        "holding up", "background", "behind me", "identify", "recognize", "enroll my face", "enroll my voice",
        "jewelry", "jewellery", "ring", "check again",
        " gesture", "gestures", "wave", "waving", "point", "pointing",
        "watch me", "look at this",
    )
    return any(signal in lowered for signal in visual_signals)


def _is_smalltalk_opening(text: str) -> bool:
    lowered = (text or "").lower()
    cues = (
        "how are you",
        "hows it going",
        "how's it going",
        "what's up",
        "whats up",
        "how you doing",
    )
    if any(c in lowered for c in cues):
        return True
    t = lowered.strip(" .,!?:;")
    return t in {"hey", "hi", "hello", "yo"}


def _smalltalk_reply(text: str) -> str:
    t = (text or "").lower()
    if "how are you" in t or "how's it going" in t or "hows it going" in t or "how you doing" in t:
        return "I'm good, thanks for asking. What's up?"
    if "what's up" in t or "whats up" in t:
        return "Not much, just here with you. What's up?"
    return "Hey."


def _mentions_nova_name(text: str) -> bool:
    return bool(re.search(r"\bnova\b", text or "", re.IGNORECASE))


def _is_anonymous_speaker(name: str | None) -> bool:
    return (not name) or str(name).strip().lower().startswith("speaker ")


_ANON_SPEAKER_SWITCH_MIN_CONF = 0.72


def _is_camera_presence_question(text: str) -> bool:
    t = (text or "").lower()
    cues = (
        "see me",
        "seeing me",
        "can you see me",
        "are you seeing me",
        "are you not seeing me",
        "do you see me",
        "you see me",
    )
    return any(c in t for c in cues)


def _is_identity_question(text: str) -> bool:
    t = (text or "").lower()
    cues = (
        "who am i",
        "who i am",
        "do you know who i am",
        "you know who i am",
    )
    return any(c in t for c in cues)


def _is_code_request(text: str) -> bool:
    """Return True when the transcript is clearly a request to write/fix/explain code."""
    t = (text or "").lower()
    # Must have a programming language or code-type keyword
    lang_or_type = (
        "java", "python", "javascript", "typescript", "kotlin", "swift",
        "c++", "c#", "golang", "rust", "ruby", "php", "bash", "html", "css",
        "react", "django", "spring", "flutter", "sql", "regex",
        "program", "function", "class", "algorithm", "code", "script",
        "snake game", "tic tac toe", "chess", "calculator", "todo app",
        "rest api", "crud", "game", "app",
    )
    action = (
        "write", "create", "make", "build", "code", "implement", "generate",
        "fix", "debug", "refactor", "explain", "show me",
    )
    has_lang = any(k in t for k in lang_or_type)
    has_action = any(a in t for a in action)
    return has_lang and has_action


@router.post("", response_model=VoiceResponse)
async def transcribe_and_respond(
    request: Request,
    audio: UploadFile = File(..., description="Audio file (WAV, MP3, M4A, or raw PCM)"),
    session_id: str | None = Form(None),
    mode: str = Form("default"),
    model_key: str | None = Form(None),
    camera_video: UploadFile | None = File(
        None,
        description="Optional short WebM/MP4 from the camera track (preferred over JPEG bursts for hands).",
    ),
    camera_frame: UploadFile | None = File(None, description="Optional JPEG camera snapshot (legacy clients)"),
    camera_frame_2: UploadFile | None = File(None, description="Optional extra snapshot"),
    camera_frame_3: UploadFile | None = File(None, description="Optional extra snapshot"),
    camera_frame_4: UploadFile | None = File(None, description="Optional frames"),
    camera_frame_5: UploadFile | None = File(None),
    camera_frame_6: UploadFile | None = File(None),
    camera_frame_7: UploadFile | None = File(None),
    camera_frame_8: UploadFile | None = File(None),
    camera_frame_9: UploadFile | None = File(None),
    orchestrator: Orchestrator = Depends(get_orchestrator),
    memory: MemoryStore = Depends(get_memory),
    current_user: User | None = Depends(get_optional_user),
) -> VoiceResponse:
    """
    Accept an audio upload, transcribe it via Whisper, run the Nova agent,
    and return the transcript + text response.

    Clients: iPhone shortcut, web app, curl.
    """
    raw = await audio.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty audio file.")

    async def _read_upload(u: UploadFile | None) -> bytes | None:
        if u is None:
            return None
        raw = await u.read()
        return raw if raw else None

    video_raw = await _read_upload(camera_video)

    _cam_uploads = (
        camera_frame,
        camera_frame_2,
        camera_frame_3,
        camera_frame_4,
        camera_frame_5,
        camera_frame_6,
        camera_frame_7,
        camera_frame_8,
        camera_frame_9,
    )
    burst_parts = await asyncio.gather(*[_read_upload(u) for u in _cam_uploads])
    burst_raw = [b for b in burst_parts if b]

    pcm = _to_pcm(raw, audio.filename or "")
    stt = _get_stt(request)

    def _resolve_frame_bytes() -> bytes | None:
        """Pick best hand frame from video or JPEG burst (runs in worker thread)."""
        fb: bytes | None = None
        if video_raw and len(video_raw) > 256:
            vframes = jpeg_frames_from_video_bytes(video_raw, 4)
            if vframes:
                fb = pick_frame_best_hands(vframes)
        if fb is None and burst_raw:
            fb = pick_frame_best_hands(burst_raw)
        return fb

    async def _do_stt() -> str:
        fast_mode = str(mode or "").strip().lower() == "fast"
        t = await asyncio.to_thread(stt.transcribe, pcm, 16000, None, fast_mode)
        if not t:
            t = await asyncio.to_thread(stt.transcribe, pcm, 16000, None, False)
        return t or ""

    # Always transcribe first; only decode camera payloads if transcript indicates visual intent.
    transcript = await _do_stt()
    transcript = _normalize_wake_homophones(transcript)
    wants_camera_context = _should_include_camera_context(transcript)
    frame_bytes: bytes | None = None
    if wants_camera_context and (video_raw or burst_raw):
        frame_bytes = await asyncio.to_thread(_resolve_frame_bytes)

    # Fast CV only: one MediaPipe pass + summary (no YOLO, no Ollama — those dominated latency).
    hand_summary = ""
    detector_summary = ""

    def _frame_metrics() -> tuple[str, str]:
        from nova.services.body_detector import detect as mp_detect

        mp_rows, hs = mp_detect(frame_bytes)
        dlist = [
            {"type": d.type, "label": d.label, "confidence": d.confidence, "box": d.box} for d in mp_rows
        ]
        det = summarize_detections_for_voice(dlist)
        return (hs or "").strip(), det.strip()

    if frame_bytes and wants_camera_context:
        try:
            hand_summary, detector_summary = await asyncio.to_thread(_frame_metrics)
        except Exception as exc:
            print(f"[Nova] Voice frame metrics error: {exc}")

    # Expensive vision LLM only when the user is likely asking about the visual scene.
    camera_vision = ""
    if frame_bytes and wants_camera_context:
        try:
            camera_vision = await asyncio.to_thread(
                describe_scene_frame,
                request.app.state.settings,
                frame_bytes,
                2.5,
            )
        except Exception as exc:
            print(f"[Nova] Utterance vision error: {exc}")

    if not transcript:
        raise HTTPException(status_code=422, detail="No speech detected in audio.")
    user_said_nova_name = _mentions_nova_name(transcript)

    _uid = current_user.id if current_user else None
    sid = memory.get_or_create_session(session_id, user_id=_uid, source="voice")
    known_user = memory.get_fact_value("user_name", "").strip()
    known_display = memory.get_fact_value("user_display_name", "").strip()
    last_known_speaker = memory.get_fact_value("last_speaker", "").strip()

    speaker_identity = _get_speaker_identity(request)
    speaker_label: str | None = None
    voice_confidence = 0.0
    declared_name = extract_declared_name(transcript)
    declared = False
    try:
        speaker_label, voice_confidence, declared = speaker_identity.identify(pcm, transcript)
        # Only trust a declared name if Nova explicitly asked this speaker to introduce themselves.
        # This prevents random phrases like "I'm located" or "I'm fine" from creating profiles.
        nova_asked = _nova_asked_this_speaker(sid, speaker_label)
        if declared_name and nova_asked:
            learned = speaker_identity.learn_identity(pcm, declared_name, fallback_text=declared_name)
            if learned:
                speaker_label = learned
                voice_confidence = 1.0
                declared = True
                _clear_identity_asked(sid, speaker_label)
        elif declared_name and not nova_asked:
            # Ignore the name — Nova didn't ask. Just continue anonymously.
            declared_name = None
    except Exception:
        speaker_label = None
        voice_confidence = 0.0

    # Do NOT default unknown voice to `known_user` — that mislabels guests as the enrolled profile.
    # A **strong voice match** keeps who is speaking even when the camera shows no face or another person.

    def _reference_name(name: str | None) -> str:
        if not name:
            return ""
        try:
            return speaker_identity.reference_name(name)
        except Exception:
            return name

    if not known_display and known_user:
        known_display = _reference_name(known_user)

    # ── Face recognition (optional camera frame) ──────────────────────
    face_name: str | None = None
    face_confidence: float | None = None
    if frame_bytes is not None:
        try:
            face_store = getattr(request.app.state, "face_identity", None)
            if face_store is not None:
                face_name, face_confidence = face_store.identify(frame_bytes)
                if face_name and (face_confidence or 0) >= 0.5:
                    strong_voice = speaker_identity.is_strong_voice_match(speaker_label, voice_confidence)
                    same_person = SpeakerIdentityStore.names_same_identity(face_name, speaker_label)

                    if strong_voice and not same_person:
                        # Enrolled voice says it's the primary user; the visible face may be someone else or a mismatch.
                        try:
                            memory.save_fact("last_face", face_name, source="face-id")
                        except Exception:
                            pass
                    else:
                        if not strong_voice:
                            speaker_label = face_name
                        try:
                            si = _get_speaker_identity(request)
                            if si and pcm:
                                learn_key = (speaker_label if strong_voice else face_name) or face_name
                                learned = si.learn_identity(pcm, learn_key, fallback_text=face_name)
                                if learned and not strong_voice:
                                    speaker_label = learned
                        except Exception:
                            pass
                        try:
                            memory.save_fact("last_face", face_name, source="face-id")
                            if not strong_voice:
                                memory.save_fact("user_name", face_name, source="face-id")
                                memory.save_fact("user_display_name", _reference_name(face_name), source="face-id")
                        except Exception:
                            pass
                elif declared_name and speaker_label:
                    # If the user declares their name while on camera, save at least one local face sample.
                    try:
                        face_store.enroll(speaker_label, [frame_bytes])
                    except Exception:
                        pass
        except Exception as exc:
            print(f"[Nova] Face recognition error in voice turn: {exc}")

    require_wake_word, wake_words, wake_active_seconds = _wake_word_settings(request)
    if require_wake_word:
        heard_wake, cleaned_transcript = _strip_wake_word(transcript, wake_words)
        now = time.time()
        active = _is_voice_active(sid, now)

        if heard_wake:
            _touch_voice_active(sid, now, wake_active_seconds)
            transcript = cleaned_transcript or transcript
            if not transcript.strip():
                ref = _reference_name(speaker_label)
                visible_transcript = f"{ref}: {transcript}" if ref else transcript
                return VoiceResponse(
                    transcript=visible_transcript,
                    response=f"I'm here, {ref or 'there'}.",
                    session_id=sid,
                )
        elif not active:
            ref = _reference_name(speaker_label)
            visible_transcript = f"{ref}: {transcript}" if ref else transcript
            return VoiceResponse(transcript=visible_transcript, response="", session_id=sid)
        else:
            _touch_voice_active(sid, now, wake_active_seconds)

    focus_cfg = request.app.state.settings.voice.get("speaker_focus", {})
    ask_identify_on_new_speaker = bool(focus_cfg.get("ask_identify_on_new_speaker", False))
    voice_lock_enabled = bool(focus_cfg.get("voice_lock_enabled", False))
    if voice_lock_enabled and ask_identify_on_new_speaker and known_user and not declared_name:
        confidence_band = speaker_identity.confidence_band(speaker_label, voice_confidence)
        reliable_voice = confidence_band in {"high", "medium"}
        same_as_primary = SpeakerIdentityStore.names_same_identity(known_user, speaker_label)
        same_as_last = SpeakerIdentityStore.names_same_identity(last_known_speaker, speaker_label) if last_known_speaker else False
        new_non_primary = bool(reliable_voice and speaker_label and not same_as_primary)
        switched_from_last = bool(reliable_voice and speaker_label and last_known_speaker and not same_as_last)
        anonymous_switch = bool(
            _is_anonymous_speaker(speaker_label)
            and float(voice_confidence) >= _ANON_SPEAKER_SWITCH_MIN_CONF
            and last_known_speaker
            and not SpeakerIdentityStore.names_same_identity(known_user, last_known_speaker)
            and not same_as_last
        )
        # Only interrupt when we have strong, non-ambiguous evidence of a different person.
        # Low-confidence / anonymous turns from the enrolled user must NOT trigger this.
        should_gate_new_speaker = bool(
            new_non_primary
            or (switched_from_last and not same_as_primary)
            or anonymous_switch
        )
        if should_gate_new_speaker:
            who = _reference_name(speaker_label) if speaker_label else "that voice"
            is_generic_who = (not who) or who == "that voice" or who.lower().startswith("speaker")
            turn_name = "" if is_generic_who else who
            visible = transcript if not turn_name else f"{turn_name}: {transcript}"
            intro_request = (
                "Sounds like someone else jumped in. Hey, can you introduce yourself?"
                if is_generic_who
                else f"I think I'm hearing {who} now. Hey, can you introduce yourself?"
            )
            if _is_smalltalk_opening(transcript):
                intro_request = f"I'm good — thanks for asking. {intro_request}"
            _mark_identity_asked(sid, speaker_label)
            return VoiceResponse(
                transcript=visible,
                response=intro_request,
                session_id=sid,
                face_name=face_name,
                face_confidence=face_confidence,
            )

    # Do not hard-stop the conversation when voice identity is unresolved.
    # Continue the turn as anonymous so Nova can still answer naturally.

    enroll_intent = bool(_ENROLL_INTENT_RE.search(transcript))
    if enroll_intent and not declared_name and not declared:
        ref = _reference_name(speaker_label)
        _mark_identity_asked(sid, speaker_label)
        return VoiceResponse(
            transcript=f"{ref}: {transcript}",
            response="Quick intro first — hey, can you introduce yourself?",
            session_id=sid,
            face_name=face_name,
            face_confidence=face_confidence,
        )

    ref_name = _reference_name(speaker_label)
    # If voice confidence dropped on a short turn but we already know a single enrolled user,
    # treat this turn as that user rather than displaying "Speaker N".
    if _is_anonymous_speaker(speaker_label) and known_user and float(voice_confidence) < _ANON_SPEAKER_SWITCH_MIN_CONF:
        ref_name = known_display or _reference_name(known_user)

    if speaker_label:
        try:
            if _is_anonymous_speaker(speaker_label):
                if float(voice_confidence) >= _ANON_SPEAKER_SWITCH_MIN_CONF:
                    memory.save_fact("last_speaker", speaker_label, source="voice-id")
                elif known_user:
                    # Re-affirm the known user for low-confidence turns — don't blank the label.
                    memory.save_fact("last_speaker", known_user, source="voice-id")
            else:
                memory.save_fact("last_speaker", speaker_label, source="voice-id")
                # Only persist a display name if this profile was created after Nova asked for an intro.
                if declared:
                    memory.save_fact("user_display_name", ref_name, source="voice-id")
            if declared:
                memory.save_fact("user_name", speaker_label, source="voice-id")
        except Exception:
            pass

    effective_ref = ref_name or (known_display if _is_anonymous_speaker(speaker_label) else "")
    spoken_input = transcript
    if effective_ref:
        spoken_input = f"[Speaker: {effective_ref}] {transcript}"
    elif _is_anonymous_speaker(speaker_label):
        spoken_input = (
            "[Identity note: speaker identity is currently unknown or low-confidence. "
            "Do not assert a specific person's name; ask for a quick introduction if needed.]\n"
            f"{spoken_input}"
        )
    # Keep voice turns tightly grounded to what the user just said.
    spoken_input = (
        "[Voice instruction: Respond directly to the user's transcript. "
        "Do not invent extra user intent or unrelated tasks.]\n"
        f"{spoken_input}"
    )

    live_prefix = get_live_prefix_for_prompt(sid, ref_name) if wants_camera_context else ""
    if live_prefix:
        spoken_input = f"{live_prefix}\n{spoken_input}"

    # Utterance snapshot: moment when speech ended (complements the continuous live feed above).
    if frame_bytes is not None and wants_camera_context:
        who = camera_who_line(face_name, face_confidence, detector_summary, ref_name)
        vision_desc = camera_vision.strip() if camera_vision else SCENE_UNAVAILABLE
        hands_line, cam_instruction = hands_ground_truth_block(hand_summary or "", live=False)
        det_part = detector_summary.strip() if detector_summary and detector_summary.strip() else ""
        det_clause = f" | Detector: {det_part}" if det_part else ""
        spoken_input = (
            f"[Utterance snapshot — when you finished speaking | Person: {who} | {hands_line}{det_clause} | "
            f"Scene: {vision_desc} | {cam_instruction}]\n{spoken_input}"
        )

    if declared and speaker_label:
        # `declared` is only True when Nova had previously asked for this speaker's intro
        # (enforced above in the identify block). So saving here is always consent-gated.
        ref = ref_name
        try:
            memory.save_fact("user_name", speaker_label, source="voice-id")
            memory.save_fact("user_display_name", ref, source="voice-id")
        except Exception:
            pass

        face_saved = False
        if frame_bytes is not None:
            try:
                face_store = getattr(request.app.state, "face_identity", None)
                if face_store is not None:
                    saved = face_store.enroll(speaker_label, [frame_bytes])
                    face_saved = saved > 0
            except Exception:
                face_saved = False

        # Conversational identity enrollment: when user asks to enroll and states name,
        # store both modalities immediately from the current turn.
        if enroll_intent:
            confirmation = (
                f"You're enrolled, {ref}. I saved your voice and face and will remember you in future conversations."
                if face_saved
                else f"You're enrolled, {ref}. I saved your voice. Keep your face in frame and say 'enroll me' again so I can store your face too."
            )
            return VoiceResponse(
                transcript=f"{ref}: {transcript}",
                response=confirmation,
                session_id=sid,
                face_name=face_name,
                face_confidence=face_confidence,
            )

        confirmation = (
            f"Got it, {ref}. I saved your voice and face profile and I'll remember you."
            if face_saved
            else (
                f"Got it, {ref}. I saved your voice profile."
                if frame_bytes is None
                else f"Got it, {ref}. I saved your voice profile. Keep your face in frame so I can save your face profile too."
            )
        )
        return VoiceResponse(
            transcript=f"{ref}: {transcript}",
            response=confirmation,
            session_id=sid,
            face_name=face_name,
            face_confidence=face_confidence,
        )

    # Clean transcript stored in memory — no system tags, no camera context blocks.
    display_message = transcript if not ref_name else f"{ref_name}: {transcript}"

    if _is_camera_presence_question(transcript):
        if face_name or ("person" in (detector_summary or "").lower()) or ("face" in (detector_summary or "").lower()):
            response = "Yeah, I can see you."
        else:
            response = "I can hear you clearly. Camera recognition can miss a frame sometimes, but you're here with me."
    elif _is_smalltalk_opening(transcript):
        response = _smalltalk_reply(transcript)
    elif _is_identity_question(transcript) and _is_anonymous_speaker(speaker_label):
        response = "I'm not fully sure which voice this is yet. Hey, can you introduce yourself?"
    else:
        # Coding requests must use the code model with a large token budget regardless of voice mode.
        effective_mode = mode
        effective_model_key = model_key
        if _is_code_request(transcript):
            effective_mode = "code"
            effective_model_key = "code"
        response = await orchestrator.run(
            user_message=spoken_input,
            session_id=sid,
            mode=effective_mode,
            model_key=effective_model_key,
            display_message=display_message,
        )
    if _should_append_identity_prompt(
        sid,
        known_user=known_user,
        declared_name=declared_name,
        speaker_label=speaker_label,
        voice_confidence=voice_confidence,
        speaker_identity=speaker_identity,
    ):
        intro = (
            "Hey, can you introduce yourself?"
            if user_said_nova_name
            else "Hey I'm Nova, nice to meet you — can you introduce yourself?"
        )
        response = (
            f"{response.rstrip()} "
            f"{intro}"
        ).strip()
        # Record that Nova just asked so the next turn can save the name if they respond.
        _mark_identity_asked(sid, speaker_label)

    # Adapt STT vocabulary over time from saved conversation/facts.
    cfg = request.app.state.settings.voice.get("stt", {})
    if bool(cfg.get("personalization", True)):
        try:
            custom_terms = cfg.get("custom_terms") or []
            if not isinstance(custom_terms, list):
                custom_terms = []
            _require_wake_word, wake_words, _wake_active_seconds = _wake_word_settings(request)
            custom_terms = _stt_terms_with_wake_words(custom_terms, wake_words)
            refresh_stt_prompt(
                memory,
                stt,
                custom_terms=custom_terms,
            )
        except Exception:
            pass

    display_label = effective_ref or ref_name
    visible_transcript = transcript if not display_label else f"{display_label}: {transcript}"
    return VoiceResponse(
        transcript=visible_transcript,
        response=response,
        session_id=sid,
        face_name=face_name,
        face_confidence=face_confidence,
    )


# ──────────────────────────────────────────────────────────────────────────
# Streaming voice endpoint
#
# `/voice/stream` is the real-time counterpart to `/voice`.
#
# It yields NDJSON events as the pipeline progresses:
#   {"type": "transcript", "text": "...", "session_id": "..."}
#   {"type": "sentence",   "text": "..."}      ← emitted each time a
#                                                sentence completes from the
#                                                streaming LLM output; the
#                                                client can start TTS on each
#                                                sentence immediately, so the
#                                                first audio plays while Nova
#                                                is still "thinking".
#   {"type": "done",       "response": "...", "session_id": "..."}
#   {"type": "error",      "detail":   "..."}
#
# Why a separate endpoint instead of modifying `/voice`?
#   The iPhone shortcut and some older clients still expect the single-JSON
#   `VoiceResponse` shape. Keeping `/voice` untouched preserves that contract
#   while the web UI can opt in to the low-latency stream.
# ──────────────────────────────────────────────────────────────────────────

# Sentence terminators we consider complete enough to pipe to TTS. We look
# for these at a buffer tail (plus optional trailing quote/bracket/space) so
# an in-flight clause like "Hello there," still waits before firing.
_SENTENCE_ENDERS = (".", "!", "?", "…")


def _split_complete_sentences(buffer: str) -> tuple[list[str], str]:
    """Return (complete_sentences, remainder) from a running LLM buffer.

    Looks for sentence terminators (. ! ? …). Handles simple cases like
    "Mr.", "U.S." by requiring the next char to be whitespace or end-of-string
    and the next non-space char (if any) to be uppercase / punctuation. This
    isn't perfect but is good enough for voice — we'd rather speak a slightly
    over-eager clause than lag a whole sentence.
    """
    if not buffer:
        return [], buffer

    sentences: list[str] = []
    start = 0
    i = 0
    n = len(buffer)
    while i < n:
        ch = buffer[i]
        if ch in _SENTENCE_ENDERS:
            # Swallow any immediately following closing punctuation (quote, paren).
            end = i + 1
            while end < n and buffer[end] in ('"', "'", ")", "]", "”", "’"):
                end += 1
            # Require next char to be whitespace OR end of buffer.
            # If end < n, also skip the whitespace and make sure we're NOT
            # in the middle of an abbreviation (next char is lowercase letter).
            if end >= n:
                # Don't emit until we know more text isn't coming. Wait.
                break
            if buffer[end] not in (" ", "\n", "\t"):
                i = end
                continue
            # Peek past whitespace — if next non-space char is lowercase, it's
            # likely mid-sentence (abbreviation); skip it.
            peek = end
            while peek < n and buffer[peek] in (" ", "\n", "\t"):
                peek += 1
            if peek < n and buffer[peek].isalpha() and buffer[peek].islower():
                i = end
                continue
            candidate = buffer[start:end].strip()
            if candidate:
                sentences.append(candidate)
            start = end
            i = end
            continue
        # Newline on its own can also terminate a sentence.
        if ch == "\n" and (i + 1 >= n or buffer[i + 1] == "\n"):
            candidate = buffer[start : i + 1].strip()
            if candidate:
                sentences.append(candidate)
            start = i + 1
        i += 1

    remainder = buffer[start:]
    # If remainder is getting too long without a terminator, flush a soft break
    # on comma/semicolon so Nova starts speaking quickly.
    if not sentences and len(remainder) > 72:
        soft_idx = -1
        for pivot in (", ", "; ", ": "):
            idx = remainder.rfind(pivot, 0, 96)
            if idx > soft_idx:
                soft_idx = idx + len(pivot) - 1
        if soft_idx > 20:
            clause = remainder[: soft_idx + 1].strip()
            if clause:
                sentences.append(clause)
                remainder = remainder[soft_idx + 1 :]
    return sentences, remainder


@router.post("/stream")
async def transcribe_and_respond_stream(
    request: Request,
    audio: UploadFile = File(..., description="User utterance audio (WAV, MP3, M4A, or raw PCM)"),
    session_id: str | None = Form(None),
    mode: str = Form("fast"),
    model_key: str | None = Form(None),
    camera_frame: UploadFile | None = File(None, description="Optional JPEG camera snapshot"),
    orchestrator: Orchestrator = Depends(get_orchestrator),
    memory: MemoryStore = Depends(get_memory),
    current_user: User | None = Depends(get_optional_user),
) -> StreamingResponse:
    """Real-time voice endpoint: streams transcript, sentence-level text, and
    a final done payload as soon as each stage completes.

    Optimized for conversation flow:
      • STT fires in a worker thread; `transcript` emits as soon as it lands.
      • Camera / face processing is skipped unless the transcript references
        vision (`_should_include_camera_context`).
      • Orchestrator runs with `stream_callback` → sentences are piped out
        the moment they complete, so the client can start TTS on sentence 1
        while the LLM is still generating sentence 2.
    """

    raw = await audio.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty audio file.")

    frame_raw: bytes | None = None
    if camera_frame is not None:
        try:
            fb = await camera_frame.read()
            frame_raw = fb if fb and len(fb) > 400 else None
        except Exception:
            frame_raw = None

    pcm = _to_pcm(raw, audio.filename or "")
    stt = _get_stt(request)

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def emit(obj: dict) -> None:
        try:
            line = json.dumps(obj, ensure_ascii=False) + "\n"
        except (TypeError, ValueError):
            line = json.dumps({"type": "error", "detail": "bad event"}) + "\n"
        # Thread-safe: callers may be the sync stream_callback running in the
        # orchestrator / Ollama worker thread.
        try:
            loop.call_soon_threadsafe(queue.put_nowait, line)
        except RuntimeError:
            # Loop closed already (client disconnect) — drop silently.
            pass

    async def pipeline() -> None:
        try:
            # ── STT (fast path: beam=1, vad_filter off) ─────────────────
            fast_mode = str(mode or "").strip().lower() == "fast"
            transcript = await asyncio.to_thread(stt.transcribe, pcm, 16000, None, fast_mode)
            if not transcript:
                transcript = await asyncio.to_thread(stt.transcribe, pcm, 16000, None, False)
            transcript = _normalize_wake_homophones(transcript or "")
            if not transcript.strip():
                emit({"type": "error", "detail": "No speech detected."})
                return

            _uid = current_user.id if current_user else None
            sid = memory.get_or_create_session(session_id, user_id=_uid, source="voice")
            emit({"type": "transcript", "text": transcript, "session_id": sid})

            # ── Speaker identity (lightweight — we use a reference name only)
            speaker_identity = _get_speaker_identity(request)
            speaker_label: str | None = None
            voice_confidence = 0.0
            try:
                speaker_label, voice_confidence, _declared = speaker_identity.identify(pcm, transcript)
            except Exception:
                speaker_label = None
                voice_confidence = 0.0

            def _reference_name(name: str | None) -> str:
                if not name:
                    return ""
                try:
                    return speaker_identity.reference_name(name)
                except Exception:
                    return name

            ref_name = _reference_name(speaker_label)
            known_user = memory.get_fact_value("user_name", "").strip()
            known_display = memory.get_fact_value("user_display_name", "").strip()
            if _is_anonymous_speaker(speaker_label) and known_user and float(voice_confidence) < _ANON_SPEAKER_SWITCH_MIN_CONF:
                ref_name = known_display or _reference_name(known_user)

            # ── Camera context (only if transcript asks about it) ───────
            wants_camera_context = _should_include_camera_context(transcript)
            frame_bytes = frame_raw if wants_camera_context else None

            hand_summary = ""
            detector_summary = ""
            camera_vision = ""
            face_name: str | None = None
            face_confidence: float | None = None

            if frame_bytes is not None:
                def _frame_metrics() -> tuple[str, str]:
                    from nova.services.body_detector import detect as mp_detect

                    mp_rows, hs = mp_detect(frame_bytes)
                    dlist = [
                        {"type": d.type, "label": d.label, "confidence": d.confidence, "box": d.box} for d in mp_rows
                    ]
                    det = summarize_detections_for_voice(dlist)
                    return (hs or "").strip(), det.strip()

                try:
                    hand_summary, detector_summary = await asyncio.to_thread(_frame_metrics)
                except Exception as exc:
                    print(f"[Nova] Stream frame metrics error: {exc}")

                try:
                    camera_vision = await asyncio.to_thread(
                        describe_scene_frame,
                        request.app.state.settings,
                        frame_bytes,
                        2.5,
                    )
                except Exception as exc:
                    print(f"[Nova] Stream utterance vision error: {exc}")

                try:
                    face_store = getattr(request.app.state, "face_identity", None)
                    if face_store is not None:
                        face_name, face_confidence = face_store.identify(frame_bytes)
                except Exception:
                    face_name = None
                    face_confidence = None

            # ── Build the prompt passed to the orchestrator ─────────────
            effective_ref = ref_name or (known_display if _is_anonymous_speaker(speaker_label) else "")
            spoken_input = transcript
            if effective_ref:
                spoken_input = f"[Speaker: {effective_ref}] {transcript}"
            elif _is_anonymous_speaker(speaker_label):
                spoken_input = (
                    "[Identity note: speaker identity is currently unknown or low-confidence. "
                    "Do not assert a specific person's name; ask for a quick introduction if needed.]\n"
                    f"{spoken_input}"
                )
            spoken_input = (
                "[Voice instruction: Respond directly to the user's transcript. "
                "Do not invent extra user intent or unrelated tasks.]\n"
                f"{spoken_input}"
            )

            live_prefix = get_live_prefix_for_prompt(sid, ref_name) if wants_camera_context else ""
            if live_prefix:
                spoken_input = f"{live_prefix}\n{spoken_input}"

            if frame_bytes is not None and wants_camera_context:
                who = camera_who_line(face_name, face_confidence, detector_summary, ref_name)
                vision_desc = camera_vision.strip() if camera_vision else SCENE_UNAVAILABLE
                hands_line, cam_instruction = hands_ground_truth_block(hand_summary or "", live=False)
                det_part = detector_summary.strip() if detector_summary and detector_summary.strip() else ""
                det_clause = f" | Detector: {det_part}" if det_part else ""
                spoken_input = (
                    f"[Utterance snapshot — when you finished speaking | Person: {who} | {hands_line}{det_clause} | "
                    f"Scene: {vision_desc} | {cam_instruction}]\n{spoken_input}"
                )

            display_label = effective_ref or ref_name
            display_message = transcript if not display_label else f"{display_label}: {transcript}"

            # ── Fast-path canned replies (no LLM round trip) ────────────
            canned: str | None = None
            if _is_camera_presence_question(transcript):
                if face_name or ("person" in (detector_summary or "").lower()) or ("face" in (detector_summary or "").lower()):
                    canned = "Yeah, I can see you."
                else:
                    canned = "I can hear you clearly. Camera recognition can miss a frame sometimes, but you're here with me."
            elif _is_smalltalk_opening(transcript):
                canned = _smalltalk_reply(transcript)
            elif _is_identity_question(transcript) and _is_anonymous_speaker(speaker_label):
                canned = "I'm not fully sure which voice this is yet. Hey, can you introduce yourself?"

            if canned is not None:
                emit({"type": "sentence", "text": canned})
                emit({"type": "done", "response": canned, "session_id": sid})
                return

            # ── Stream the LLM response, emitting sentences as they close
            effective_mode = mode
            effective_model_key = model_key
            if _is_code_request(transcript):
                effective_mode = "code"
                effective_model_key = "code"

            buffer = {"text": ""}
            emitted_any = {"flag": False}

            def on_chunk(chunk: str) -> None:
                if not chunk:
                    return
                buffer["text"] += chunk
                sentences, rest = _split_complete_sentences(buffer["text"])
                for s in sentences:
                    emit({"type": "sentence", "text": s})
                    emitted_any["flag"] = True
                buffer["text"] = rest

            full_response = await orchestrator.run(
                user_message=spoken_input,
                session_id=sid,
                mode=effective_mode,
                model_key=effective_model_key,
                display_message=display_message,
                stream_callback=on_chunk,
            )

            # Flush the tail.
            tail = buffer["text"].strip()
            if tail:
                emit({"type": "sentence", "text": tail})
                emitted_any["flag"] = True

            # Defensive: if nothing streamed (some code paths return without
            # invoking stream_callback), emit the full response so the
            # client still gets audio.
            if not emitted_any["flag"] and full_response:
                sentences, remainder = _split_complete_sentences(full_response)
                for s in sentences:
                    emit({"type": "sentence", "text": s})
                if remainder.strip():
                    emit({"type": "sentence", "text": remainder.strip()})

            emit({"type": "done", "response": full_response or "", "session_id": sid})

            # Best-effort STT vocabulary refresh (non-critical — doesn't block).
            try:
                cfg = request.app.state.settings.voice.get("stt", {})
                if bool(cfg.get("personalization", True)):
                    custom_terms = cfg.get("custom_terms") or []
                    if not isinstance(custom_terms, list):
                        custom_terms = []
                    _require_wake, wake_words, _wake_active = _wake_word_settings(request)
                    custom_terms = _stt_terms_with_wake_words(custom_terms, wake_words)
                    refresh_stt_prompt(memory, stt, custom_terms=custom_terms)
            except Exception:
                pass

        except Exception as exc:
            print(f"[Nova] Voice stream error: {exc}")
            emit({"type": "error", "detail": str(exc)})
        finally:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, None)
            except RuntimeError:
                pass

    async def generator():
        task = asyncio.create_task(pipeline())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except Exception:
                    pass

    return StreamingResponse(
        generator(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "X-Nova-Stream": "voice",
        },
    )


def _to_pcm(data: bytes, filename: str) -> bytes:
    """
    Convert uploaded audio bytes to raw int16 PCM at 16 kHz mono.
    Accepts WAV, FLAC, OGG, MP3 (via soundfile), or bare PCM.
    """
    try:
        buf = io.BytesIO(data)
        samples, sr = sf.read(buf, dtype="int16", always_2d=False)
        if samples.ndim > 1:
            samples = samples[:, 0]  # take left channel
        if sr != 16000:
            # Simple linear resample (good enough for speech)
            ratio   = 16000 / sr
            new_len = int(len(samples) * ratio)
            samples = np.interp(
                np.linspace(0, len(samples) - 1, new_len),
                np.arange(len(samples)),
                samples.astype(np.float32),
            ).astype(np.int16)
        return samples.tobytes()
    except Exception:
            converted = _convert_with_ffmpeg(data)
            if converted is not None:
                return converted
            # Fall back to treating as raw PCM
            return data


@router.post("/speak")
async def synthesize_voiceover(
    request: Request,
    body: VoiceSpeakRequest,
) -> Response:
    text = _clean_spoken_text((body.text or "").strip())
    if not text:
        raise HTTPException(status_code=400, detail="Text is required.")

    settings = request.app.state.settings
    tts_cfg = settings.voice.get("tts", {})
    preferred_engine = tts_cfg.get("engine", "macos_say")

    if preferred_engine == "kokoro":
        import asyncio
        loop = asyncio.get_event_loop()
        try:
            audio_bytes, media_type = await loop.run_in_executor(
                _tts_executor, _synthesize_kokoro, settings, text
            )
        except Exception as exc:
            print(f"[Nova] Kokoro speak error: {exc} — falling back to macOS say.")
            audio_bytes, media_type = _synthesize_macos_say(settings, text)
        return Response(
            content=audio_bytes,
            media_type=media_type,
            headers={"Cache-Control": "no-store"},
        )

    api_key = settings.elevenlabs_api_key
    if not api_key or preferred_engine == "macos_say":
        audio_bytes, media_type = _synthesize_macos_say(settings, text)
        return Response(
            content=audio_bytes,
            media_type=media_type,
            headers={"Cache-Control": "no-store"},
        )

    elevenlabs_cfg = tts_cfg.get("elevenlabs", {})
    fallback_voice_id = elevenlabs_cfg.get("voice_id", "XB0fDUnXU5powFXDhCwa")
    voice_name = elevenlabs_cfg.get("voice_name")
    voice_id = _resolve_voice_id(request, voice_name, fallback_voice_id)

    try:
        from elevenlabs.client import ElevenLabs

        client = ElevenLabs(api_key=api_key)
        audio_gen = client.text_to_speech.convert(
            text=text,
            voice_id=voice_id,
            model_id=elevenlabs_cfg.get("model_id", "eleven_turbo_v2_5"),
            voice_settings={
                "stability": elevenlabs_cfg.get("stability", 0.5),
                "similarity_boost": elevenlabs_cfg.get("similarity_boost", 0.85),
            },
        )
        audio_bytes = b"".join(audio_gen)
    except Exception:
        audio_bytes, media_type = _synthesize_macos_say(settings, text)
        return Response(
            content=audio_bytes,
            media_type=media_type,
            headers={"Cache-Control": "no-store"},
        )

    return Response(
        content=audio_bytes,
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/speak/stream")
async def synthesize_stream(
    request: Request,
    body: VoiceSpeakRequest,
) -> Response:
    """Stream clause-by-clause WAV chunks for low time-to-first-audio and accurate word sync."""
    # Use the stream-specific cleaner — preserves newlines for finer chunking.
    text = _clean_text_for_tts_stream((body.text or "").strip())
    if not text:
        raise HTTPException(status_code=400, detail="Text is required.")

    settings = request.app.state.settings
    tts_cfg = settings.voice.get("tts", {})
    if tts_cfg.get("engine", "macos_say") != "kokoro":
        audio_bytes, media_type = _synthesize_macos_say(settings, text)
        return Response(content=audio_bytes, media_type=media_type,
                        headers={"Cache-Control": "no-store"})

    import asyncio
    from fastapi.responses import StreamingResponse

    async def generate():
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def produce():
            try:
                for chunk in _sentence_wav_chunks(settings, text):
                    loop.call_soon_threadsafe(queue.put_nowait, chunk)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        loop.run_in_executor(_tts_executor, produce)
        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield chunk

    return StreamingResponse(
        generate(),
        media_type="application/octet-stream",
        headers={"Cache-Control": "no-store", "X-Nova-TTS": "kokoro-stream"},
    )
