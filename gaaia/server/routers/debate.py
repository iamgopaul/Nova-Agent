"""
GAAIA Debate — 4-model battle royale with elimination rounds.

Round 1 (Opening):   All 4 speak → judge scores → 1 eliminated  (3 remain)
Round 2 (Rebuttal):  3 speak     → judge scores → 1 eliminated  (2 remain)
Round 3 (Final):     2 speak     → judge declares winner + full report

SSE protocol:
  {"type":"init",        "topic":str, "contestants":[...], "judge":{...}}
  {"type":"round_start", "round":int, "label":str, "active":[ids]}
  {"type":"thinking",    "contestant_id":str}
  {"type":"turn_start",  "contestant_id":str, "round":int, "model":str, "identity":str}
  {"type":"token",       "contestant_id":str, "text":str}
  {"type":"turn_end",    "contestant_id":str, "round":int}
  {"type":"judging",     "round":int}
  {"type":"scores",      "round":int, "scores":{id:int,...}}
  {"type":"elimination", "round":int, "eliminated_id":str, "identity":str,
                         "reason":str, "survivors":[ids]}
  {"type":"verdict_start"}
  {"type":"verdict_token","text":str}
  {"type":"report",      "winner_id":str, "winner_identity":str, "winner_model":str,
                         "winner_color":str, "reasoning":str, "best_argument":str,
                         "synthesis":str, "round_scores":{round:{id:score}},
                         "elimination_log":[{round,eliminated_id,identity,model,reason,score}],
                         "topic":str}
  {"type":"done"}
"""
from __future__ import annotations

import asyncio
import json
import re
import threading
import uuid
from typing import Any, AsyncGenerator

import ollama
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from gaaia.memory.models import User
from gaaia.server.dependencies import get_current_user

router = APIRouter()
_debates: dict[str, dict[str, Any]] = {}

ROUND_LABELS = {1: "Opening Statements", 2: "Rebuttals", 3: "Final Showdown"}


# ── Contestant & judge selection ──────────────────────────────────────────────

def _pick_contestants(settings) -> tuple[list[dict], dict]:
    """Return 4 contestants across light→heavy tiers + a judge model."""
    m = settings.model

    slots = [
        ("alpha", ["fast_model",  "swift_model", "core_model"],              "GAIA Spark", "blue"),
        ("beta",  ["swift_model", "fast_model",  "core_model"],              "GAIA Air",   "violet"),
        ("gamma", ["core_model",  "mind_model",  "name"],                    "GAIA Core",  "amber"),
        ("delta", ["heavy_model", "name",        "core_model", "mind_model"],"GAIA Pro",   "rose"),
    ]
    contestants: list[dict] = []
    for cid, fallbacks, identity, color in slots:
        model = next((m.get(k) for k in fallbacks if m.get(k)), None) or "llama3.2:3b"
        contestants.append({"id": cid, "model": model, "identity": identity, "color": color})

    judge_model = (
        m.get("heavy_model") or m.get("name") or m.get("insight_model")
        or m.get("core_model") or "mistral:7b"
    )
    judge = {"model": judge_model, "identity": "GAIA Judge"}
    return contestants, judge


# ── Ollama streaming ──────────────────────────────────────────────────────────

async def _stream(host: str, model: str, messages: list[dict], options: dict) -> AsyncGenerator[str, None]:
    """Async generator yielding tokens from Ollama via a thread→queue bridge."""
    loop = asyncio.get_event_loop()
    q: asyncio.Queue[str | None] = asyncio.Queue()

    def _run() -> None:
        client = ollama.Client(host=host, timeout=180)
        try:
            for chunk in client.chat(model=model, messages=messages, stream=True, options=options):
                tok = (chunk.get("message") or {}).get("content") or ""
                if tok:
                    loop.call_soon_threadsafe(q.put_nowait, tok)
        except Exception as exc:
            print(f"[Debate] Ollama error ({model}): {exc}", flush=True)
        finally:
            loop.call_soon_threadsafe(q.put_nowait, None)

    threading.Thread(target=_run, daemon=True).start()
    while True:
        tok = await q.get()
        if tok is None:
            break
        yield tok


async def _complete(host: str, model: str, messages: list[dict], options: dict) -> str:
    return "".join([t async for t in _stream(host, model, messages, options)])


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


def _parse_json(raw: str) -> dict:
    try:
        m = re.search(r"\{[\s\S]*?\}", raw, re.DOTALL)
        if not m:
            m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            return json.loads(m.group())
    except Exception:
        pass
    return {}


# ── Prompts ───────────────────────────────────────────────────────────────────

def _contestant_prompt(identity: str, topic: str, round_num: int,
                       transcript: str, others: list[str]) -> tuple[str, str]:
    others_str = ", ".join(others)
    brevity = "3–4 punchy sentences. No bullet points. First person. Speak as a competitor."

    if round_num == 1:
        sys = (
            f"You are {identity}, competing in a 4-way AI debate battle royal against {others_str}. "
            f'Topic: "{topic}". '
            f"Deliver your opening statement. Be bold, specific, and memorable. {brevity}"
        )
        usr = f'Topic: "{topic}"\n\nDeliver your opening statement. Stand out from the others.'

    elif round_num == 2:
        sys = (
            f"You are {identity}, having survived round 1. "
            f'Topic: "{topic}". '
            f"Attack the weakest argument you see in the transcript. Counter it directly. {brevity}"
        )
        usr = f'Topic: "{topic}"\n\nTranscript so far:\n{transcript}\n\nDeliver your rebuttal.'

    else:
        sys = (
            f"You are {identity}, in the final round. "
            f'Topic: "{topic}". '
            f"This is your last chance to win. Give the most persuasive closing argument possible. {brevity}"
        )
        usr = f'Topic: "{topic}"\n\nFull debate:\n{transcript}\n\nDeliver your final argument.'

    return sys, usr


def _judge_score_prompt(topic: str, active_ids: list[str], transcript: str) -> tuple[str, str]:
    ids_literal = ", ".join(f'"{i}"' for i in active_ids)
    placeholder_scores = ", ".join(f'"{i}": 0' for i in active_ids)
    sys = (
        "You are an impartial debate judge. Score each debater's LATEST round argument 1–10 "
        "(logic + evidence + persuasion). The lowest score is eliminated. "
        "Respond ONLY with valid JSON — no other text:\n"
        f'{{"scores": {{{placeholder_scores}}}, "eliminated_id": "{active_ids[0]}", '
        '"reason": "one sentence why they were weakest"}}\n'
        f"eliminated_id MUST be one of: {ids_literal}"
    )
    usr = (
        f'Topic: "{topic}"\n\nFull transcript:\n{transcript}\n\n'
        "Score each debater and eliminate the weakest. JSON only."
    )
    return sys, usr


def _judge_final_prompt(topic: str, active_ids: list[str], transcript: str) -> tuple[str, str]:
    ids_literal = ", ".join(f'"{i}"' for i in active_ids)
    sys = (
        "You are an expert debate judge. The battle is over. Deliver the final verdict. "
        "Respond ONLY with valid JSON — no other text:\n"
        '{"winner_id": "...", '
        '"reasoning": "2-3 sentences on why they won", '
        '"best_argument": "quote their single strongest sentence verbatim", '
        '"synthesis": "5-7 sentences: the definitive best answer to the topic, drawing from all arguments"}\n'
        f"winner_id MUST be one of: {ids_literal}"
    )
    usr = (
        f'Topic: "{topic}"\n\nFull debate transcript:\n{transcript}\n\n'
        "Declare the winner and deliver your full report as JSON."
    )
    return sys, usr


# ── Endpoints ─────────────────────────────────────────────────────────────────

class StartDebateBody(BaseModel):
    topic: str = Field(..., min_length=3, max_length=1000)


@router.post("/start")
async def start_debate(
    body: StartDebateBody,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict:
    settings = request.app.state.settings
    contestants, judge = _pick_contestants(settings)
    host = str(settings.model.get("host") or "http://localhost:11434")

    debate_id = str(uuid.uuid4())
    _debates[debate_id] = {
        "topic": body.topic.strip(),
        "contestants": contestants,
        "judge": judge,
        "host": host,
    }
    return {
        "debate_id": debate_id,
        "topic": body.topic.strip(),
        "contestants": contestants,
        "judge": judge,
    }


@router.get("/{debate_id}/stream")
async def stream_debate(
    debate_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    if debate_id not in _debates:
        raise HTTPException(status_code=404, detail="Debate not found.")

    cfg = _debates.pop(debate_id)

    async def generate():
        topic       = cfg["topic"]
        contestants = cfg["contestants"]
        judge       = cfg["judge"]
        host        = cfg["host"]

        by_id      = {c["id"]: c for c in contestants}
        active_ids = [c["id"] for c in contestants]

        SPEAK_OPT = {"temperature": 0.76, "num_predict": 420}
        JUDGE_OPT = {"temperature": 0.20, "num_predict": 700}

        yield _sse({"type": "init", "topic": topic,
                    "contestants": contestants, "judge": judge})

        history: list[str] = []
        round_scores: dict[str, dict] = {}
        elimination_log: list[dict] = []

        for round_num in range(1, 4):
            yield _sse({
                "type": "round_start", "round": round_num,
                "label": ROUND_LABELS[round_num], "active": list(active_ids),
            })

            # ── Each active contestant speaks ─────────────────────────────────
            for cid in list(active_ids):
                c = by_id[cid]
                others = [by_id[oid]["identity"] for oid in active_ids if oid != cid]
                sys_p, usr_p = _contestant_prompt(
                    c["identity"], topic, round_num, "\n\n".join(history), others
                )

                yield _sse({"type": "thinking", "contestant_id": cid})
                await asyncio.sleep(0.35)
                yield _sse({
                    "type": "turn_start", "contestant_id": cid,
                    "round": round_num, "model": c["model"], "identity": c["identity"],
                })

                parts: list[str] = []
                async for tok in _stream(
                    host, c["model"],
                    [{"role": "system", "content": sys_p}, {"role": "user", "content": usr_p}],
                    SPEAK_OPT,
                ):
                    parts.append(tok)
                    yield _sse({"type": "token", "contestant_id": cid, "text": tok})

                full = "".join(parts)
                history.append(f"[Round {round_num}] {c['identity']}: {full}")
                yield _sse({"type": "turn_end", "contestant_id": cid, "round": round_num})
                await asyncio.sleep(0.45)

            # ── Judge phase ───────────────────────────────────────────────────
            yield _sse({"type": "judging", "round": round_num})
            await asyncio.sleep(0.5)
            transcript = "\n\n".join(history)

            if round_num < 3:
                sys_p, usr_p = _judge_score_prompt(topic, list(active_ids), transcript)
                raw = await _complete(host, judge["model"],
                    [{"role": "system", "content": sys_p}, {"role": "user", "content": usr_p}],
                    JUDGE_OPT)
                result = _parse_json(raw)

                scores    = result.get("scores", {i: 5 for i in active_ids})
                elim_id   = result.get("eliminated_id", "")
                reason    = result.get("reason", "Weakest argument this round.")

                # Fallback: pick lowest score if judge output is invalid
                if elim_id not in active_ids:
                    elim_id = min(active_ids, key=lambda i: scores.get(i, 0))

                round_scores[str(round_num)] = {k: int(v) for k, v in scores.items() if k in active_ids}
                yield _sse({"type": "scores", "round": round_num, "scores": round_scores[str(round_num)]})
                await asyncio.sleep(0.4)

                elim_c = by_id[elim_id]
                elimination_log.append({
                    "round": round_num,
                    "eliminated_id": elim_id,
                    "identity": elim_c["identity"],
                    "model": elim_c["model"],
                    "reason": reason,
                    "score": int(scores.get(elim_id, 0)),
                })
                active_ids.remove(elim_id)
                yield _sse({
                    "type": "elimination", "round": round_num,
                    "eliminated_id": elim_id, "identity": elim_c["identity"],
                    "reason": reason, "survivors": list(active_ids),
                })
                await asyncio.sleep(0.9)

            else:
                # Final — stream judge thinking, then emit full report
                sys_p, usr_p = _judge_final_prompt(topic, list(active_ids), transcript)
                yield _sse({"type": "verdict_start"})

                verdict_parts: list[str] = []
                async for tok in _stream(
                    host, judge["model"],
                    [{"role": "system", "content": sys_p}, {"role": "user", "content": usr_p}],
                    {"temperature": 0.20, "num_predict": 900},
                ):
                    verdict_parts.append(tok)
                    yield _sse({"type": "verdict_token", "text": tok})

                verdict_raw = "".join(verdict_parts)
                result      = _parse_json(verdict_raw)

                winner_id = result.get("winner_id", active_ids[0])
                if winner_id not in active_ids:
                    winner_id = active_ids[0]

                winner = by_id[winner_id]
                final_scores = result.get("scores", {i: (9 if i == winner_id else 7) for i in active_ids})
                round_scores["3"] = {k: int(v) for k, v in final_scores.items() if k in active_ids}

                yield _sse({
                    "type": "report",
                    "winner_id":       winner_id,
                    "winner_identity": winner["identity"],
                    "winner_model":    winner["model"],
                    "winner_color":    winner["color"],
                    "reasoning":       result.get("reasoning", "Won on the strength of their arguments."),
                    "best_argument":   result.get("best_argument", ""),
                    "synthesis":       result.get("synthesis", ""),
                    "round_scores":    round_scores,
                    "elimination_log": elimination_log,
                    "topic":           topic,
                })

        yield _sse({"type": "done"})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
