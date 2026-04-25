from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from nova.memory.models import User
from nova.memory.store import MemoryStore
from nova.server.dependencies import get_current_user, get_memory
from nova.server.schemas import (
    FactCreate,
    FactResponse,
    FolderCreate,
    FolderResponse,
    MessageResponse,
    SessionSummary,
    SessionUpdate,
)

router = APIRouter()


# ── Facts ────────────────────────────────────────────────────────────

@router.get("/facts", response_model=list[FactResponse])
def list_facts(
    memory: MemoryStore = Depends(get_memory),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    return memory.get_facts(user_id=current_user.id)


@router.post("/facts", response_model=FactResponse, status_code=201)
def save_fact(
    body: FactCreate,
    memory: MemoryStore = Depends(get_memory),
    current_user: User = Depends(get_current_user),
) -> dict:
    memory.save_fact(body.key, body.value, body.source, user_id=current_user.id)
    return {"key": body.key, "value": body.value, "source": body.source}


@router.delete("/facts/{key}", status_code=204)
def delete_fact(
    key: str,
    memory: MemoryStore = Depends(get_memory),
    current_user: User = Depends(get_current_user),
) -> None:
    deleted = memory.delete_fact(key, user_id=current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Fact '{key}' not found.")


# ── Conversation history ──────────────────────────────────────────────

@router.get("/history/{session_id}", response_model=list[MessageResponse])
def get_history(
    session_id: str,
    n: int = 2000,
    memory: MemoryStore = Depends(get_memory),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    n = min(max(n, 1), 10_000)
    return memory.get_recent_turns(session_id, n, user_id=current_user.id)


@router.get("/sessions", response_model=list[SessionSummary])
def list_sessions(
    memory: MemoryStore = Depends(get_memory),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    return memory.list_sessions(user_id=current_user.id, source="chat")


@router.get("/voice-sessions", response_model=list[SessionSummary])
def list_voice_sessions(
    memory: MemoryStore = Depends(get_memory),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    return memory.list_voice_sessions(user_id=current_user.id)


@router.patch("/sessions/{session_id}", status_code=204)
def update_session(
    session_id: str,
    body: SessionUpdate,
    memory: MemoryStore = Depends(get_memory),
    current_user: User = Depends(get_current_user),
) -> None:
    if body.title is None and body.folder is None:
        raise HTTPException(status_code=400, detail="At least one field must be provided.")

    if body.title is not None:
        renamed = memory.rename_session(session_id, body.title, user_id=current_user.id)
        if not renamed:
            raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

    if body.folder is not None:
        moved = memory.move_session_to_folder(session_id, body.folder, user_id=current_user.id)
        if not moved:
            raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: str,
    memory: MemoryStore = Depends(get_memory),
    current_user: User = Depends(get_current_user),
) -> None:
    deleted = memory.delete_session(session_id, user_id=current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")


@router.get("/folders", response_model=list[FolderResponse])
def list_folders(
    memory: MemoryStore = Depends(get_memory),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    return memory.list_folders(user_id=current_user.id)


@router.post("/folders", response_model=FolderResponse, status_code=201)
def create_folder(
    body: FolderCreate,
    memory: MemoryStore = Depends(get_memory),
    current_user: User = Depends(get_current_user),
) -> dict:
    created = memory.create_folder(body.name, user_id=current_user.id)
    if not created:
        raise HTTPException(status_code=400, detail="Folder name is required.")
    folders = memory.list_folders(user_id=current_user.id)
    for folder in folders:
        if folder["name"] == body.name.strip():
            return folder
    raise HTTPException(status_code=500, detail="Folder was not created.")


@router.delete("/folders/{folder_name}", status_code=204)
def delete_folder(
    folder_name: str,
    memory: MemoryStore = Depends(get_memory),
    current_user: User = Depends(get_current_user),
) -> None:
    deleted = memory.delete_folder(folder_name, user_id=current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Folder '{folder_name}' not found.")
