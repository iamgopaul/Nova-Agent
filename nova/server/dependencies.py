from __future__ import annotations

from fastapi import Request

from nova.agent.orchestrator import Orchestrator
from nova.approval.manager import ApprovalManager
from nova.memory.store import MemoryStore


def get_orchestrator(request: Request) -> Orchestrator:
    return request.app.state.orchestrator


def get_memory(request: Request) -> MemoryStore:
    return request.app.state.memory


def get_approval(request: Request) -> ApprovalManager:
    return request.app.state.approval
