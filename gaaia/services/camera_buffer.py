"""
Session-scoped rolling state from a **live** camera stream (browser pushes JPEGs).

GAAIA prepends this to voice turns and text chat so the model sees what you are doing *now*,
not only a snapshot at the end of speech.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

# How long a session's last update stays "fresh" for prompts
LIVE_MAX_AGE_SEC = 42.0
# Full YOLO + Haar path only every N live frames (~1× per ~20s wall time; client sends ~2.2/s small JPEGs)
FULL_DETECT_EVERY_N_FRAMES = 44
# Live path skips Ollama entirely — scene line uses SCENE_UNAVAILABLE (utterance snapshot has scene when needed).

_lock = threading.Lock()
_processing_lock = threading.Lock()
_entries: dict[str, "LiveCameraEntry"] = {}
_live_frame_n: dict[str, int] = {}
# Consecutive full-detection frames with no person/face/hands/body (user likely left the frame).
_no_subject_streak: dict[str, int] = {}
# After this many empty full frames, drop live state so returning to the camera isn't fighting stale context.
CLEAR_AFTER_EMPTY_FULL_FRAMES = 4


@dataclass
class LiveCameraEntry:
    updated_at: float
    face_name: str | None
    face_confidence: float
    hand_summary: str
    detector_line: str
    vision_scene: str


def _detections_have_subject(dets: list[dict]) -> bool:
    """True if we see a person, face, hand, or pose — not an empty room."""
    for d in dets:
        t = d.get("type", "")
        if t in ("person", "face", "hand", "finger", "body", "body_part"):
            return True
    return False


def _truncate(s: str, max_len: int = 900) -> str:
    s = (s or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1].rstrip() + "…"


def refresh_from_frame(session_id: str, _settings, image_bytes: bytes, face_store) -> None:
    """
    Ingest one live frame (call from a worker thread).

    Drops frames while a previous live frame is still processing so voice/STT never pile up behind YOLO.
    Uses **one** MediaPipe pass per frame; full YOLO detect only occasionally.
    """
    sid = (session_id or "").strip()
    if not sid or not image_bytes:
        return

    if not _processing_lock.acquire(blocking=False):
        return

    detector_line = ""
    mp_hand_summary = ""
    face_name: str | None = None
    face_confidence = 0.0

    try:
        from gaaia.services.body_detector import BodyDetection, detect as mp_detect
        from gaaia.services.frame_detection import detect_all as frame_detect_all
        from gaaia.services.frame_detection import summarize_detections_for_voice

        mp_rows: list[BodyDetection] = []
        try:
            mp_rows, mp_hand_summary = mp_detect(image_bytes)
        except Exception as exc:
            print(f"[GAIA] Live camera MediaPipe error: {exc}")

        if any(getattr(d, "type", "") in ("face", "hand", "finger", "body", "body_part") for d in mp_rows):
            with _lock:
                _no_subject_streak[sid] = 0

        dlist = [
            {"type": d.type, "label": d.label, "confidence": d.confidence, "box": d.box} for d in mp_rows
        ]
        from gaaia.services.detection_geometry import (
            drop_faces_on_hands,
            drop_finger_and_hand_on_faces,
            nms_faces,
        )

        dlist = drop_faces_on_hands(dlist)
        dlist = nms_faces(dlist, iou_thresh=0.32)
        dlist = drop_finger_and_hand_on_faces(dlist)
        detector_line = summarize_detections_for_voice(dlist)

        with _lock:
            n = _live_frame_n.get(sid, 0) + 1
            _live_frame_n[sid] = n
            do_full = (n % FULL_DETECT_EVERY_N_FRAMES) == 0

        if do_full:
            try:
                dets = frame_detect_all(image_bytes, face_store)
                detector_line = summarize_detections_for_voice(dets)
                if _detections_have_subject(dets):
                    with _lock:
                        _no_subject_streak[sid] = 0
                else:
                    with _lock:
                        st = _no_subject_streak.get(sid, 0) + 1
                        _no_subject_streak[sid] = st
                        if st >= CLEAR_AFTER_EMPTY_FULL_FRAMES:
                            _entries.pop(sid, None)
                            _live_frame_n.pop(sid, None)
                            _no_subject_streak.pop(sid, None)
                    return
            except Exception as exc:
                print(f"[GAIA] Live camera full detector error: {exc}")

        if face_store is not None and getattr(face_store, "enabled", True):
            try:
                fn, fc = face_store.identify(image_bytes)
                face_name, face_confidence = fn, float(fc or 0.0)
            except Exception:
                pass

        now = time.time()
    finally:
        _processing_lock.release()

    entry = LiveCameraEntry(
        updated_at=now,
        face_name=face_name,
        face_confidence=face_confidence,
        hand_summary=(mp_hand_summary or "").strip(),
        detector_line=detector_line.strip(),
        vision_scene="",
    )

    with _lock:
        _entries[sid] = entry
        if len(_entries) > 200:
            cutoff = time.time() - 600.0
            dead = [k for k, v in _entries.items() if v.updated_at < cutoff]
            for k in dead[:80]:
                _entries.pop(k, None)
                _live_frame_n.pop(k, None)
                _no_subject_streak.pop(k, None)


def get_live_prefix_for_prompt(session_id: str, ref_name: str = "") -> str:
    """
    Compact prefix for the LLM, or empty if no fresh live feed.

    ``ref_name`` is the display name from voice (for Person line when face-id is weak).
    """
    from gaaia.services.camera_context import (
        SCENE_UNAVAILABLE,
        camera_who_line,
        hands_ground_truth_block,
    )

    sid = (session_id or "").strip()
    if not sid:
        return ""

    with _lock:
        ent = _entries.get(sid)
    if ent is None:
        return ""

    age = time.time() - ent.updated_at
    if age > LIVE_MAX_AGE_SEC:
        return ""

    who = camera_who_line(ent.face_name, ent.face_confidence, ent.detector_line, ref_name)
    hands_line, cam_instr = hands_ground_truth_block(ent.hand_summary or "", live=True)
    det_part = ent.detector_line
    det_clause = f" | Detector: {det_part}" if det_part else ""
    vis = _truncate(ent.vision_scene) if ent.vision_scene else SCENE_UNAVAILABLE

    return (
        f"[Live camera — feed ~{int(age)}s old | Person: {who} | {hands_line}{det_clause} | "
        f"Scene: {vis} | {cam_instr}]"
    )


def clear_session(session_id: str) -> None:
    sid = (session_id or "").strip()
    if not sid:
        return
    with _lock:
        _entries.pop(sid, None)
        _live_frame_n.pop(sid, None)
        _no_subject_streak.pop(sid, None)
