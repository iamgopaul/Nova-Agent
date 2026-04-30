from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from gaaia.memory.models import User
from gaaia.memory.store import MemoryStore
from gaaia.server.dependencies import get_current_user, get_memory

router = APIRouter()


class AgentRunBody(BaseModel):
    request: str = Field(..., min_length=3, max_length=4000)


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


@router.post("/run")
async def start_run(
    body: AgentRunBody,
    user: User = Depends(get_current_user),
    memory: MemoryStore = Depends(get_memory),
) -> dict:
    run = memory.create_agent_run(user.id, body.request.strip())
    return {"run_id": run.id}


@router.get("/runs")
async def list_runs(
    user: User = Depends(get_current_user),
    memory: MemoryStore = Depends(get_memory),
) -> list[dict]:
    return memory.list_agent_runs(user.id)


@router.get("/{run_id}/stream")
async def stream_run(
    run_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    memory: MemoryStore = Depends(get_memory),
) -> StreamingResponse:
    run = memory.get_agent_run(run_id, user_id=user.id)
    if not run:
        raise HTTPException(status_code=404, detail="Agent run not found.")
    if run.status not in ("running", "pending"):
        raise HTTPException(status_code=409, detail="Agent run already completed.")

    user_request = run.request
    settings = request.app.state.settings

    async def generate():
        from gaaia.agent.workflow import WorkflowRunner

        runner = WorkflowRunner(settings)
        loop = asyncio.get_event_loop()
        q: asyncio.Queue[dict | None] = asyncio.Queue()
        task_db_ids: dict[str, int] = {}  # agent_id → AgentTask.id

        def _cb(event: dict) -> None:
            loop.call_soon_threadsafe(q.put_nowait, event)

        async def _run() -> None:
            try:
                await runner.run(user_request, event_callback=_cb)
            except Exception as exc:
                _cb({"type": "error", "message": str(exc)})
            finally:
                loop.call_soon_threadsafe(q.put_nowait, None)

        asyncio.create_task(_run())

        goal_set = False

        while True:
            event = await q.get()
            if event is None:
                break

            etype = event.get("type")

            if etype == "plan" and not goal_set:
                memory.update_agent_run(run_id, status="running", goal=event.get("goal"))
                goal_set = True
            elif etype == "agent_start":
                agent_id = event.get("agent_id", "")
                t = memory.create_agent_task(
                    run_id=run_id,
                    agent_id=agent_id,
                    agent_name=event.get("agent_name", ""),
                    task=event.get("task", ""),
                )
                task_db_ids[agent_id] = t.id
            elif etype == "agent_done":
                agent_id = event.get("agent_id", "")
                if agent_id in task_db_ids:
                    memory.update_agent_task(task_db_ids[agent_id], status="done")
            elif etype == "agent_error":
                agent_id = event.get("agent_id", "")
                if agent_id in task_db_ids:
                    memory.update_agent_task(
                        task_db_ids[agent_id], status="error",
                        output=event.get("error", ""),
                    )
            elif etype == "done":
                memory.update_agent_run(run_id, status="done", output=event.get("output", ""))
            elif etype == "error":
                memory.update_agent_run(run_id, status="error", output=event.get("message", ""))

            yield _sse(event)
            if etype in ("done", "error"):
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
