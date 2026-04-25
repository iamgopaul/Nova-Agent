from __future__ import annotations

import subprocess

from gaaia.tools.base import BaseTool, ToolResult


class GetClipboardTool(BaseTool):
    name = "get_clipboard"
    description = "Read the current text content of the macOS clipboard."

    def schema(self) -> dict:
        return self._schema(
            {"type": "object", "properties": {}, "required": []}
        )

    async def run(self) -> ToolResult:
        result = subprocess.run(["pbpaste"], capture_output=True, text=True)
        content = result.stdout.strip()
        if not content:
            return ToolResult(content="The clipboard is empty.")
        return ToolResult(content=content)


class SetClipboardTool(BaseTool):
    name = "set_clipboard"
    description = "Write text to the macOS clipboard."

    def schema(self) -> dict:
        return self._schema(
            {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The text to copy to the clipboard.",
                    }
                },
                "required": ["text"],
            }
        )

    async def run(self, text: str) -> ToolResult:
        subprocess.run(["pbcopy"], input=text.encode(), check=True)
        preview = text[:60] + "..." if len(text) > 60 else text
        return ToolResult(
            content=f"Copied to clipboard: {preview}",
            metadata={"length": len(text)},
        )
