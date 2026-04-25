from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum


class ApprovalDecision(Enum):
    AUTO = "auto"
    CONFIRM = "confirm"
    BLOCKED = "blocked"


@dataclass
class ApprovalRequest:
    tool_name: str
    tool_input: dict
    risk_level: str
    description: str


class ApprovalManager:
    def __init__(self, approval_config: dict) -> None:
        self._default = approval_config.get("default", "confirm")
        self._rules: dict[str, dict] = {
            r["tool"]: r for r in approval_config.get("rules", [])
        }

    def check(self, tool_name: str) -> ApprovalDecision:
        rule = self._rules.get(tool_name, {})
        action = rule.get("action", self._default)
        if action == "auto":
            return ApprovalDecision.AUTO
        if action == "blocked":
            return ApprovalDecision.BLOCKED
        return ApprovalDecision.CONFIRM

    def get_request(self, tool_name: str, tool_input: dict) -> ApprovalRequest:
        rule = self._rules.get(tool_name, {})
        return ApprovalRequest(
            tool_name=tool_name,
            tool_input=tool_input,
            risk_level=rule.get("risk_level", "medium"),
            description=rule.get("description", f"Run tool: {tool_name}"),
        )

    def resolve(
        self,
        tool_name: str,
        tool_input: dict,
        ui_callback: Callable[[ApprovalRequest], bool] | None = None,
    ) -> bool:
        """
        Synchronous approval resolution — safe to call from a worker thread.
        Returns True if the tool should proceed, False if denied or blocked.
        """
        decision = self.check(tool_name)

        if decision == ApprovalDecision.AUTO:
            return True
        if decision == ApprovalDecision.BLOCKED:
            return False

        # CONFIRM — ask the user
        if ui_callback:
            return ui_callback(self.get_request(tool_name, tool_input))

        # No UI wired yet (headless / test mode) — allow by default
        return True
