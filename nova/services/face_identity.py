from __future__ import annotations

import shutil
import threading
from pathlib import Path

# Lazy singleton — imported once on the first identify() call under a module lock
# so concurrent threads can't race on TensorFlow's module import machinery.
_deepface_cls = None
_deepface_import_lock = threading.Lock()


def _get_deepface():
    global _deepface_cls
    if _deepface_cls is not None:
        return _deepface_cls
    with _deepface_import_lock:
        if _deepface_cls is None:
            from deepface import DeepFace  # type: ignore
            _deepface_cls = DeepFace
    return _deepface_cls


class FaceIdentityStore:
    """
    Persistent face identity store backed by DeepFace (ArcFace model).

    Profiles live at db_path/{name}/frame_NNN.jpg.
    DeepFace builds a representations cache (.pkl) beside each sub-folder;
    we delete that cache whenever profiles change so it rebuilds cleanly.
    """

    def __init__(
        self,
        db_path: Path | str,
        model_name: str = "ArcFace",
        distance_metric: str = "cosine",
        threshold: float = 0.40,
        enabled: bool = True,
        detector_backend: str = "opencv",
    ) -> None:
        self.db_path = Path(db_path).expanduser()
        self.model_name = model_name
        self.distance_metric = distance_metric
        self.threshold = threshold
        self.enabled = enabled
        self.detector_backend = detector_backend
        self._lock = threading.Lock()

        if self.enabled:
            self.db_path.mkdir(parents=True, exist_ok=True)

    # ── Public API ────────────────────────────────────────────────────

    def identify(self, image_bytes: bytes) -> tuple[str | None, float]:
        """
        Given a JPEG/PNG image as bytes, return (name, confidence_0_to_1).
        Returns (None, 0.0) when no enrolled profile matches or on error.
        """
        if not self.enabled:
            return None, 0.0

        # Fast path: skip DeepFace entirely if no profiles are enrolled
        profiles = list(self.db_path.iterdir()) if self.db_path.exists() else []
        profiles = [p for p in profiles if p.is_dir()]
        if not profiles:
            return None, 0.0

        # Non-blocking: drop frame if a prior identify call is still running.
        # Using a trylock instead of a flag so the check+acquire is atomic.
        if not self._lock.acquire(blocking=False):
            return None, 0.0

        try:
            DeepFace = _get_deepface()

            from nova.services.image_decode import bgr_from_bytes

            dec = bgr_from_bytes(image_bytes)
            if dec is None:
                return None, 0.0
            img = dec[0]

            results = DeepFace.find(
                img_path=img,
                db_path=str(self.db_path),
                model_name=self.model_name,
                distance_metric=self.distance_metric,
                detector_backend=self.detector_backend,
                enforce_detection=False,
                silent=True,
            )

            if not results or results[0].empty:
                return None, 0.0

            df = results[0]
            dist_col = [c for c in df.columns if "distance" in c.lower()]
            if not dist_col:
                return None, 0.0

            best_row = df.loc[df[dist_col[0]].idxmin()]
            distance = float(best_row[dist_col[0]])
            if distance > self.threshold:
                return None, 0.0

            identity_path = str(best_row.get("identity", ""))
            name = Path(identity_path).parent.name
            confidence = max(0.0, min(1.0, 1.0 - distance / self.threshold))
            return name, round(confidence, 3)

        except Exception as exc:
            print(f"[Nova] Face identify error: {exc}")
            return None, 0.0
        finally:
            self._lock.release()

    def enroll(self, name: str, image_bytes_list: list[bytes]) -> int:
        """
        Enroll a person by saving their images.
        Returns the number of frames successfully saved.
        """
        if not self.enabled or not name or not image_bytes_list:
            return 0

        safe_name = _safe_name(name)
        person_dir = self.db_path / safe_name
        person_dir.mkdir(parents=True, exist_ok=True)

        existing = len(list(person_dir.glob("frame_*.jpg")))
        saved = 0
        for i, img_bytes in enumerate(image_bytes_list):
            frame_path = person_dir / f"frame_{existing + i + 1:03d}.jpg"
            try:
                frame_path.write_bytes(img_bytes)
                saved += 1
            except Exception as exc:
                print(f"[Nova] Face enroll save error: {exc}")

        if saved:
            self._bust_cache()

        return saved

    def list_profiles(self) -> list[dict]:
        if not self.db_path.exists():
            return []
        profiles = []
        for person_dir in sorted(self.db_path.iterdir()):
            if not person_dir.is_dir():
                continue
            frames = list(person_dir.glob("frame_*.jpg"))
            if not frames:
                continue
            enrolled_at = min(f.stat().st_mtime for f in frames)
            profiles.append({
                "name": person_dir.name,
                "sample_count": len(frames),
                "enrolled_at": enrolled_at,
            })
        return profiles

    def delete_profile(self, name: str) -> bool:
        safe_name = _safe_name(name)
        person_dir = self.db_path / safe_name
        if not person_dir.exists():
            return False
        try:
            shutil.rmtree(person_dir)
            self._bust_cache()
            return True
        except Exception as exc:
            print(f"[Nova] Face delete error: {exc}")
            return False

    # ── Internal ──────────────────────────────────────────────────────

    def _bust_cache(self) -> None:
        """Remove DeepFace representations cache so it rebuilds on next identify()."""
        for pkl in self.db_path.glob("representations_*.pkl"):
            try:
                pkl.unlink()
            except OSError:
                pass


def _safe_name(name: str) -> str:
    """Sanitize a person name to a safe directory name."""
    import re
    cleaned = re.sub(r"[^\w\s-]", "", name.strip()).strip()
    return re.sub(r"\s+", "_", cleaned)[:64] or "unknown"
