"""
Temporal smoothing + hold-over for camera detections so boxes do not flicker when
a frame briefly drops or a score dips slightly.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field


def _iou(a: dict, b: dict) -> float:
    ax1, ay1 = a["x"], a["y"]
    ax2, ay2 = ax1 + a["w"], ay1 + a["h"]
    bx1, by1 = b["x"], b["y"]
    bx2, by2 = bx1 + b["w"], by1 + b["h"]
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    aa = max(0.0, a["w"]) * max(0.0, a["h"])
    bb = max(0.0, b["w"]) * max(0.0, b["h"])
    union = aa + bb - inter
    return inter / union if union > 0 else 0.0


def _hand_side_from_label(lab: str) -> str | None:
    m = re.match(r"\s*(Left|Right)\s+hand", lab, re.I)
    return m.group(1).lower() if m else None


def _finger_identity(lab: str) -> tuple[str, str] | None:
    """`Left thumb` → (`left`, `thumb`); `Hand index` → (`hand`, `index`)."""
    m = re.match(r"\s*(Left|Right|Hand)\s+(thumb|index|middle|ring|pinky)\b", lab, re.I)
    if not m:
        return None
    return m.group(1).lower(), m.group(2).lower()


def _labels_match_track(ty: str, la: str, lb: str) -> bool:
    """Hands match by Left/Right; finger segments match by side + digit name (stable when the box jumps)."""
    if ty == "hand":
        sa, sb = _hand_side_from_label(la), _hand_side_from_label(lb)
        if sa and sb:
            return sa == sb
    if ty == "finger":
        a, b = _finger_identity(la), _finger_identity(lb)
        if a and b:
            return a == b
    return la == lb


def _ema_box(prev: dict, new: dict, alpha: float) -> dict:
    return {
        "x": round(alpha * new["x"] + (1 - alpha) * prev["x"], 4),
        "y": round(alpha * new["y"] + (1 - alpha) * prev["y"], 4),
        "w": round(alpha * new["w"] + (1 - alpha) * prev["w"], 4),
        "h": round(alpha * new["h"] + (1 - alpha) * prev["h"], 4),
    }


@dataclass
class _Track:
    type: str
    label: str
    box: dict
    conf: float
    missed: int = 0


@dataclass
class DetectionStabilizer:
    """
    Smooths box corners with EMA; keeps last box for up to `max_missed` consecutive
    frames without a matching detection. Finger segments use shorter holdover — fast
    motion used to orphan tracks and draw duplicate boxes.
    """

    max_missed: int = 20
    max_missed_finger: int = 5
    iou_match: float = 0.07
    ema_alpha: float = 0.48
    _tracks: list[_Track] = field(default_factory=list)

    def _miss_limit(self, tr: _Track) -> int:
        return self.max_missed_finger if tr.type == "finger" else self.max_missed

    def update(self, raw: list[dict]) -> list[dict]:
        if not raw:
            return self._step_missed_only()

        matched_track: set[int] = set()
        new_tracks: list[_Track] = []

        for det in raw:
            t = det.get("type", "")
            lab = str(det.get("label", ""))
            box = det.get("box") or {}
            conf = float(det.get("confidence", 0.5))
            if not isinstance(box, dict) or "x" not in box:
                continue

            best_j = -1
            best_iou = 0.0
            for j, tr in enumerate(self._tracks):
                if j in matched_track:
                    continue
                if tr.type != t or not _labels_match_track(t, tr.label, lab):
                    continue
                iou = _iou(tr.box, box)
                acx = tr.box["x"] + tr.box["w"] * 0.5
                acy = tr.box["y"] + tr.box["h"] * 0.5
                bcx = box["x"] + box["w"] * 0.5
                bcy = box["y"] + box["h"] * 0.5
                cd = ((acx - bcx) ** 2 + (acy - bcy) ** 2) ** 0.5
                if t == "hand" and _labels_match_track("hand", tr.label, lab):
                    if cd < 0.11:
                        iou = max(iou, 0.14)
                # Same finger label can move fast — IoU drops; use center proximity to keep one track.
                if t == "finger" and _labels_match_track("finger", tr.label, lab):
                    if cd < 0.20:
                        iou = max(iou, 0.15)
                if iou > best_iou:
                    best_iou = iou
                    best_j = j

            if best_j >= 0 and best_iou >= self.iou_match:
                tr = self._tracks[best_j]
                alpha = self.ema_alpha
                if tr.type == "finger":
                    alpha = min(0.82, self.ema_alpha + 0.30)
                tr.box = _ema_box(tr.box, box, alpha)
                tr.label = lab
                tr.conf = min(1.0, max(conf, tr.conf * 0.97))
                tr.missed = 0
                matched_track.add(best_j)
            elif best_j >= 0 and best_iou >= 0.04:
                tr = self._tracks[best_j]
                wk = self.ema_alpha * 0.55
                if tr.type == "finger":
                    wk = min(0.65, wk + 0.22)
                tr.box = _ema_box(tr.box, box, wk)
                tr.label = lab
                tr.missed = 0
                matched_track.add(best_j)
            else:
                new_tracks.append(
                    _Track(type=t, label=lab, box=copy.deepcopy(box), conf=conf, missed=0)
                )

        for j, tr in enumerate(self._tracks):
            if j not in matched_track:
                tr.missed += 1

        self._tracks = [t for t in self._tracks if t.missed <= self._miss_limit(t)]
        self._tracks.extend(new_tracks)
        return self._emit()

    def _step_missed_only(self) -> list[dict]:
        for tr in self._tracks:
            tr.missed += 1
        self._tracks = [t for t in self._tracks if t.missed <= self._miss_limit(t)]
        return self._emit()

    def _emit(self) -> list[dict]:
        return [
            {
                "label": tr.label,
                "type": tr.type,
                "confidence": round(min(1.0, tr.conf), 2),
                "box": copy.deepcopy(tr.box),
            }
            for tr in self._tracks
        ]
