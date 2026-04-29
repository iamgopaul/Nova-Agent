from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from gaaia.memory.store import MemoryStore
from gaaia.server.dependencies import get_current_user, get_memory
from gaaia.memory.models import User

logger = logging.getLogger(__name__)
router = APIRouter()

_NAMED_SCHEDULES = {"hourly", "daily", "weekly"}


class TaskBody(BaseModel):
    name: str
    prompt: str
    schedule: str
    notify_email: bool = False


@router.get("")
def list_tasks(
    current_user: User = Depends(get_current_user),
    memory: MemoryStore = Depends(get_memory),
) -> list[dict]:
    tasks = memory.list_scheduled_tasks(current_user.id)
    return [_task_dict(t) for t in tasks]


@router.post("", status_code=201)
def create_task(
    body: TaskBody,
    current_user: User = Depends(get_current_user),
    memory: MemoryStore = Depends(get_memory),
) -> dict:
    if body.schedule not in _NAMED_SCHEDULES and not _valid_cron(body.schedule):
        raise HTTPException(
            status_code=422,
            detail=f"schedule must be one of {_NAMED_SCHEDULES} or a valid 5-field cron expression.",
        )
    task = memory.create_scheduled_task(
        user_id=current_user.id,
        name=body.name,
        prompt=body.prompt,
        schedule=body.schedule,
        notify_email=body.notify_email,
    )
    return _task_dict(task)


@router.patch("/{task_id}/toggle")
def toggle_task(
    task_id: str,
    enabled: bool,
    current_user: User = Depends(get_current_user),
    memory: MemoryStore = Depends(get_memory),
) -> dict:
    ok = memory.toggle_scheduled_task(task_id, current_user.id, enabled)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found.")
    return {"enabled": enabled}


@router.delete("/{task_id}", status_code=204)
def delete_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    memory: MemoryStore = Depends(get_memory),
) -> None:
    ok = memory.delete_scheduled_task(task_id, current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found.")


def _task_dict(t) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "prompt": t.prompt,
        "schedule": t.schedule,
        "enabled": t.enabled,
        "last_run_at": t.last_run_at,
        "next_run_at": t.next_run_at,
        "last_status": t.last_status,
        "notify_email": t.notify_email,
        "created_at": t.created_at,
    }


def _valid_cron(expr: str) -> bool:
    parts = expr.strip().split()
    return len(parts) == 5


# ── Background task runner (called from main.py lifespan) ────────────

def start_scheduler(memory: MemoryStore, orchestrator) -> None:
    """Start APScheduler to run user-defined tasks."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger
    except ImportError:
        logger.warning("[Scheduler] APScheduler not installed — scheduled tasks disabled.")
        return

    sched = BackgroundScheduler()

    # Check every minute which tasks are due
    sched.add_job(
        _tick,
        trigger=IntervalTrigger(minutes=1),
        args=[memory, orchestrator],
        id="gaaia_task_tick",
        replace_existing=True,
    )
    sched.start()
    logger.info("[Scheduler] APScheduler started.")
    return sched


def _tick(memory: MemoryStore, orchestrator) -> None:
    """Run any enabled tasks that are due."""
    import asyncio
    now = datetime.now(timezone.utc)
    tasks = memory.list_all_enabled_scheduled_tasks()
    for task in tasks:
        if _is_due(task, now):
            asyncio.run(_run_task(task, memory, orchestrator))


def _is_due(task, now: datetime) -> bool:
    if task.last_run_at is None:
        return True
    elapsed = (now - task.last_run_at).total_seconds()
    schedule_map = {"hourly": 3600, "daily": 86400, "weekly": 604800}
    if task.schedule in schedule_map:
        return elapsed >= schedule_map[task.schedule]
    # For cron, defer to APScheduler — just return False here
    return False


async def _run_task(task, memory: MemoryStore, orchestrator) -> None:
    from gaaia.memory.store import MemoryStore
    from gaaia.services.resend_service import send_scheduled_task_result

    logger.info("[Scheduler] Running task %s (%s)", task.name, task.id)
    sid = memory.get_or_create_session(user_id=task.user_id, source="scheduler")
    output_parts = []
    try:
        async for chunk in orchestrator.handle_message(
            message=task.prompt,
            session_id=sid,
            user_id=task.user_id,
        ):
            if hasattr(chunk, "content"):
                output_parts.append(chunk.content)
        output = "".join(output_parts)
        memory.update_scheduled_task_run(task.id, output, "success")

        if task.notify_email:
            user = memory.get_user_by_id(task.user_id)
            if user:
                send_scheduled_task_result(user.email, task.name, output)
    except Exception as exc:
        logger.error("[Scheduler] Task %s failed: %s", task.id, exc)
        memory.update_scheduled_task_run(task.id, str(exc), "failed")
