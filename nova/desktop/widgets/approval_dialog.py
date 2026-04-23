from __future__ import annotations

import threading

import customtkinter as ctk

from nova.approval.manager import ApprovalRequest

_BG      = "#12131b"
_BTN_YES = "#7dd3fc"
_BTN_NO  = "#223046"
_RED     = "#ef4444"
_AMBER   = "#f59e0b"
_GREEN   = "#10b981"
_RISK_COLOURS = {"high": _RED, "medium": _AMBER, "low": _GREEN}

_FONT_TITLE = ("SF Pro Display", 15, "bold")
_FONT_BODY  = ("SF Pro Display", 13)
_FONT_META  = ("SF Pro Display", 11)


class ApprovalDialog(ctk.CTkToplevel):
    """
    Modal confirmation dialog shown when a tool requires user approval.

    Runs in the main thread (created via app.after(0, ...)).
    The calling background thread waits on a threading.Event and reads the result.
    """

    def __init__(self, parent, request: ApprovalRequest) -> None:
        super().__init__(parent)
        self._result = False
        self._event = threading.Event()

        self.title("Confirmation Required")
        self.geometry("420x240")
        self.resizable(False, False)
        self.configure(fg_color=_BG)
        self.grab_set()
        self.lift()
        self.focus_force()
        self.protocol("WM_DELETE_WINDOW", self._deny)

        self._build(request)

    # ── Layout ────────────────────────────────────────────────────────

    def _build(self, req: ApprovalRequest) -> None:
        risk_colour = _RISK_COLOURS.get(req.risk_level, _AMBER)

        # Description
        ctk.CTkLabel(
            self, text=req.description,
            font=_FONT_TITLE, text_color="#e2e8f0",
            wraplength=380,
        ).pack(padx=24, pady=(20, 6))

        # Tool name + risk badge
        meta_frame = ctk.CTkFrame(self, fg_color="transparent")
        meta_frame.pack(padx=24, pady=(0, 4))

        ctk.CTkLabel(
            meta_frame,
            text=f"Tool: {req.tool_name}",
            font=_FONT_META, text_color="#94a3b8",
        ).pack(side="left", padx=(0, 10))

        ctk.CTkLabel(
            meta_frame,
            text=req.risk_level.upper(),
            font=_FONT_META, text_color=risk_colour,
        ).pack(side="left")

        # Args preview (truncated)
        if req.tool_input:
            preview = str(req.tool_input)
            if len(preview) > 80:
                preview = preview[:77] + "…"
            ctk.CTkLabel(
                self, text=preview,
                font=_FONT_META, text_color="#64748b",
                wraplength=380,
            ).pack(padx=24, pady=(0, 12))

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=(8, 20))

        ctk.CTkButton(
            btn_frame, text="Allow", width=120, height=36,
            fg_color=_BTN_YES, hover_color="#38bdf8",
            font=_FONT_BODY, command=self._approve,
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            btn_frame, text="Deny", width=120, height=36,
            fg_color=_BTN_NO, hover_color="#334155",
            font=_FONT_BODY, command=self._deny,
        ).pack(side="left", padx=8)

    # ── Actions ───────────────────────────────────────────────────────

    def _approve(self) -> None:
        self._result = True
        self._event.set()
        self.destroy()

    def _deny(self) -> None:
        self._result = False
        self._event.set()
        self.destroy()

    def wait_result(self, timeout: float = 60.0) -> bool:
        """Block the calling thread until the user decides. Safe to call from any thread."""
        self._event.wait(timeout=timeout)
        return self._result
