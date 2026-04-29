"""
GAAIA Music router — generates instrumental beats via MusicGen.

POST /music/generate   { "prompt": "...", "duration": 10 }
  → 200  audio/wav  (raw WAV bytes)  + X-GAAIA-Asset-URL header
  → 503  if audiocraft is not installed
  → 500  on any other generation error

GET /music/assets/{filename}
  → 200  audio/wav  (serves saved WAV file)
"""

from __future__ import annotations

import asyncio
import os
import uuid as _uuid_mod
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

router = APIRouter()


def _music_assets_dir() -> Path:
    from config.settings import get_settings
    d = get_settings().assets_dir / "music"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_music_asset(wav_bytes: bytes) -> str:
    filename = f"{_uuid_mod.uuid4().hex}.wav"
    (_music_assets_dir() / filename).write_bytes(wav_bytes)
    return f"/music/assets/{filename}"


class MusicRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=300)
    duration: int = Field(
        default=12,
        ge=5,
        le=30,
        description="Clip length in seconds. Shorter clips (10–15s) are more reliable on Apple Silicon.",
    )


@router.post("/generate")
async def generate_music_endpoint(body: MusicRequest) -> Response:
    """
    Generate an instrumental beat from a text description.
    Uses MusicGen (facebook/musicgen-small) via audiocraft.
    Generation runs in a thread pool to avoid blocking the event loop.
    """
    from gaaia.services.music_generator import generate_music

    try:
        wav_bytes = await asyncio.to_thread(
            generate_music,
            body.prompt.strip(),
            body.duration,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Music generation failed: {exc}"
        ) from exc

    asset_url = _save_music_asset(wav_bytes)
    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={
            "Content-Disposition": "inline; filename=gaaia_beat.wav",
            "X-GAAIA-Asset-URL": asset_url,
        },
    )


@router.get("/assets/{filename}")
async def get_music_asset(filename: str) -> Response:
    """Serve a previously generated WAV file by name."""
    # Prevent path traversal
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = _music_assets_dir() / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return Response(
        content=path.read_bytes(),
        media_type="audio/wav",
        headers={
            "Content-Disposition": f"inline; filename={filename}",
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )
