"""OAuth 2.0 social login — Google and GitHub.

Setup (one-time):
  Google: https://console.cloud.google.com → APIs & Services → Credentials
    Authorized redirect URI: http://127.0.0.1:8765/auth/oauth/google/callback
    Set env: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

  GitHub: https://github.com/settings/developers → OAuth Apps
    Authorization callback URL: http://127.0.0.1:8765/auth/oauth/github/callback
    Set env: GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET

Without these env vars the buttons render in the UI but return a 501 with a
helpful setup message.
"""
from __future__ import annotations

import os
import secrets
import time
from typing import Optional
from urllib.parse import urlencode
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from config.settings import get_settings
from gaaia.memory.store import MemoryStore
from gaaia.server.auth_utils import COOKIE_NAME, create_token, decode_token
from gaaia.server.dependencies import get_memory

router = APIRouter()

_s = get_settings()

FRONTEND_URL = os.environ.get("GAAIA_FRONTEND_URL", "http://127.0.0.1:3000")

# In-memory CSRF state store:
# {state_token: {"expires_at": float, "mode": "login"|"link", "user_id": str|None}}
_pending_states: dict[str, dict[str, object]] = {}
_STATE_TTL = 300  # 5 minutes


def _safe_frontend_url(url: str | None) -> str:
    raw = (url or "").strip()
    if not raw:
        return FRONTEND_URL
    try:
        parsed = urlparse(raw)
    except Exception:
        return FRONTEND_URL
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return FRONTEND_URL
    return f"{parsed.scheme}://{parsed.netloc}"


def _preferred_frontend_url(request: Request) -> str:
    # Prefer explicit origin header; fall back to referer origin.
    origin = request.headers.get("origin")
    if origin:
        return _safe_frontend_url(origin)
    referer = request.headers.get("referer")
    if referer:
        return _safe_frontend_url(referer)
    return FRONTEND_URL


def _new_state(mode: str = "login", user_id: str | None = None, frontend_url: str | None = None) -> str:
    state = secrets.token_urlsafe(16)
    _pending_states[state] = {
        "expires_at": time.monotonic() + _STATE_TTL,
        "mode": mode,
        "user_id": user_id,
        "frontend_url": _safe_frontend_url(frontend_url),
    }
    return state


def _consume_state(state: str) -> dict[str, object] | None:
    """Return state payload if valid, removing it and expired entries."""
    now = time.monotonic()
    expired = [k for k, v in _pending_states.items() if float(v.get("expires_at", 0)) < now]
    for k in expired:
        del _pending_states[k]
    payload = _pending_states.pop(state, None)
    if payload is None:
        return None
    return payload


def _frontend_oauth_success_redirect(
    user_id: str,
    provider: str,
    token_version: int = 0,
    linked: bool = False,
    frontend_url: str | None = None,
) -> RedirectResponse:
    """
    Bridge OAuth auth from backend host to frontend host.
    We redirect with a signed token so the frontend can set its own cookie
    (required for middleware-protected routes like /chat).
    The token embeds the user's current token_version so it immediately
    respects any prior password changes.
    """
    token = create_token(user_id, token_version)
    base = _safe_frontend_url(frontend_url)
    query = urlencode({
        "token": token,
        "provider": provider,
        "linked": "1" if linked else "0",
    })
    return RedirectResponse(f"{base}/auth/oauth/success?{query}")


def _find_or_create_oauth_user(
    memory: MemoryStore,
    provider: str,
    provider_user_id: str,
    email: str,
    display_name: str,
    avatar_color: str = "#38bdf8",
) -> str:
    linked_user_id = memory.get_user_id_by_oauth(provider, provider_user_id)
    if linked_user_id:
        return linked_user_id

    existing = memory.get_user_by_email(email)
    if existing:
        user_id = existing.id
    else:
        is_first = memory.count_users() == 0
        user = memory.create_user(
            email=email,
            # OAuth users do not have a local password.
            # Store a non-empty sentinel so DB constraints pass; login checks treat
            # this as non-verifiable and return 401 instead of crashing.
            hashed_password="oauth_account",
            display_name=display_name,
            avatar_color=avatar_color,
        )
        if is_first:
            memory.claim_orphaned_sessions(user.id)
        user_id = user.id

    ok, _ = memory.link_oauth_identity(user_id, provider, provider_user_id, email=email)
    if not ok:
        raise HTTPException(status_code=409, detail="OAuth identity is already linked to another user.")
    return user_id


# ── Google ────────────────────────────────────────────────────────────────────

GOOGLE_CLIENT_ID     = _s.google_client_id or os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = _s.google_client_secret or os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_AUTH_URL      = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL     = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL  = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_REDIRECT_URI  = os.environ.get(
    "GOOGLE_REDIRECT_URI", f"{FRONTEND_URL}/api/auth/oauth/google/callback"
)


@router.get("/google")
def google_initiate(request: Request, link: bool = False) -> RedirectResponse:
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=501,
            detail="Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
        )

    frontend_url = _preferred_frontend_url(request)

    mode = "login"
    user_id: str | None = None
    if link:
        token = request.cookies.get(COOKIE_NAME)
        _result = decode_token(token) if token else None
        user_id = _result[0] if _result else None
        if not user_id:
            raise HTTPException(status_code=401, detail="Sign in before linking Google.")
        mode = "link"

    params = urlencode({
        "client_id":     GOOGLE_CLIENT_ID,
        "redirect_uri":  GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope":         "openid email profile",
        "state":         _new_state(mode=mode, user_id=user_id, frontend_url=frontend_url),
        "access_type":   "online",
        "prompt":        "select_account",
    })
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{params}")


@router.get("/google/callback")
async def google_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    memory: MemoryStore = Depends(get_memory),
) -> RedirectResponse:
    frontend_url = FRONTEND_URL
    if error or not code:
        return RedirectResponse(f"{frontend_url}/login?error=oauth_cancelled")

    state_payload = _consume_state(state) if state else None
    if not state_payload:
        return RedirectResponse(f"{frontend_url}/login?error=oauth_invalid_state")
    frontend_url = _safe_frontend_url(str(state_payload.get("frontend_url") or FRONTEND_URL))

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(GOOGLE_TOKEN_URL, data={
            "code":          code,
            "client_id":     GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri":  GOOGLE_REDIRECT_URI,
            "grant_type":    "authorization_code",
        })
        if token_resp.status_code != 200:
            return RedirectResponse(f"{frontend_url}/login?error=oauth_token_failed")

        access_token = token_resp.json().get("access_token")
        userinfo_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if userinfo_resp.status_code != 200:
            return RedirectResponse(f"{frontend_url}/login?error=oauth_userinfo_failed")
        info = userinfo_resp.json()

    email = info.get("email", "")
    if not email:
        return RedirectResponse(f"{frontend_url}/login?error=oauth_no_email")

    provider_user_id = str(info.get("sub") or "")
    if not provider_user_id:
        return RedirectResponse(f"{frontend_url}/login?error=oauth_userinfo_failed")

    mode = str(state_payload.get("mode") or "login")
    name = info.get("name") or email.split("@")[0]

    if mode == "link":
        link_user_id = str(state_payload.get("user_id") or "")
        if not link_user_id:
            return RedirectResponse(f"{frontend_url}/login?error=oauth_link_forbidden")
        ok, err = memory.link_oauth_identity(link_user_id, "google", provider_user_id, email=email)
        if not ok:
            return RedirectResponse(f"{frontend_url}/chat?error={err or 'oauth_link_failed'}")
        u = memory.get_user_by_id(link_user_id)
        ver = u.token_version if u else 0
        return _frontend_oauth_success_redirect(link_user_id, "google", token_version=ver, linked=True, frontend_url=frontend_url)

    try:
        user_id = _find_or_create_oauth_user(memory, "google", provider_user_id, email, name)
    except Exception:
        return RedirectResponse(f"{frontend_url}/login?error=oauth_user_create_failed")
    u = memory.get_user_by_id(user_id)
    ver = u.token_version if u else 0
    return _frontend_oauth_success_redirect(user_id, "google", token_version=ver, frontend_url=frontend_url)


# ── GitHub ────────────────────────────────────────────────────────────────────

GITHUB_CLIENT_ID     = _s.github_client_id or os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = _s.github_client_secret or os.environ.get("GITHUB_CLIENT_SECRET", "")
GITHUB_AUTH_URL      = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL     = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL      = "https://api.github.com/user"
GITHUB_EMAIL_URL     = "https://api.github.com/user/emails"
GITHUB_REDIRECT_URI  = os.environ.get(
    "GITHUB_REDIRECT_URI", f"{FRONTEND_URL}/api/auth/oauth/github/callback"
)

_AVATAR_COLORS = ["#818cf8", "#34d399", "#fb923c", "#f472b6", "#a78bfa", "#38bdf8"]


@router.get("/github")
def github_initiate(request: Request, link: bool = False) -> RedirectResponse:
    if not GITHUB_CLIENT_ID:
        raise HTTPException(
            status_code=501,
            detail="GitHub OAuth not configured. Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET.",
        )

    frontend_url = _preferred_frontend_url(request)

    mode = "login"
    user_id: str | None = None
    if link:
        token = request.cookies.get(COOKIE_NAME)
        _result = decode_token(token) if token else None
        user_id = _result[0] if _result else None
        if not user_id:
            raise HTTPException(status_code=401, detail="Sign in before linking GitHub.")
        mode = "link"

    params = urlencode({
        "client_id":    GITHUB_CLIENT_ID,
        "redirect_uri": GITHUB_REDIRECT_URI,
        "scope":        "read:user user:email",
        "state":        _new_state(mode=mode, user_id=user_id, frontend_url=frontend_url),
    })
    return RedirectResponse(f"{GITHUB_AUTH_URL}?{params}")


@router.get("/github/callback")
async def github_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    memory: MemoryStore = Depends(get_memory),
) -> RedirectResponse:
    frontend_url = FRONTEND_URL
    if error or not code:
        return RedirectResponse(f"{frontend_url}/login?error=oauth_cancelled")

    state_payload = _consume_state(state) if state else None
    if not state_payload:
        return RedirectResponse(f"{frontend_url}/login?error=oauth_invalid_state")
    frontend_url = _safe_frontend_url(str(state_payload.get("frontend_url") or FRONTEND_URL))

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id":     GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code":          code,
                "redirect_uri":  GITHUB_REDIRECT_URI,
            },
            headers={"Accept": "application/json"},
        )
        access_token = token_resp.json().get("access_token")
        if not access_token:
            return RedirectResponse(f"{frontend_url}/login?error=oauth_token_failed")

        auth_header = {"Authorization": f"Bearer {access_token}"}
        user_resp = await client.get(GITHUB_USER_URL, headers=auth_header)
        if user_resp.status_code != 200:
            return RedirectResponse(f"{frontend_url}/login?error=oauth_userinfo_failed")
        gh_user = user_resp.json()

        email: str = gh_user.get("email") or ""
        if not email:
            emails_resp = await client.get(GITHUB_EMAIL_URL, headers=auth_header)
            if emails_resp.status_code == 200:
                payload = emails_resp.json()
                if isinstance(payload, list):
                    for entry in payload:
                        if isinstance(entry, dict) and entry.get("primary") and entry.get("verified"):
                            email = entry.get("email", "")
                            if email:
                                break

    if not email:
        return RedirectResponse(f"{frontend_url}/login?error=oauth_no_email")

    provider_user_id = str(gh_user.get("id") or "")
    if not provider_user_id:
        return RedirectResponse(f"{frontend_url}/login?error=oauth_userinfo_failed")

    name = gh_user.get("name") or gh_user.get("login") or email.split("@")[0]
    try:
        color_index = int(provider_user_id) % len(_AVATAR_COLORS)
    except Exception:
        color_index = 0
    color = _AVATAR_COLORS[color_index]

    mode = str(state_payload.get("mode") or "login")
    if mode == "link":
        link_user_id = str(state_payload.get("user_id") or "")
        if not link_user_id:
            return RedirectResponse(f"{frontend_url}/login?error=oauth_link_forbidden")
        ok, err = memory.link_oauth_identity(link_user_id, "github", provider_user_id, email=email)
        if not ok:
            return RedirectResponse(f"{frontend_url}/chat?error={err or 'oauth_link_failed'}")
        u = memory.get_user_by_id(link_user_id)
        ver = u.token_version if u else 0
        return _frontend_oauth_success_redirect(link_user_id, "github", token_version=ver, linked=True, frontend_url=frontend_url)

    try:
        user_id = _find_or_create_oauth_user(memory, "github", provider_user_id, email, name, color)
    except Exception:
        return RedirectResponse(f"{frontend_url}/login?error=oauth_user_create_failed")
    u = memory.get_user_by_id(user_id)
    ver = u.token_version if u else 0
    return _frontend_oauth_success_redirect(user_id, "github", token_version=ver, frontend_url=frontend_url)
