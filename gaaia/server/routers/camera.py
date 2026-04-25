from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from gaaia.server.dependencies import get_memory
from gaaia.memory.store import MemoryStore
from gaaia.services.frame_detection import detect_all as _detect_all

router = APIRouter()


def _require_local_request(request: Request) -> None:
    client_host = (request.client.host if request.client else "") or ""
    if client_host not in {"127.0.0.1", "::1", "localhost"} and not client_host.startswith("::ffff:127.0.0.1"):
        raise HTTPException(status_code=403, detail="Identity features are local-only.")


def _get_face_identity(request: Request):
    store = getattr(request.app.state, "face_identity", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Face identity service not available.")
    return store


# ── Detect ───────────────────────────────────────────────────────────

class DetectionBox(BaseModel):
    x: float
    y: float
    w: float
    h: float

class Detection(BaseModel):
    label: str
    type: str        # "face" | "object"
    confidence: float
    box: DetectionBox

class DetectResponse(BaseModel):
    detections: list[Detection]


@router.post("/detect", response_model=DetectResponse)
async def detect_frame(
    request: Request,
    image: UploadFile = File(..., description="JPEG or PNG camera frame"),
    memory: MemoryStore = Depends(get_memory),
):
    _require_local_request(request)
    raw = await image.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty image.")

    face_store = getattr(request.app.state, "face_identity", None)

    detections = await asyncio.to_thread(_detect_all, raw, face_store)

    # If no face was named by face recognition, label anonymous face boxes with the
    # voice-confirmed known user so the overlay stays informative across restarts.
    has_named_face = any(
        d.get("type") == "face" and d.get("label", "").lower() not in {"face", ""}
        for d in detections
    )
    if not has_named_face:
        known_display = memory.get_fact_value("user_display_name", "").strip()
        if known_display:
            for d in detections:
                if d.get("type") == "face":
                    d["label"] = known_display

    return DetectResponse(detections=[Detection(**d) for d in detections])


# ── Live stream (rolling buffer for prompts) ─────────────────────────

@router.post("/live")
async def ingest_live_frame(
    request: Request,
    session_id: str = Form(..., description="Chat / voice session id"),
    image: UploadFile = File(..., description="JPEG frame from the webcam"),
):
    """
    Push frames while the UI is open; GAAIA prepends the latest rolling summary to voice + text chat.
    Intended ~2–4 fps from the browser.
    """
    _require_local_request(request)
    raw = await image.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty image.")
    sid = (session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id is required.")

    settings = request.app.state.settings
    face_store = getattr(request.app.state, "face_identity", None)

    def _work() -> None:
        from gaaia.services.camera_buffer import refresh_from_frame

        refresh_from_frame(sid, settings, raw, face_store)

    await asyncio.to_thread(_work)
    return {"ok": True}


@router.post("/live/clear")
async def clear_live_buffer(
    request: Request,
    session_id: str = Form(..., description="Drop rolling live state for this session (e.g. voice UI closed)."),
):
    """Clear cached live-camera context so stepping away / closing mic does not leave stale prompts."""
    _require_local_request(request)
    sid = (session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id is required.")

    from gaaia.services.camera_buffer import clear_session

    clear_session(sid)
    return {"ok": True}


# ── Identify ──────────────────────────────────────────────────────────

class IdentifyResponse(BaseModel):
    name: str | None
    confidence: float
    enrolled_count: int


@router.post("/identify", response_model=IdentifyResponse)
async def identify_face(
    request: Request,
    image: UploadFile = File(..., description="JPEG or PNG camera frame"),
):
    _require_local_request(request)
    face_identity = _get_face_identity(request)
    raw = await image.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty image.")

    name, confidence = face_identity.identify(raw)
    profiles = face_identity.list_profiles()
    return IdentifyResponse(name=name, confidence=confidence, enrolled_count=len(profiles))


# ── Enroll ────────────────────────────────────────────────────────────

class EnrollResponse(BaseModel):
    name: str
    frames_saved: int
    sample_count: int


@router.post("/enroll", response_model=EnrollResponse)
async def enroll_face(
    request: Request,
    name: str = Form(..., description="Person's name"),
    images: list[UploadFile] = File(..., description="One or more JPEG/PNG frames"),
):
    _require_local_request(request)
    if not name.strip():
        raise HTTPException(status_code=400, detail="Name is required.")
    if not images:
        raise HTTPException(status_code=400, detail="At least one image is required.")

    face_identity = _get_face_identity(request)
    image_bytes_list = [await img.read() for img in images]
    image_bytes_list = [b for b in image_bytes_list if b]

    if not image_bytes_list:
        raise HTTPException(status_code=400, detail="All uploaded images were empty.")

    frames_saved = face_identity.enroll(name.strip(), image_bytes_list)
    profiles = face_identity.list_profiles()
    sample_count = next(
        (p["sample_count"] for p in profiles if p["name"].lower() == name.strip().lower()),
        frames_saved,
    )
    return EnrollResponse(name=name.strip(), frames_saved=frames_saved, sample_count=sample_count)


# ── Profiles ──────────────────────────────────────────────────────────

class ProfileEntry(BaseModel):
    name: str
    sample_count: int
    enrolled_at: float


class IdentitySummaryEntry(BaseModel):
    name: str
    has_face: bool
    has_voice: bool
    face_samples: int
    voice_samples: int
    total_samples: int


@router.get("/profiles", response_model=list[ProfileEntry])
async def list_profiles(request: Request):
    _require_local_request(request)
    face_identity = _get_face_identity(request)
    return face_identity.list_profiles()


@router.get("/identities", response_model=list[IdentitySummaryEntry])
async def list_identities(request: Request):
    _require_local_request(request)

    face_identity = _get_face_identity(request)
    face_profiles = face_identity.list_profiles()
    face_map = {
        str(profile["name"]): int(profile.get("sample_count", 0))
        for profile in face_profiles
    }

    settings = request.app.state.settings
    speaker_path = Path(settings.data_dir / "speaker_profiles.json").expanduser()
    voice_map: dict[str, int] = {}
    if speaker_path.exists():
        try:
            payload = json.loads(speaker_path.read_text())
            profiles = payload.get("profiles", {})
            if isinstance(profiles, dict):
                for name, record in profiles.items():
                    if isinstance(record, dict):
                        voice_map[str(name)] = int(record.get("samples", 0))
        except Exception:
            voice_map = {}

    names = sorted(set(face_map) | set(voice_map), key=str.lower)
    return [
        IdentitySummaryEntry(
            name=name,
            has_face=name in face_map,
            has_voice=name in voice_map,
            face_samples=face_map.get(name, 0),
            voice_samples=voice_map.get(name, 0),
            total_samples=face_map.get(name, 0) + voice_map.get(name, 0),
        )
        for name in names
    ]


@router.delete("/profiles/{name}")
async def delete_profile(name: str, request: Request):
    _require_local_request(request)
    face_identity = _get_face_identity(request)
    deleted_face = face_identity.delete_profile(name)
    from gaaia.server.routers.voice import _get_speaker_identity

    deleted_voice = _get_speaker_identity(request).delete_profile(name)
    if not deleted_face and not deleted_voice:
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found.")
    return {"deleted": name, "face": deleted_face, "voice": deleted_voice}
