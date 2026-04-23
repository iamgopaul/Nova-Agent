from __future__ import annotations

from datetime import datetime
from pathlib import Path

from nova.tools.base import BaseTool, ToolResult


def _safe_filename(title: str) -> str:
    return "".join(c if c.isalnum() or c in " -_" else "_" for c in title).strip()


class WriteNoteTool(BaseTool):
    name = "write_note"
    description = "Save a note with a title and content to the notes folder."

    def __init__(self, notes_dir: Path) -> None:
        self._dir = notes_dir

    def schema(self) -> dict:
        return self._schema(
            {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Short title for the note (used as filename).",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full text content of the note.",
                    },
                },
                "required": ["title", "content"],
            }
        )

    async def run(self, title: str, content: str) -> ToolResult:
        self._dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{_safe_filename(title)}_{ts}.md"
        path = self._dir / filename
        path.write_text(f"# {title}\n\n{content}", encoding="utf-8")
        return ToolResult(
            content=f"Note saved: {filename}",
            metadata={"path": str(path), "filename": filename},
        )


class ReadNoteTool(BaseTool):
    name = "read_note"
    description = "Read a saved note by filename. Use list_notes first if unsure of the filename."

    def __init__(self, notes_dir: Path) -> None:
        self._dir = notes_dir

    def schema(self) -> dict:
        return self._schema(
            {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Exact filename of the note to read.",
                    }
                },
                "required": ["filename"],
            }
        )

    async def run(self, filename: str) -> ToolResult:
        path = self._dir / filename
        if not path.exists():
            return ToolResult(
                content=f"Note not found: {filename}",
                error="File not found",
            )
        return ToolResult(
            content=path.read_text(encoding="utf-8"),
            metadata={"path": str(path)},
        )


class ListNotesTool(BaseTool):
    name = "list_notes"
    description = "List all saved notes, most recent first."

    def __init__(self, notes_dir: Path) -> None:
        self._dir = notes_dir

    def schema(self) -> dict:
        return self._schema(
            {"type": "object", "properties": {}, "required": []}
        )

    async def run(self) -> ToolResult:
        if not self._dir.exists():
            return ToolResult(content="No notes saved yet.")
        notes = sorted(
            self._dir.glob("*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not notes:
            return ToolResult(content="No notes saved yet.")
        listing = "\n".join(f"- {p.name}" for p in notes)
        return ToolResult(content=listing)
