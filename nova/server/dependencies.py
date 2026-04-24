from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from nova.agent.orchestrator import Orchestrator
from nova.approval.manager import ApprovalManager
from nova.memory.models import User
from nova.memory.store import MemoryStore
from nova.server.auth_utils import COOKIE_NAME, decode_token


def get_orchestrator(request: Request) -> Orchestrator:
    return request.app.state.orchestrator


def get_memory(request: Request) -> MemoryStore:
    return request.app.state.memory


def get_approval(request: Request) -> ApprovalManager:
    return request.app.state.approval


def get_current_user(
    request: Request,
    memory: MemoryStore = Depends(get_memory),
) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    user_id = decode_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    user = memory.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    return user


def get_optional_user(
    request: Request,
    memory: MemoryStore = Depends(get_memory),
) -> User | None:
    """Like get_current_user but returns None instead of raising 401."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    user_id = decode_token(token)
    if not user_id:
        return None
    return memory.get_user_by_id(user_id)
