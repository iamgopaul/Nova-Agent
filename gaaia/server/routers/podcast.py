"""
GAAIA Podcast — Two-host AI podcast on any topic.

  Host A: "GAAIA Cast"  — warm, curious, accessible; asks great questions; keeps it relatable
  Host B: "GAAIA Deep"  — analytical, thoughtful; digs deeper; surfaces non-obvious angles

Structure (8 turns):
  Intro       (2 turns)  — A introduces topic, B adds framing
  Discussion  (4 turns)  — alternating Q&A / insight exchange
  Outro       (2 turns)  — A wraps up, B delivers final thought

SSE protocol:
  {"type":"init",          "topic":str, "host_a":{model,identity,color}, "host_b":{model,identity,color}}
  {"type":"segment_start", "segment":"intro"|"discussion"|"outro", "label":str}
  {"type":"thinking",      "speaker":"host_a"|"host_b"}
  {"type":"turn_start",    "speaker":"host_a"|"host_b", "turn":int, "model":str, "identity":str}
  {"type":"token",         "speaker":"host_a"|"host_b", "text":str}
  {"type":"turn_end",      "speaker":"host_a"|"host_b", "turn":int}
  {"type":"done"}
"""
from __future__ import annotations

import asyncio
import threading
import json
import uuid
from typing import Any, AsyncGenerator

from gaaia.services.model_client import get_model_client
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from gaaia.memory.models import User
from gaaia.server.dependencies import get_current_user

router = APIRouter()
_podcasts: dict[str, dict[str, Any]] = {}

SEGMENT_LABELS = {
    "intro":      "Introduction",
    "discussion": "Discussion",
    "outro":      "Outro",
}

# 8-turn script: (speaker_key, segment, role_hint)
SCRIPT: list[tuple[str, str, str]] = [
    ("host_a", "intro",      "introduce"),
    ("host_b", "intro",      "react_and_frame"),
    ("host_a", "discussion", "ask_question"),
    ("host_b", "discussion", "answer_and_insight"),
    ("host_a", "discussion", "build_on"),
    ("host_b", "discussion", "deepen"),
    ("host_a", "outro",      "wrap_up"),
    ("host_b", "outro",      "final_thought"),
]


# ── Model selection ────────────────────────────────────────────────────────────

def _pick_hosts(settings) -> tuple[dict, dict]:
    from gaaia.services.model_router import vram_safe_model
    m = settings.model
    host = str(m.get("host") or "http://localhost:11434")
    host_a_model = (
        m.get("fast_model") or m.get("swift_model") or m.get("core_model") or "llama3.2:3b"
    )
    host_b_model = (
        m.get("core_model") or m.get("mind_model") or m.get("name") or "mistral:7b"
    )
    # Podcast hosts hold long multi-turn conversations — keep both small enough
    # to fit in VRAM so cohost replies don't take a minute each.
    _chain_a = ["llama3.2:3b", "gemma3:4b", "phi:2.7b", "mistral:7b"]
    _chain_b = ["mistral:7b", "qwen2.5:7b", "llama3.1:8b", "gemma3:4b", "llama3.2:3b"]
    host_a_model = vram_safe_model(host_a_model, _chain_a, host=host)
    host_b_model = vram_safe_model(host_b_model, _chain_b, host=host)
    host_a = {"model": host_a_model, "identity": "GAAIA Cast",  "color": "violet"}
    host_b = {"model": host_b_model, "identity": "GAAIA Deep",  "color": "purple"}
    return host_a, host_b


# ── Ollama streaming ───────────────────────────────────────────────────────────

async def _stream(
    host: str, model: str, messages: list[dict], options: dict
) -> AsyncGenerator[str, None]:
    loop = asyncio.get_event_loop()
    q: asyncio.Queue[str | None] = asyncio.Queue()

    def _run() -> None:
        client = get_model_client(host=host, timeout=180.0)
        try:
            for tok in client.chat_stream(model=model, messages=messages, options=options):
                loop.call_soon_threadsafe(q.put_nowait, tok)
        except Exception as exc:
            print(f"[Podcast] Backend error ({model}): {exc}", flush=True)
        finally:
            loop.call_soon_threadsafe(q.put_nowait, None)

    threading.Thread(target=_run, daemon=True).start()
    while True:
        tok = await q.get()
        if tok is None:
            break
        yield tok


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


# ── Prompts ────────────────────────────────────────────────────────────────────

_HOST_A_PERSONA = (
    "You are GAIA Cast, an enthusiastic and warm podcast host. "
    "You make complex ideas feel accessible. You ask sharp, interesting questions. "
    "Your tone is conversational and energetic. You love moments of discovery. "
    "Speak naturally, as if talking — not writing. No bullet points, no headers."
)

_HOST_B_PERSONA = (
    "You are GAIA Deep, a thoughtful and analytical podcast co-host. "
    "You provide depth, context, and non-obvious angles. "
    "You gently challenge assumptions and surface the 'so what' behind ideas. "
    "Your tone is calm, intellectually curious, and slightly philosophical. "
    "Speak naturally, as if talking — not writing. No bullet points, no headers."
)

_ROLE_INSTRUCTIONS: dict[str, str] = {
    "introduce": (
        "Open the episode. Welcome listeners and introduce the topic with energy. "
        "Hook them with a surprising fact, question, or angle. 3-4 sentences."
    ),
    "react_and_frame": (
        "React to GAAIA Cast's intro. Add an interesting framing or a different lens on the topic. "
        "Set up what the discussion will explore. 3-4 sentences."
    ),
    "ask_question": (
        "Ask GAAIA Deep a specific, thoughtful question about the topic. "
        "Make it something a curious listener would genuinely want answered. 2-3 sentences."
    ),
    "answer_and_insight": (
        "Answer GAAIA Cast's question with a clear, insightful response. "
        "End with a surprising angle or a thought that opens the next thread. 4-5 sentences."
    ),
    "build_on": (
        "Build on what GAAIA Deep just said. Share a perspective or example that extends the idea. "
        "Then probe deeper with a follow-up observation or question. 3-4 sentences."
    ),
    "deepen": (
        "Respond to GAAIA Cast. Deepen the analysis — push back gently or affirm with nuance. "
        "Arrive at the core insight of this topic. 4-5 sentences."
    ),
    "wrap_up": (
        "Bring the episode to a close. Summarize the key takeaway in plain terms. "
        "Thank the listener and hint at why this topic matters. 3-4 sentences."
    ),
    "final_thought": (
        "Give the final word. Offer one lasting thought, insight, or question for the listener to carry with them. "
        "Sign off warmly. 2-3 sentences."
    ),
}


def _build_messages(
    speaker_key: str,
    topic: str,
    role_hint: str,
    transcript: list[str],
    host_a: dict,
    host_b: dict,
) -> list[dict]:
    persona = _HOST_A_PERSONA if speaker_key == "host_a" else _HOST_B_PERSONA
    other_identity = host_b["identity"] if speaker_key == "host_a" else host_a["identity"]
    own_identity   = host_a["identity"] if speaker_key == "host_a" else host_b["identity"]

    system = (
        f"{persona}\n\n"
        f"You are co-hosting a podcast with {other_identity}. "
        f'The topic of today\'s episode: "{topic}".'
    )

    instruction = _ROLE_INSTRUCTIONS.get(role_hint, "Continue the conversation naturally. 3-4 sentences.")

    if transcript:
        history_block = "\n\n".join(transcript[-6:])  # last 6 turns for context window efficiency
        user = (
            f'Topic: "{topic}"\n\n'
            f"Conversation so far:\n{history_block}\n\n"
            f"Your turn, {own_identity}: {instruction}"
        )
    else:
        user = f'Topic: "{topic}"\n\n{own_identity}: {instruction}'

    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


# ── Endpoints ──────────────────────────────────────────────────────────────────

class StartPodcastBody(BaseModel):
    topic: str = Field(..., min_length=3, max_length=500)


@router.post("/start")
async def start_podcast(
    body: StartPodcastBody,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict:
    settings  = request.app.state.settings
    host_a, host_b = _pick_hosts(settings)
    host      = str(settings.model.get("host") or "http://localhost:11434")

    podcast_id = str(uuid.uuid4())
    _podcasts[podcast_id] = {
        "topic":  body.topic.strip(),
        "host_a": host_a,
        "host_b": host_b,
        "host":   host,
    }
    return {
        "podcast_id": podcast_id,
        "topic":      body.topic.strip(),
        "host_a":     host_a,
        "host_b":     host_b,
    }


@router.get("/{podcast_id}/stream")
async def stream_podcast(
    podcast_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    if podcast_id not in _podcasts:
        raise HTTPException(status_code=404, detail="Podcast session not found.")

    cfg = _podcasts.pop(podcast_id)

    async def generate():
        topic  = cfg["topic"]
        host_a = cfg["host_a"]
        host_b = cfg["host_b"]
        host   = cfg["host"]

        SPEAK_OPT = {"temperature": 0.78, "num_predict": 380}

        yield _sse({"type": "init", "topic": topic, "host_a": host_a, "host_b": host_b})

        transcript: list[str] = []
        current_segment = ""

        for turn_idx, (speaker_key, segment, role_hint) in enumerate(SCRIPT):
            # Emit segment boundary when segment changes
            if segment != current_segment:
                current_segment = segment
                yield _sse({
                    "type": "segment_start",
                    "segment": segment,
                    "label": SEGMENT_LABELS[segment],
                })
                await asyncio.sleep(0.3)

            host_info = host_a if speaker_key == "host_a" else host_b
            model     = host_info["model"]
            identity  = host_info["identity"]

            yield _sse({"type": "thinking", "speaker": speaker_key})
            await asyncio.sleep(0.4)

            yield _sse({
                "type":     "turn_start",
                "speaker":  speaker_key,
                "turn":     turn_idx,
                "model":    model,
                "identity": identity,
            })

            messages = _build_messages(
                speaker_key, topic, role_hint, transcript, host_a, host_b
            )

            parts: list[str] = []
            async for tok in _stream(host, model, messages, SPEAK_OPT):
                parts.append(tok)
                yield _sse({"type": "token", "speaker": speaker_key, "text": tok})

            full_text = "".join(parts).strip()
            transcript.append(f"{identity}: {full_text}")

            yield _sse({"type": "turn_end", "speaker": speaker_key, "turn": turn_idx})
            await asyncio.sleep(0.5)

        yield _sse({"type": "done"})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "Connection":       "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
