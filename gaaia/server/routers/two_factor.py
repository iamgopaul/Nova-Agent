from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from gaaia.memory.store import MemoryStore
from gaaia.server.auth_utils import (
    COOKIE_NAME,
    TOKEN_EXPIRE_DAYS,
    create_challenge_token,
    create_token,
    decode_challenge_token,
)
from gaaia.server.dependencies import get_current_user, get_memory
from gaaia.memory.models import User
from gaaia.services import totp_service, resend_service

router = APIRouter()
_COOKIE_MAX_AGE = TOKEN_EXPIRE_DAYS * 24 * 60 * 60


# ── TOTP setup ────────────────────────────────────────────────────────

@router.post("/totp/setup")
def totp_setup(current_user: User = Depends(get_current_user)) -> dict:
    """Generate a new TOTP secret and QR code. Does NOT enable 2FA yet."""
    secret = totp_service.generate_totp_secret()
    uri = totp_service.get_totp_uri(secret, current_user.email)
    qr_url = totp_service.get_qr_code_data_url(uri)
    return {"secret": secret, "qr_data_url": qr_url, "uri": uri}


class TOTPEnableBody(BaseModel):
    secret: str
    code: str


@router.post("/totp/enable")
def totp_enable(
    body: TOTPEnableBody,
    request: Request,
    current_user: User = Depends(get_current_user),
    memory: MemoryStore = Depends(get_memory),
) -> dict:
    """Verify the TOTP code against the pending secret and activate 2FA."""
    if not totp_service.verify_totp(body.secret, body.code):
        raise HTTPException(status_code=400, detail="Invalid TOTP code.")
    plain_codes, hashed_codes = totp_service.generate_backup_codes()
    memory.update_user_totp(
        current_user.id, secret=body.secret, enabled=True,
        backup_codes=json.dumps(hashed_codes),
    )
    memory.log_action("2fa_enabled", user_id=current_user.id,
                      ip_address=request.client.host if request.client else None)
    return {"backup_codes": plain_codes}


class TOTPDisableBody(BaseModel):
    code: str


@router.post("/totp/disable")
def totp_disable(
    body: TOTPDisableBody,
    request: Request,
    current_user: User = Depends(get_current_user),
    memory: MemoryStore = Depends(get_memory),
) -> dict:
    if not current_user.totp_enabled or not current_user.totp_secret:
        raise HTTPException(status_code=400, detail="TOTP is not enabled.")
    ok = totp_service.verify_totp(current_user.totp_secret, body.code)
    if not ok and current_user.totp_backup_codes:
        code_hash = totp_service.hash_backup_code(body.code)
        ok = memory.consume_backup_code(current_user.id, code_hash)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid code.")
    memory.update_user_totp(current_user.id, secret=None, enabled=False)
    memory.log_action("2fa_disabled", user_id=current_user.id,
                      ip_address=request.client.host if request.client else None)
    return {"message": "2FA disabled."}


@router.get("/status")
def two_factor_status(current_user: User = Depends(get_current_user)) -> dict:
    return {
        "totp_enabled": current_user.totp_enabled,
        "backup_codes_remaining": (
            len(json.loads(current_user.totp_backup_codes))
            if current_user.totp_backup_codes else 0
        ),
    }


# ── Email OTP ─────────────────────────────────────────────────────────

@router.post("/email/send")
def send_email_otp(
    request: Request,
    current_user: User = Depends(get_current_user),
    memory: MemoryStore = Depends(get_memory),
) -> dict:
    """Send a 6-digit OTP to the user's email (for initial 2FA challenge)."""
    code, code_hash = totp_service.generate_otp_code()
    expires = datetime.now(timezone.utc) + timedelta(minutes=10)
    memory.create_email_otp(current_user.id, code_hash, expires, purpose="2fa_login")
    resend_service.send_otp_email(current_user.email, code, current_user.display_name)
    return {"message": "OTP sent to your email."}


class SendChallengeBody(BaseModel):
    challenge_token: str


@router.post("/email/send-challenge")
def send_email_otp_challenge(
    body: SendChallengeBody,
    memory: MemoryStore = Depends(get_memory),
) -> dict:
    """Send an email OTP during login (unauthenticated — user holds a challenge token)."""
    result = decode_challenge_token(body.challenge_token)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid or expired challenge token.")
    user_id, method = result
    if method != "email":
        raise HTTPException(status_code=400, detail="Challenge is not an email method.")
    user = memory.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    code, code_hash = totp_service.generate_otp_code()
    expires = datetime.now(timezone.utc) + timedelta(minutes=10)
    memory.create_email_otp(user.id, code_hash, expires, purpose="2fa_login")
    resend_service.send_otp_email(user.email, code, user.display_name)
    return {"message": "OTP sent to your email."}


# ── Verify (for login challenge) ──────────────────────────────────────

class VerifyBody(BaseModel):
    challenge_token: str
    code: str


@router.post("/verify")
def verify_two_factor(
    body: VerifyBody,
    request: Request,
    response: Response,
    memory: MemoryStore = Depends(get_memory),
) -> dict:
    """
    Complete the 2FA login flow.
    Accepts a challenge_token (from /auth/login) + the OTP/TOTP code.
    On success sets the auth cookie and returns the user profile.
    """
    result = decode_challenge_token(body.challenge_token)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid or expired challenge token.")
    user_id, method = result

    user = memory.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")

    verified = False

    if method == "totp" and user.totp_secret:
        verified = totp_service.verify_totp(user.totp_secret, body.code)
        # Try backup code if TOTP fails
        if not verified and user.totp_backup_codes:
            code_hash = totp_service.hash_backup_code(body.code)
            verified = memory.consume_backup_code(user.id, code_hash)

    elif method == "email":
        otp_row = memory.get_valid_email_otp(user_id, purpose="2fa_login")
        if otp_row and totp_service.verify_otp_code(body.code, otp_row.code_hash):
            memory.consume_email_otp(otp_row.id)
            verified = True

    if not verified:
        memory.log_action("2fa_failed", user_id=user_id,
                          ip_address=request.client.host if request.client else None)
        raise HTTPException(status_code=401, detail="Invalid verification code.")

    memory.log_action("login_2fa", user_id=user_id,
                      ip_address=request.client.host if request.client else None)
    token = create_token(user.id, user.token_version or 0)
    response.set_cookie(
        key=COOKIE_NAME, value=token, httponly=True,
        samesite="lax", path="/", max_age=_COOKIE_MAX_AGE, secure=False,
    )
    return {
        "id": user.id, "email": user.email,
        "display_name": user.display_name,
        "avatar_color": user.avatar_color,
        "subscription_tier": user.subscription_tier,
    }
