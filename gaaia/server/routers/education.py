"""
GAAIA Education — generate quizzes/exams and grade submissions via local Ollama.

No chat memory writes; each call is stateless aside from auth.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from typing import Any, Literal

import ollama
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from gaaia.attachments import _extract_pdf_text
from gaaia.memory.models import User
from gaaia.server.dependencies import get_current_user

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
    client = ollama.Client(host=host, timeout=120)
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
    difficulty: Literal["elementary", "middle", "high", "college", "bachelors", "masters", "doctorate"] = "high"
    num_questions: int = Field(default=5, ge=3, le=15)
    focus: str | None = Field(default=None, max_length=800)
    document_context: str | None = Field(default=None, max_length=50000)
    degree_field: str | None = Field(default=None, max_length=200)


class GradeSubmissionBody(BaseModel):
    """Full quiz payload from /generate plus user answers (question id -> answer text or 0-based option index)."""

    quiz: dict[str, Any]
    answers: dict[str, str] = Field(default_factory=dict)


_TECHNICAL_KEYWORDS = {
    "python", "java", "javascript", "typescript", "c++", "c#", "rust", "go",
    "programming", "code", "coding", "algorithm", "data structure", "software",
    "computer science", "cs", "database", "sql", "web", "api", "machine learning",
    "deep learning", "neural network", "ai", "artificial intelligence", "math",
    "mathematics", "calculus", "statistics", "linear algebra", "physics",
    "chemistry", "biology", "engineering", "networking", "cybersecurity",
    "operating system", "compiler", "recursion", "sorting", "graph", "tree",
    "dynamic programming", "complexity", "big o", "react", "node", "django",
    "flask", "docker", "kubernetes", "cloud", "aws", "git", "devops",
}


def _is_technical(topic: str) -> bool:
    low = topic.lower()
    return any(kw in low for kw in _TECHNICAL_KEYWORDS)


_LEVEL_CALIBRATION: dict[str, str] = {
    "elementary": (
        "Questions must be appropriate for ages 6–11. "
        "EASY: single-fact recall (What is…?). "
        "MEDIUM: simple comprehension or 1-step reasoning. "
        "HARD: apply a concept to a familiar scenario."
    ),
    "middle": (
        "Questions must be appropriate for ages 11–14. "
        "EASY: define a term or recall a key fact. "
        "MEDIUM: explain why or how something works. "
        "HARD: compare/contrast concepts or solve a basic multi-step problem."
    ),
    "high": (
        "Questions must be appropriate for high-school students (ages 14–18). "
        "EASY: recall or state a definition/formula. "
        "MEDIUM: explain a mechanism, solve a standard problem, or identify cause-and-effect. "
        "HARD: synthesize across multiple concepts, evaluate trade-offs, or tackle a non-trivial problem."
    ),
    "college": (
        "Questions must be appropriate for undergraduate students. "
        "EASY: recall an advanced concept or state a theorem correctly. "
        "MEDIUM: apply theory to a realistic scenario or solve a moderately complex problem. "
        "HARD: analyze edge cases, derive a result, or evaluate competing approaches with justification."
    ),
    "bachelors": (
        "Questions must reflect mastery expected at the end of a Bachelor's degree program. "
        "EASY: apply a core concept to a straightforward scenario. "
        "MEDIUM: design a solution, debug non-trivial code, or perform multi-step analysis. "
        "HARD: evaluate architectural/methodological trade-offs, handle ambiguous real-world constraints, "
        "or solve a problem requiring integration of multiple sub-disciplines."
    ),
    "masters": (
        "Questions must reflect graduate-level (Master's) depth. "
        "EASY: apply an advanced technique to a well-defined problem. "
        "MEDIUM: critically compare methodologies, derive non-obvious results, or extend a standard algorithm. "
        "HARD: identify limitations of state-of-the-art approaches, design novel solutions, "
        "or reason about systems under complex real-world constraints."
    ),
    "doctorate": (
        "Questions must reflect doctoral/research-level expertise. "
        "EASY: situate a concept within the research literature or apply an expert technique. "
        "MEDIUM: critically analyze a published method's assumptions, failure modes, or scope. "
        "HARD: identify open problems, propose a novel research direction, evaluate contradictory findings, "
        "or reason rigorously about a problem that has no standard answer."
    ),
}

_LEVEL_LABELS: dict[str, str] = {
    "elementary": "Elementary school (ages 6–11)",
    "middle": "Middle school (ages 11–14)",
    "high": "High school (ages 14–18)",
    "college": "College / undergraduate",
    "bachelors": "Bachelor's degree level",
    "masters": "Master's degree level",
    "doctorate": "Doctoral / PhD level",
}

_HIGHER_LEVELS = {"bachelors", "masters", "doctorate"}


@router.post("/generate")
async def generate_quiz(
    request: Request,
    body: GenerateQuizBody,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Produce a short lesson plus structured questions (MCQ + short answer).
    Questions are distributed across easy/medium/hard tiers for the chosen level.
    Response includes marking metadata for /grade — clients must not display
    `correct_index` / `acceptable_answers` to the learner.
    """
    settings = request.app.state.settings
    host = str(settings.model.get("host") or "http://localhost:11434")
    model = str(settings.model.get("core_model") or settings.model.get("name") or "qwen2.5:7b")

    n = body.num_questions
    # For higher degree levels, skew toward short-answer (harder to guess)
    if body.difficulty in _HIGHER_LEVELS:
        mcq = max(1, n // 3)
    else:
        mcq = max(1, n // 2)
    short = n - mcq

    mode_label = "a focused quiz" if body.mode == "quiz" else "a formal exam-style assessment"
    technical = _is_technical(body.topic)
    calibration = _LEVEL_CALIBRATION[body.difficulty]
    level_label = _LEVEL_LABELS[body.difficulty]

    # Difficulty tier distribution
    easy_n  = max(1, n // 3)
    hard_n  = max(1, n // 3)
    medium_n = n - easy_n - hard_n

    # Degree context
    degree_ctx = ""
    if body.difficulty in _HIGHER_LEVELS and body.degree_field:
        df = body.degree_field.strip()
        degree_ctx = (
            f"\nLearner's degree field: {df}. "
            f"Questions must be grounded in {df} — use field-specific terminology, "
            f"problems, and frameworks typical of a {level_label} graduate in {df}."
        )

    # Technical / code instructions
    code_instructions = ""
    if technical:
        code_instructions = """
CODE-BASED QUESTION RULES (apply to technical topics):
- At least 1 MEDIUM and 1 HARD question must include an inline code snippet.
- Question types may include: "What does this code output?", "Find and fix the bug",
  "What is the time/space complexity?", "Complete the missing line", "Which refactor is correct?".
- Embed code blocks directly in the "question" field using escaped newlines (\\n) and spaces.
  Example: "What does the following Python code print?\\n\\n    x = [1,2,3]\\n    print(x[::-1])"
- Wrong MCQ options for code questions must be plausible outputs or fixes, not obviously wrong.
- Short-answer code questions must ask for precise answers (e.g. exact output, Big-O notation).
"""

    system = (
        "You are GAIA Education — an elite tutor generating rigorous assessments. "
        "You output ONLY valid JSON with no markdown fences, no commentary. "
        "Every question must be genuinely challenging for its tier and level — "
        "never trivial, never easier than specified."
    )

    user = f"""Create {mode_label} on the following topic.

Topic: {body.topic.strip()}
Level: {level_label}{degree_ctx}
{f"Additional constraints: {body.focus.strip()}" if body.focus else ""}
{f"Base questions on this source material:{chr(10)}{body.document_context[:8000]}" if body.document_context else ""}

LEVEL CALIBRATION:
{calibration}
{code_instructions}
QUESTION DISTRIBUTION — produce exactly {n} questions across three tiers:
  {easy_n} × EASY   (tag: "tier": "easy")
  {medium_n} × MEDIUM (tag: "tier": "medium")
  {hard_n} × HARD   (tag: "tier": "hard")

TYPE SPLIT — exactly {mcq} multiple_choice and {short} short_answer total.
  Prefer assigning harder tiers to short_answer questions.

QUALITY RULES:
1. Every wrong MCQ option must be a plausible distractor — no obviously silly answers.
2. Hard questions require multi-step reasoning or expert knowledge; they should be difficult even for
   someone who studied the lesson.
3. Short-answer rubric must specify exactly what the answer needs to include for full credit.
4. The lesson must teach the concepts needed to answer the EASY and MEDIUM questions;
   HARD questions should also require prior knowledge the lesson alone may not cover.

LESSON: Write 2–4 paragraphs covering the core concepts. For technical topics, include a
brief code example if appropriate.

Return ONLY the following JSON object (no markdown, no extra text):
{{
  "title": "string",
  "lesson": "string — 2-4 paragraphs, may contain inline code using backticks",
  "questions": [
    {{
      "id": "q1",
      "tier": "easy",
      "type": "multiple_choice",
      "question": "string (may contain embedded code with \\\\n for newlines)",
      "options": ["option A", "option B", "option C", "option D"],
      "correct_index": 0
    }},
    {{
      "id": "q2",
      "tier": "medium",
      "type": "short_answer",
      "question": "string",
      "acceptable_answers": ["key phrase 1", "alternate phrasing"],
      "rubric": "string — exactly what a full-credit answer must state"
    }}
  ]
}}"""

    try:
        raw = await asyncio.to_thread(_ollama_chat_sync, host, model, system, user, 4096)
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
        tier = str(q.get("tier") or "medium").lower()
        entry: dict[str, Any] = {
            "id": qid,
            "tier": tier if tier in ("easy", "medium", "hard") else "medium",
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
        "You are GAIA Education. Reply with ONLY valid JSON: "
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


@router.post("/extract-context")
async def extract_document_context(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Extract text from an uploaded PDF or TXT file to use as quiz source material."""
    raw = await file.read()
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        text = await asyncio.to_thread(_extract_pdf_text, raw)
    elif ext in ("txt", "md"):
        text = raw.decode("utf-8", errors="replace")
    else:
        raise HTTPException(
            status_code=400,
            detail="Only PDF and TXT files are supported for context extraction.",
        )

    text = (text or "").strip()
    if not text:
        raise HTTPException(
            status_code=422,
            detail="Could not extract any text from the document. Ensure the file contains readable text.",
        )

    truncated = text[:50000]
    return {"text": truncated, "chars": len(truncated), "filename": filename}
