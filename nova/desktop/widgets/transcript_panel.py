from __future__ import annotations

import re
import textwrap
import tkinter as tk

import customtkinter as ctk

# ── Palette ───────────────────────────────────────────────────────────
_BG = "#0b0f16"
_USER_BG = "#1b2a3d"
_USER_FG = "#e5eef8"
_NOVA_FG = "#e5eef8"
_NOVA_MUTED = "#9fb0c2"
_MUTED = "#7f8ea3"
_ACCENT = "#7dd3fc"
_CODE_BG = "#0f141b"
_CODE_BORDER = "#1f2d3d"
_CODE_FG = "#dbeafe"
_CODE_DIM = "#93a4b8"
_INLINE_BG = "#162033"
_INLINE_FG = "#9fd4ff"
_FONT_MSG = ("SF Pro Display", 14)
_FONT_LABEL = ("SF Pro Display", 11)
_FONT_CODE = ("SF Mono", 12)
_FONT_STRONG = ("SF Pro Display", 14, "bold")
_FONT_H1 = ("SF Pro Display", 18, "bold")
_FONT_H2 = ("SF Pro Display", 16, "bold")
_FONT_H3 = ("SF Pro Display", 15, "bold")

_CODE_BLOCK_RE = re.compile(r"```([a-zA-Z0-9_+-]*)\n(.*?)```", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$")
_BULLET_RE = re.compile(r"^([\s\t]*)([-*+])\s+(.*)$")
_NUMBER_RE = re.compile(r"^([\s\t]*)(\d+)[\.)]\s+(.*)$")
_QUOTE_RE = re.compile(r"^\s*>\s?(.*)$")
_INLINE_RE = re.compile(r"(`[^`]+`|\*\*[^*]+\*\*|__[^_]+__)")


class TranscriptPanel(ctk.CTkScrollableFrame):
    """Scrollable transcript with a simple ChatGPT-style layout."""

    def __init__(self, parent: ctk.CTkFrame, **kwargs) -> None:
        super().__init__(
            parent,
            fg_color=_BG,
            scrollbar_button_color="#233244",
            scrollbar_button_hover_color="#31465e",
            **kwargs,
        )
        self._entries: list[ctk.CTkFrame] = []
        self.grid_columnconfigure(0, weight=1)

    def add_message(self, role: str, text: str) -> None:
        if role == "user":
            self._add_user_message(text)
        else:
            self._add_assistant_message(text)

    def add_assistant_response(self, text: str, boxed: bool = False) -> None:
        self._add_assistant_message(text)

    def _add_user_message(self, text: str) -> None:
        row = len(self._entries)
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.grid(row=row, column=0, sticky="ew", padx=10, pady=(6, 4))
        outer.grid_columnconfigure(0, weight=1)

        bubble = ctk.CTkFrame(
            outer,
            fg_color=_USER_BG,
            corner_radius=14,
        )
        bubble.grid(row=0, column=0, sticky="e", padx=(120, 8))
        bubble.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            bubble,
            text=text,
            text_color=_USER_FG,
            font=_FONT_MSG,
            wraplength=320,
            justify="left",
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=10)

        self._entries.append(outer)
        self._scroll_to_bottom()

    def _add_assistant_message(self, text: str) -> None:
        row = len(self._entries)
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.grid(row=row, column=0, sticky="ew", padx=10, pady=(8, 6))
        outer.grid_columnconfigure(1, weight=1)

        avatar = ctk.CTkLabel(
            outer,
            text="N",
            width=28,
            height=28,
            fg_color="#122033",
            text_color=_ACCENT,
            corner_radius=14,
            font=("SF Pro Display", 13, "bold"),
        )
        avatar.grid(row=0, column=0, sticky="nw", padx=(2, 10), pady=2)

        content = ctk.CTkFrame(outer, fg_color="transparent")
        content.grid(row=0, column=1, sticky="ew")
        content.grid_columnconfigure(0, weight=1)

        self._render_response_body(content, text)
        self._entries.append(outer)
        self._scroll_to_bottom()

    def _render_response_body(self, parent: ctk.CTkFrame, text: str) -> None:
        segments = self._split_segments(text)
        row = 0
        for kind, payload in segments:
            if kind == "text":
                for block in self._split_prose_blocks(self._normalize_text(payload)):
                    self._render_prose_block(parent, block, row)
                    row += 1
            else:
                language, code = payload
                self._render_code_block(parent, code, language, row)
                row += 1

    def _split_segments(self, text: str) -> list[tuple[str, str | tuple[str, str]]]:
        text = text.replace("\r\n", "\n")
        segments: list[tuple[str, str | tuple[str, str]]] = []
        last_index = 0
        for match in _CODE_BLOCK_RE.finditer(text):
            start, end = match.span()
            if start > last_index:
                segments.append(("text", text[last_index:start]))
            language = match.group(1).strip()
            code = self._normalize_code_block(match.group(2))
            segments.append(("code", (language, code)))
            last_index = end
        if last_index < len(text):
            segments.append(("text", text[last_index:]))
        if not segments:
            segments.append(("text", text))
        return segments

    def _normalize_text(self, text: str) -> str:
        return text.strip()

    def _normalize_code_block(self, code: str) -> str:
        cleaned = code.replace("\r\n", "\n").rstrip()
        cleaned = textwrap.dedent(cleaned)
        cleaned = cleaned.lstrip("\n")
        return cleaned.expandtabs(4)

    def _split_prose_blocks(self, text: str) -> list[str]:
        blocks: list[str] = []
        current: list[str] = []
        for line in text.splitlines():
            if not line.strip():
                if current:
                    blocks.append("\n".join(current).strip())
                    current = []
                continue
            current.append(line)
        if current:
            blocks.append("\n".join(current).strip())
        return blocks or ([text] if text else [])

    def _estimate_prose_height(self, text: str) -> int:
        lines = text.splitlines() or [text]
        height = 1
        for line in lines:
            stripped = line.strip()
            if not stripped:
                height += 1
                continue
            if _HEADING_RE.match(stripped):
                height += 2
                continue
            if _QUOTE_RE.match(stripped) or _BULLET_RE.match(stripped) or _NUMBER_RE.match(stripped):
                height += max(1, (len(stripped) + 34) // 42)
                continue
            height += max(1, (len(stripped) + 48) // 52)
        return min(18, max(2, height))

    def _render_prose_block(self, parent: ctk.CTkFrame, text: str, row: int) -> None:
        block = tk.Text(
            parent,
            height=self._estimate_prose_height(text),
            bg=_BG,
            fg=_NOVA_FG,
            insertbackground=_NOVA_FG,
            borderwidth=0,
            highlightthickness=0,
            padx=0,
            pady=0,
            wrap="word",
            font=_FONT_MSG,
        )
        block.grid(row=row, column=0, sticky="ew", padx=0, pady=(0 if row == 0 else 4, 4))
        block.grid_columnconfigure = None
        block.tag_configure("strong", font=_FONT_STRONG, foreground=_ACCENT)
        block.tag_configure("h1", font=_FONT_H1, foreground=_ACCENT, spacing1=6, spacing3=6)
        block.tag_configure("h2", font=_FONT_H2, foreground=_ACCENT, spacing1=5, spacing3=5)
        block.tag_configure("h3", font=_FONT_H3, foreground=_ACCENT, spacing1=4, spacing3=4)
        block.tag_configure("bullet", lmargin1=18, lmargin2=24)
        block.tag_configure("number", lmargin1=18, lmargin2=28)
        block.tag_configure("quote", foreground=_CODE_DIM, lmargin1=18, lmargin2=24)
        block.tag_configure("inline_code", font=_FONT_CODE, foreground=_INLINE_FG, background=_INLINE_BG)

        for line in text.splitlines() or [text]:
            if not line.strip():
                block.insert("end", "\n")
                continue

            heading = _HEADING_RE.match(line)
            if heading:
                level = len(heading.group(1))
                rendered = heading.group(2).strip()
                tag = "h1" if level == 1 else "h2" if level == 2 else "h3"
                self._insert_marked_text(block, rendered, tag=tag)
                block.insert("end", "\n")
                continue

            quote = _QUOTE_RE.match(line)
            if quote:
                block.insert("end", "▌ ", ("quote",))
                self._insert_marked_text(block, quote.group(1).strip(), tag="quote")
                block.insert("end", "\n")
                continue

            bullet = _BULLET_RE.match(line)
            if bullet:
                block.insert("end", "• ", ("bullet",))
                self._insert_marked_text(block, bullet.group(3).strip(), tag="bullet")
                block.insert("end", "\n")
                continue

            number = _NUMBER_RE.match(line)
            if number:
                block.insert("end", f"{number.group(2)}. ", ("number",))
                self._insert_marked_text(block, number.group(3).strip(), tag="number")
                block.insert("end", "\n")
                continue

            self._insert_marked_text(block, line.strip())
            block.insert("end", "\n")

        block.configure(state="disabled")

    def _insert_marked_text(self, widget: tk.Text, text: str, tag: str | None = None) -> None:
        cursor = 0
        for match in _INLINE_RE.finditer(text):
            start, end = match.span()
            if start > cursor:
                widget.insert("end", text[cursor:start], (tag,) if tag else ())
            token = match.group(1)
            if token.startswith("`"):
                widget.insert("end", token.strip("`"), ("inline_code",))
            else:
                widget.insert("end", token.strip("*_"), ("strong",))
            cursor = end
        if cursor < len(text):
            widget.insert("end", text[cursor:], (tag,) if tag else ())

    def _render_code_block(self, parent: ctk.CTkFrame, code: str, language: str, row: int) -> None:
        block = ctk.CTkFrame(
            parent,
            fg_color=_CODE_BG,
            border_color=_CODE_BORDER,
            border_width=1,
            corner_radius=10,
        )
        block.grid(row=row, column=0, sticky="ew", pady=(4, 8))
        block.grid_columnconfigure(1, weight=1)

        topbar = ctk.CTkFrame(block, fg_color=_CODE_BG, corner_radius=0)
        topbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        topbar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            topbar,
            text=language or "code",
            text_color=_CODE_DIM,
            font=("SF Pro Display", 10),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(8, 6))

        ctk.CTkButton(
            topbar,
            text="Copy",
            width=52,
            height=22,
            fg_color="#1f2937",
            hover_color="#2a3b52",
            text_color=_CODE_DIM,
            font=("SF Pro Display", 10),
            corner_radius=7,
            command=lambda: self._copy_to_clipboard(code),
        ).grid(row=0, column=1, sticky="e", padx=10, pady=(6, 4))

        editor = tk.Text(
            block,
            height=max(1, min(20, len(code.splitlines()) or 1)),
            bg=_CODE_BG,
            fg=_CODE_FG,
            insertbackground=_CODE_FG,
            borderwidth=0,
            highlightthickness=0,
            padx=10,
            pady=10,
            wrap="none",
            font=_FONT_CODE,
        )
        editor.grid(row=1, column=0, columnspan=2, sticky="nsew")
        editor.insert("1.0", code)
        editor.configure(state="disabled")

    def clear(self) -> None:
        for widget in self._entries:
            widget.destroy()
        self._entries.clear()

    def _copy_to_clipboard(self, text: str) -> None:
        try:
            self.winfo_toplevel().clipboard_clear()
            self.winfo_toplevel().clipboard_append(text)
            self.winfo_toplevel().update()
        except Exception:
            pass

    def _scroll_to_bottom(self) -> None:
        self.after(60, lambda: self._parent_canvas.yview_moveto(1.0))
