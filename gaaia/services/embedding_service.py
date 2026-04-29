from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# nomic-embed-text produces 768-dim embeddings and runs well on 8 GB RAM.
# Users can override via GAAIA_EMBED_MODEL env var.
DEFAULT_EMBED_MODEL = "nomic-embed-text"


def _ollama_host() -> str:
    return os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")


async def embed_text(text: str, model: str | None = None) -> list[float] | None:
    """
    Generate a text embedding via Ollama.
    Returns None if Ollama is unavailable or the model is not installed.
    """
    model = model or os.environ.get("GAAIA_EMBED_MODEL", DEFAULT_EMBED_MODEL)
    url = f"{_ollama_host()}/api/embeddings"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json={"model": model, "prompt": text})
            resp.raise_for_status()
            return resp.json().get("embedding")
    except Exception as exc:
        logger.warning("[Embedding] Failed to embed text: %s", exc)
        return None


def embed_text_sync(text: str, model: str | None = None) -> list[float] | None:
    """Synchronous version for background workers."""
    model = model or os.environ.get("GAAIA_EMBED_MODEL", DEFAULT_EMBED_MODEL)
    url = f"{_ollama_host()}/api/embeddings"
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, json={"model": model, "prompt": text})
            resp.raise_for_status()
            return resp.json().get("embedding")
    except Exception as exc:
        logger.warning("[Embedding] Failed to embed text (sync): %s", exc)
        return None
