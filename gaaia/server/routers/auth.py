from __future__ import annotations

import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from gaaia.memory.store import MemoryStore
from gaaia.server.auth_utils import (
    COOKIE_NAME,
    TOKEN_EXPIRE_DAYS,
    create_challenge_token,
    create_token,
    hash_password,
    verify_password,
)
from gaaia.server.dependencies import get_current_user, get_memory
from gaaia.server.schemas import (
    LoginRequest,
    RegisterRequest,
    SetPasswordRequest,
    UpdateProfileRequest,
    UserResponse,
)
from gaaia.server.security import (
    check_password_strength,
    get_client_ip,
    login_rate,
    login_throttler,
    password_rate,
    register_rate,
    require_rate_limit,
)
from gaaia.memory.models import User

router = APIRouter()

_COOKIE_MAX_AGE = TOKEN_EXPIRE_DAYS * 24 * 60 * 60

_OAUTH_SENTINELS = {"", "oauth_account"}

# When the frontend is hosted on a different domain than the backend
# (e.g. Vercel + Cloudflare Tunnel), the auth cookie must be SameSite=None +
# Secure or browsers refuse to send it cross-origin. Toggle via env var so the
# default local-only setup keeps working without HTTPS.
_CROSS_DOMAIN_COOKIES = (os.environ.get("GAAIA_CROSS_DOMAIN_COOKIES") or "").strip().lower() in ("1", "true", "yes")
_COOKIE_SAMESITE: Literal["lax", "none"] = "none" if _CROSS_DOMAIN_COOKIES else "lax"
_COOKIE_SECURE = _CROSS_DOMAIN_COOKIES
# Explicit cookie domain for production. Without this the browser stores the
# cookie scoped to the exact host of the response (e.g. gaaia.co only), so
# www.gaaia.co — or any other subdomain — won't see the auth cookie. Setting
# `.gaaia.co` makes the cookie valid for the apex AND every subdomain. Leave
# unset for local dev so cookies stick to localhost.
_COOKIE_DOMAIN: str | None = (os.environ.get("GAAIA_COOKIE_DOMAIN") or "").strip() or None


def _has_password(user: User) -> bool:
    return bool(user.hashed_password) and user.hashed_password not in _OAUTH_SENTINELS


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        avatar_color=user.avatar_color,
        has_password=_has_password(user),
        created_at=user.created_at,
    )


def _set_auth_cookie(response: Response, user: User) -> None:
    """Issue a JWT that embeds the user's current token_version."""
    token = create_token(user.id, user.token_version or 0)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        # "lax" for same-site dev; "none" + secure required when frontend is
        # on a different domain (Vercel) and backend is on a tunnel.
        samesite=_COOKIE_SAMESITE,
        path="/",
        max_age=_COOKIE_MAX_AGE,
        secure=_COOKIE_SECURE,
        domain=_COOKIE_DOMAIN,
    )


@router.post("/register", response_model=UserResponse, status_code=201)
def register(
    request: Request,
    body: RegisterRequest,
    response: Response,
    memory: MemoryStore = Depends(get_memory),
) -> UserResponse:
    ip = get_client_ip(request)
    require_rate_limit(
        register_rate, ip,
        "Too many registration attempts. Please wait a few minutes.",
    )

    # Enforce password strength on registration
    ok, issues = check_password_strength(body.password)
    if not ok:
        raise HTTPException(status_code=422, detail="; ".join(issues))

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

    _set_auth_cookie(response, user)
    return _user_response(user)


@router.post("/login", response_model=UserResponse)
def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    memory: MemoryStore = Depends(get_memory),
) -> UserResponse:
    ip = get_client_ip(request)

    # IP-level rate limit: slow down credential-stuffing attempts
    require_rate_limit(
        login_rate, ip,
        "Too many login attempts from this address. Please wait a minute.",
    )

    # Account-level lockout: prevent targeted brute force
    email_key = body.email.lower().strip()
    locked, secs = login_throttler.is_locked(email_key)
    if locked:
        raise HTTPException(
            status_code=429,
            detail=f"Account temporarily locked after too many failed attempts. "
                   f"Try again in {secs} seconds.",
        )

    user = memory.get_user_by_email(body.email)

    # Constant-time comparison prevents user enumeration timing attacks
    if not user or not verify_password(body.password, user.hashed_password):
        login_throttler.record_failure(email_key)
        failures = login_throttler.failure_count(email_key)
        remaining = max(0, 5 - failures)  # warn when approaching first lockout
        detail = "Invalid email or password."
        if failures >= 3 and remaining > 0:
            detail += f" ({remaining} attempt{'s' if remaining != 1 else ''} before temporary lockout)"
        raise HTTPException(status_code=401, detail=detail)

    # Successful password check — clear failure counter
    login_throttler.record_success(email_key)
    login_rate.reset(ip)

    # If 2FA is enabled, return a challenge token instead of the auth cookie
    if user.totp_enabled:
        method = "totp"
        challenge = create_challenge_token(user.id, method)
        memory.log_action("login_2fa_challenge", user_id=user.id,
                          ip_address=ip, resource="auth")
        response.status_code = 202
        return {"requires_2fa": True, "challenge_token": challenge, "method": method}

    _set_auth_cookie(response, user)
    memory.log_action("login", user_id=user.id, ip_address=ip, resource="auth")
    return _user_response(user)


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    # The delete-cookie Set-Cookie header MUST mirror the attributes the cookie
    # was set with, otherwise the browser refuses the deletion. In particular:
    # SameSite=None requires Secure — Chrome silently rejects a delete header
    # that has SameSite=None without Secure, and the original cookie persists.
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        samesite=_COOKIE_SAMESITE,
        secure=_COOKIE_SECURE,
        httponly=True,
        domain=_COOKIE_DOMAIN,
    )


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


@router.post("/password", response_model=UserResponse)
def set_or_change_password(
    request: Request,
    body: SetPasswordRequest,
    current_user: User = Depends(get_current_user),
    memory: MemoryStore = Depends(get_memory),
) -> UserResponse:
    """Set a new password or change an existing one.

    - OAuth-only accounts can set a password without ``current_password``.
    - Accounts with an existing password must supply ``current_password``.
    - Changing password bumps ``token_version``, invalidating all other sessions.
    """
    # Per-user rate limit to prevent password-grinding via the API
    require_rate_limit(
        password_rate, current_user.id,
        "Too many password change attempts. Please wait a few minutes.",
    )

    if body.new_password != body.confirm_password:
        raise HTTPException(status_code=422, detail="Passwords do not match.")

    # Enforce strength requirements
    ok, issues = check_password_strength(body.new_password)
    if not ok:
        raise HTTPException(status_code=422, detail="; ".join(issues))

    account_has_password = _has_password(current_user)
    if account_has_password:
        if not body.current_password:
            raise HTTPException(
                status_code=422,
                detail="Current password is required to change your password.",
            )
        if not verify_password(body.current_password, current_user.hashed_password):
            raise HTTPException(status_code=401, detail="Current password is incorrect.")

    new_hash = hash_password(body.new_password)
    updated = memory.update_user_password(current_user.id, new_hash)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found.")
    return _user_response(updated)
