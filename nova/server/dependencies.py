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
    result = decode_token(token)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    user_id, token_version = result
    user = memory.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    # Reject tokens issued before the most recent password change
    if (user.token_version or 0) != token_version:
        raise HTTPException(
            status_code=401,
            detail="Session expired after a password change. Please sign in again.",
        )
    return user


def get_optional_user(
    request: Request,
    memory: MemoryStore = Depends(get_memory),
) -> User | None:
    """Like get_current_user but returns None instead of raising 401."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    result = decode_token(token)
    if not result:
        return None
    user_id, _ = result
    return memory.get_user_by_id(user_id)
