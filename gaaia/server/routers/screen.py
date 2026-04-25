"""
GAAIA Screen — take a screenshot or read clipboard, then stream analysis.

POST /screen/capture   { "question": "..." }  → SSE tokens (vision LLM)
POST /screen/clipboard { "question": "..." }  → SSE tokens (text LLM)
"""
from __future__ import annotations

import asyncio
import base64
import json
import subprocess
import tempfile
import threading
from pathlib import Path

import ollama
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from gaaia.memory.models import User
from gaaia.server.dependencies import get_current_user

router = APIRouter()


class ScreenRequest(BaseModel):
    question: str = ""


class ClipboardRequest(BaseModel):
    question: str = ""


# ── OS helpers ────────────────────────────────────────────────────────────────

def _take_screenshot() -> bytes | None:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        path = f.name
    result = subprocess.run(["screencapture", "-x", path], capture_output=True)
    if result.returncode != 0:
        return None
    try:
        data = Path(path).read_bytes()
        Path(path).unlink(missing_ok=True)
        return data
    except Exception:
        return None


def _read_clipboard() -> str:
    result = subprocess.run(["pbpaste"], capture_output=True, text=True)
    return result.stdout.strip()


# ── Streaming helpers ─────────────────────────────────────────────────────────

async def _stream_vision(host: str, model: str, question: str, image_b64: str):
    prompt = question.strip() or "Describe this screen in detail. What is the user looking at? What are the key elements, text, and actions visible?"
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    def _run():
        try:
            client = ollama.Client(host=host, timeout=120)
            for chunk in client.chat(
                model=model,
                messages=[{"role": "user", "content": prompt, "images": [image_b64]}],
                stream=True,
            ):
                token = chunk.get("message", {}).get("content", "")
                if token:
                    loop.call_soon_threadsafe(queue.put_nowait, token)
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, f"\n\n*Error: {exc}*")
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=_run, daemon=True).start()
    while True:
        token = await queue.get()
        if token is None:
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            break
        yield f"data: {json.dumps({'type': 'token', 'text': token})}\n\n"


async def _stream_text(host: str, model: str, system: str, user_msg: str):
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    def _run():
        try:
            client = ollama.Client(host=host, timeout=120)
            for chunk in client.chat(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
                stream=True,
            ):
                token = chunk.get("message", {}).get("content", "")
                if token:
                    loop.call_soon_threadsafe(queue.put_nowait, token)
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, f"\n\n*Error: {exc}*")
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=_run, daemon=True).start()
    while True:
        token = await queue.get()
        if token is None:
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            break
        yield f"data: {json.dumps({'type': 'token', 'text': token})}\n\n"


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/capture")
async def capture_screen(
    body: ScreenRequest,
    request: Request,
    _user: User = Depends(get_current_user),
):
    settings = request.app.state.settings
    host = str(settings.model.get("host", "http://localhost:11434"))
    vision_model = (
        settings._effective_model_overrides.get("vision_model")
        or settings.model.get("vision_model")
        or "llama3.2-vision:11b"
    )

    image_bytes = await asyncio.to_thread(_take_screenshot)
    if not image_bytes:
        async def _err():
            yield f"data: {json.dumps({'type': 'token', 'text': 'Screenshot failed — check screen recording permissions in System Settings > Privacy.'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return StreamingResponse(_err(), media_type="text/event-stream")

    image_b64 = base64.b64encode(image_bytes).decode()
    return StreamingResponse(
        _stream_vision(host, vision_model, body.question, image_b64),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.post("/clipboard")
async def analyze_clipboard(
    body: ClipboardRequest,
    request: Request,
    _user: User = Depends(get_current_user),
):
    settings = request.app.state.settings
    host = str(settings.model.get("host", "http://localhost:11434"))
    model = (
        settings._effective_model_overrides.get("core_model")
        or settings.model.get("core_model")
        or "mistral:7b"
    )

    text = await asyncio.to_thread(_read_clipboard)
    if not text:
        async def _err():
            yield f"data: {json.dumps({'type': 'token', 'text': 'Clipboard is empty.'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return StreamingResponse(_err(), media_type="text/event-stream")

    system = (
        "You are GAAIA — sharp, direct, and helpful. "
        "The user has copied something to their clipboard and wants you to explain, summarize, or answer a question about it. "
        "Be concise unless asked to elaborate. Respond in plain conversational language."
    )
    user_msg = f"Clipboard content:\n\n{text[:8000]}"
    if body.question.strip():
        user_msg += f"\n\nQuestion: {body.question.strip()}"
    else:
        user_msg += "\n\nExplain or summarize this briefly."

    return StreamingResponse(
        _stream_text(host, model, system, user_msg),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
