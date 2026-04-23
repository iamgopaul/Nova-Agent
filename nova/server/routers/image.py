"""
Nova Image router — generates images via the best available free model.

Tier auto-selection (checked at first use):
  ≥ 8 GB free RAM  →  SDXL Lightning  (1024 px, 4-step, Apache 2.0)
  ≥ 4 GB free RAM  →  Dreamlike Photoreal 2.0  (640 px, 30-step, SD 1.5 fine-tune)
  fallback         →  Stable Diffusion v1.5    (640 px, 30-step)

POST /image/generate  { "prompt": "...", "width": 640, "height": 640, "steps": 30 }
  → 200  image/png
  → 503  if diffusers not installed
  → 500  on failure

GET  /image/model
  → 200  { "model": "...", "tier": "sdxl"|"sd15" }
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

router = APIRouter()


class ImageRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=500)
    negative_prompt: str = Field(default="")   # empty → service fills in full negative
    width: int = Field(default=640, ge=256, le=768)
    height: int = Field(default=640, ge=256, le=768)
    steps: int = Field(default=30, ge=15, le=60)
    guidance_scale: float = Field(default=8.5, ge=1.0, le=20.0)


@router.get("/model")
async def get_image_model() -> dict:
    """Return the currently loaded (or to-be-loaded) image model tier."""
    import nova.services.image_gen_service as _svc
    pipe_type   = _svc._pipe_type
    pipe_device = _svc._pipe_device
    if pipe_type == "sdxl":
        model = f"{_svc._SDXL_BASE_ID} + SDXL-Lightning LoRA (4-step, 1024 px)"
    elif pipe_type == "sd15":
        # Could be Dreamlike or SD 1.5 — read from the loaded pipeline config
        try:
            model = _svc._pipe.config._name_or_path or _svc._DREAMLIKE_ID
        except Exception:
            model = _svc._DREAMLIKE_ID
    else:
        model = "not loaded yet (auto-selected on first image request)"
    return {"model": model, "tier": pipe_type or "pending", "device": pipe_device or "pending"}


@router.post("/generate")
async def generate_image_endpoint(body: ImageRequest) -> Response:
    """
    Generate an image using the best available free model.
    Tier is auto-selected at first call based on available RAM.
    First call may trigger a model download.
    """
    from nova.services.image_gen_service import generate_image

    try:
        png_bytes = await asyncio.to_thread(
            generate_image,
            body.prompt.strip(),
            body.negative_prompt.strip(),
            body.width,
            body.height,
            body.steps,
            body.guidance_scale,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Image generation failed: {exc}"
        ) from exc

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Content-Disposition": "inline; filename=nova_image.png"},
    )
