"""
GAAIA Image router — generates images via the best available free model.

Tier auto-selection (checked at first use):
  ≥ 8 GB free RAM  →  SDXL Lightning  (1024 px, 4-step, Apache 2.0)
  ≥ 4 GB free RAM  →  Dreamlike Photoreal 2.0  (640 px, 30-step, SD 1.5 fine-tune)
  fallback         →  Stable Diffusion v1.5    (640 px, 30-step)

POST /image/generate  { "prompt": "...", "session_id": "...", "is_variation": false }
  → 200  image/png
  → 503  if diffusers not installed
  → 500  on failure

GET  /image/model
  → 200  { "model": "...", "tier": "sdxl"|"sd15" }
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid as _uuid_mod
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


def _image_assets_dir() -> Path:
    """Return (and create) the directory where generated images are persisted."""
    base = Path(os.path.expanduser("~/GAAIA/assets/images"))
    base.mkdir(parents=True, exist_ok=True)
    return base


def _save_image_asset(png_bytes: bytes) -> str:
    """Save *png_bytes* to disk and return the backend URL path."""
    filename = f"{_uuid_mod.uuid4()}.png"
    (_image_assets_dir() / filename).write_bytes(png_bytes)
    return f"/image/assets/{filename}"


@router.get("/assets/{filename}")
async def serve_image_asset(filename: str) -> Response:
    """Serve a previously generated image from the local asset store."""
    assets_dir = _image_assets_dir()
    # Reject path traversal attempts
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename.")
    filepath = assets_dir / filename
    if not filepath.exists() or not filepath.is_file():
        raise HTTPException(status_code=404, detail="Image not found.")
    return Response(
        content=filepath.read_bytes(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )

# ── Session image cache (in-process, cleared on restart) ─────────────────────
# Maps session_id → last generated PNG bytes so follow-up requests can use
# img2img for visual consistency.
_SESSION_IMG_CACHE: dict[str, bytes] = {}
_SESSION_IMG_MAX = 50   # evict oldest when over limit


def _cache_store(session_id: str, png_bytes: bytes) -> None:
    if not session_id:
        return
    if len(_SESSION_IMG_CACHE) >= _SESSION_IMG_MAX:
        # evict first (oldest) entry
        try:
            oldest = next(iter(_SESSION_IMG_CACHE))
            del _SESSION_IMG_CACHE[oldest]
        except StopIteration:
            pass
    _SESSION_IMG_CACHE[session_id] = png_bytes


def _cache_get(session_id: str) -> bytes | None:
    return _SESSION_IMG_CACHE.get(session_id)


class ImageRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=500)
    negative_prompt: str = Field(default="")       # empty → service fills in full negative
    width: int = Field(default=640, ge=256, le=768)
    height: int = Field(default=640, ge=256, le=768)
    steps: int = Field(default=30, ge=15, le=60)
    guidance_scale: float = Field(default=8.5, ge=1.0, le=20.0)
    # Consistency / variation fields
    session_id: str = Field(default="")            # ties this request to a prior image
    is_variation: bool = Field(default=False)       # True → img2img from cached image
    strength: float = Field(default=0.75, ge=0.1, le=1.0)  # img2img deviation (0=copy, 1=ignore)
    ref_image_url: str = Field(default="")          # web reference URL for first generation


@router.get("/model")
async def get_image_model() -> dict:
    """Return the currently loaded (or to-be-loaded) image model tier."""
    import gaaia.services.image_generator as _svc
    pipe_type   = _svc._pipe_type
    pipe_device = _svc._pipe_device
    if pipe_type == "sdxl":
        model = f"{_svc._SDXL_BASE_ID} + SDXL-Lightning LoRA (4-step, 1024 px)"
    elif pipe_type == "sd15":
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

    If body.is_variation is True and the session has a cached image, uses
    img2img (Stable Diffusion image-to-image) to maintain visual consistency
    with the previous result.  Otherwise falls through to standard txt2img.

    If body.ref_image_url is provided and this is the first generation in the
    session, the reference image is fetched and used as a light img2img anchor
    (strength=0.35) so the output is grounded in real-world reference imagery.
    """
    from gaaia.services.image_generator import generate_image, generate_image_variation

    session_id   = body.session_id.strip()
    is_variation = body.is_variation
    cached_img   = _cache_get(session_id) if session_id else None

    try:
        # ── Variation of previous image ─────────────────────────────────────
        if is_variation and cached_img is not None:
            logger.info("[ImageRouter] img2img variation (session=%s, strength=%.2f)", session_id, body.strength)
            png_bytes = await asyncio.to_thread(
                generate_image_variation,
                cached_img,
                body.prompt.strip(),
                body.negative_prompt.strip(),
                body.strength,
                body.steps,
                body.guidance_scale,
            )

        # ── First generation with web reference ─────────────────────────────
        elif body.ref_image_url.strip():
            ref_bytes = await _fetch_ref_image(body.ref_image_url.strip())
            if ref_bytes:
                logger.info("[ImageRouter] img2img from web ref (session=%s)", session_id)
                png_bytes = await asyncio.to_thread(
                    generate_image_variation,
                    ref_bytes,
                    body.prompt.strip(),
                    body.negative_prompt.strip(),
                    0.35,               # light anchor — stay close to reference
                    body.steps,
                    body.guidance_scale,
                )
            else:
                png_bytes = await asyncio.to_thread(
                    generate_image,
                    body.prompt.strip(),
                    body.negative_prompt.strip(),
                    body.width,
                    body.height,
                    body.steps,
                    body.guidance_scale,
                )

        # ── Standard txt2img ────────────────────────────────────────────────
        else:
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

    # Cache result for future variation requests
    _cache_store(session_id, png_bytes)

    # Persist to disk so the URL survives page refreshes
    asset_url = _save_image_asset(png_bytes)

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "Content-Disposition": "inline; filename=gaaia_image.png",
            "X-GAAIA-Asset-URL": asset_url,
        },
    )


@router.post("/generate/stream")
async def generate_image_stream(body: ImageRequest) -> StreamingResponse:
    """
    SSE endpoint that streams diffusion step progress then delivers a stable asset URL.

    Events:
      data: {"type": "progress", "step": N, "total": T}
      data: {"type": "done",     "url": "/image/assets/<uuid>.png"}
      data: {"type": "error",    "detail": "..."}
    """
    from gaaia.services.image_generator import generate_image, generate_image_variation

    session_id   = body.session_id.strip()
    is_variation = body.is_variation
    cached_img   = _cache_get(session_id) if session_id else None

    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()

    def step_cb(step: int, total: int) -> None:
        try:
            loop.call_soon_threadsafe(q.put_nowait, {"type": "progress", "step": step, "total": total})
        except Exception:
            pass

    async def run() -> None:
        try:
            if is_variation and cached_img is not None:
                logger.info("[ImageRouter/stream] img2img variation (session=%s)", session_id)
                png_bytes = await asyncio.to_thread(
                    generate_image_variation,
                    cached_img,
                    body.prompt.strip(),
                    body.negative_prompt.strip(),
                    body.strength,
                    body.steps,
                    body.guidance_scale,
                    step_cb,
                )
            elif body.ref_image_url.strip():
                ref_bytes = await _fetch_ref_image(body.ref_image_url.strip())
                if ref_bytes:
                    logger.info("[ImageRouter/stream] img2img from web ref (session=%s)", session_id)
                    png_bytes = await asyncio.to_thread(
                        generate_image_variation,
                        ref_bytes,
                        body.prompt.strip(),
                        body.negative_prompt.strip(),
                        0.35,
                        body.steps,
                        body.guidance_scale,
                        step_cb,
                    )
                else:
                    png_bytes = await asyncio.to_thread(
                        generate_image,
                        body.prompt.strip(),
                        body.negative_prompt.strip(),
                        body.width,
                        body.height,
                        body.steps,
                        body.guidance_scale,
                        step_cb,
                    )
            else:
                png_bytes = await asyncio.to_thread(
                    generate_image,
                    body.prompt.strip(),
                    body.negative_prompt.strip(),
                    body.width,
                    body.height,
                    body.steps,
                    body.guidance_scale,
                    step_cb,
                )

            _cache_store(session_id, png_bytes)
            asset_url = _save_image_asset(png_bytes)
            await q.put({"type": "done", "url": asset_url})
        except Exception as exc:
            await q.put({"type": "error", "detail": str(exc)})

    asyncio.create_task(run())

    async def stream():
        while True:
            evt = await q.get()
            yield f"data: {json.dumps(evt)}\n\n"
            if evt["type"] in ("done", "error"):
                break

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


async def _fetch_ref_image(url: str) -> bytes | None:
    """Fetch a reference image from a URL.  Returns bytes or None on failure."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, follow_redirects=True)
            if r.status_code == 200 and "image" in r.headers.get("content-type", ""):
                return r.content
    except Exception as exc:
        logger.warning("[ImageRouter] Failed to fetch ref image from %s: %s", url, exc)
    return None
