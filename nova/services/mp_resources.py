"""Ensure bundled MediaPipe task models exist on disk (downloaded once)."""

from __future__ import annotations

import urllib.request
from pathlib import Path

# Official MediaPipe Hand Landmarker (newer full-range model vs legacy solutions.hands)
HAND_LANDMARKER_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"
)
# Tasks API (MediaPipe 0.10.30+ wheels no longer ship `mediapipe.solutions`).
FACE_DETECTOR_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
)
POSE_LANDMARKER_LITE_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
)

_MODELS_DIR = Path(__file__).resolve().parent / "models"


def hand_landmarker_model_path() -> Path:
    """Path to hand_landmarker.task; downloads on first call if missing."""
    _MODELS_DIR.mkdir(parents=True, exist_ok=True)
    path = _MODELS_DIR / "hand_landmarker.task"
    if path.exists() and path.stat().st_size > 1000:
        return path
    tmp = path.with_suffix(".task.download")
    try:
        urllib.request.urlretrieve(HAND_LANDMARKER_URL, tmp)  # noqa: S310 — official Google URL
        tmp.replace(path)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise
    return path


def face_detector_model_path() -> Path:
    """BlazeFace short-range .tflite for FaceDetector task."""
    _MODELS_DIR.mkdir(parents=True, exist_ok=True)
    path = _MODELS_DIR / "blaze_face_short_range.tflite"
    if path.exists() and path.stat().st_size > 1000:
        return path
    tmp = path.with_suffix(".tflite.download")
    try:
        urllib.request.urlretrieve(FACE_DETECTOR_URL, tmp)  # noqa: S310
        tmp.replace(path)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise
    return path


def pose_landmarker_model_path() -> Path:
    """Pose landmarker lite .task bundle."""
    _MODELS_DIR.mkdir(parents=True, exist_ok=True)
    path = _MODELS_DIR / "pose_landmarker_lite.task"
    if path.exists() and path.stat().st_size > 1000:
        return path
    tmp = path.with_suffix(".task.download")
    try:
        urllib.request.urlretrieve(POSE_LANDMARKER_LITE_URL, tmp)  # noqa: S310
        tmp.replace(path)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise
    return path
