"""
GAAIA Video — analyze video content (YouTube, URL, or local file) via Ollama vision.

POST /video/analyze
  Body: { "video_source": "...", "frame_count": 5, "focus": "all", "question": "" }
  Response: SSE stream  {"type":"token","text":"..."} ... {"type":"done"}
  Or error: {"type":"error","text":"..."}
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import tempfile
import threading
from typing import AsyncGenerator

import ollama
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from gaaia.memory.models import User
from gaaia.server.dependencies import get_current_user

router = APIRouter()


class VideoRequest(BaseModel):
    video_source: str = Field(..., min_length=1)
    frame_count: int = Field(default=5, ge=1, le=20)
    focus: str = Field(default="all")
    question: str = ""


# ── Video / frame helpers ─────────────────────────────────────────────────────

def _download_youtube(url: str) -> str | None:
    try:
        import yt_dlp
        temp_dir = tempfile.gettempdir()
        output_path = os.path.join(temp_dir, "gaaia_video_%(id)s.mp4")
        opts = {"format": "best[height<=480]", "quiet": True, "outtmpl": output_path, "socket_timeout": 30}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = ydl.prepare_filename(info)
            return path if os.path.isfile(path) else None
    except Exception:
        return None


def _download_video(url: str) -> str | None:
    try:
        import requests as _req
        resp = _req.get(url, timeout=30, stream=True)
        if resp.status_code != 200:
            return None
        ext = next((e for e in [".mp4", ".webm", ".mov", ".avi"] if e in url.lower()), ".mp4")
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
            for chunk in resp.iter_content(8192):
                if chunk:
                    f.write(chunk)
            return f.name if os.path.getsize(f.name) > 0 else None
    except Exception:
        return None


def _get_video_file(source: str) -> str | None:
    if os.path.isfile(source):
        return source
    if "youtube.com" in source or "youtu.be" in source:
        return _download_youtube(source)
    if source.startswith(("http://", "https://")):
        return _download_video(source)
    return None


def _extract_frames(video_path: str, count: int) -> list[str]:
    try:
        dur_result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=10,
        )
        try:
            duration = float(dur_result.stdout.strip())
        except (ValueError, AttributeError):
            duration = 30.0

        interval = duration / (count + 1) if duration > 0 else 5.0
        timestamps = [interval * (i + 1) for i in range(count)]

        frames: list[str] = []
        tmp = tempfile.gettempdir()
        for i, ts in enumerate(timestamps):
            frame_path = os.path.join(tmp, f"gaaia_frame_{i}.jpg")
            subprocess.run(
                ["ffmpeg", "-ss", str(ts), "-i", video_path,
                 "-vf", "scale=640:360", "-vframes", "1", "-q:v", "2", "-y", frame_path],
                capture_output=True, timeout=10,
            )
            if os.path.isfile(frame_path):
                frames.append(base64.b64encode(open(frame_path, "rb").read()).decode())
                try:
                    os.remove(frame_path)
                except Exception:
                    pass
        return frames
    except Exception:
        return []


# ── SSE stream ────────────────────────────────────────────────────────────────

async def _stream_analysis(
    host: str, model: str, frames: list[str], focus: str, question: str
) -> AsyncGenerator[str, None]:
    focus_prompts = {
        "general": "Describe what you see in these video frames. Summarise the scenes, actions, and overall context.",
        "text": "Carefully read and extract all visible text, captions, titles, and labels from these frames.",
        "objects": "Identify and describe all visible objects, people, logos, and entities in these frames.",
        "all": (
            "Provide a comprehensive analysis: "
            "1) Scene descriptions and narrative; "
            "2) All visible text and captions; "
            "3) Key objects, people, and entities; "
            "4) Overall content summary."
        ),
    }
    base_prompt = focus_prompts.get(focus, focus_prompts["all"])
    prompt = f"{base_prompt}\n\nAdditional question: {question.strip()}" if question.strip() else base_prompt

    loop = asyncio.get_event_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    def _run():
        try:
            client = ollama.Client(host=host, timeout=180)
            for chunk in client.chat(
                model=model,
                messages=[{"role": "user", "content": prompt, "images": frames}],
                stream=True,
            ):
                token = chunk.get("message", {}).get("content", "")
                if token:
                    loop.call_soon_threadsafe(queue.put_nowait, token)
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, f"\n\n*Vision analysis error: {exc}*")
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=_run, daemon=True).start()
    while True:
        token = await queue.get()
        if token is None:
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            break
        yield f"data: {json.dumps({'type': 'token', 'text': token})}\n\n"


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post("/analyze")
async def analyze_video(
    body: VideoRequest,
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

    async def _run_pipeline():
        yield f"data: {json.dumps({'type': 'status', 'text': 'Fetching video…'})}\n\n"

        video_path = await asyncio.to_thread(_get_video_file, body.video_source)
        if not video_path:
            yield f"data: {json.dumps({'type': 'error', 'text': 'Could not access video. Check the URL or file path.'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'status', 'text': f'Extracting {body.frame_count} frames…'})}\n\n"
        frames = await asyncio.to_thread(_extract_frames, video_path, body.frame_count)

        # clean up downloaded temp file
        if body.video_source.startswith(("http://", "https://")) or "youtube" in body.video_source:
            try:
                os.remove(video_path)
            except Exception:
                pass

        if not frames:
            yield f"data: {json.dumps({'type': 'error', 'text': 'Frame extraction failed. Make sure ffmpeg is installed (brew install ffmpeg).'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'status', 'text': f'Analysing {len(frames)} frames with {vision_model}…'})}\n\n"
        async for chunk in _stream_analysis(host, vision_model, frames, body.focus, body.question):
            yield chunk

    return StreamingResponse(
        _run_pipeline(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
