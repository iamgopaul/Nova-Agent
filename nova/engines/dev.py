from __future__ import annotations

import os
import subprocess
from pathlib import Path

from nova.tools.base import BaseTool, ToolResult

_MAX_FILE_BYTES = 100_000   # ~3,000 lines; truncate beyond this
_MAX_SEARCH_HITS = 30


class ReadFileTool(BaseTool):
    name = "read_file"
    description = (
        "Read the contents of a file on disk. "
        "Returns up to ~3,000 lines with the full path shown. "
        "Useful for reviewing code, config, notes, or any text file."
    )

    def schema(self) -> dict:
        return self._schema(
            {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or ~ path to the file.",
                    }
                },
                "required": ["path"],
            }
        )

    async def run(self, path: str) -> ToolResult:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return ToolResult(content=f"File not found: {p}", error="not_found")
        if not p.is_file():
            return ToolResult(content=f"Not a file: {p}", error="not_a_file")

        raw = p.read_bytes()
        truncated = False
        if len(raw) > _MAX_FILE_BYTES:
            raw = raw[:_MAX_FILE_BYTES]
            truncated = True

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1", errors="replace")

        if truncated:
            text += f"\n\n[… file truncated at {_MAX_FILE_BYTES} bytes]"

        return ToolResult(
            content=f"```{p.suffix.lstrip('.')}\n{text}\n```",
            metadata={"path": str(p), "truncated": truncated},
        )


class ListFilesTool(BaseTool):
    name = "list_files"
    description = (
        "List files and directories in a folder, up to 4 levels deep. "
        "Shows a tree view filtered to common code and config extensions."
    )

    def __init__(self, include_extensions: list[str] | None = None) -> None:
        self._exts = set(
            include_extensions
            or [".py", ".ts", ".js", ".go", ".md", ".json", ".yaml",
                ".toml", ".swift", ".rs", ".c", ".cpp", ".h", ".txt"]
        )

    def schema(self) -> dict:
        return self._schema(
            {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory to list. Defaults to home directory.",
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "How many levels deep to show (1–4).",
                    },
                },
                "required": [],
            }
        )

    async def run(self, path: str = "~", max_depth: int = 3) -> ToolResult:
        root = Path(path).expanduser().resolve()
        if not root.exists():
            return ToolResult(content=f"Directory not found: {root}", error="not_found")
        max_depth = min(max(1, max_depth), 4)
        lines: list[str] = [str(root)]
        self._walk(root, lines, depth=0, max_depth=max_depth)
        return ToolResult(content="\n".join(lines))

    def _walk(
        self,
        directory: Path,
        lines: list[str],
        depth: int,
        max_depth: int,
    ) -> None:
        if depth >= max_depth:
            return
        try:
            entries = sorted(
                directory.iterdir(),
                key=lambda p: (p.is_file(), p.name.lower()),
            )
        except PermissionError:
            return

        for entry in entries:
            if entry.name.startswith(".") or entry.name in (
                "__pycache__", "node_modules", ".venv", "venv", ".git",
                "dist", "build", ".eggs",
            ):
                continue
            prefix = "  " * (depth + 1)
            if entry.is_dir():
                lines.append(f"{prefix}{entry.name}/")
                self._walk(entry, lines, depth + 1, max_depth)
            elif entry.suffix in self._exts:
                lines.append(f"{prefix}{entry.name}")


class GitStatusTool(BaseTool):
    name = "git_status"
    description = (
        "Show the git status of a project directory: staged changes, "
        "unstaged changes, untracked files, and recent commits."
    )

    def schema(self) -> dict:
        return self._schema(
            {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the git repository. Defaults to home.",
                    }
                },
                "required": [],
            }
        )

    async def run(self, path: str = "~") -> ToolResult:
        cwd = str(Path(path).expanduser().resolve())
        parts: list[str] = []

        status = subprocess.run(
            ["git", "status", "--short", "--branch"],
            cwd=cwd, capture_output=True, text=True,
        )
        if status.returncode != 0:
            return ToolResult(
                content=f"Not a git repo or git not available at: {cwd}",
                error=status.stderr.strip(),
            )
        parts.append(status.stdout.strip() or "Working tree clean.")

        log = subprocess.run(
            ["git", "log", "--oneline", "-5"],
            cwd=cwd, capture_output=True, text=True,
        )
        if log.returncode == 0 and log.stdout.strip():
            parts.append("\nRecent commits:\n" + log.stdout.strip())

        return ToolResult(content="\n".join(parts))


class SearchCodeTool(BaseTool):
    name = "search_code"
    description = (
        "Search for a pattern across source files in a directory. "
        "Uses ripgrep if available (fast), otherwise Python fallback. "
        "Returns file paths, line numbers, and matching lines."
    )

    def schema(self) -> dict:
        return self._schema(
            {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Text or regex pattern to search for.",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to search. Defaults to home.",
                    },
                    "file_type": {
                        "type": "string",
                        "description": "File extension filter e.g. 'py', 'ts'. Leave blank for all.",
                    },
                },
                "required": ["pattern"],
            }
        )

    async def run(
        self, pattern: str, path: str = "~", file_type: str = ""
    ) -> ToolResult:
        cwd = str(Path(path).expanduser().resolve())

        # Try ripgrep first
        try:
            cmd = ["rg", "--line-number", "--max-count=3", "--max-depth=5"]
            if file_type:
                cmd += ["-t", file_type]
            cmd += [pattern, cwd]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            out = result.stdout.strip()
            if result.returncode == 0:
                lines = out.splitlines()[:_MAX_SEARCH_HITS]
                return ToolResult(content="\n".join(lines) or "No matches.")
            if result.returncode == 1:
                return ToolResult(content="No matches found.")
        except FileNotFoundError:
            pass  # rg not installed
        except subprocess.TimeoutExpired:
            return ToolResult(content="Search timed out.", error="timeout")

        # Python fallback
        exts = {f".{file_type}"} if file_type else {
            ".py", ".ts", ".js", ".go", ".md", ".json", ".yaml", ".toml",
        }
        matches: list[str] = []
        root = Path(cwd)
        pattern_lower = pattern.lower()

        for ext in exts:
            for fp in root.rglob(f"*{ext}"):
                if any(
                    skip in fp.parts
                    for skip in ("__pycache__", "node_modules", ".venv", ".git")
                ):
                    continue
                try:
                    for i, line in enumerate(
                        fp.read_text(errors="replace").splitlines(), 1
                    ):
                        if pattern_lower in line.lower():
                            rel = fp.relative_to(root)
                            matches.append(f"{rel}:{i}: {line.strip()}")
                            if len(matches) >= _MAX_SEARCH_HITS:
                                break
                except Exception:
                    continue
                if len(matches) >= _MAX_SEARCH_HITS:
                    break

        return ToolResult(
            content="\n".join(matches) if matches else "No matches found."
        )
