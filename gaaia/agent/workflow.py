from __future__ import annotations

import asyncio
from typing import Any, Callable

from gaaia.agent.agents import (
    AgentResult,
    GAAIAAnalystAgent,
    GAAIACodeAgent,
    GAAIAManagerAgent,
    GAAIAResearchAgent,
    GAAIAWriterAgent,
)


class WorkflowRunner:
    """
    Executes multi-agent workflows planned by GAAIA Manager.

    SSE events emitted via event_callback:
      {"type": "planning"}
      {"type": "plan",           "goal": str, "agents": [...]}
      {"type": "agent_start",    "agent_id": str, "agent_name": str, "task": str}
      {"type": "agent_status",   "agent_id": str, "status": str}
      {"type": "token",          "agent_id": str, "text": str}
      {"type": "agent_done",     "agent_id": str}
      {"type": "agent_error",    "agent_id": str, "error": str}
      {"type": "synthesizing"}
      {"type": "synthesis_token","text": str}
      {"type": "done",           "output": str}
      {"type": "error",          "message": str}
    """

    def __init__(self, settings) -> None:
        self._manager = GAAIAManagerAgent(settings)
        self._agents: dict[str, Any] = {
            "research": GAAIAResearchAgent(settings),
            "code":     GAAIACodeAgent(settings),
            "analyst":  GAAIAAnalystAgent(settings),
            "writer":   GAAIAWriterAgent(settings),
        }

    async def run(
        self,
        user_request: str,
        event_callback: Callable[[dict], None],
    ) -> str:
        try:
            # ── 1. Manager plans ────────────────────────────────────────────────
            event_callback({"type": "planning"})
            plan = await self._manager.plan(user_request)
            event_callback({
                "type": "plan",
                "goal": plan.get("goal", user_request),
                "agents": plan.get("agents", []),
            })

            # ── 2. Topological execution ────────────────────────────────────────
            results: dict[str, AgentResult] = {}
            pending = list(plan.get("agents", []))

            while pending:
                ready = [
                    a for a in pending
                    if all(dep in results for dep in a.get("depends_on", []))
                ]
                if not ready:
                    # Unresolvable deps — run whatever is left anyway
                    ready = pending[:1]

                tasks = [self._run_agent(a, results, event_callback) for a in ready]
                completed = await asyncio.gather(*tasks, return_exceptions=True)

                for i, outcome in enumerate(completed):
                    agent_id = ready[i]["id"]
                    if isinstance(outcome, AgentResult):
                        results[agent_id] = outcome
                    else:
                        err = str(outcome)
                        results[agent_id] = AgentResult(
                            agent=agent_id,
                            task=ready[i].get("task", ""),
                            output="",
                            status="error",
                            error=err,
                        )
                        event_callback({"type": "agent_error", "agent_id": agent_id, "error": err})

                pending = [a for a in pending if a["id"] not in results]

            # ── 3. Manager synthesizes ──────────────────────────────────────────
            event_callback({"type": "synthesizing"})

            def _syn_tok(tok: str) -> None:
                event_callback({"type": "synthesis_token", "text": tok})

            output = await self._manager.synthesize(user_request, results, token_callback=_syn_tok)
            event_callback({"type": "done", "output": output})
            return output

        except Exception as exc:
            event_callback({"type": "error", "message": str(exc)})
            return ""

    async def _run_agent(
        self,
        agent_plan: dict,
        results: dict[str, AgentResult],
        event_callback: Callable[[dict], None],
    ) -> AgentResult:
        agent_id = agent_plan["id"]
        task = agent_plan.get("task", "")
        agent = self._agents.get(agent_id)

        if not agent:
            return AgentResult(
                agent=agent_id, task=task, output="",
                status="error", error=f"Unknown agent: {agent_id}",
            )

        context = "\n\n".join(
            f"[{results[dep].agent}]:\n{results[dep].output}"
            for dep in agent_plan.get("depends_on", [])
            if dep in results and results[dep].output
        )

        event_callback({
            "type": "agent_start",
            "agent_id": agent_id,
            "agent_name": agent.name,
            "task": task,
        })

        def _tok(text: str) -> None:
            event_callback({"type": "token", "agent_id": agent_id, "text": text})

        def _status(msg: str) -> None:
            event_callback({"type": "agent_status", "agent_id": agent_id, "status": msg})

        result = await agent.run(task, context=context, token_callback=_tok, status_callback=_status)
        event_callback({"type": "agent_done", "agent_id": agent_id})
        return result
