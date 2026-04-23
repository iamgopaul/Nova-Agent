"""
Sample JPEG frames from a short browser-recorded video (WebM / MP4) for hand/vision pipelines.

OpenCV reads the file from disk; we evenly subsample decoded frames to cap CPU.
"""

from __future__ import annotations

import os
import tempfile


def _sniff_suffix(video_bytes: bytes) -> str:
    if len(video_bytes) >= 12 and video_bytes[4:8] == b"ftyp":
        return ".mp4"
    return ".webm"


def jpeg_frames_from_video_bytes(video_bytes: bytes, max_frames: int = 24) -> list[bytes]:
    """Return up to ``max_frames`` JPEG-encoded stills sampled evenly across the clip."""
    if not video_bytes or len(video_bytes) < 256:
        return []

    suf = _sniff_suffix(video_bytes)
    fd, path = tempfile.mkstemp(suffix=suf)
    os.close(fd)
    try:
        with open(path, "wb") as f:
            f.write(video_bytes)
        return jpeg_frames_from_video_file(path, max_frames=max_frames)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def jpeg_frames_from_video_file(path: str, max_frames: int = 24) -> list[bytes]:
    import cv2

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return []

    n = 0
    while cap.grab():
        n += 1
    cap.release()

    if n == 0:
        return []

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return []

    if n <= max_frames:
        wanted = set(range(n))
    else:
        step = (n - 1) / (max_frames - 1)
        wanted = {int(round(i * step)) for i in range(max_frames)}

    out: list[bytes] = []
    i = 0
    try:
        while True:
            ok = cap.grab()
            if not ok:
                break
            if i in wanted:
                ok2, bgr = cap.retrieve()
                if ok2 and bgr is not None:
                    ok_j, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
                    if ok_j:
                        out.append(buf.tobytes())
            i += 1
    finally:
        cap.release()

    return out
