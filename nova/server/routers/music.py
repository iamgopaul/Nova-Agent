"""
Nova Music router — generates instrumental beats via MusicGen.

POST /music/generate   { "prompt": "...", "duration": 10 }
  → 200  audio/wav  (raw WAV bytes)
  → 503  if audiocraft is not installed
  → 500  on any other generation error
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

router = APIRouter()


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
    from nova.services.music_generator import generate_music

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

    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={"Content-Disposition": "inline; filename=nova_beat.wav"},
    )
