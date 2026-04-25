from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import Callable


@dataclass
class AgentResult:
    agent: str
    task: str
    output: str
    status: str = "done"  # "done" | "error"
    error: str | None = None


def _emit(cb: Callable | None, msg: str) -> None:
    if cb:
        cb(msg)


class BaseAgent:
    name: str = "GAAIA Agent"
    description: str = ""

    def __init__(self, settings) -> None:
        self._settings = settings
        m = settings.model
        self._host = str(m.get("host") or "http://localhost:11434")
        self._model = self._resolve_model(m)

    def _resolve_model(self, m: dict) -> str:
        return m.get("core_model") or m.get("name") or "mistral:7b"

    def _system_prompt(self) -> str:
        return "You are a helpful AI agent."

    async def _llm(
        self,
        messages: list[dict],
        token_callback: Callable | None = None,
        options: dict | None = None,
    ) -> str:
        import ollama

        loop = asyncio.get_event_loop()
        q: asyncio.Queue[str | None] = asyncio.Queue()
        _opts = {"temperature": 0.7, "num_predict": 2048, **(options or {})}

        def _run() -> None:
            client = ollama.Client(host=self._host, timeout=120)
            try:
                for chunk in client.chat(
                    model=self._model,
                    messages=messages,
                    stream=True,
                    options=_opts,
                ):
                    tok = (chunk.get("message") or {}).get("content") or ""
                    if tok:
                        loop.call_soon_threadsafe(q.put_nowait, tok)
            except Exception as exc:
                print(f"[{self.name}] LLM error: {exc}", flush=True)
            finally:
                loop.call_soon_threadsafe(q.put_nowait, None)

        threading.Thread(target=_run, daemon=True).start()
        parts: list[str] = []
        while True:
            tok = await q.get()
            if tok is None:
                break
            parts.append(tok)
            if token_callback:
                token_callback(tok)
        return "".join(parts)

    async def run(
        self,
        task: str,
        context: str = "",
        token_callback: Callable | None = None,
        status_callback: Callable | None = None,
    ) -> AgentResult:
        raise NotImplementedError


# ── GAAIA Research ─────────────────────────────────────────────────────────────

class GAAIAResearchAgent(BaseAgent):
    name = "GAAIA Research"
    description = "Web search and information synthesis"

    def _resolve_model(self, m: dict) -> str:
        return m.get("core_model") or m.get("name") or "mistral:7b"

    def _system_prompt(self) -> str:
        return (
            "You are GAIA Research — a precise, fast web research specialist. "
            "Given a research task, synthesize all available information into clear, factual findings. "
            "Structure your output with: **Key Findings** (bullet points), **Summary** (2-3 sentences), "
            "and **Confidence** (high/medium/low based on source quality). "
            "Be specific. Cite details from search results when provided. Never pad."
        )

    async def _search(self, query: str) -> str:
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=6))
            snippets = [
                f"**{r.get('title', '')}**\n{r.get('body', '')}"
                for r in results
                if r.get("body")
            ]
            return "\n\n".join(snippets[:5])
        except Exception:
            return ""

    async def run(self, task, context="", token_callback=None, status_callback=None) -> AgentResult:
        _emit(status_callback, "Searching the web…")
        search_ctx = await self._search(task)

        user_content = f"Research Task: {task}"
        if context:
            user_content += f"\n\nContext from prior agents:\n{context}"
        if search_ctx:
            user_content += f"\n\nSearch Results:\n{search_ctx}"
        else:
            user_content += "\n\n(No live search results available — answer from training knowledge.)"

        _emit(status_callback, "Synthesizing findings…")
        messages = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": user_content},
        ]
        try:
            output = await self._llm(messages, token_callback)
            return AgentResult(agent=self.name, task=task, output=output)
        except Exception as exc:
            return AgentResult(agent=self.name, task=task, output="", status="error", error=str(exc))


# ── GAIA Code ─────────────────────────────────────────────────────────────────

class GAAIACodeAgent(BaseAgent):
    name = "GAIA Code"
    description = "Code writing, debugging, and architecture"

    def _resolve_model(self, m: dict) -> str:
        return m.get("code_model") or m.get("name") or "mistral:7b"

    def _system_prompt(self) -> str:
        return (
            "You are GAIA Code — a senior software engineer. "
            "Write clean, production-ready code. "
            "Always include: working implementation, a brief note on key decisions, and a usage example. "
            "Prefer clarity over cleverness. No unnecessary comments. No filler text."
        )

    async def run(self, task, context="", token_callback=None, status_callback=None) -> AgentResult:
        _emit(status_callback, "Writing code…")
        user_content = f"Coding Task: {task}"
        if context:
            user_content += f"\n\nContext:\n{context}"

        messages = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": user_content},
        ]
        try:
            output = await self._llm(
                messages, token_callback,
                options={"temperature": 0.2, "num_predict": 3000},
            )
            return AgentResult(agent=self.name, task=task, output=output)
        except Exception as exc:
            return AgentResult(agent=self.name, task=task, output="", status="error", error=str(exc))


# ── GAAIA Analyst ──────────────────────────────────────────────────────────────

class GAAIAAnalystAgent(BaseAgent):
    name = "GAAIA Analyst"
    description = "Data analysis, patterns, and strategic insights"

    def _resolve_model(self, m: dict) -> str:
        return m.get("insight_model") or m.get("core_model") or m.get("name") or "mistral:7b"

    def _system_prompt(self) -> str:
        return (
            "You are GAIA Analyst — a sharp data analyst and strategic thinker. "
            "Given data or a topic, produce: "
            "**Analysis** (what the data or situation shows), "
            "**Key Patterns** (3–5 bullet point insights), "
            "**Implications** (what this means and why it matters), "
            "**Recommendation** (one clear, actionable next step). "
            "Use numbers when available. Avoid vague language."
        )

    async def run(self, task, context="", token_callback=None, status_callback=None) -> AgentResult:
        _emit(status_callback, "Analyzing…")
        user_content = f"Analysis Task: {task}"
        if context:
            user_content += f"\n\nAvailable data and context:\n{context}"

        messages = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": user_content},
        ]
        try:
            output = await self._llm(
                messages, token_callback,
                options={"temperature": 0.3, "num_predict": 2048},
            )
            return AgentResult(agent=self.name, task=task, output=output)
        except Exception as exc:
            return AgentResult(agent=self.name, task=task, output="", status="error", error=str(exc))


# ── GAAIA Writer ───────────────────────────────────────────────────────────────

class GAAIAWriterAgent(BaseAgent):
    name = "GAAIA Writer"
    description = "Documents, reports, and long-form writing"

    def _resolve_model(self, m: dict) -> str:
        return m.get("heavy_model") or m.get("name") or "mistral:7b"

    def _system_prompt(self) -> str:
        return (
            "You are GAIA Writer — a professional writer with expert command of structure, tone, and prose. "
            "Write clear, compelling, well-structured documents. "
            "Use proper headings, logical flow, and strong transitions. "
            "The output should be ready to hand to a stakeholder. "
            "No meta-commentary — deliver the document directly."
        )

    async def run(self, task, context="", token_callback=None, status_callback=None) -> AgentResult:
        _emit(status_callback, "Drafting document…")
        user_content = f"Writing Task: {task}"
        if context:
            user_content += f"\n\nResearch and analysis to incorporate:\n{context}"

        messages = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": user_content},
        ]
        try:
            output = await self._llm(
                messages, token_callback,
                options={"temperature": 0.7, "num_predict": 4096},
            )
            return AgentResult(agent=self.name, task=task, output=output)
        except Exception as exc:
            return AgentResult(agent=self.name, task=task, output="", status="error", error=str(exc))


# ── GAAIA Manager ──────────────────────────────────────────────────────────────

class GAAIAManagerAgent(BaseAgent):
    name = "GAAIA Manager"
    description = "Plans and coordinates the specialist agents"

    _PLAN_PROMPT = """\
You are GAIA Manager — an orchestration AI. Break down the user's request into tasks for your specialist agents.

Available agents:
- research : Web search and information synthesis. Use for: facts, current events, market data, background info.
- code     : Code writing, debugging, architecture. Use for: any programming task, scripts, APIs.
- analyst  : Data analysis, patterns, insights. Use for: interpreting data, finding trends, making recommendations.
- writer   : Documents, reports, long-form writing. Use for: final reports, summaries, polished output.

Rules:
- Only include agents that are genuinely needed for this specific request.
- Use "depends_on" to express ordering. Agents with empty "depends_on" run in parallel.
- "writer" almost always runs last and depends on research/analyst.
- Keep task descriptions short and specific — one focused job per agent.
- For a simple coding request, use only "code". For a report request, use "research" then "writer".

Respond ONLY with valid JSON — no other text:
{
  "goal": "one sentence describing the overall objective",
  "agents": [
    {"id": "research", "task": "specific task description", "depends_on": []},
    {"id": "writer",   "task": "specific task description", "depends_on": ["research"]}
  ]
}"""

    _SYNTHESIS_PROMPT = """\
You are GAIA Manager. Your specialist agents have completed their work.
Synthesize all agent outputs into one coherent, high-quality final answer.

Rules:
- Read every agent output carefully and combine them into a unified response.
- Remove redundancy; add flow and cohesion between sections.
- The final answer must feel like it came from one expert, not a committee.
- Match the format to the request: if it was a report, write a report; if it was code, present the code cleanly.
- No meta-commentary about the process ("the research agent found…", "as analyzed above…")."""

    def _resolve_model(self, m: dict) -> str:
        return m.get("heavy_model") or m.get("name") or "mistral:7b"

    async def plan(self, user_request: str) -> dict:
        import json
        import re

        messages = [
            {"role": "system", "content": self._PLAN_PROMPT},
            {"role": "user", "content": f"User request: {user_request}"},
        ]
        raw = await self._llm(messages, options={"temperature": 0.1, "num_predict": 600})

        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass

        # Fallback: research + writer
        return {
            "goal": user_request,
            "agents": [
                {"id": "research", "task": user_request, "depends_on": []},
                {"id": "writer", "task": f"Write a comprehensive response about: {user_request}", "depends_on": ["research"]},
            ],
        }

    async def synthesize(
        self,
        user_request: str,
        results: dict,
        token_callback: Callable | None = None,
    ) -> str:
        agent_outputs = "\n\n".join(
            f"=== {result.agent} ===\n{result.output}"
            for result in results.values()
            if result.output and result.status == "done"
        )
        messages = [
            {"role": "system", "content": self._SYNTHESIS_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Original request: {user_request}\n\n"
                    f"Agent outputs:\n{agent_outputs}\n\n"
                    "Produce the final unified answer."
                ),
            },
        ]
        return await self._llm(messages, token_callback, options={"temperature": 0.7, "num_predict": 4096})

    async def run(self, task, context="", token_callback=None, status_callback=None) -> AgentResult:
        output = await self._llm(
            [{"role": "system", "content": self._SYNTHESIS_PROMPT}, {"role": "user", "content": task}],
            token_callback,
        )
        return AgentResult(agent=self.name, task=task, output=output)
