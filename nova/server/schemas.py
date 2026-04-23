from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


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


# ── Voice ────────────────────────────────────────────────────────────

class VoiceResponse(BaseModel):
    transcript: str
    response: str
    session_id: str
    face_name: str | None = None
    face_confidence: float | None = None
