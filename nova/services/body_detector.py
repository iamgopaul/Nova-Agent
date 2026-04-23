from __future__ import annotations

"""
MediaPipe **Tasks** body-part detector (Hand / Face / Pose landmarker).

Returns bounding boxes (0-1 normalised) and labels for:
  - Faces (with landmarks for nose, eyes, ears)
  - Hands (which digits are extended: thumb, index, middle, ring, pinky)
  - Full-body pose landmarks (wrists, elbows, shoulders, feet, etc.)
"""

import math
import threading
from dataclasses import dataclass

_lock = threading.Lock()


@dataclass(frozen=True)
class FingerStates:
    """Which digits are classified as extended (MediaPipe landmarks)."""

    thumb: bool
    index: bool
    middle: bool
    ring: bool
    pinky: bool

    def count(self) -> int:
        return int(self.thumb) + int(self.index) + int(self.middle) + int(self.ring) + int(self.pinky)


def _extended_digit_names(fs: FingerStates) -> list[str]:
    out: list[str] = []
    if fs.thumb:
        out.append("thumb")
    if fs.index:
        out.append("index")
    if fs.middle:
        out.append("middle")
    if fs.ring:
        out.append("ring")
    if fs.pinky:
        out.append("pinky")
    return out


def _hand_overlay_label(side: str) -> str:
    """Whole-hand outline only — per-finger boxes are labelled thumb/index/… separately."""
    return f"{side} hand"


def _hand_ground_truth_phrase(side: str, fs: FingerStates) -> str:
    """One sentence for the LLM: exact digit names (not just a count)."""
    names = _extended_digit_names(fs)
    if not names:
        return (
            f"{side} hand: no fingers clearly extended (fist or unclear pose). "
            "If asked which finger, say the tracker did not register an extended digit."
        )
    if len(names) == 1:
        n = names[0]
        if n == "thumb":
            return f"{side} hand: ground truth — only the thumb is extended."
        return f"{side} hand: ground truth — only the {n} finger is extended."
    oxford = ", ".join(names[:-1]) + f", and {names[-1]}"
    return (
        f"{side} hand: ground truth — extended digits are {oxford} ({fs.count()} total). "
        "When asked which finger(s), name these digits only."
    )

# Overlay density: per-finger and per-pose-joint boxes clutter the preview; hand/body outline still show state.
EMIT_FINGER_SEGMENT_BOXES = True
EMIT_POSE_LANDMARK_BOXES = False


def _hand_pipeline_settings() -> tuple[str, str, bool]:
    """Returns (backend, mmpose_device, fallback_to_mediapipe)."""
    try:
        from config.settings import get_settings

        cam = get_settings().camera
        backend = str(cam.get("hand_backend", "mediapipe")).strip().lower()
        device = str(cam.get("mmpose_device", "cpu")).strip() or "cpu"
        fallback = bool(cam.get("hand_mmpose_fallback", True))
        if backend not in ("mediapipe", "mmpose"):
            backend = "mediapipe"
        return backend, device, fallback
    except Exception:
        return "mediapipe", "cpu", True


def _detect_hands_for_frame(img_rgb):
    """Resolve hand_backend: MMPose (optional) or MediaPipe (+ legacy Tasks)."""
    backend, mp_dev, mp_fallback = _hand_pipeline_settings()
    if backend == "mmpose":
        from nova.services.mmpose_hand_runner import detect_hands_mmpose

        rows = detect_hands_mmpose(img_rgb, device=mp_dev)
        if rows or not mp_fallback:
            return rows
    from nova.services.hand_landmarker_runner import detect_hands_task_or_legacy

    return detect_hands_task_or_legacy(img_rgb)


@dataclass
class BodyDetection:
    label: str          # e.g. "face", "Left hand" (outline), "Left thumb" (finger segment)
    type: str           # "face" | "hand" | "finger" | "body" | "body_part"
    confidence: float
    box: dict           # {x, y, w, h} normalised 0-1


class _PoseLm:
    """BlazePose-compatible view of Tasks NormalizedLandmark."""

    __slots__ = ("x", "y", "visibility")

    def __init__(self, lm) -> None:
        self.x = float(lm.x or 0.0)
        self.y = float(lm.y or 0.0)
        if lm.visibility is not None:
            self.visibility = float(lm.visibility)
        elif getattr(lm, "presence", None) is not None:
            self.visibility = float(lm.presence)
        else:
            self.visibility = 0.5


def _d2(a, b) -> float:
    """Squared distance between two normalized landmarks (x,y; z down-weighted)."""
    dz = (getattr(a, "z", 0) or 0) - (getattr(b, "z", 0) or 0)
    return (a.x - b.x) ** 2 + (a.y - b.y) ** 2 + dz * dz * 0.25


def _infer_hand_side_from_landmarks(lm) -> tuple[str | None, float]:
    """
    Palm toward camera (typical selfie): thumb tip (4) vs pinky tip (20) x-order is a strong cue.
    Returns (side, thumb–pinky separation in norm coords) for confidence gating.
    """
    try:
        t4, t20 = lm[4], lm[20]
        sep = abs(float(t4.x) - float(t20.x))
        if sep >= 0.018:
            side = "Right" if float(t4.x) < float(t20.x) else "Left"
            return side, sep
        i5, i17 = lm[5], lm[17]
        sep2 = abs(float(i5.x) - float(i17.x))
        if sep2 >= 0.015:
            side = "Right" if float(i5.x) < float(i17.x) else "Left"
            return side, sep2
    except (IndexError, TypeError, ValueError, AttributeError):
        pass
    return None, 0.0


def _normalize_hand_side(hand_landmarks, side: str) -> str:
    s = (side or "").strip()
    inferred, spread = _infer_hand_side_from_landmarks(hand_landmarks.landmark)
    if s not in ("Left", "Right"):
        return inferred if inferred else (s if s else "Hand")
    if inferred and inferred != s and spread >= 0.04:
        return inferred
    return s


def _mirror_swap_handedness_label(side_geo: str) -> str:
    """
    Raw webcam frames are not mirrored; the UI preview often is. Swap Left/Right on labels so
    \"Left hand\" / \"Right: Index\" match what the user sees. Finger-counting still uses `side_geo`.
    """
    if side_geo not in ("Left", "Right"):
        return side_geo
    try:
        from config.settings import get_settings

        if not get_settings().camera.get("swap_handedness_for_mirrored_camera", False):
            return side_geo
    except Exception:
        return side_geo
    return "Right" if side_geo == "Left" else "Left"


def _angle_deg_at_joint(prev_lm, joint_lm, next_lm) -> float:
    """Interior angle at `joint` (degrees). Uses x,y only (stable for webcam)."""
    import math

    v1 = (prev_lm.x - joint_lm.x, prev_lm.y - joint_lm.y)
    v2 = (next_lm.x - joint_lm.x, next_lm.y - joint_lm.y)
    n1 = math.hypot(v1[0], v1[1])
    n2 = math.hypot(v2[0], v2[1])
    if n1 < 1e-8 or n2 < 1e-8:
        return 0.0
    dot = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
    return math.degrees(math.acos(dot))


def _finger_states(hand_landmarks, handedness: str) -> FingerStates:
    """
    Index–pinky: conservative PIP/DIP + tip–knuckle checks so curled digits do not get overlay boxes.
    Thumb: stricter IP angle + spread (aligned with “holding up” vs resting on palm).
    """
    lm = hand_landmarks.landmark
    wrist = 0

    def _digit_up(mcp_i: int, pip_i: int, dip_i: int, tip_i: int) -> bool:
        ang_pip = _angle_deg_at_joint(lm[mcp_i], lm[pip_i], lm[tip_i])
        ang_dip = _angle_deg_at_joint(lm[pip_i], lm[dip_i], lm[tip_i])
        if ang_pip < 82.0:
            return False
        dt_m = _d2(lm[tip_i], lm[mcp_i])
        dp_m = max(_d2(lm[pip_i], lm[mcp_i]), 1e-9)
        tip_past_pip = dt_m > dp_m * 1.16
        dt_w = _d2(lm[tip_i], lm[wrist])
        dp_w = max(_d2(lm[pip_i], lm[wrist]), 1e-9)
        tip_clear = dt_w > dp_w * 1.10
        if ang_pip >= 132.0 and ang_dip >= 108.0 and tip_past_pip:
            return True
        if ang_pip >= 118.0 and ang_dip >= 100.0 and tip_past_pip and tip_clear:
            return True
        if ang_pip >= 126.0 and ang_dip >= 96.0 and tip_past_pip and tip_clear and dt_m > dp_m * 1.22:
            return True
        return False

    index = _digit_up(5, 6, 7, 8)
    middle = _digit_up(9, 10, 11, 12)
    ring = _digit_up(13, 14, 15, 16)
    pinky = _digit_up(17, 18, 19, 20)

    ang_thumb = _angle_deg_at_joint(lm[2], lm[3], lm[4])
    if ang_thumb < 92.0:
        thumb = False
    else:
        t_dist = _d2(lm[4], lm[2]) > _d2(lm[3], lm[2]) * 1.16
        idx_mcp = lm[5]
        pinky_mcp = lm[17]
        spread = math.hypot(lm[4].x - idx_mcp.x, lm[4].y - idx_mcp.y)
        palm_w = max(math.hypot(lm[2].x - idx_mcp.x, lm[2].y - idx_mcp.y), 1e-6)
        palm_span = max(math.hypot(idx_mcp.x - pinky_mcp.x, idx_mcp.y - pinky_mcp.y), 1e-6)
        tip_ip_clear = _d2(lm[4], lm[wrist]) > _d2(lm[3], lm[wrist]) * 1.10
        palm_cx = (lm[0].x + lm[5].x + lm[9].x + lm[13].x + lm[17].x) / 5.0
        palm_cy = (lm[0].y + lm[5].y + lm[9].y + lm[13].y + lm[17].y) / 5.0
        tip_from_center = math.hypot(lm[4].x - palm_cx, lm[4].y - palm_cy)
        tip_outside_palm = tip_from_center > palm_span * 0.46
        if handedness in ("Left", "Right"):
            thumb_splayed = (lm[4].x < lm[3].x) if handedness == "Right" else (lm[4].x > lm[3].x)
        else:
            thumb_splayed = True
        thumb = t_dist and tip_ip_clear and tip_outside_palm and (
            (ang_thumb >= 132.0 and spread > palm_w * 0.92)
            or (ang_thumb >= 120.0 and thumb_splayed and spread > palm_w * 1.05)
        )

    return FingerStates(thumb=thumb, index=index, middle=middle, ring=ring, pinky=pinky)


def _landmarks_to_box(landmarks, img_w: int, img_h: int, pad: float = 0.02) -> dict:
    xs = [lm.x for lm in landmarks]
    ys = [lm.y for lm in landmarks]
    x_min, x_max = max(0.0, min(xs)), min(1.0, max(xs))
    y_min, y_max = max(0.0, min(ys)), min(1.0, max(ys))
    return {
        "x": round(max(0.0, x_min - pad), 4),
        "y": round(max(0.0, y_min - pad), 4),
        "w": round(min(1.0, x_max - x_min + 2 * pad), 4),
        "h": round(min(1.0, y_max - y_min + 2 * pad), 4),
    }


def _segment_box_from_indices(landmarks, indices: tuple[int, ...], min_side: float = 0.034) -> dict:
    """Tight box around a chain of landmarks; enforced minimum size so overlays stay visible."""
    lm = landmarks
    xs = [lm[i].x for i in indices]
    ys = [lm[i].y for i in indices]
    raw_x0, raw_x1 = max(0.0, min(xs)), min(1.0, max(xs))
    raw_y0, raw_y1 = max(0.0, min(ys)), min(1.0, max(ys))
    w = max(raw_x1 - raw_x0, min_side)
    h = max(raw_y1 - raw_y0, min_side)
    cx = (raw_x0 + raw_x1) / 2
    cy = (raw_y0 + raw_y1) / 2
    x0 = max(0.0, cx - w / 2)
    y0 = max(0.0, cy - h / 2)
    if x0 + w > 1.0:
        x0 = max(0.0, 1.0 - w)
    if y0 + h > 1.0:
        y0 = max(0.0, 1.0 - h)
    return {
        "x": round(x0, 4),
        "y": round(y0, 4),
        "w": round(min(w, 1.0 - x0), 4),
        "h": round(min(h, 1.0 - y0), 4),
    }


def _hand_landmarks_to_tight_box(landmarks) -> dict:
    """
    Tighter AABB around palm + digits (full hand silhouette), not the entire MP arm span.
    Uses wrist, palm bases, and finger tips — avoids oversized pads.
    """
    lm = landmarks
    # Wrist, thumb side, pinky base, finger tips (MediaPipe order)
    idxs = (
        0, 1, 2, 3, 4,  # thumb chain
        5, 6, 7, 8,      # index
        9, 10, 11, 12,  # middle
        13, 14, 15, 16,  # ring
        17, 18, 19, 20,  # pinky
    )
    xs = [lm[i].x for i in idxs]
    ys = [lm[i].y for i in idxs]
    x_min, x_max = max(0.0, min(xs)), min(1.0, max(xs))
    y_min, y_max = max(0.0, min(ys)), min(1.0, max(ys))
    pw, ph = x_max - x_min, y_max - y_min
    # Slight asymmetric pad: knuckles need a hair more room upward (lower y in image = higher on screen)
    px = max(0.01, min(0.04, pw * 0.08 + 0.01))
    py_top = max(0.01, min(0.05, ph * 0.1 + 0.012))
    py_bot = max(0.008, min(0.04, ph * 0.06 + 0.008))
    return {
        "x": round(max(0.0, x_min - px), 4),
        "y": round(max(0.0, y_min - py_top), 4),
        "w": round(min(1.0, x_max - x_min + 2 * px), 4),
        "h": round(min(1.0, y_max - y_min + py_top + py_bot), 4),
    }


# BlazePose 33 landmarks — full-body map for overlay
_POSE_ALL: dict[int, str] = {
    0: "nose",
    1: "L eye in",
    2: "L eye",
    3: "L eye out",
    4: "R eye in",
    5: "R eye",
    6: "R eye out",
    7: "L ear",
    8: "R ear",
    9: "mouth L",
    10: "mouth R",
    11: "L shoulder",
    12: "R shoulder",
    13: "L elbow",
    14: "R elbow",
    15: "L wrist",
    16: "R wrist",
    17: "L pinky",
    18: "R pinky",
    19: "L index",
    20: "R index",
    21: "L thumb",
    22: "R thumb",
    23: "L hip",
    24: "R hip",
    25: "L knee",
    26: "R knee",
    27: "L ankle",
    28: "R ankle",
    29: "L heel",
    30: "R heel",
    31: "L toes",
    32: "R toes",
}

_FINGER_CHAINS: tuple[tuple[str, tuple[int, ...]], ...] = (
    ("thumb", (1, 2, 3, 4)),
    ("index", (5, 6, 7, 8)),
    ("middle", (9, 10, 11, 12)),
    ("ring", (13, 14, 15, 16)),
    ("pinky", (17, 18, 19, 20)),
)


def detect(image_bytes: bytes) -> tuple[list[BodyDetection], str]:
    """
    Run all detectors on a JPEG/PNG frame.
    Returns (detections, hand_summary_text).
    hand_summary_text lists which digits are extended per hand, e.g.
    "Left hand: ground truth — extended digits are thumb, index, and middle (3 total). ..."
    """
    from nova.services.image_decode import bytes_to_rgb

    img_rgb = bytes_to_rgb(image_bytes)
    if img_rgb is None:
        return [], ""

    h, w = img_rgb.shape[:2]
    detections: list[BodyDetection] = []
    hand_parts: list[str] = []

    with _lock:
        from nova.services.mediapipe_tasks_runtime import (
            get_face_detector,
            get_pose_landmarker,
            numpy_rgb_to_mp_image,
        )

        mp_img = numpy_rgb_to_mp_image(img_rgb)

        # ── Hands: MediaPipe Tasks (default) or optional MMPose RTMPose `hand` alias ──
        hand_rows = _detect_hands_for_frame(img_rgb)
        hand_rows = sorted(hand_rows, key=lambda r: float(r[0].landmark[0].x))
        for hand_lm, side, conf in hand_rows:
            side_geo = _normalize_hand_side(hand_lm, side)
            fs = _finger_states(hand_lm, side_geo)
            side = _mirror_swap_handedness_label(side_geo)
            label = _hand_overlay_label(side)
            box = _hand_landmarks_to_tight_box(hand_lm.landmark)
            detections.append(
                BodyDetection(label=label, type="hand", confidence=round(conf, 2), box=box)
            )
            hand_parts.append(_hand_ground_truth_phrase(side, fs))
            if EMIT_FINGER_SEGMENT_BOXES:
                for fname, idxs in _FINGER_CHAINS:
                    if not getattr(fs, fname, False):
                        continue
                    fbox = _segment_box_from_indices(hand_lm.landmark, idxs, min_side=0.022)
                    detections.append(
                        BodyDetection(
                            label=f"{side} {fname}",
                            type="finger",
                            confidence=round(conf, 2),
                            box=fbox,
                        )
                    )

        # ── Face (Tasks FaceDetector — BlazeFace, pixel boxes → normalized) ──
        primary_face_xywh: tuple[float, float, float, float, float] | None = None
        try:
            fd = get_face_detector()
            face_results = fd.detect(mp_img)
            if face_results.detections:
                best = max(
                    face_results.detections,
                    key=lambda d: float(d.categories[0].score) if d.categories else 0.0,
                )
                bb = best.bounding_box
                score = float(best.categories[0].score) if best.categories else 0.0
                rx = float(bb.origin_x) / float(w)
                ry = float(bb.origin_y) / float(h)
                rw = float(bb.width) / float(w)
                rh = float(bb.height) / float(h)
                mx = rw * 0.06
                my_top = rh * 0.08
                my_bot = rh * 0.05
                xmin = max(0.0, rx - mx * 0.5)
                ymin = max(0.0, ry - my_top)
                fw = min(1.0 - xmin, rw + mx)
                fh = min(1.0 - ymin, rh + my_top + my_bot)
                primary_face_xywh = (xmin, ymin, fw, fh, score)
                detections.append(
                    BodyDetection(
                        label="face",
                        type="face",
                        confidence=round(score, 2),
                        box={
                            "x": round(xmin, 4),
                            "y": round(ymin, 4),
                            "w": round(fw, 4),
                            "h": round(fh, 4),
                        },
                    )
                )
        except Exception as exc:
            print(f"[Nova] MediaPipe FaceDetector error: {exc}", flush=True)

        # ── Pose (Tasks PoseLandmarker — 33-pt BlazePose topology) ───────────
        try:
            pl = get_pose_landmarker()
            pose_results = pl.detect(mp_img)
            if pose_results.pose_landmarks:
                raw = pose_results.pose_landmarks[0]
                if len(raw) >= 33:
                    lms = [_PoseLm(raw[i]) for i in range(33)]
                    vis_thr = 0.25
                    visible_points = [lm for lm in lms if lm.visibility >= vis_thr]
                    if visible_points:
                        detections.append(
                            BodyDetection(
                                label="body",
                                type="body",
                                confidence=round(
                                    min(1.0, sum(lm.visibility for lm in visible_points) / len(visible_points)),
                                    2,
                                ),
                                box=_landmarks_to_box(visible_points, w, h, pad=0.05),
                            )
                        )
                    if EMIT_POSE_LANDMARK_BOXES:
                        for idx, part_name in _POSE_ALL.items():
                            lm = lms[idx]
                            if lm.visibility < vis_thr:
                                continue
                            if primary_face_xywh is not None and idx <= 10:
                                fx, fy, fww, fhh, _fs = primary_face_xywh
                                px, py = lm.x, lm.y
                                if fx <= px <= fx + fww and fy <= py <= fy + fhh:
                                    continue
                            r = 0.032
                            detections.append(
                                BodyDetection(
                                    label=part_name,
                                    type="body_part",
                                    confidence=round(lm.visibility, 2),
                                    box={
                                        "x": round(max(0.0, lm.x - r), 4),
                                        "y": round(max(0.0, lm.y - r), 4),
                                        "w": round(min(1.0 - max(0.0, lm.x - r), 2 * r), 4),
                                        "h": round(min(1.0 - max(0.0, lm.y - r), 2 * r), 4),
                                    },
                                )
                            )
        except Exception as exc:
            print(f"[Nova] MediaPipe PoseLandmarker error: {exc}", flush=True)

    hand_summary = " ".join(hand_parts) if hand_parts else "No hands detected."
    return detections, hand_summary


def pick_frame_best_hands(jpeg_frames: list[bytes]) -> bytes | None:
    """
    Choose one camera frame that has the strongest hand detection.

    Voice mode used to take a single snapshot *after* recording ended, when the user may have
    already lowered their hand. The client can now send a short burst; this picks the best.

    Uses only the hand landmarker path for scoring (not full face/pose) so burst scoring stays cheap.
    """
    from nova.services.image_decode import bytes_to_rgb

    valid = [f for f in jpeg_frames if f]
    if not valid:
        return None
    if len(valid) == 1:
        return valid[0]

    def _count_hands_only(fb: bytes) -> int:
        img_rgb = bytes_to_rgb(fb)
        if img_rgb is None:
            return 0
        with _lock:
            return len(_detect_hands_for_frame(img_rgb))

    scored: list[tuple[int, bytes]] = []
    for fb in valid:
        try:
            scored.append((_count_hands_only(fb), fb))
        except Exception:
            scored.append((0, fb))

    max_n = max(s[0] for s in scored)
    best_fb = valid[-1]
    for n, fb in scored:
        if n == max_n:
            best_fb = fb
    return best_fb
