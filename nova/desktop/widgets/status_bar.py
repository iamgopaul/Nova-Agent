from __future__ import annotations

import customtkinter as ctk

_STATES: dict[str, tuple[str, str, str]] = {
    #            icon   colour     label
    "idle":      ("○",  "#4b5563", "Ready — hold Ctrl+Space to speak"),
    "recording": ("●",  "#ef4444", "Listening…"),
    "thinking":  ("◌",  "#f59e0b", "Thinking…"),
    "speaking":  ("▶",  "#7dd3fc", "Speaking…"),
}

_BG       = "#0a0f18"
_DIVIDER  = "#1b2536"
_FONT_DOT = ("SF Pro Display", 16, "bold")
_FONT_LBL = ("SF Pro Display", 13)
_FONT_BADGE = ("SF Pro Display", 10, "bold")


class StatusBar(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkFrame, **kwargs) -> None:
        super().__init__(parent, fg_color=_BG, corner_radius=0, **kwargs)
        self.grid_columnconfigure(1, weight=1)

        self._dot = ctk.CTkLabel(
            self, text="○", text_color="#4b5563",
            font=_FONT_DOT, width=24,
        )
        self._dot.grid(row=0, column=0, padx=(16, 6), pady=12)

        self._label = ctk.CTkLabel(
            self, text="Ready — hold Ctrl+Space to speak",
            text_color="#cbd5e1", font=_FONT_LBL, anchor="w",
        )
        self._label.grid(row=0, column=1, sticky="w", pady=12, padx=(0, 16))

        self._mode_badge = ctk.CTkLabel(
            self,
            text="LISTENING OFF",
            text_color="#93c5fd",
            fg_color="#111827",
            corner_radius=999,
            font=_FONT_BADGE,
            padx=10,
            pady=4,
        )
        self._mode_badge.grid(row=0, column=2, sticky="e", padx=(0, 16), pady=12)

    def set_state(self, state: str) -> None:
        icon, colour, text = _STATES.get(state, _STATES["idle"])
        self._dot.configure(text=icon, text_color=colour)
        self._label.configure(text=text)

    def set_detail(self, text: str) -> None:
        detail = (text or "").strip()
        if detail:
            self._label.configure(text=detail)

    def set_listening_mode(self, active: bool) -> None:
        if active:
            self._mode_badge.configure(text="LISTENING ON", text_color="#86efac", fg_color="#052e16")
        else:
            self._mode_badge.configure(text="LISTENING OFF", text_color="#93c5fd", fg_color="#111827")
