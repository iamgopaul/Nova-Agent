from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from gaaia.memory.models import User
from gaaia.server.dependencies import get_current_user

router = APIRouter()

# In-memory run store: run_id → config dict
_runs: dict[str, dict[str, Any]] = {}


class AgentRunBody(BaseModel):
    request: str = Field(..., min_length=3, max_length=4000)


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


@router.post("/run")
async def start_run(
    body: AgentRunBody,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict:
    run_id = str(uuid.uuid4())
    _runs[run_id] = {"request": body.request.strip(), "user_id": user.id}
    return {"run_id": run_id}


@router.get("/{run_id}/stream")
async def stream_run(
    run_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    if run_id not in _runs:
        raise HTTPException(status_code=404, detail="Agent run not found.")

    cfg = _runs.pop(run_id)
    settings = request.app.state.settings

    async def generate():
        from gaaia.agent.workflow import WorkflowRunner

        runner = WorkflowRunner(settings)
        loop = asyncio.get_event_loop()
        q: asyncio.Queue[dict | None] = asyncio.Queue()

        def _cb(event: dict) -> None:
            loop.call_soon_threadsafe(q.put_nowait, event)

        async def _run() -> None:
            try:
                await runner.run(cfg["request"], event_callback=_cb)
            except Exception as exc:
                _cb({"type": "error", "message": str(exc)})
            finally:
                loop.call_soon_threadsafe(q.put_nowait, None)

        asyncio.create_task(_run())

        while True:
            event = await q.get()
            if event is None:
                break
            yield _sse(event)
            if event.get("type") in ("done", "error"):
                break

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
