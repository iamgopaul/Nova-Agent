"""
MediaPipe **Tasks** Hand Landmarker for snapshots (voice, /camera/detect).

Pipelines upscaled input + flips + CLAHE — tuned for webcams / selfies.
(Legacy `mediapipe.solutions` was removed from recent pip wheels — we use Tasks only.)
"""

from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()

# Strong upscale: small laptop / phone preview JPEGs need more pixels for palm detection.
_MIN_SHORT_EDGE = 768


class _Pt:
    __slots__ = ("x", "y", "z")

    def __init__(self, x: float, y: float, z: float = 0.0):
        self.x = x
        self.y = y
        self.z = z


class _HandLike:
    """Matches `hand_lm.landmark[i]` access expected by `body_detector`."""

    def __init__(self, landmarks: list[_Pt]):
        self.landmark = landmarks


def _clahe_rgb(img_rgb):
    """Mild contrast normalization — helps indoor / backlit webcam without changing semantics much."""
    import cv2

    try:
        lab = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
        l2 = clahe.apply(l_ch)
        merged = cv2.merge((l2, a_ch, b_ch))
        return cv2.cvtColor(merged, cv2.COLOR_LAB2RGB)
    except Exception:
        return img_rgb


def _from_task_result(res, ww: int, wh: int, w0: int, h0: int, mirror_x_output: bool) -> list[tuple[Any, str, float]]:
    out: list[tuple[Any, str, float]] = []
    for hi, hand_lms in enumerate(res.hand_landmarks):
        pts: list[_Pt] = []
        for lm in hand_lms:
            nx, ny = float(lm.x), float(lm.y)
            if mirror_x_output:
                nx = 1.0 - nx
            nz = float(getattr(lm, "z", 0.0) or 0.0)
            ox = (nx * ww) / w0
            oy = (ny * wh) / h0
            pts.append(_Pt(ox, oy, nz))
        side = "Hand"
        conf = 0.9
        if res.handedness and hi < len(res.handedness):
            cat = res.handedness[hi][0]
            side = cat.category_name
            conf = float(cat.score)
        # Inference ran on a horizontally flipped image; handedness is relative to that input.
        # Swap so labels match the original (unflipped) frame and the user's left/right.
        if mirror_x_output and side in ("Left", "Right"):
            side = "Right" if side == "Left" else "Left"
        out.append((_HandLike(pts), side, conf))
    return out


def _run_hand_tasks(work_rgb, ww: int, wh: int, w0: int, h0: int, mirror_x_output: bool) -> list[tuple[Any, str, float]]:
    import numpy as np
    from mediapipe.tasks.python.vision.core.image import Image, ImageFormat

    from nova.services.mediapipe_tasks_runtime import get_hand_landmarker

    mp_image = Image(ImageFormat.SRGB, np.ascontiguousarray(work_rgb))
    with _lock:
        res = get_hand_landmarker().detect(mp_image)
    return _from_task_result(res, ww, wh, w0, h0, mirror_x_output)


def _detect_hands_once(
    img_rgb,
    *,
    mirror_x_output: bool,
) -> list[tuple[Any, str, float]]:
    import cv2

    h0, w0 = img_rgb.shape[0], img_rgb.shape[1]
    work = img_rgb
    ww, wh = w0, h0
    short = min(h0, w0)
    if short < _MIN_SHORT_EDGE:
        scale = float(_MIN_SHORT_EDGE) / float(short)
        ww = max(1, int(round(w0 * scale)))
        wh = max(1, int(round(h0 * scale)))
        work = cv2.resize(img_rgb, (ww, wh), interpolation=cv2.INTER_LINEAR)

    try:
        out = _run_hand_tasks(img_rgb, w0, h0, w0, h0, mirror_x_output)
        if out:
            return out
        if work is not img_rgb:
            out = _run_hand_tasks(work, ww, wh, w0, h0, mirror_x_output)
            if out:
                return out
    except Exception as exc:
        print(f"[Nova] Hand Landmarker detect error: {exc}", flush=True)
    return []


def detect_hands_task_or_legacy(img_rgb, _legacy_unused=None) -> list[tuple[Any, str, float]]:
    """
    Returns [(hand_adapter, side_name, confidence), ...].
    Landmarks are normalized to the **original** `img_rgb` width/height.
    Second argument is unused (kept for call-site compatibility).
    """
    import cv2

    first = _detect_hands_once(img_rgb, mirror_x_output=False)
    if first:
        return first
    flipped = cv2.flip(img_rgb, 1)
    second = _detect_hands_once(flipped, mirror_x_output=True)
    if second:
        return second

    boosted = _clahe_rgb(img_rgb)
    third = _detect_hands_once(boosted, mirror_x_output=False)
    if third:
        return third
    fourth = _detect_hands_once(cv2.flip(boosted, 1), mirror_x_output=True)
    return fourth if fourth else []
