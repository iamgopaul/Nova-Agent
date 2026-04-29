from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from gaaia.memory.store import MemoryStore
from gaaia.server.dependencies import get_current_user, get_memory
from gaaia.memory.models import User

router = APIRouter()


def _require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")
    return current_user


@router.get("/stats")
def admin_stats(
    _admin: User = Depends(_require_admin),
    memory: MemoryStore = Depends(get_memory),
) -> dict:
    return memory.get_stats()


@router.get("/users")
def admin_list_users(
    limit: int = 100,
    offset: int = 0,
    _admin: User = Depends(_require_admin),
    memory: MemoryStore = Depends(get_memory),
) -> list[dict]:
    return memory.list_users(limit=limit, offset=offset)


@router.patch("/users/{user_id}/admin")
def set_admin_flag(
    user_id: str,
    is_admin: bool,
    _admin: User = Depends(_require_admin),
    memory: MemoryStore = Depends(get_memory),
) -> dict:
    memory.set_admin(user_id, is_admin)
    return {"message": f"User {user_id} admin={is_admin}"}


@router.get("/audit")
def admin_audit_logs(
    user_id: str | None = None,
    limit: int = 200,
    offset: int = 0,
    _admin: User = Depends(_require_admin),
    memory: MemoryStore = Depends(get_memory),
) -> list[dict]:
    return memory.list_audit_logs(user_id=user_id, limit=limit, offset=offset)
