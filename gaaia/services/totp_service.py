from __future__ import annotations

import base64
import hashlib
import io
import json
import secrets

import pyotp


ISSUER = "GAAIA"
BACKUP_CODE_COUNT = 10


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def get_totp_uri(secret: str, email: str) -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER)


def get_qr_code_data_url(uri: str) -> str:
    """Return a base64 PNG data URL for the given OTP auth URI."""
    import qrcode
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


def verify_totp(secret: str, code: str) -> bool:
    totp = pyotp.TOTP(secret)
    # valid_window=1 accepts codes 30s before/after current window
    return totp.verify(code, valid_window=1)


def generate_backup_codes() -> tuple[list[str], list[str]]:
    """Return (plaintext_codes, hashed_codes). Store only hashed."""
    plain = [secrets.token_hex(4).upper() for _ in range(BACKUP_CODE_COUNT)]
    hashed = [hashlib.sha256(c.encode()).hexdigest() for c in plain]
    return plain, hashed


def verify_backup_code(plain_code: str, hashed_codes_json: str) -> bool:
    h = hashlib.sha256(plain_code.upper().encode()).hexdigest()
    codes: list[str] = json.loads(hashed_codes_json)
    return h in codes


def hash_backup_code(plain: str) -> str:
    return hashlib.sha256(plain.upper().encode()).hexdigest()


def generate_otp_code() -> tuple[str, str]:
    """Generate a 6-digit email OTP. Returns (plain_code, bcrypt_hash)."""
    from passlib.context import CryptContext
    code = f"{secrets.randbelow(1_000_000):06d}"
    ctx = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
    return code, ctx.hash(code)


def verify_otp_code(plain: str, hashed: str) -> bool:
    from passlib.context import CryptContext
    ctx = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
    try:
        return ctx.verify(plain, hashed)
    except Exception:
        return False
