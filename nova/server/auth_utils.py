from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jose import JWTError, jwt
from passlib.context import CryptContext
from passlib.exc import UnknownHashError

_pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")

COOKIE_NAME = "nova_token"
TOKEN_EXPIRE_DAYS = 30
ALGORITHM = "HS256"

_secret: str | None = None


def _get_secret() -> str:
    global _secret
    if _secret:
        return _secret

    # Prefer explicit env var; fall back to a persisted random key
    env_key = os.environ.get("NOVA_JWT_SECRET", "").strip()
    if env_key:
        _secret = env_key
        return _secret

    key_file = Path(os.path.expanduser("~/Nova/.jwt_secret"))
    key_file.parent.mkdir(parents=True, exist_ok=True)
    if key_file.exists():
        _secret = key_file.read_text().strip()
    else:
        _secret = secrets.token_hex(32)
        key_file.write_text(_secret)
        key_file.chmod(0o600)

    return _secret


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return _pwd_context.verify(plain, hashed)
    except (UnknownHashError, ValueError, TypeError):
        return False


def create_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": user_id, "exp": expire},
        _get_secret(),
        algorithm=ALGORITHM,
    )


def decode_token(token: str) -> str | None:
    """Return user_id from a valid token, or None if invalid/expired."""
    try:
        payload = jwt.decode(token, _get_secret(), algorithms=[ALGORITHM])
        user_id: str | None = payload.get("sub")
        return user_id
    except JWTError:
        return None
