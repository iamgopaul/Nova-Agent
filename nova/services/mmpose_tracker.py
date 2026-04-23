"""
Optional MMPose RTMPose **hand** pipeline (alias: ``hand`` — SSDLite hand detector + RTMPose-m).

Install (heavy — see https://mmpose.readthedocs.io/en/latest/installation.html):
  ``pip install mmengine`` and a matching ``mmcv`` wheel for your PyTorch/CUDA, then ``pip install mmpose``.

If imports fail, Nova falls back to MediaPipe when ``hand_mmpose_fallback`` is true.
"""

from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_inferencer: Any = None
_inferencer_failed: bool = False
_warned: bool = False


class _Pt:
    __slots__ = ("x", "y", "z")

    def __init__(self, x: float, y: float, z: float = 0.0):
        self.x = x
        self.y = y
        self.z = z


class _HandLike:
    def __init__(self, landmarks: list[_Pt]):
        self.landmark = landmarks


def _parse_instances(raw: dict) -> list[dict]:
    """Normalize inferencer output across MMPose versions."""
    preds = raw.get("predictions")
    if not preds:
        return []
    first = preds[0]
    if isinstance(first, list):
        return [x for x in first if isinstance(x, dict)]
    if isinstance(first, dict):
        return [first]
    return []


def _kpts_from_instance(inst: dict) -> tuple[Any, Any]:
    import numpy as np

    kpts = inst.get("keypoints")
    scores = inst.get("keypoint_scores") or inst.get("keypoint_score")
    if kpts is None:
        return None, None
    arr = np.asarray(kpts, dtype=np.float32)
    if arr.ndim == 1:
        return None, None
    return arr, scores


def _instances_to_hand_rows(
    instances: list[dict],
    img_w: int,
    img_h: int,
) -> list[tuple[Any, str, float]]:
    """Build MediaPipe-compatible hand rows: (hand_like, Left|Right, conf)."""
    prepared: list[tuple[float, dict, float]] = []
    for inst in instances:
        kpts, scores = _kpts_from_instance(inst)
        if kpts is None or len(kpts) < 21:
            continue
        conf = 0.85
        if scores is not None:
            import numpy as np

            sc = np.asarray(scores, dtype=np.float32).reshape(-1)
            if sc.size >= 21:
                conf = float(max(0.15, min(1.0, float(sc[:21].mean()))))
        wx = float(kpts[0][0]) / float(img_w)
        prepared.append((wx, inst, conf))

    prepared.sort(key=lambda t: t[0])
    prepared = prepared[:2]

    out: list[tuple[Any, str, float]] = []
    for i, (_wx, inst, conf) in enumerate(prepared):
        kpts, _scores = _kpts_from_instance(inst)
        if kpts is None:
            continue
        pts: list[_Pt] = []
        for j in range(min(21, len(kpts))):
            nx = float(kpts[j][0]) / float(img_w)
            ny = float(kpts[j][1]) / float(img_h)
            pts.append(_Pt(nx, ny, 0.0))
        while len(pts) < 21:
            pts.append(pts[-1])
        if len(prepared) == 1:
            side = "Left" if _wx < 0.5 else "Right"
        else:
            side = "Left" if i == 0 else "Right"
        out.append((_HandLike(pts), side, conf))
    return out


def _get_inferencer(device: str):
    global _inferencer, _inferencer_failed, _warned
    if _inferencer_failed:
        return None
    if _inferencer is not None:
        return _inferencer
    with _lock:
        if _inferencer_failed:
            return None
        if _inferencer is not None:
            return _inferencer
        try:
            from mmpose.apis import MMPoseInferencer  # type: ignore

            dev = (device or "cpu").strip() or "cpu"
            _inferencer = MMPoseInferencer("hand", device=dev)
            if not _warned:
                print(f"[Nova] MMPose hand inferencer ready (device={dev}).", flush=True)
                _warned = True
        except Exception as exc:
            _inferencer_failed = True
            if not _warned:
                print(f"[Nova] MMPose unavailable ({exc}); use MediaPipe or install mmpose+mmcv.", flush=True)
                _warned = True
            return None
    return _inferencer


def detect_hands_mmpose(img_rgb, *, device: str = "cpu") -> list[tuple[Any, str, float]]:
    """
    Returns the same structure as ``hand_tracker.detect_hands_task_or_legacy``:
    ``[(hand_adapter, Left|Right, confidence), ...]`` with 21 landmarks normalized to image size.
    """
    if img_rgb is None or img_rgb.size == 0:
        return []
    inferencer = _get_inferencer(device)
    if inferencer is None:
        return []

    h0, w0 = int(img_rgb.shape[0]), int(img_rgb.shape[1])
    if h0 < 2 or w0 < 2:
        return []

    bgr = img_rgb[:, :, ::-1].copy()
    try:
        gen = inferencer(bgr, show=False, return_vis=False)
        raw = next(gen)
    except Exception as exc:
        print(f"[Nova] MMPose hand inference error: {exc}", flush=True)
        return []

    if not isinstance(raw, dict):
        return []
    instances = _parse_instances(raw)
    return _instances_to_hand_rows(instances, w0, h0)


def count_hands_mmpose(img_rgb, *, device: str = "cpu") -> int:
    return len(detect_hands_mmpose(img_rgb, device=device))


def reset_inferencer_for_tests() -> None:
    global _inferencer, _inferencer_failed, _warned
    _inferencer = None
    _inferencer_failed = False
    _warned = False
