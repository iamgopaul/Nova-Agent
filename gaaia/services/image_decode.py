"""
Decode uploaded camera JPEG/PNG bytes to RGB uint8 (H, W, 3).

Uses Pillow with EXIF orientation when available — ``cv2.imdecode`` ignores EXIF, so phone /
browser captures can appear sideways to MediaPipe and hand detection fails completely.
"""

from __future__ import annotations

import io
import numpy as np


def bytes_to_rgb(image_bytes: bytes) -> np.ndarray | None:
    """
    Return RGB numpy array or None if decoding fails.
    Prefer PIL (EXIF transpose); fall back to OpenCV.
    """
    if not image_bytes:
        return None

    try:
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(image_bytes)) as im:
            im = ImageOps.exif_transpose(im)
            rgb = im.convert("RGB")
            arr = np.asarray(rgb, dtype=np.uint8)
            if arr.ndim == 2:
                return None
            if arr.shape[2] != 3:
                return None
            return np.ascontiguousarray(arr)
    except Exception:
        pass

    try:
        import cv2

        nparr = np.frombuffer(image_bytes, np.uint8)
        img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img_bgr is None:
            return None
        return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    except Exception:
        return None


def bgr_from_bytes(image_bytes: bytes) -> tuple[np.ndarray, int, int] | None:
    """OpenCV BGR image + (h, w) for YOLO / Haar paths, with same decode rules as RGB."""
    rgb = bytes_to_rgb(image_bytes)
    if rgb is None:
        return None
    import cv2

    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    h, w = bgr.shape[:2]
    return bgr, h, w
