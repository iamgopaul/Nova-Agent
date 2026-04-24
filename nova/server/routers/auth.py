from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from nova.memory.store import MemoryStore
from nova.server.auth_utils import (
    COOKIE_NAME,
    TOKEN_EXPIRE_DAYS,
    create_token,
    hash_password,
    verify_password,
)
from nova.server.dependencies import get_current_user, get_memory
from nova.server.schemas import (
    LoginRequest,
    RegisterRequest,
    UpdateProfileRequest,
    UserResponse,
)
from nova.memory.models import User

router = APIRouter()

_COOKIE_MAX_AGE = TOKEN_EXPIRE_DAYS * 24 * 60 * 60


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        avatar_color=user.avatar_color,
        created_at=user.created_at,
    )


def _set_auth_cookie(response: Response, user_id: str) -> None:
    token = create_token(user_id)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="strict",
        path="/",
        max_age=_COOKIE_MAX_AGE,
        secure=False,  # local app — set True in production behind HTTPS
    )


@router.post("/register", response_model=UserResponse, status_code=201)
def register(
    body: RegisterRequest,
    response: Response,
    memory: MemoryStore = Depends(get_memory),
) -> UserResponse:
    if memory.get_user_by_email(body.email):
        raise HTTPException(status_code=409, detail="Email already registered.")

    is_first_user = memory.count_users() == 0
    hashed = hash_password(body.password)
    user = memory.create_user(
        email=body.email,
        hashed_password=hashed,
        display_name=body.display_name,
        avatar_color=body.avatar_color,
    )

    if is_first_user:
        memory.claim_orphaned_sessions(user.id)

    _set_auth_cookie(response, user.id)
    return _user_response(user)


@router.post("/login", response_model=UserResponse)
def login(
    body: LoginRequest,
    response: Response,
    memory: MemoryStore = Depends(get_memory),
) -> UserResponse:
    user = memory.get_user_by_email(body.email)
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    _set_auth_cookie(response, user.id)
    return _user_response(user)


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/", samesite="strict")


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return _user_response(current_user)


@router.patch("/me", response_model=UserResponse)
def update_me(
    body: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    memory: MemoryStore = Depends(get_memory),
) -> UserResponse:
    updated = memory.update_user(
        user_id=current_user.id,
        display_name=body.display_name,
        avatar_color=body.avatar_color,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="User not found.")
    return _user_response(updated)


@router.get("/providers")
def get_linked_providers(
    current_user: User = Depends(get_current_user),
    memory: MemoryStore = Depends(get_memory),
) -> dict[str, bool]:
    linked = set(memory.list_oauth_providers(current_user.id))
    return {
        "google": "google" in linked,
        "github": "github" in linked,
    }
