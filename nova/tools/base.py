from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ToolResult:
    content: str
    metadata: dict = field(default_factory=dict)
    error: str | None = None


class BaseTool(ABC):
    name: str
    description: str

    @abstractmethod
    def schema(self) -> dict:
        """Return an OpenAI/Ollama-compatible function tool schema."""
        ...

    @abstractmethod
    async def run(self, **kwargs) -> ToolResult:
        ...

    def _schema(self, parameters: dict) -> dict:
        """Helper: wraps name + description + parameters into the standard shape."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
            },
        }
