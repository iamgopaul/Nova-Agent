from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor

from nova.tools.base import BaseTool, ToolResult

# Dedicated executor so tool coroutines always run in a fresh thread
# with no existing event loop — avoids "cannot run nested event loop" errors.
_tool_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="nova-tool")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get_all_schemas(self) -> list[dict]:
        return [t.schema() for t in self._tools.values()]

    def has(self, name: str) -> bool:
        return name in self._tools

    def execute(self, name: str, arguments: dict | str) -> ToolResult:
        """
        Dispatch a tool call synchronously from any context (async or sync).
        Runs the coroutine in a dedicated thread pool where no event loop
        exists, so asyncio.run() always succeeds regardless of the caller.
        """
        if name not in self._tools:
            return ToolResult(
                content=f"Unknown tool '{name}'.",
                error=f"Tool '{name}' is not registered.",
            )

        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}

        if not isinstance(arguments, dict):
            arguments = {}

        tool = self._tools[name]
        kwargs = dict(arguments)

        def _run() -> ToolResult:
            try:
                return asyncio.run(tool.run(**kwargs))
            except TypeError as exc:
                return ToolResult(
                    content=f"Tool '{name}' called with wrong arguments: {exc}",
                    error=str(exc),
                )
            except Exception as exc:
                return ToolResult(
                    content=f"Tool '{name}' failed: {exc}",
                    error=str(exc),
                )

        future = _tool_executor.submit(_run)
        try:
            return future.result(timeout=30)
        except Exception as exc:
            return ToolResult(
                content=f"Tool '{name}' timed out or crashed: {exc}",
                error=str(exc),
            )

    async def async_execute(
        self,
        name: str,
        arguments: dict | str,
        timeout: float = 25.0,
    ) -> ToolResult:
        """
        Await a tool directly — use this from async contexts to avoid blocking.

        A hard *timeout* (default 25 s) prevents any tool from hanging the
        entire request.  Individual tools may impose their own stricter limits.
        """
        if name not in self._tools:
            return ToolResult(
                content=f"Unknown tool '{name}'.",
                error=f"Tool '{name}' is not registered.",
            )

        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}

        if not isinstance(arguments, dict):
            arguments = {}

        tool = self._tools[name]
        try:
            return await asyncio.wait_for(tool.run(**arguments), timeout=timeout)
        except asyncio.TimeoutError:
            return ToolResult(
                content=f"Tool '{name}' timed out after {timeout:.0f}s.",
                error="timeout",
            )
        except TypeError as exc:
            return ToolResult(
                content=f"Tool '{name}' called with wrong arguments: {exc}",
                error=str(exc),
            )
        except Exception as exc:
            return ToolResult(
                content=f"Tool '{name}' failed: {exc}",
                error=str(exc),
            )
