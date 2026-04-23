"""
Shared one-line formatters for camera / voice prompts (live stream + utterance snapshots).
"""

from __future__ import annotations

import re

_DETECTOR_FACE_NAMES_RE = re.compile(r"faces \(from detector\):\s*([^|]+)", re.IGNORECASE)

SCENE_UNAVAILABLE = "(scene description unavailable — Hands and Detector lines above still apply)"


def display_face_label(det_name: str, ref_name: str) -> str:
    """Show 'Josh' instead of enrolled slug `Josh_Gopaul` when they clearly match."""
    dn = (det_name or "").replace("_", " ").strip()
    ref = (ref_name or "").strip()
    if not ref:
        return dn or det_name
    if ref.lower() in dn.lower():
        return ref
    parts = dn.lower().split()
    if parts and parts[0] == ref.lower():
        return ref
    return dn or det_name


def detector_face_names(detector_summary: str) -> list[str]:
    if not detector_summary or not detector_summary.strip():
        return []
    m = _DETECTOR_FACE_NAMES_RE.search(detector_summary)
    if not m:
        return []
    return [x.strip() for x in m.group(1).split(",") if x.strip()]


def camera_who_line(
    face_name: str | None,
    face_confidence: float | None,
    detector_summary: str,
    ref_name: str,
) -> str:
    """Prefer full-frame face-id; fall back to detector crop IDs; then voice-only name."""
    conf = face_confidence or 0.0
    if face_name and conf > 0.4:
        shown = display_face_label(face_name, ref_name)
        return f"{shown} ({int(conf * 100)}% full-frame face-id)"
    det_names = detector_face_names(detector_summary)
    if det_names:
        extra = f"; full-frame face-id {int(conf * 100)}%" if face_name and conf > 0 else ""
        shown = display_face_label(det_names[0], ref_name)
        return f"{shown} (face from detector){extra}"
    if ref_name:
        return (
            f"{ref_name} (identified by voice — automated face match may be missing; "
            "they can still be on camera; do not say they are invisible or absent)"
        )
    return "person on camera (automated face match unavailable — do not claim no one is there)"


def hands_ground_truth_block(hand_summary: str, *, live: bool = False) -> tuple[str, str]:
    """Returns (compact hands line, single instruction for the model)."""
    h = (hand_summary or "").strip()
    if not h or h == "No hands detected.":
        if live:
            return (
                "Hands: no confident hand pose in the latest processed frame (lighting, motion, or angle).",
                "Instruction: Never tell the user they are not on camera or not visible. If asked about "
                "hands or fingers, say your **software** did not lock a hand in this frame — suggest "
                "holding still, palms toward the camera, good light, larger in frame. Do not infer "
                "finger counts from Scene.",
            )
        return (
            "Hands: no confident hand pose in these snapshot frames.",
            "Instruction: Never say the user is not on camera or not visible. If asked about hands, say "
            "the **tracker** did not lock this time — suggest steady pose, larger in frame, light, palms "
            "toward camera. Do not insist their hand was absent. Do not infer finger counts from Scene.",
        )
    return (
        f"Hands: {h}",
        "Instruction: for how many fingers OR which specific fingers (thumb, index, middle, ring, pinky), "
        "use ONLY the Hands line — repeat the exact digit names listed there. Ignore Scene if it conflicts.",
    )
