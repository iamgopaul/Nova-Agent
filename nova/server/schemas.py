from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ── Chat ─────────────────────────────────────────────────────────────

class AttachmentInput(BaseModel):
    name: str
    content_type: str = "application/octet-stream"
    data: str

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    mode: str = "default"       # "default" | "fast" | "code"
    model_key: Optional[str] = None
    attachments: list[AttachmentInput] = Field(default_factory=list)


class ChatChunk(BaseModel):
    type: str                   # "text" | "done" | "error"
    content: str = ""


# ── Memory — facts ────────────────────────────────────────────────────

class FactCreate(BaseModel):
    key: str = Field(..., min_length=1, max_length=256)
    value: str = Field(..., min_length=1)
    source: str = "user"


class FactResponse(BaseModel):
    key: str
    value: str
    source: str


# ── Memory — history ─────────────────────────────────────────────────

class MessageResponse(BaseModel):
    role: str
    content: str
    created_at: datetime


class SessionSummary(BaseModel):
    id: str
    title: str
    preview: str
    folder: str | None = None
    created_at: datetime
    last_message_at: datetime | None = None
    message_count: int = 0


class SessionUpdate(BaseModel):
    title: str | None = None
    folder: str | None = None


class FolderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


class FolderResponse(BaseModel):
    name: str
    created_at: datetime


# ── Auth ─────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=80)
    avatar_color: str = Field(default="#38bdf8", max_length=20)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str
    avatar_color: str
    has_password: bool
    created_at: datetime


class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    avatar_color: str | None = Field(default=None, max_length=20)


class SetPasswordRequest(BaseModel):
    """Set or change the account password.

    - ``current_password`` is required only when the account already has a
      password (i.e. ``has_password`` is True).  OAuth-only accounts may omit
      it when creating a password for the first time.
    - ``new_password`` must be at least 8 characters.
    """
    current_password: str | None = Field(default=None)
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)


# ── Web Watcher ──────────────────────────────────────────────────────

class WatchedTopicCreate(BaseModel):
    label: str = Field(..., min_length=1, max_length=200)
    query: str = Field(..., min_length=1, max_length=500)
    category: str = Field(default="custom", max_length=50)


class WatchedTopicToggle(BaseModel):
    enabled: bool


class WatchedTopicResponse(BaseModel):
    id: str
    label: str
    query: str
    category: str
    enabled: bool
    last_fetched_at: datetime | None = None
    last_result: str | None = None
    created_at: datetime


# ── Voice ────────────────────────────────────────────────────────────

class VoiceResponse(BaseModel):
    transcript: str
    response: str
    session_id: str
    face_name: str | None = None
    face_confidence: float | None = None
