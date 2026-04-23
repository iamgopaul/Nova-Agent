from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from nova.tools.base import BaseTool, ToolResult


class ScreenshotTool(BaseTool):
    name = "take_screenshot"
    description = (
        "Take a screenshot of the entire screen and save it. "
        "Returns the file path of the saved image."
    )

    def __init__(self, save_dir: Path) -> None:
        self._save_dir = save_dir

    def schema(self) -> dict:
        return self._schema(
            {
                "type": "object",
                "properties": {},
                "required": [],
            }
        )

    async def run(self) -> ToolResult:
        self._save_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self._save_dir / f"screenshot_{timestamp}.png"

        result = subprocess.run(
            ["screencapture", "-x", str(path)],
            capture_output=True,
        )

        if result.returncode != 0:
            err = result.stderr.decode().strip()
            return ToolResult(content=f"Screenshot failed: {err}", error=err)

        return ToolResult(
            content=f"Screenshot saved to {path}",
            metadata={"path": str(path)},
        )
