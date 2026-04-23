"""Shared NMS / overlap helpers for camera detections."""

from __future__ import annotations



def box_iou_xywh(a: dict, b: dict) -> float:
    ax1, ay1 = a["x"], a["y"]
    ax2, ay2 = ax1 + a["w"], ay1 + a["h"]
    bx1, by1 = b["x"], b["y"]
    bx2, by2 = bx1 + b["w"], by1 + b["h"]
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    area_a = max(a["w"], 0) * max(a["h"], 0)
    area_b = max(b["w"], 0) * max(b["h"], 0)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _area_xywh(box: dict) -> float:
    return max(0.0, float(box.get("w", 0))) * max(0.0, float(box.get("h", 0)))


def _intersection_area_xywh(a: dict, b: dict) -> float:
    ax1, ay1 = a["x"], a["y"]
    ax2, ay2 = ax1 + a["w"], ay1 + a["h"]
    bx1, by1 = b["x"], b["y"]
    bx2, by2 = bx1 + b["w"], by1 + b["h"]
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    return iw * ih


def fraction_of_a_in_b(a: dict, b: dict) -> float:
    """Share of `a`'s area that lies inside `b` (0–1)."""
    ia = _intersection_area_xywh(a, b)
    return ia / max(_area_xywh(a), 1e-9)


def box_center_inside(inner: dict, outer: dict, pad: float = 0.0) -> bool:
    """True if center of `inner` lies inside expanded `outer` (norm 0–1)."""
    cx = inner["x"] + inner["w"] * 0.5
    cy = inner["y"] + inner["h"] * 0.5
    ox1 = outer["x"] - pad
    oy1 = outer["y"] - pad
    ox2 = outer["x"] + outer["w"] + pad
    oy2 = outer["y"] + outer["h"] + pad
    return ox1 <= cx <= ox2 and oy1 <= cy <= oy2


def nms_faces(detections: list[dict], iou_thresh: float = 0.35) -> list[dict]:
    """Keep a single best face when multiple MediaPipe/Haar boxes overlap."""
    faces = [(i, d) for i, d in enumerate(detections) if d.get("type") == "face"]
    if len(faces) <= 1:
        return detections

    faces.sort(key=lambda x: float(x[1].get("confidence", 0)), reverse=True)
    removed: set[int] = set()

    for i, (idx_i, di) in enumerate(faces):
        if idx_i in removed:
            continue
        bi = di["box"]
        for j in range(i + 1, len(faces)):
            idx_j, dj = faces[j]
            if idx_j in removed:
                continue
            bj = dj["box"]
            if box_iou_xywh(bi, bj) >= iou_thresh:
                removed.add(idx_j)

    if not removed:
        return detections
    return [d for k, d in enumerate(detections) if k not in removed]


def drop_faces_on_hands(detections: list[dict], pad: float = 0.04) -> list[dict]:
    """
    Remove **spurious** face boxes whose center lies on a hand/finger (e.g. palm texture).
    Uses a stricter IoU gate so a real face beside a raised hand is not dropped.
    """
    regions = [
        d["box"]
        for d in detections
        if d.get("type") in ("hand", "finger")
    ]
    if not regions:
        return detections

    out: list[dict] = []
    for d in detections:
        if d.get("type") != "face":
            out.append(d)
            continue
        bb = d["box"]
        bad = False
        for hb in regions:
            iou = box_iou_xywh(bb, hb)
            if iou >= 0.28:
                bad = True
                break
            if box_center_inside(bb, hb, pad=pad) and iou >= 0.10:
                bad = True
                break
        if not bad:
            out.append(d)
    return out


def drop_finger_and_hand_on_faces(detections: list[dict], *, face_pad: float = 0.035) -> list[dict]:
    """
    Remove hand/finger boxes that sit on the **face** region (landmark drift / selfie confusion).
    Face boxes win — keeps overlays semantically clean.
    """
    faces = [d["box"] for d in detections if d.get("type") == "face"]
    if not faces:
        return detections

    out: list[dict] = []
    for d in detections:
        t = d.get("type")
        if t not in ("hand", "finger"):
            out.append(d)
            continue
        bb = d["box"]
        drop = False
        for fb in faces:
            if t == "finger":
                if box_center_inside(bb, fb, pad=face_pad):
                    drop = True
                    break
                if box_iou_xywh(bb, fb) >= 0.055:
                    drop = True
                    break
                if fraction_of_a_in_b(bb, fb) >= 0.36:
                    drop = True
                    break
            else:
                if box_iou_xywh(bb, fb) >= 0.48:
                    drop = True
                    break
                if box_center_inside(bb, fb, pad=0.02) and _area_xywh(bb) <= _area_xywh(fb) * 0.92:
                    drop = True
                    break
        if not drop:
            out.append(d)
    return out


def dedupe_finger_detections(detections: list[dict]) -> list[dict]:
    """Keep one finger box per label (guards rare duplicate rows / double hand quirks)."""
    seen: set[str] = set()
    out: list[dict] = []
    for d in detections:
        if d.get("type") != "finger":
            out.append(d)
            continue
        lab = str(d.get("label", "")).strip()
        if lab in seen:
            continue
        seen.add(lab)
        out.append(d)
    return out


def drop_confused_objects_on_faces(
    detections: list[dict],
    *,
    confused_labels: frozenset[str],
    min_iou: float = 0.035,
) -> list[dict]:
    """Drop YOLO classes that often fire on skin (phone, toothbrush, …) when they overlap a face box."""
    faces = [d["box"] for d in detections if d.get("type") == "face"]
    if not faces:
        return detections

    out: list[dict] = []
    for d in detections:
        if d.get("type") != "object":
            out.append(d)
            continue
        lab = str(d.get("label", "")).lower().strip()
        if lab not in confused_labels:
            out.append(d)
            continue
        bb = d["box"]
        drop = False
        for fb in faces:
            if box_center_inside(bb, fb, pad=0.07):
                drop = True
                break
            iou = box_iou_xywh(bb, fb)
            if iou >= min_iou and fraction_of_a_in_b(bb, fb) >= 0.22:
                drop = True
                break
        if not drop:
            out.append(d)
    return out

