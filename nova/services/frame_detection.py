"""
Unified camera frame detection: MediaPipe (hands, face, pose), optional YOLO objects,
and face identity when a FaceIdentityStore is available.

Used by `/camera/detect` and the voice pipeline so Nova sees the same structured labels
as the on-screen overlay.
"""

from __future__ import annotations

import threading
from pathlib import Path

import numpy as np

_yolo_model = None
_yolo_model_name: str | None = None
_yolo_lock = threading.Lock()


def _yolo_settings() -> tuple[str, float]:
    try:
        from config.settings import get_settings

        cam = get_settings().camera
        name = str(cam.get("yolo_model", "yolov8n.pt")).strip() or "yolov8n.pt"
        conf = float(cam.get("yolo_conf", 0.26))
        conf = max(0.12, min(0.85, conf))
        return name, conf
    except Exception:
        return "yolov8n.pt", 0.28


def _get_yolo():
    """Load YOLO once; reload if config model name changes (e.g. after deploy)."""
    global _yolo_model, _yolo_model_name
    name, _ = _yolo_settings()
    if _yolo_model is False and _yolo_model_name == name:
        return None
    if _yolo_model is False and _yolo_model_name != name:
        _yolo_model = None
    if _yolo_model is not None and _yolo_model_name == name:
        return _yolo_model
    with _yolo_lock:
        if _yolo_model is False and _yolo_model_name == name:
            return None
        if _yolo_model is False and _yolo_model_name != name:
            _yolo_model = None
        if _yolo_model is not None and _yolo_model_name == name:
            return _yolo_model
        try:
            from ultralytics import YOLO, YOLOE  # type: ignore

            # Open-vocabulary YOLOE weights (e.g. yoloe-26n-seg-pf.pt) require the YOLOE class.
            if "yoloe" in name.lower():
                _yolo_model = YOLOE(name)
            else:
                _yolo_model = YOLO(name)

            # Pre-fuse so first inference doesn't hit 'Conv has no attribute bn'.
            # Weights saved in a fused state raise AttributeError — that's fine, skip.
            try:
                _yolo_model.fuse()
            except AttributeError:
                pass

            _yolo_model_name = name
            print(f"[Nova] YOLO loaded: {name}", flush=True)
        except Exception as exc:
            print(f"[Nova] YOLO unavailable: {exc}", flush=True)
            _yolo_model = False
            _yolo_model_name = name
    return _yolo_model if _yolo_model else None


def _wrist_proxy_hand_boxes(detections: list[dict]) -> list[dict]:
    """
    When MediaPipe Hands misses, pose wrists still give a coarse palm region — YOLO often
    labels that skin region as cell phone / remote. These expanded boxes feed suppression.
    """
    zones: list[dict] = []
    for d in detections:
        if d.get("type") != "body_part":
            continue
        lab = str(d.get("label", "")).lower()
        if "wrist" not in lab:
            continue
        b = d.get("box") or {}
        try:
            bx, by, bw, bh = float(b["x"]), float(b["y"]), float(b["w"]), float(b["h"])
        except (KeyError, TypeError, ValueError):
            continue
        cx, cy = bx + bw / 2.0, by + bh / 2.0
        hw, hh = 0.28, 0.34
        x = max(0.0, cx - hw / 2.0)
        y = max(0.0, cy - hh * 0.55)
        ww = min(1.0 - x, hw)
        hh2 = min(1.0 - y, hh)
        zones.append({"x": round(x, 4), "y": round(y, 4), "w": round(ww, 4), "h": round(hh2, 4)})
    return zones


def _box_center_in_hand_region(
    nx1: float, ny1: float, nx2: float, ny2: float, hand_boxes: list[dict]
) -> bool:
    """True if object box center lies inside an expanded hand bbox (0–1 coords)."""
    cx = (nx1 + nx2) * 0.5
    cy = (ny1 + ny2) * 0.5
    pad = 0.10
    for hb in hand_boxes:
        xmin = max(0.0, hb["x"] - pad)
        ymin = max(0.0, hb["y"] - pad)
        xmax = min(1.0, hb["x"] + hb["w"] + pad)
        ymax = min(1.0, hb["y"] + hb["h"] + pad)
        if xmin <= cx <= xmax and ymin <= cy <= ymax:
            return True
    return False


def _object_center_in_person_arm_region(
    nx1: float, ny1: float, nx2: float, ny2: float, pbox: dict
) -> bool:
    """
    True if object bbox center lies in the lower / central band of a YOLO person box
    (typical selfie: hands, torso — where YOLO mislabels skin as phone/remote).
    """
    cx = (nx1 + nx2) * 0.5
    cy = (ny1 + ny2) * 0.5
    px, py, pw, ph = float(pbox["x"]), float(pbox["y"]), float(pbox["w"]), float(pbox["h"])
    y_start = py + 0.20 * ph
    x_lo = max(0.0, px - 0.10 * pw)
    x_hi = min(1.0, px + pw + 0.10 * pw)
    return x_lo <= cx <= x_hi and cy >= y_start


def _iou_xyxy(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    x1b: float,
    y1b: float,
    x2b: float,
    y2b: float,
) -> float:
    ix1, iy1 = max(x1, x1b), max(y1, y1b)
    ix2, iy2 = min(x2, x2b), min(y2, y2b)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    a1 = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    a2 = max(0.0, x2b - x1b) * max(0.0, y2b - y1b)
    union = a1 + a2 - inter
    return inter / union if union > 0 else 0.0


def detect_all(image_bytes: bytes, face_store) -> list[dict]:
    """Return list of {label, type, confidence, box:{x,y,w,h}} in 0-1 coords."""
    import cv2

    detections: list[dict] = []
    has_face_detection = False

    from nova.services.image_decode import bgr_from_bytes

    _bgr_dec = bgr_from_bytes(image_bytes)
    img_cv = _bgr_dec[0] if _bgr_dec else None

    try:
        from nova.services.body_detector import detect as mp_detect

        mp_detections, _ = mp_detect(image_bytes)
        for d in mp_detections:
            entry: dict = {
                "label": d.label,
                "type": d.type,
                "confidence": d.confidence,
                "box": d.box,
            }
            if d.type == "face":
                has_face_detection = True
            if d.type == "face" and face_store and getattr(face_store, "enabled", True):
                try:
                    img = img_cv
                    if img is not None:
                        h, w = img.shape[:2]
                        x = int(d.box["x"] * w)
                        y = int(d.box["y"] * h)
                        fw = int(d.box["w"] * w)
                        fh = int(d.box["h"] * h)
                        crop = img[y : y + fh, x : x + fw]
                        if crop.size > 0:
                            _, buf = cv2.imencode(".jpg", crop)
                            name, id_conf = face_store.identify(bytes(buf))
                            if name:
                                entry["label"] = name
                                entry["confidence"] = id_conf
                except Exception:
                    pass
            detections.append(entry)
    except Exception as exc:
        print(f"[Nova] MediaPipe detect error: {exc}")

    # One consolidated face list: de-duplicate overlapping boxes; drop errant face-on-hand.
    from nova.services.detection_geometry import (
        dedupe_finger_detections,
        drop_confused_objects_on_faces,
        drop_faces_on_hands,
        drop_finger_and_hand_on_faces,
        nms_faces,
    )

    detections = drop_faces_on_hands(detections)
    detections = nms_faces(detections, iou_thresh=0.32)

    if not has_face_detection:
        try:
            img = img_cv
            if img is not None:
                h, w = img.shape[:2]
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                cascade = cv2.CascadeClassifier(
                    str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
                )
                faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(48, 48))
                for (x, y, fw, fh) in faces:
                    label = "Face"
                    confidence = 0.55
                    if face_store and getattr(face_store, "enabled", True):
                        try:
                            crop = img[y : y + fh, x : x + fw]
                            if crop.size > 0:
                                _, buf = cv2.imencode(".jpg", crop)
                                name, id_conf = face_store.identify(bytes(buf))
                                if name:
                                    label = name
                                    confidence = id_conf
                        except Exception:
                            pass
                    detections.append(
                        {
                            "label": label,
                            "type": "face",
                            "confidence": confidence,
                            "box": {
                                "x": round(float(x) / w, 4),
                                "y": round(float(y) / h, 4),
                                "w": round(float(fw) / w, 4),
                                "h": round(float(fh) / h, 4),
                            },
                        }
                    )
        except Exception as exc:
            print(f"[Nova] Fallback face detect error: {exc}")

    detections = drop_faces_on_hands(detections)
    detections = nms_faces(detections, iou_thresh=0.32)

    # Face wins over hand/finger segments (stops finger boxes on cheeks / mis-placed hand boxes on face).
    detections = drop_finger_and_hand_on_faces(detections)

    hand_boxes = [d["box"] for d in detections if d.get("type") == "hand"]
    hand_boxes.extend([d["box"] for d in detections if d.get("type") == "finger"])
    hand_boxes.extend(_wrist_proxy_hand_boxes(detections))

    # YOLO often labels knuckles / bare hands as toothbrush, remote, phone — suppress when overlapping hands or pose wrists.
    _HAND_CONFUSED_OBJECTS = frozenset(
        {
            "cell phone",
            "remote",
            "mouse",
            "toothbrush",
            "hair drier",
            "scissors",
            "book",
            "keyboard",
            "knife",
            "wine glass",
            "cup",
        }
    )
    _IOU_SUPPRESS_CONFUSED = 0.22

    yolo = _get_yolo()
    _, yolo_conf = _yolo_settings()
    if yolo:
        try:
            img = img_cv
            if img is not None:
                h, w = img.shape[:2]
                results = yolo(img, verbose=False, conf=yolo_conf)
                yolo_person_boxes: list[dict] = []
                for r in results:
                    for box in r.boxes:
                        if r.names[int(box.cls[0])] != "person":
                            continue
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        yolo_person_boxes.append(
                            {
                                "x": round(x1 / w, 4),
                                "y": round(y1 / h, 4),
                                "w": round((x2 - x1) / w, 4),
                                "h": round((y2 - y1) / h, 4),
                            }
                        )

                for r in results:
                    for box in r.boxes:
                        label = r.names[int(box.cls[0])]
                        conf = float(box.conf[0])
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        nx1_, ny1_, nx2_, ny2_ = x1 / w, y1 / h, x2 / w, y2 / h

                        if label == "person":
                            detections.append(
                                {
                                    "label": "person",
                                    "type": "person",
                                    "confidence": round(conf, 2),
                                    "box": {
                                        "x": round(x1 / w, 4),
                                        "y": round(y1 / h, 4),
                                        "w": round((x2 - x1) / w, 4),
                                        "h": round((y2 - y1) / h, 4),
                                    },
                                }
                            )
                            continue

                        skip_hand_fp = False
                        if label in _HAND_CONFUSED_OBJECTS:
                            if hand_boxes:
                                if _box_center_in_hand_region(nx1_, ny1_, nx2_, ny2_, hand_boxes):
                                    skip_hand_fp = True
                                if not skip_hand_fp:
                                    for hb in hand_boxes:
                                        hx1, hy1 = hb["x"], hb["y"]
                                        hx2, hy2 = hb["x"] + hb["w"], hb["y"] + hb["h"]
                                        if (
                                            _iou_xyxy(nx1_, ny1_, nx2_, ny2_, hx1, hy1, hx2, hy2)
                                            >= _IOU_SUPPRESS_CONFUSED
                                        ):
                                            skip_hand_fp = True
                                            break
                            # MediaPipe missed hands but YOLO still sees a person — suppress phone/remote on torso/hands.
                            if not skip_hand_fp and yolo_person_boxes:
                                for pb in yolo_person_boxes:
                                    if _object_center_in_person_arm_region(nx1_, ny1_, nx2_, ny2_, pb):
                                        skip_hand_fp = True
                                        break
                        if skip_hand_fp:
                            continue

                        detections.append(
                            {
                                "label": label,
                                "type": "object",
                                "confidence": round(conf, 2),
                                "box": {
                                    "x": round(x1 / w, 4),
                                    "y": round(y1 / h, 4),
                                    "w": round((x2 - x1) / w, 4),
                                    "h": round((y2 - y1) / h, 4),
                                },
                            }
                        )
        except Exception as exc:
            print(f"[Nova] YOLO detect error: {exc}")

    detections = drop_confused_objects_on_faces(detections, confused_labels=_HAND_CONFUSED_OBJECTS)
    detections = dedupe_finger_detections(detections)

    return _stable_detections(detections)


def _stable_detections(raw: list[dict]) -> list[dict]:
    """Passthrough only — temporal EMA + track holdover caused ghost boxes on the camera overlay."""
    return raw


def summarize_detections_for_voice(detections: list[dict]) -> str:
    """
    Compact English line for the LLM: objects, identified faces, pose/body.
    Omits type \"hand\" — voice already gets MediaPipe finger summary separately.
    """
    if not detections:
        return ""

    objects: list[str] = []
    faces: list[str] = []
    parts: list[str] = []
    has_body = False
    n_person = 0

    for d in detections:
        t = d.get("type", "")
        lab = str(d.get("label", "")).strip()
        if t == "person":
            n_person += 1
        elif t == "object":
            objects.append(lab)
        elif t == "face":
            if lab.lower() != "face":
                faces.append(lab)
        elif t == "hand":
            continue
        elif t == "finger":
            continue
        elif t == "body":
            has_body = True
        elif t == "body_part":
            parts.append(lab)

    def _uniq(seq: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for x in seq:
            k = x.lower()
            if k not in seen:
                seen.add(k)
                out.append(x)
        return out

    chunks: list[str] = []
    if n_person > 0:
        chunks.append(f"people (full-body YOLO): {n_person}")
    objs = _uniq(objects)
    if objs:
        chunks.append(f"objects: {', '.join(objs)}")
    fac = _uniq(faces)
    if fac:
        chunks.append(f"faces (from detector): {', '.join(fac)}")
    if has_body:
        chunks.append("upper body / pose visible")
    uparts = _uniq(parts)
    if uparts:
        head = ", ".join(uparts[:12])
        if len(uparts) > 12:
            chunks.append(f"visible landmarks: {head}, …")
        else:
            chunks.append(f"visible landmarks: {head}")

    out = " | ".join(chunks)
    if objs:
        out += (
            " | note: small YOLO labels (phone/remote/etc.) are often false on hands or skin — "
            "do not treat them as ground truth; prefer Scene + Hands lines."
        )
    return out
