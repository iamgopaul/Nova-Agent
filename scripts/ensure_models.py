#!/usr/bin/env python3
"""Prefetch MediaPipe / GAAIA asset files so the first camera request does not block on network."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    try:
        from gaaia.services.mediapipe_resources import hand_landmarker_model_path

        p = hand_landmarker_model_path()
        print(f"[GAAIA] Hand Landmarker model ready: {p} ({p.stat().st_size // 1024} KB)", flush=True)
    except Exception as exc:
        print(f"[GAAIA] Model prefetch failed (camera hands may use legacy detector): {exc}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
