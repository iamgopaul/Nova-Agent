"""
nova/server/routers/watcher.py
──────────────────────────────
CRUD + manual-refresh endpoints for user-defined web-watch topics.

All routes require authentication.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from gaaia.memory.models import User
from gaaia.memory.store import MemoryStore
from gaaia.server.dependencies import get_current_user, get_memory
from gaaia.server.schemas import (
    WatchedTopicCreate,
    WatchedTopicResponse,
    WatchedTopicToggle,
)

router = APIRouter()


# ── List ──────────────────────────────────────────────────────────────

@router.get("/topics", response_model=list[WatchedTopicResponse])
def list_topics(
    memory: MemoryStore = Depends(get_memory),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    return memory.list_watched_topics(user_id=current_user.id)


# ── Create ────────────────────────────────────────────────────────────

@router.post("/topics", response_model=WatchedTopicResponse, status_code=201)
def add_topic(
    body: WatchedTopicCreate,
    memory: MemoryStore = Depends(get_memory),
    current_user: User = Depends(get_current_user),
) -> dict:
    existing = memory.list_watched_topics(user_id=current_user.id)
    if len(existing) >= 50:
        raise HTTPException(status_code=400, detail="Maximum of 50 watch topics reached.")
    return memory.add_watched_topic(
        user_id=current_user.id,
        label=body.label,
        query=body.query,
        category=body.category,
    )


# ── Toggle (enable / disable) ─────────────────────────────────────────

@router.patch("/topics/{topic_id}", status_code=204)
def toggle_topic(
    topic_id: str,
    body: WatchedTopicToggle,
    memory: MemoryStore = Depends(get_memory),
    current_user: User = Depends(get_current_user),
) -> None:
    ok = memory.toggle_watched_topic(topic_id, current_user.id, body.enabled)
    if not ok:
        raise HTTPException(status_code=404, detail="Topic not found.")


# ── Delete ────────────────────────────────────────────────────────────

@router.delete("/topics/{topic_id}", status_code=204)
def delete_topic(
    topic_id: str,
    memory: MemoryStore = Depends(get_memory),
    current_user: User = Depends(get_current_user),
) -> None:
    deleted = memory.delete_watched_topic(topic_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Topic not found.")


# ── Manual refresh ────────────────────────────────────────────────────

@router.post("/topics/{topic_id}/run", response_model=WatchedTopicResponse)
async def run_topic(
    topic_id: str,
    request: Request,
    memory: MemoryStore = Depends(get_memory),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Immediately fetch fresh web results for one topic."""
    topics = memory.list_watched_topics(user_id=current_user.id)
    topic = next((t for t in topics if t["id"] == topic_id), None)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found.")

    from gaaia.services.web_watcher import fetch_topic
    await fetch_topic(memory, {"id": topic_id, "label": topic["label"], "query": topic["query"]})

    # Return the updated record
    updated = memory.list_watched_topics(user_id=current_user.id)
    return next((t for t in updated if t["id"] == topic_id), topic)
