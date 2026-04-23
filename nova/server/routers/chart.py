"""
Nova Chart router — matplotlib-powered chart generation.

POST /chart/generate   { "spec": {...} }
  → 200  image/png  (chart image bytes)
  → 400  invalid spec
  → 500  rendering failure

The spec format matches what Nova Core emits in ```json blocks during chat.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

router = APIRouter()


class ChartRequest(BaseModel):
    spec: dict = Field(..., description="Chart specification dict")


@router.post("/generate")
async def generate_chart_endpoint(body: ChartRequest) -> Response:
    """Render a chart from a spec dict and return a PNG image."""
    from nova.services.chart_gen_service import generate_chart

    if not body.spec or not body.spec.get("type"):
        raise HTTPException(status_code=400, detail="spec.type is required")

    try:
        png_bytes = await asyncio.to_thread(generate_chart, body.spec)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chart render failed: {exc}") from exc

    return Response(content=png_bytes, media_type="image/png")
