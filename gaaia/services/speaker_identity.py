from __future__ import annotations

import json
import re
import threading
import time
from functools import lru_cache
from pathlib import Path

import numpy as np


_NAME_PATTERNS = [
    re.compile(r"\bmy name is\s+([a-zA-Z][a-zA-Z'\- ]{1,60})", re.IGNORECASE),
    re.compile(r"\bthis is\s+([a-zA-Z][a-zA-Z'\- ]{1,60})", re.IGNORECASE),
    re.compile(r"\bi am\s+([a-zA-Z][a-zA-Z'\- ]{1,60})", re.IGNORECASE),
    re.compile(r"\bi'm\s+([a-zA-Z][a-zA-Z'\- ]{1,60})", re.IGNORECASE),
]

_CREATOR_CANONICAL = "Josh Gopaul"
_CREATOR_CANONICAL_NORM = "josh gopaul"
_EMBEDDING_BACKEND_FALLBACK = "fallback"
_EMBEDDING_BACKEND_ECAPA = "ecapa"

# Common words that are never real names — prevents "I'm tired" → "Tired" etc.
_NON_NAME_WORDS = frozenset({
    "a", "an", "the", "just", "also", "not", "so", "very", "really", "actually",
    "here", "there", "good", "great", "fine", "okay", "ok", "sure", "right",
    "trying", "going", "coming", "looking", "working", "talking", "saying",
    "showing", "telling", "you", "me", "us", "them",
    "multi", "millionaire", "rich", "poor", "happy", "sad", "tired", "busy",
    "ready", "done", "back", "new", "old", "big", "small", "tall", "short",
    "currently", "usually", "always", "never", "still", "already", "now",
    "your", "my", "his", "her", "our", "their", "its", "this", "that",
    "getting", "annoyed", "angry", "frustrated",
    # gerunds / action words that "I'm <verb>ing" patterns capture incorrectly
    "chatting", "watching", "listening", "waiting", "playing", "thinking",
    "wondering", "asking", "answering", "helping", "doing", "speaking",
    "starting", "stopping", "walking", "running", "sitting", "standing",
    "calling", "texting", "typing", "reading", "writing", "using",
    "laughing", "joking", "kidding", "testing", "checking", "working",
    "introducing", "visiting", "joining", "leaving", "staying", "coming",
    # location / state words — "I'm located", "I'm based", "I'm in", etc.
    "located", "location", "based", "situated", "nearby", "around",
    "inside", "outside", "upstairs", "downstairs", "outside", "indoors", "outdoors",
    "home", "away", "downtown", "uptown", "abroad", "local",
    # adjective / state false-positives — "I'm fine", "I'm good", "I'm available"
    "available", "unavailable", "offline", "online", "free", "busy",
    "lost", "found", "stuck", "bored", "excited", "confused", "nervous",
    "awake", "asleep", "hungry", "full", "sick", "well", "better",
    "here", "there", "in", "at", "on", "with", "from",
})


def first_name(name: str) -> str:
    cleaned = _normalize_name(name)
    if not cleaned:
        return ""
    return cleaned.split()[0]


def _normalize_name(raw: str) -> str:
    # Treat underscore like space so enrolled ids such as Josh_Gopaul parse to first name Josh.
    cleaned = re.sub(r"\s+", " ", (raw or "").replace("_", " ").strip(" .,!?:;\"'"))
    if not cleaned:
        return ""
    words = [w for w in cleaned.split(" ") if w]
    if len(words) > 4:
        words = words[:4]
    return " ".join(word[:1].upper() + word[1:] for word in words)


def _is_creator_name(raw: str | None) -> bool:
    normalized = _normalize_name(raw or "").lower()
    if not normalized:
        return False
    if normalized == _CREATOR_CANONICAL_NORM:
        return True
    # Accept common separators/slug forms that normalize to the same tokens.
    collapsed = re.sub(r"\s+", " ", normalized).strip()
    return collapsed == _CREATOR_CANONICAL_NORM


def _looks_like_name(candidate: str) -> bool:
    """Return True only if candidate looks like an actual person name."""
    words = candidate.strip().split()
    if not words or len(words) > 4:
        return False
    for word in words:
        w = word.lower().rstrip(".,!?")
        # Reject if any word is a common non-name word
        if w in _NON_NAME_WORDS:
            return False
        # Reject if any word is fewer than 2 chars (single initials are ok only in full names)
        if len(w) < 2:
            return False
        # Reject if any word contains digits
        if any(c.isdigit() for c in w):
            return False
    return True


_CLAUSE_BREAKERS = frozenset({"and", "but", "or", "so", "because", "though", "although", "while", "when", "if"})


def extract_declared_name(text: str) -> str | None:
    for pattern in _NAME_PATTERNS:
        match = pattern.search(text or "")
        if not match:
            continue
        raw_words = match.group(1).strip().split()
        # Truncate at the first clause-breaking conjunction so that
        # "I'm Josh and I'm fine" → ["Josh"] not ["Josh", "And"]
        trimmed: list[str] = []
        for w in raw_words[:4]:
            if w.lower().rstrip(".,!?") in _CLAUSE_BREAKERS:
                break
            trimmed.append(w)
        # Only keep the first 1-2 name tokens
        candidate = _normalize_name(" ".join(trimmed[:2]))
        if len(candidate) >= 2 and _looks_like_name(candidate):
            return candidate
    return None


def _looks_like_plain_name(text: str) -> str | None:
    candidate = _normalize_name(text)
    if not candidate:
        return None
    words = candidate.split()
    if 1 <= len(words) <= 4 and all(len(word) >= 2 for word in words) and _looks_like_name(candidate):
        return candidate
    return None


@lru_cache(maxsize=1)
def _load_ecapa_encoder():
    """Lazy-load SpeechBrain ECAPA encoder if installed; returns None on any failure."""
    try:
        from speechbrain.inference.speaker import EncoderClassifier  # type: ignore
    except Exception:
        return None
    try:
        return EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir=str((Path.home() / ".cache" / "gaaia-ecapa").expanduser()),
            run_opts={"device": "cpu"},
        )
    except Exception:
        return None


class SpeakerIdentityStore:
    """Persistent multi-speaker identity mapping using lightweight local embeddings."""

    def __init__(
        self,
        profile_path: Path,
        enabled: bool = True,
        similarity_threshold: float = 0.76,
        sample_rate: int = 16000,
        auto_create_unknown: bool = True,
        embedding_backend: str = _EMBEDDING_BACKEND_ECAPA,
        max_embeddings_per_profile: int = 12,
    ) -> None:
        self._path = profile_path
        self._enabled = enabled
        self._threshold = float(similarity_threshold)
        self._sr = int(sample_rate)
        self._auto_create_unknown = auto_create_unknown
        self._embedding_backend = str(embedding_backend or _EMBEDDING_BACKEND_ECAPA).strip().lower()
        if self._embedding_backend not in {_EMBEDDING_BACKEND_ECAPA, _EMBEDDING_BACKEND_FALLBACK}:
            self._embedding_backend = _EMBEDDING_BACKEND_ECAPA
        self._max_embeddings_per_profile = max(3, int(max_embeddings_per_profile))
        self._lock = threading.Lock()
        self._profiles: dict[str, dict] = {}
        self._counter = 0
        self._load()

    def identify(self, pcm: bytes, transcript: str) -> tuple[str | None, float, bool]:
        """Return (speaker_name, confidence, was_declared_name)."""
        if not self._enabled:
            return None, 0.0, False

        emb = self._extract_embedding(pcm)
        declared_name = extract_declared_name(transcript)

        with self._lock:
            if declared_name and emb is not None:
                resolved_name = self._resolve_declared_name(declared_name, emb)
                self._upsert_profile(resolved_name, emb)
                self._save()
                return resolved_name, 1.0, True

            if emb is None:
                return None, 0.0, False

            best_name, best_score = self._best_match(emb)
            if best_name and best_score >= self._threshold:
                self._upsert_profile(best_name, emb)
                self._save()
                return best_name, best_score, False

            # Unknown-speaker stability: allow reusing an existing anonymous profile at a
            # slightly lower threshold so the same guest does not become Speaker 7, 8, 9...
            if (
                best_name
                and str(best_name).startswith("Speaker ")
                and best_score >= max(0.55, self._threshold - 0.20)
            ):
                self._upsert_profile(best_name, emb)
                self._save()
                return best_name, best_score, False

            if self._auto_create_unknown:
                anon = self._new_anonymous_name()
                self._upsert_profile(anon, emb)
                self._save()
                return anon, 0.6, False

        return None, 0.0, False

    def learn_identity(self, pcm: bytes, transcript: str, fallback_text: str | None = None) -> str | None:
        """Persist a speaker identity from a spoken introduction."""
        if not self._enabled:
            return None

        emb = self._extract_embedding(pcm)
        if emb is None:
            return None

        name = extract_declared_name(transcript) or _looks_like_plain_name(transcript)
        if not name and fallback_text:
            name = extract_declared_name(fallback_text) or _looks_like_plain_name(fallback_text)
        if not name:
            return None

        with self._lock:
            resolved_name = self._resolve_declared_name(name, emb)
            self._upsert_profile(resolved_name, emb)
            self._save()
        return resolved_name

    def reference_name(self, canonical_name: str) -> str:
        """Prefer first name unless multiple enrolled users share that first name."""
        normalized = _normalize_name(canonical_name)
        if not normalized:
            return canonical_name
        if _is_creator_name(normalized):
            return _CREATOR_CANONICAL
        first = first_name(normalized)
        if not first:
            return normalized

        with self._lock:
            collisions = [
                name for name in self._profiles
                if first_name(name).lower() == first.lower()
            ]
        if len(collisions) <= 1:
            return first
        return normalized

    def delete_profile(self, name: str) -> bool:
        """Remove one speaker profile by exact key or case-insensitive / normalized match."""
        if not self._enabled or not (name or "").strip():
            return False
        raw = name.strip()
        with self._lock:
            if raw in self._profiles:
                del self._profiles[raw]
                self._save()
                return True
            rl = raw.lower()
            norm = _normalize_name(raw).lower()
            for key in list(self._profiles.keys()):
                if key.lower() == rl or _normalize_name(key).lower() == norm:
                    del self._profiles[key]
                    self._save()
                    return True
        return False

    def is_strong_voice_match(self, speaker_name: str | None, confidence: float) -> bool:
        """Enrolled voice match above threshold — not an anonymous Speaker N placeholder."""
        if not speaker_name or str(speaker_name).startswith("Speaker "):
            return False
        return float(confidence) >= self._threshold

    def confidence_band(self, speaker_name: str | None, confidence: float) -> str:
        """
        Classify identity confidence.
        - high: very likely match
        - medium: plausible match
        - low: uncertain/new speaker (use fallback prompts here only)
        """
        if not speaker_name or str(speaker_name).startswith("Speaker "):
            return "low"
        score = float(confidence)
        high_cutoff = min(0.98, self._threshold + 0.08)
        medium_cutoff = max(0.0, self._threshold - 0.05)
        if score >= high_cutoff:
            return "high"
        if score >= medium_cutoff:
            return "medium"
        return "low"

    @staticmethod
    def names_same_identity(a: str | None, b: str | None) -> bool:
        """Same person across face slug and voice profile (Josh vs Josh_Gopaul)."""
        if not a or not b:
            return False
        if _is_creator_name(a) and _is_creator_name(b):
            return True
        na = _normalize_name(str(a)).lower()
        nb = _normalize_name(str(b)).lower()
        if na == nb:
            return True
        fa = first_name(_normalize_name(str(a))).lower()
        fb = first_name(_normalize_name(str(b))).lower()
        return bool(fa and fb and fa == fb)

    # Persistence

    def _load(self) -> None:
        try:
            if not self._path.exists():
                return
            data = json.loads(self._path.read_text())
            self._counter = int(data.get("counter", 0))
            profiles = data.get("profiles", {})
            if not isinstance(profiles, dict):
                return
            for name, payload in profiles.items():
                emb_list = payload.get("embeddings", [])
                vectors: list[np.ndarray] = []
                if isinstance(emb_list, list):
                    for row in emb_list:
                        vec = np.array(row, dtype=np.float32)
                        if vec.size == 0:
                            continue
                        norm = np.linalg.norm(vec) + 1e-12
                        vectors.append(vec / norm)
                if not vectors:
                    vec = np.array(payload.get("embedding", []), dtype=np.float32)
                    if vec.size:
                        norm = np.linalg.norm(vec) + 1e-12
                        vectors.append(vec / norm)
                if not vectors:
                    continue
                centroid = np.mean(np.stack(vectors, axis=0), axis=0)
                c_norm = np.linalg.norm(centroid) + 1e-12
                self._profiles[name] = {
                    "embedding": (centroid / c_norm),
                    "embeddings": vectors[-self._max_embeddings_per_profile :],
                    "samples": int(payload.get("samples", 1)),
                    "last_seen": float(payload.get("last_seen", time.time())),
                }
        except Exception:
            self._profiles = {}
            self._counter = 0

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "counter": self._counter,
            "embedding_backend": self._embedding_backend,
            "profiles": {
                name: {
                    "embedding": data["embedding"].astype(float).tolist(),
                    "embeddings": [v.astype(float).tolist() for v in data.get("embeddings", [])],
                    "samples": int(data.get("samples", 1)),
                    "last_seen": float(data.get("last_seen", time.time())),
                }
                for name, data in self._profiles.items()
            },
        }
        self._path.write_text(json.dumps(payload))

    # Profile ops

    def _best_match(self, emb: np.ndarray) -> tuple[str | None, float]:
        best_name = None
        best_score = -1.0
        for name, payload in self._profiles.items():
            score = float(np.dot(payload["embedding"], emb))
            for proto in payload.get("embeddings", []):
                try:
                    pscore = float(np.dot(proto, emb))
                except Exception:
                    continue
                if pscore > score:
                    score = pscore
            if score > best_score:
                best_name = name
                best_score = score
        return best_name, max(best_score, 0.0)

    def _resolve_declared_name(self, declared_name: str, emb: np.ndarray) -> str:
        """Resolve user-declared names to a canonical profile key and avoid duplicates."""
        declared = _normalize_name(declared_name)
        if not declared:
            return declared_name
        if _is_creator_name(declared):
            # Enforce a single canonical creator profile.
            for existing in list(self._profiles.keys()):
                if existing != _CREATOR_CANONICAL and _is_creator_name(existing):
                    self._rename_profile(existing, _CREATOR_CANONICAL)
            return _CREATOR_CANONICAL

        # Exact case-insensitive match: reuse existing profile key.
        for existing in self._profiles:
            if existing.lower() == declared.lower():
                return existing

        best_name, best_score = self._best_match(emb)
        declared_first = first_name(declared).lower()
        declared_parts = declared.split()

        if best_name and best_score >= (self._threshold - 0.05):
            best_first = first_name(best_name).lower()
            if declared_first and declared_first == best_first:
                # Promote a short profile like "Josh" to "Josh Gopaul" when confidently matched.
                if len(declared_parts) > 1 and len(best_name.split()) == 1 and best_name != declared:
                    self._rename_profile(best_name, declared)
                    return declared
                return best_name

        # If user only gives first name and exactly one profile shares it, reuse that profile.
        if len(declared_parts) == 1:
            same_first = [name for name in self._profiles if first_name(name).lower() == declared_first]
            if len(same_first) == 1:
                return same_first[0]

        return declared

    def _rename_profile(self, old_name: str, new_name: str) -> None:
        if old_name not in self._profiles:
            return
        if new_name in self._profiles:
            # Merge into existing target if needed.
            target = self._profiles[new_name]
            source = self._profiles[old_name]
            n_t = max(1, int(target.get("samples", 1)))
            n_s = max(1, int(source.get("samples", 1)))
            merged = (target["embedding"] * n_t + source["embedding"] * n_s) / float(n_t + n_s)
            norm = np.linalg.norm(merged) + 1e-12
            target["embedding"] = merged / norm
            merged_protos = list(target.get("embeddings", [])) + list(source.get("embeddings", []))
            target["embeddings"] = merged_protos[-self._max_embeddings_per_profile :]
            target["samples"] = n_t + n_s
            target["last_seen"] = max(float(target.get("last_seen", 0.0)), float(source.get("last_seen", 0.0)))
            del self._profiles[old_name]
            return

        self._profiles[new_name] = self._profiles.pop(old_name)

    def _upsert_profile(self, name: str, emb: np.ndarray) -> None:
        now = time.time()
        existing = self._profiles.get(name)
        if not existing:
            self._profiles[name] = {
                "embedding": emb,
                "embeddings": [emb],
                "samples": 1,
                "last_seen": now,
            }
            return

        n = max(1, int(existing.get("samples", 1)))
        prev = existing["embedding"]
        merged = (prev * n + emb) / float(n + 1)
        norm = np.linalg.norm(merged) + 1e-12
        existing["embedding"] = merged / norm
        protos = list(existing.get("embeddings", []))
        protos.append(emb)
        existing["embeddings"] = protos[-self._max_embeddings_per_profile :]
        existing["samples"] = n + 1
        existing["last_seen"] = now

    def _new_anonymous_name(self) -> str:
        self._counter += 1
        return f"Speaker {self._counter}"

    # Embedding

    def _extract_embedding(self, pcm: bytes) -> np.ndarray | None:
        if self._embedding_backend == _EMBEDDING_BACKEND_ECAPA:
            ecapa = self._extract_embedding_ecapa(pcm)
            if ecapa is not None:
                return ecapa
        return self._extract_embedding_fallback(pcm)

    def _extract_embedding_ecapa(self, pcm: bytes) -> np.ndarray | None:
        if not pcm or len(pcm) < 4096:
            return None
        model = _load_ecapa_encoder()
        if model is None:
            return None
        try:
            import torch  # type: ignore
        except Exception:
            return None
        try:
            x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
            if x.size < self._sr // 2:
                return None
            wav = torch.from_numpy((x / 32768.0).reshape(1, -1))
            with torch.no_grad():
                emb = model.encode_batch(wav).squeeze().detach().cpu().numpy().astype(np.float32)
            norm = np.linalg.norm(emb) + 1e-12
            return emb / norm
        except Exception:
            return None

    def _extract_embedding_fallback(self, pcm: bytes) -> np.ndarray | None:
        if not pcm or len(pcm) < 4096:
            return None

        x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        if x.size < self._sr // 2:
            return None

        x = x / 32768.0
        absx = np.abs(x)
        idx = np.where(absx > 0.01)[0]
        if idx.size > 0:
            x = x[idx[0] : idx[-1] + 1]
        if x.size < self._sr // 3:
            return None

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
