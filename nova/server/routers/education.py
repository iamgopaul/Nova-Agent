"""
Nova Education — generate quizzes/exams and grade submissions via local Ollama.

No chat memory writes; each call is stateless aside from auth.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from typing import Any, Literal

import ollama
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from nova.memory.models import User
from nova.server.dependencies import get_current_user

router = APIRouter()


def _extract_json_object(raw: str) -> dict[str, Any]:
    t = (raw or "").strip()
    if "```" in t:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", t, re.IGNORECASE)
        if m:
            t = m.group(1).strip()
    try:
        obj = json.loads(t)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502,
            detail="Model returned invalid JSON. Try again with fewer questions or a narrower topic.",
        ) from exc
    if not isinstance(obj, dict):
        raise HTTPException(status_code=502, detail="Model JSON was not an object.")
    return obj


def _ollama_chat_sync(host: str, model: str, system: str, user: str, num_predict: int = 4096) -> str:
    client = ollama.Client(host=host)
    resp = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        options={"temperature": 0.35, "num_predict": num_predict},
    )
    msg = resp.get("message") or {}
    return str(msg.get("content") or "").strip()


class GenerateQuizBody(BaseModel):
    topic: str = Field(..., min_length=2, max_length=500)
    mode: Literal["quiz", "exam"] = "quiz"
    difficulty: Literal["elementary", "middle", "high", "college"] = "high"
    num_questions: int = Field(default=5, ge=3, le=15)
    focus: str | None = Field(default=None, max_length=800)


class GradeSubmissionBody(BaseModel):
    """Full quiz payload from /generate plus user answers (question id -> answer text or 0-based option index)."""

    quiz: dict[str, Any]
    answers: dict[str, str] = Field(default_factory=dict)


@router.post("/generate")
async def generate_quiz(
    request: Request,
    body: GenerateQuizBody,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Produce a short lesson plus structured questions (MCQ + short answer).
    Response includes marking metadata for /grade — clients should not display
    `correct_index` / `acceptable_answers` to the learner.
    """
    settings = request.app.state.settings
    host = str(settings.model.get("host") or "http://localhost:11434")
    model = str(settings.model.get("name") or "qwen2.5:72b")

    n = body.num_questions
    mcq = max(1, n // 2)
    short = n - mcq
    mode_label = "a focused quiz" if body.mode == "quiz" else "a formal exam-style assessment"

    system = (
        "You are Nova Education — an expert tutor. You output ONLY valid JSON, no markdown outside "
        "the JSON object, no commentary. The JSON must match the schema exactly."
    )
    user = f"""Create {mode_label} for a learner.

Topic: {body.topic.strip()}
Difficulty level: {body.difficulty}
{f"Additional focus / constraints: {body.focus.strip()}" if body.focus else ""}

Requirements:
- Include a "lesson" string (2–4 short paragraphs) that teaches the core ideas needed to answer.
- Exactly {n} questions total: {mcq} multiple_choice and {short} short_answer.
- Each question: "id" (stable string like "q1"), "type" ("multiple_choice" | "short_answer"),
  "question" (stem), for MCQ include "options" (array of 4 strings) and "correct_index" (0-3 integer),
  for short_answer include "acceptable_answers" (array of 1-4 acceptable short phrases) and
  "rubric" (one sentence: what a full-credit answer must include).

JSON schema:
{{
  "lesson": "string",
  "title": "string",
  "questions": [
    {{
      "id": "q1",
      "type": "multiple_choice",
      "question": "string",
      "options": ["A","B","C","D"],
      "correct_index": 0
    }},
    {{
      "id": "q2",
      "type": "short_answer",
      "question": "string",
      "acceptable_answers": ["phrase"],
      "rubric": "string"
    }}
  ]
}}
"""

    try:
        raw = await asyncio.to_thread(_ollama_chat_sync, host, model, system, user, 6144)
        data = _extract_json_object(raw)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Model error: {exc}") from exc

    lesson = str(data.get("lesson") or "").strip()
    title = str(data.get("title") or body.topic[:80]).strip()
    questions = data.get("questions")
    if not lesson or not isinstance(questions, list) or len(questions) < 2:
        raise HTTPException(
            status_code=502,
            detail="Model returned an incomplete quiz. Try again.",
        )

    quiz_id = str(uuid.uuid4())
    # Public payload for UI (no answers); `filtered_key` stays aligned for grading.
    public_questions: list[dict[str, Any]] = []
    filtered_key: list[dict[str, Any]] = []
    for q in questions:
        if len(public_questions) >= n:
            break
        if not isinstance(q, dict):
            continue
        qid = str(q.get("id") or "").strip() or f"q{len(public_questions) + 1}"
        qtype = str(q.get("type") or "short_answer").lower()
        stem = str(q.get("question") or "").strip()
        if not stem:
            continue
        entry: dict[str, Any] = {
            "id": qid,
            "type": "multiple_choice" if "choice" in qtype else "short_answer",
            "question": stem,
        }
        if entry["type"] == "multiple_choice":
            opts = q.get("options")
            if not (isinstance(opts, list) and len(opts) >= 2):
                continue
            entry["options"] = [str(o) for o in opts[:6]]
        q_copy = dict(q)
        q_copy["id"] = qid
        public_questions.append(entry)
        filtered_key.append(q_copy)

    if len(public_questions) < 2:
        raise HTTPException(status_code=502, detail="Could not parse enough questions.")

    return {
        "quiz_id": quiz_id,
        "title": title,
        "lesson": lesson,
        "questions": public_questions,
        "grading": {
            "questions": filtered_key,
            "topic": body.topic,
            "difficulty": body.difficulty,
            "mode": body.mode,
        },
    }


@router.post("/grade")
async def grade_submission(
    request: Request,
    body: GradeSubmissionBody,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Score the learner's answers. Uses deterministic checks where possible and
    one model pass for holistic feedback + short-answer partial credit.
    """
    settings = request.app.state.settings
    host = str(settings.model.get("host") or "http://localhost:11434")
    model = str(settings.model.get("core_model") or settings.model.get("name") or "mistral:7b")

    grading = body.quiz.get("grading") if isinstance(body.quiz, dict) else None
    if not isinstance(grading, dict):
        raise HTTPException(status_code=400, detail="Missing quiz.grading payload from generate response.")

    key_questions = grading.get("questions")
    if not isinstance(key_questions, list):
        raise HTTPException(status_code=400, detail="Invalid grading.questions array.")

    results: list[dict[str, Any]] = []
    earned = 0.0
    total = 0.0

    for q in key_questions:
        if not isinstance(q, dict):
            continue
        qid = str(q.get("id") or "")
        if not qid:
            continue
        total += 1.0
        raw_ans = body.answers.get(qid, "")
        user_text = str(raw_ans).strip() if raw_ans is not None else ""
        qtype = str(q.get("type") or "").lower()

        if "choice" in qtype:
            opts = q.get("options")
            correct_idx = q.get("correct_index")
            try:
                ci = int(correct_idx) if correct_idx is not None else -1
            except (TypeError, ValueError):
                ci = -1
            score = 0.0
            detail = "No answer selected."
            if user_text.isdigit():
                ui = int(user_text)
                nopts = len(opts) if isinstance(opts, list) else 0
                if 0 <= ui < nopts:
                    if ui == ci:
                        score = 1.0
                        detail = "Correct."
                    else:
                        detail = "Incorrect option."
            elif user_text:
                # allow passing letter A-D
                letter = user_text.upper()[:1]
                if letter in "ABCD" and isinstance(opts, list):
                    ui = ord(letter) - ord("A")
                    if 0 <= ui < len(opts) and ui == ci:
                        score = 1.0
                        detail = "Correct."
                    else:
                        detail = "Incorrect option."
            earned += score
            results.append(
                {
                    "id": qid,
                    "type": "multiple_choice",
                    "question": str(q.get("question") or ""),
                    "score": round(score, 2),
                    "max": 1.0,
                    "detail": detail,
                    "correct_index": ci if score < 1.0 else None,
                }
            )
        else:
            acceptable = q.get("acceptable_answers")
            phrases: list[str] = []
            if isinstance(acceptable, list):
                phrases = [str(a).lower().strip() for a in acceptable if str(a).strip()]
            ut = user_text.lower()
            score = 0.0
            detail = "No answer provided."
            if user_text:
                if phrases and any(p in ut or ut in p for p in phrases if len(p) > 1):
                    score = 1.0
                    detail = "Matches expected key points."
                elif phrases and any(p == ut for p in phrases):
                    score = 1.0
                    detail = "Exact match."
                else:
                    detail = "Answer submitted; see overall feedback for nuance."
                    score = 0.35 if len(user_text) > 12 else 0.0
            earned += score
            results.append(
                {
                    "id": qid,
                    "type": "short_answer",
                    "question": str(q.get("question") or ""),
                    "score": round(score, 2),
                    "max": 1.0,
                    "detail": detail,
                }
            )

    pct = round(100.0 * earned / total, 1) if total > 0 else 0.0

    # Holistic feedback from model
    system = (
        "You are Nova Education. Reply with ONLY valid JSON: "
        '{"summary": "one paragraph", "strengths": ["..."], "improve": ["..."], '
        '"encouragement": "one short sentence"}'
    )
    payload = {
        "topic": grading.get("topic"),
        "difficulty": grading.get("difficulty"),
        "per_question": results,
        "learner_answers": body.answers,
    }
    user_fb = (
        "Given this graded quiz, write concise feedback for the learner.\n"
        + json.dumps(payload, ensure_ascii=False)[:12000]
    )
    try:
        raw_fb = await asyncio.to_thread(_ollama_chat_sync, host, model, system, user_fb, 2048)
        fb = _extract_json_object(raw_fb)
    except HTTPException:
        fb = {}
    except Exception:
        fb = {}

    return {
        "percent": pct,
        "earned": round(earned, 2),
        "total_points": round(total, 2),
        "results": results,
        "feedback": {
            "summary": str(fb.get("summary") or "").strip(),
            "strengths": fb.get("strengths") if isinstance(fb.get("strengths"), list) else [],
            "improve": fb.get("improve") if isinstance(fb.get("improve"), list) else [],
            "encouragement": str(fb.get("encouragement") or "").strip(),
        },
    }
