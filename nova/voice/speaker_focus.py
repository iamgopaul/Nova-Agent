from __future__ import annotations

import json
from pathlib import Path

import numpy as np


class SpeakerFocusManager:
    """
    Lightweight local voice-lock manager.

    Uses a compact spectral embedding derived from PCM audio and cosine
    similarity against an enrolled centroid profile.
    """

    def __init__(
        self,
        profile_path: Path,
        enabled: bool = False,
        similarity_threshold: float = 0.68,
        enrollment_samples: int = 3,
        sample_rate: int = 16000,
    ) -> None:
        self._path = profile_path
        self._enabled = enabled
        self._threshold = similarity_threshold
        self._enrollment_samples = max(1, enrollment_samples)
        self._sr = sample_rate

        self._profile: np.ndarray | None = None
        self._pending: list[np.ndarray] = []

        self._load_profile()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def is_enrolling(self) -> bool:
        return self._enabled and len(self._pending) > 0

    @property
    def has_profile(self) -> bool:
        return self._enabled and self._profile is not None

    def start_enrollment(self) -> None:
        if not self._enabled:
            return
        self._pending = []

    def clear_profile(self) -> bool:
        self._profile = None
        self._pending = []
        try:
            if self._path.exists():
                self._path.unlink()
            return True
        except OSError:
            return False

    def add_enrollment_sample(self, pcm: bytes) -> tuple[bool, int]:
        """
        Returns (completed, remaining_samples).
        If sample is unusable, remaining is unchanged.
        """
        if not self._enabled:
            return False, 0

        emb = self._extract_embedding(pcm)
        if emb is None:
            return False, self._enrollment_samples - len(self._pending)

        self._pending.append(emb)
        remaining = self._enrollment_samples - len(self._pending)
        if remaining > 0:
            return False, remaining

        centroid = np.mean(np.stack(self._pending, axis=0), axis=0)
        norm = np.linalg.norm(centroid) + 1e-12
        self._profile = centroid / norm
        self._pending = []
        self._save_profile()
        return True, 0

    def verify(self, pcm: bytes) -> tuple[bool, float]:
        if not self.has_profile:
            return True, 1.0

        emb = self._extract_embedding(pcm)
        if emb is None:
            return False, 0.0

        score = float(np.dot(self._profile, emb))
        return score >= self._threshold, score

    # ── Persistence ────────────────────────────────────────────────

    def _load_profile(self) -> None:
        try:
            if not self._path.exists():
                return
            data = json.loads(self._path.read_text())
            vec = np.array(data.get("embedding", []), dtype=np.float32)
            if vec.size == 0:
                return
            norm = np.linalg.norm(vec) + 1e-12
            self._profile = vec / norm
        except Exception:
            self._profile = None

    def _save_profile(self) -> None:
        if self._profile is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "embedding": self._profile.astype(float).tolist(),
        }
        self._path.write_text(json.dumps(payload))

    # ── Embedding ─────────────────────────────────────────────────

    def _extract_embedding(self, pcm: bytes) -> np.ndarray | None:
        if not pcm or len(pcm) < 4096:
            return None

        x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        if x.size < self._sr // 2:
            return None

        x = x / 32768.0
        # Trim obvious silence first.
        absx = np.abs(x)
        idx = np.where(absx > 0.01)[0]
        if idx.size > 0:
            x = x[idx[0] : idx[-1] + 1]
        if x.size < self._sr // 3:
            return None

        # Mild pre-emphasis and energy normalization.
        x = np.append(x[0], x[1:] - 0.97 * x[:-1])
        x = x / (np.std(x) + 1e-8)

        frame = 400
        hop = 160
        if x.size < frame:
            return None

        n_frames = 1 + (x.size - frame) // hop
        frames = np.stack([x[i * hop : i * hop + frame] for i in range(n_frames)], axis=0)
        window = np.hanning(frame).astype(np.float32)
        spec = np.abs(np.fft.rfft(frames * window, axis=1)).astype(np.float32)
        if spec.size == 0:
            return None

        log_spec = np.log1p(spec)
        bins = log_spec.shape[1]
        n_bands = 48
        edges = np.linspace(0, bins, n_bands + 1, dtype=int)

        bands = []
        for i in range(n_bands):
            a, b = int(edges[i]), int(edges[i + 1])
            if b <= a:
                b = min(a + 1, bins)
            bands.append(log_spec[:, a:b].mean(axis=1))
        band_mat = np.stack(bands, axis=1)

        mu = band_mat.mean(axis=0)
        sigma = band_mat.std(axis=0)
        delta = np.diff(band_mat, axis=0)
        dmu = delta.mean(axis=0) if delta.shape[0] else np.zeros_like(mu)

        feat = np.concatenate([mu, sigma, dmu]).astype(np.float32)
        norm = np.linalg.norm(feat) + 1e-12
        return feat / norm