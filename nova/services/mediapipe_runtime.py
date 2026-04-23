"""
Lazy singletons for MediaPipe **Tasks** (no `mediapipe.solutions` — removed in recent pip wheels).

Used by body_detector and hand_landmarker_runner.
"""

from __future__ import annotations

import threading

import numpy as np

_lock = threading.Lock()
_hand_lm = None
_face_det = None
_pose_lm = None


def numpy_rgb_to_mp_image(rgb: np.ndarray):
    from mediapipe.tasks.python.vision.core.image import Image, ImageFormat

    arr = np.ascontiguousarray(rgb)
    return Image(ImageFormat.SRGB, arr)


def get_hand_landmarker():
    global _hand_lm
    if _hand_lm is not None:
        return _hand_lm
    with _lock:
        if _hand_lm is not None:
            return _hand_lm
        from mediapipe.tasks.python.core import base_options as bo
        from mediapipe.tasks.python.vision import hand_landmarker as hl
        from mediapipe.tasks.python.vision.core import vision_task_running_mode as vrm

        from nova.services.mp_resources import hand_landmarker_model_path

        p = str(hand_landmarker_model_path())
        opts = hl.HandLandmarkerOptions(
            base_options=bo.BaseOptions(model_asset_path=p),
            running_mode=vrm.VisionTaskRunningMode.IMAGE,
            num_hands=2,
            min_hand_detection_confidence=0.15,
            min_hand_presence_confidence=0.12,
            min_tracking_confidence=0.12,
        )
        _hand_lm = hl.HandLandmarker.create_from_options(opts)
        print("[Nova] MediaPipe HandLandmarker (Tasks) ready.", flush=True)
        return _hand_lm


def get_face_detector():
    global _face_det
    if _face_det is not None:
        return _face_det
    with _lock:
        if _face_det is not None:
            return _face_det
        from mediapipe.tasks.python.core import base_options as bo
        from mediapipe.tasks.python.vision import face_detector as fd
        from mediapipe.tasks.python.vision.core import vision_task_running_mode as vrm

        from nova.services.mp_resources import face_detector_model_path

        p = str(face_detector_model_path())
        opts = fd.FaceDetectorOptions(
            base_options=bo.BaseOptions(model_asset_path=p),
            running_mode=vrm.VisionTaskRunningMode.IMAGE,
            min_detection_confidence=0.5,
            min_suppression_threshold=0.3,
        )
        _face_det = fd.FaceDetector.create_from_options(opts)
        print("[Nova] MediaPipe FaceDetector (Tasks) ready.", flush=True)
        return _face_det


def get_pose_landmarker():
    global _pose_lm
    if _pose_lm is not None:
        return _pose_lm
    with _lock:
        if _pose_lm is not None:
            return _pose_lm
        from mediapipe.tasks.python.vision import pose_landmarker as pl

        from nova.services.mp_resources import pose_landmarker_model_path

        _pose_lm = pl.PoseLandmarker.create_from_model_path(str(pose_landmarker_model_path()))
        print("[Nova] MediaPipe PoseLandmarker (Tasks) ready.", flush=True)
        return _pose_lm
