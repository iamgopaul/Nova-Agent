"""GAAIA security utilities.

Provides:
  - IP-based rate limiting (sliding-window, in-memory, thread-safe)
  - Per-account login throttling with progressive lockout
  - Password strength validation
  - SecurityHeadersMiddleware for FastAPI
  - Helper to extract the real client IP
"""
from __future__ import annotations

import re
import threading
import time
from collections import defaultdict, deque
from typing import NamedTuple

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


# ── Rate limiter (sliding window) ────────────────────────────────────────────

class RateLimiter:
    """Thread-safe sliding-window rate limiter.

    ``is_allowed(key)`` records the call and returns True if under the limit.
    ``reset(key)`` clears the history for a key (e.g. on successful login).
    """

    def __init__(self, max_calls: int, window_seconds: int) -> None:
        self._max = max_calls
        self._window = window_seconds
        self._lock = threading.Lock()
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            q = self._buckets[key]
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= self._max:
                return False
            q.append(now)
            return True

    def reset(self, key: str) -> None:
        with self._lock:
            self._buckets.pop(key, None)

    def peek_remaining(self, key: str) -> int:
        """How many more calls are allowed in this window (without recording one)."""
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            q = self._buckets[key]
            count = sum(1 for t in q if t >= cutoff)
            return max(0, self._max - count)


# Shared singletons — applied per IP unless noted
login_rate    = RateLimiter(max_calls=10, window_seconds=60)    # 10 attempts / 60 s
register_rate = RateLimiter(max_calls=5,  window_seconds=300)   # 5 registrations / 5 min
password_rate = RateLimiter(max_calls=8,  window_seconds=300)   # 8 password changes / 5 min (per user)


# ── Progressive account lockout ───────────────────────────────────────────────

class _LockoutEntry(NamedTuple):
    failures: int
    locked_until: float  # monotonic timestamp; 0.0 means not locked


# (failures_threshold, lockout_seconds)
_LOCKOUT_SCHEDULE: list[tuple[int, int]] = [
    (5,  60),     # 5 failures   →  1 min
    (10, 300),    # 10 failures  →  5 min
    (15, 1800),   # 15 failures  → 30 min
    (20, 7200),   # 20 failures  →  2 hr
    (25, 86400),  # 25 failures  → 24 hr
]


class LoginThrottler:
    """Per-account progressive lockout.  Thread-safe, in-memory."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, _LockoutEntry] = {}

    def is_locked(self, key: str) -> tuple[bool, int]:
        """Return ``(locked, seconds_remaining)``."""
        now = time.monotonic()
        with self._lock:
            entry = self._data.get(key)
            if not entry:
                return False, 0
            if entry.locked_until and now < entry.locked_until:
                return True, int(entry.locked_until - now)
            return False, 0

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            entry = self._data.get(key)
            failures = (entry.failures if entry else 0) + 1
            lockout_secs = 0
            for threshold, duration in _LOCKOUT_SCHEDULE:
                if failures >= threshold:
                    lockout_secs = duration
            locked_until = now + lockout_secs if lockout_secs else 0.0
            self._data[key] = _LockoutEntry(failures=failures, locked_until=locked_until)

    def record_success(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def failure_count(self, key: str) -> int:
        with self._lock:
            entry = self._data.get(key)
            return entry.failures if entry else 0


login_throttler = LoginThrottler()


# ── Password strength ─────────────────────────────────────────────────────────

_COMMON_PASSWORDS = {
    "password", "password1", "password2", "password123", "Password1",
    "12345678", "123456789", "1234567890", "qwerty123", "qwertyui",
    "iloveyou", "admin123", "welcome1", "letmein1", "monkey123",
    "dragon123", "master123", "abc12345", "passw0rd", "pass1234",
    "sunshine", "princess", "football", "baseball", "superman",
    "batman123", "shadow123", "michael1", "jessica1", "charlie1",
}

_SEQUENCES = ["abcdefgh", "qwertyui", "12345678", "87654321", "zxcvbnm"]


def check_password_strength(password: str) -> tuple[bool, list[str]]:
    """Return ``(ok, issues)``.  ``ok=True`` means strong enough to accept."""
    issues: list[str] = []

    if len(password) < 8:
        issues.append("Must be at least 8 characters.")
    if not re.search(r"[A-Z]", password):
        issues.append("Add at least one uppercase letter (A–Z).")
    if not re.search(r"[a-z]", password):
        issues.append("Add at least one lowercase letter (a–z).")
    if not re.search(r"\d", password):
        issues.append("Add at least one number (0–9).")
    if not re.search(r"[^A-Za-z0-9]", password):
        issues.append("Add at least one special character (!, @, #, $ …).")
    if password.lower() in _COMMON_PASSWORDS:
        issues.append("This password is too common. Choose something unique.")
    for seq in _SEQUENCES:
        if seq in password.lower():
            issues.append("Avoid keyboard sequences like 'qwerty' or '12345'.")
            break

    return len(issues) == 0, issues


def password_strength_score(password: str) -> int:
    """Return a 0–4 score: 0=very weak, 4=strong.  Used by the API response."""
    score = 0
    if len(password) >= 8:
        score += 1
    if len(password) >= 12:
        score += 1
    checks = [
        bool(re.search(r"[A-Z]", password)),
        bool(re.search(r"[a-z]", password)),
        bool(re.search(r"\d", password)),
        bool(re.search(r"[^A-Za-z0-9]", password)),
    ]
    score += sum(checks) // 2
    if password.lower() in _COMMON_PASSWORDS:
        score = max(0, score - 2)
    return min(4, score)


# ── Security headers middleware ───────────────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject security headers into every response."""

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        response = await call_next(request)
        # Prevent browsers from MIME-sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Disallow embedding in iframes (clickjacking protection)
        response.headers["X-Frame-Options"] = "DENY"
        # Legacy XSS filter (belt-and-suspenders for older browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Limit referrer information leakage
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Restrict Permissions for camera/mic (only the app itself should request them)
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(self), camera=(self), payment=()"
        )
        # Basic content security — allow same-origin + the specific local hosts used
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "connect-src 'self' http://127.0.0.1:8765 http://localhost:8765; "
            "img-src 'self' data: blob: https:; "
            "media-src 'self' blob:; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "font-src 'self' data:; "
            "frame-ancestors 'none';"
        )
        return response


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_client_ip(request: Request) -> str:
    """Best-effort real client IP extraction."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def require_rate_limit(
    limiter: RateLimiter,
    key: str,
    detail: str = "Too many requests. Please slow down and try again.",
) -> None:
    """Raise HTTP 429 if the key has exceeded the rate limit."""
    if not limiter.is_allowed(key):
        raise HTTPException(status_code=429, detail=detail)
