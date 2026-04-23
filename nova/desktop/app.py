from __future__ import annotations

import asyncio
import random
import re
import threading
from collections.abc import Callable

import customtkinter as ctk

from config.settings import Settings
from nova.agent.orchestrator import Orchestrator
from nova.approval.manager import ApprovalRequest
from nova.desktop.tray import TrayIcon
from nova.desktop.widgets.approval_dialog import ApprovalDialog
from nova.desktop.widgets.status_bar import StatusBar
from nova.desktop.widgets.transcript_panel import TranscriptPanel
from nova.voice.pipeline import VoicePipeline

# ── Palette ───────────────────────────────────────────────────────────
_WIN_BG    = "#0e0e1a"
_HEADER_BG = "#12121f"
_INPUT_BG  = "#12121f"
_ACCENT    = "#7dd3fc"
_SEND_HVR  = "#38bdf8"
_BORDER    = "#1b2536"
_FG        = "#e2e8f0"
_MUTED     = "#64748b"
_FONT_HDR  = ("SF Pro Display", 15, "bold")
_FONT_IN   = ("SF Pro Display", 14)
_FONT_HINT = ("SF Pro Display", 11)

_GREETINGS: list[tuple[str, str]] = [
    (
        "Nova's up.",
        "Nova's up.",
    ),
    (
        "Ready.",
        "Ready.",
    ),
    (
        "What next?",
        "What next?",
    ),
    (
        "Listening.",
        "Listening.",
    ),
    (
        "Let's go.",
        "Let's go.",
    ),
]

_LONG_FORM_HINTS = re.compile(
    r"\b(code|python|javascript|typescript|sql|essay|write\s+an\s+essay|sketch|draft|outline|report|proposal|summary|table|list)\b",
    re.IGNORECASE,
)


class NovaApp(ctk.CTk):
    """
    Main desktop window for Nova.

    Layout:
      ┌─ header (title + model badge) ──────────────────────┐
      ├─ transcript (scrollable conversation) ──────────────┤
      ├─ status bar (idle / recording / thinking / speaking) ┤
      ├─ text input + send button ──────────────────────────┤
      └─────────────────────────────────────────────────────┘

    All UI mutations happen on the main thread via self.after(0, fn).
    Voice pipeline callbacks bridge from background threads using that pattern.
    """

    def __init__(
        self,
        settings: Settings,
        orchestrator: Orchestrator,
        session_id: str,
        pipeline: "VoicePipeline | None" = None,
    ) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        super().__init__()

        self._settings = settings
        self._orchestrator = orchestrator
        self._session_id = session_id

        ui = settings.ui
        win = ui.get("window", {})

        self._setup_window(win, ui)
        self._build_ui()
        self._setup_voice_pipeline(pipeline)
        # Share the pipeline's TTS so voice and text use the same instance
        self._tts = self._pipeline._tts
        self._setup_tray()

        if self._settings.voice.get("auto_listen_on_start", True):
            self._mic_active = True
            self._status.set_listening_mode(True)
            self.after(300, self._start_live_listening)
        else:
            self._status.set_listening_mode(False)

        # Greet the user
        self.after(600, self._greet)

    # ── Window setup ─────────────────────────────────────────────────

    def _setup_window(self, win: dict, ui: dict) -> None:
        self.title("Nova")
        w, h = win.get("width", 480), win.get("height", 720)
        self.geometry(f"{w}x{h}")
        self.minsize(400, 500)
        self.configure(fg_color=_WIN_BG)
        self.attributes("-topmost", win.get("always_on_top", False))
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)  # transcript expands

    # ── UI construction ───────────────────────────────────────────────

    def _build_ui(self) -> None:
        self._build_header()
        self._build_transcript()
        self._build_status_bar()
        self._build_input_area()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color=_HEADER_BG, corner_radius=0, height=52)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        header.grid_propagate(False)

        # Accent dot + name
        ctk.CTkLabel(
            header, text="●", text_color=_ACCENT,
            font=("SF Pro Display", 14), width=20,
        ).grid(row=0, column=0, padx=(16, 6), pady=14)

        ctk.CTkLabel(
            header, text="Nova", text_color=_FG,
            font=_FONT_HDR, anchor="w",
        ).grid(row=0, column=1, sticky="w")

        m = self._settings.model
        _model_options = list(dict.fromkeys(filter(None, [
            m.get("name"), m.get("fast_model"), m.get("heavy_model"), m.get("code_model"),
        ])))
        self._model_var = ctk.StringVar(value=m.get("name", _model_options[0]))
        ctk.CTkOptionMenu(
            header,
            values=_model_options,
            variable=self._model_var,
            command=self._on_model_change,
            fg_color="#111827",
            button_color=_ACCENT,
            button_hover_color=_SEND_HVR,
            text_color=_MUTED,
            font=_FONT_HINT,
            width=160,
            height=28,
            corner_radius=6,
            dynamic_resizing=False,
        ).grid(row=0, column=2, padx=(0, 16), sticky="e")

    def _on_model_change(self, model_name: str) -> None:
        self._orchestrator.set_active_model(model_name)
        self._transcript.add_message("nova", f"Switched to {model_name}.")

    def _build_transcript(self) -> None:
        self._transcript = TranscriptPanel(self)
        self._transcript.grid(
            row=1, column=0, sticky="nsew", padx=0, pady=0,
        )

    def _build_status_bar(self) -> None:
        # Thin divider
        ctk.CTkFrame(self, fg_color=_BORDER, height=1, corner_radius=0).grid(
            row=2, column=0, sticky="ew"
        )
        self._status = StatusBar(self)
        self._status.grid(row=3, column=0, sticky="ew")

    def _build_input_area(self) -> None:
        # Thin divider
        ctk.CTkFrame(self, fg_color=_BORDER, height=1, corner_radius=0).grid(
            row=4, column=0, sticky="ew"
        )
        input_frame = ctk.CTkFrame(self, fg_color=_INPUT_BG, corner_radius=0)
        input_frame.grid(row=5, column=0, sticky="ew", padx=0)
        input_frame.grid_columnconfigure(1, weight=1)

        self._mic_active = False

        self._mic_btn = ctk.CTkButton(
            input_frame,
            text="🎙",
            width=40, height=40,
            fg_color="#111827", hover_color="#1f2937",
            border_width=1, border_color=_BORDER,
            font=("SF Pro Display", 18), corner_radius=8,
            command=self._on_mic_toggle,
        )
        self._mic_btn.grid(row=0, column=0, padx=(12, 6), pady=12, sticky="w")

        self._input = ctk.CTkEntry(
            input_frame,
            placeholder_text="Type a message…",
            fg_color="#111827",
            border_color=_BORDER,
            text_color=_FG,
            placeholder_text_color=_MUTED,
            font=_FONT_IN,
            height=40,
            corner_radius=8,
        )
        self._input.grid(row=0, column=1, padx=(0, 6), pady=12, sticky="ew")
        self._input.bind("<Return>", self._on_enter)

        ctk.CTkButton(
            input_frame,
            text="Send",
            width=70, height=40,
            fg_color=_ACCENT, hover_color=_SEND_HVR,
            font=_FONT_IN, corner_radius=8,
            command=self._on_send,
        ).grid(row=0, column=2, padx=(0, 12), pady=12)

    # ── Mic button ───────────────────────────────────────────────────

    def _on_mic_toggle(self) -> None:
        if not self._mic_active:
            self._mic_active = True
            self._mic_btn.configure(fg_color="#0f172a", hover_color="#1e293b", text="⏹")
            self._status.set_listening_mode(True)
            self._start_live_listening()
        else:
            self._mic_active = False
            self._mic_btn.configure(fg_color="#111827", hover_color="#1f2937", text="🎙")
            self._status.set_listening_mode(False)
            self._pipeline.stop_live_conversation()
            self._transcript.add_message("nova", "Live voice mode off.")

    def _start_live_listening(self) -> None:
        self._tts.stop()
        self._transcript.add_message("nova", "Live voice mode on. I'm listening.")
        self._pipeline.start_live_conversation()

    # ── Voice pipeline ────────────────────────────────────────────────

    def _setup_voice_pipeline(self, pipeline: "VoicePipeline | None" = None) -> None:
        # Accept a pre-built pipeline (Whisper must be loaded before Cocoa/tkinter)
        if pipeline is None:
            pipeline = VoicePipeline(
                settings=self._settings,
                orchestrator=self._orchestrator,
                session_id=self._session_id,
                approval_callback=self._request_approval,
            )
        else:
            pipeline._session_id = self._session_id
            pipeline._approval_callback = self._request_approval

        self._pipeline = pipeline
        self._pipeline.on_state_change   = self._on_state_change
        self._pipeline.on_status         = self._on_pipeline_status
        self._pipeline.on_transcript     = self._on_transcript
        self._pipeline.on_response_chunk = self._on_response_chunk
        self._pipeline.on_response_done  = self._on_response_done
        self._pipeline.on_error          = self._on_pipeline_error

        self._response_buffer: list[str] = []
        self._pipeline.start()

    # ── Approval bridge ───────────────────────────────────────────────

    def _request_approval(self, request: ApprovalRequest) -> bool:
        """
        Called from a background thread when a tool needs confirmation.
        Schedules the dialog on the main thread and blocks until the user decides.
        """
        result: list[bool] = [False]
        ready = threading.Event()

        def show() -> None:
            dialog = ApprovalDialog(self, request)
            result[0] = dialog.wait_result()
            ready.set()

        self.after(0, show)
        ready.wait(timeout=60)
        return result[0]

    # ── Pipeline callbacks (all arrive from background threads) ───────

    def _on_state_change(self, state: str) -> None:
        self.after(0, lambda: self._status.set_state(state))

    def _on_pipeline_status(self, text: str) -> None:
        self.after(0, lambda: self._status.set_detail(text))

    def _on_transcript(self, text: str) -> None:
        self.after(0, lambda: self._transcript.add_message("user", text))

    def _on_response_chunk(self, chunk: str) -> None:
        self._response_buffer.append(chunk)

    def _on_response_done(self, full_text: str) -> None:
        self._response_buffer.clear()
        self.after(0, lambda: self._transcript.add_assistant_response(full_text, boxed=True))

    def _on_pipeline_error(self, message: str) -> None:
        self.after(0, lambda: self._status.set_state("idle"))
        self.after(0, lambda: self._status.set_detail(message))
        self.after(0, lambda: self._transcript.add_message("nova", f"[Voice error] {message}"))

    # ── Text input ────────────────────────────────────────────────────

    _STOP_RE = re.compile(
        r"^\s*(shut\s+up|stop(\s+talking|\s+speaking)?|be\s+quiet|quiet|silence|shush|enough|ok+ay?\s+stop|wait(\s+please)?|pause|hold\s+on)\s*[.!]?\s*$",
        re.IGNORECASE,
    )

    def _on_enter(self, event=None) -> None:
        self._on_send()

    def _on_send(self) -> None:
        text = self._input.get().strip()
        if not text:
            return
        self._input.delete(0, "end")
        if self._STOP_RE.match(text):
            self._tts.stop()
            self._status.set_state("idle")
            return
        self._tts.stop()
        self._transcript.add_message("user", text)
        self._status.set_state("thinking")
        threading.Thread(
            target=self._process_text, args=(text,), daemon=True
        ).start()

    def _process_text(self, text: str) -> None:
        chunks: list[str] = []

        def collect(chunk: str) -> None:
            chunks.append(chunk)

        try:
            response = asyncio.run(
                self._orchestrator.run(
                    user_message=text,
                    session_id=self._session_id,
                    stream_callback=collect,
                    approval_callback=self._request_approval,
                )
            )
        except Exception as exc:
            response = f"[Error: {exc}]"

        # Fallback: if orchestrator returned empty string, use streamed chunks
        if not response and chunks:
            response = "".join(chunks)

        self.after(0, lambda: self._transcript.add_assistant_response(response, boxed=True))
        self.after(0, lambda: self._status.set_state("idle"))

    # ── Greeting ──────────────────────────────────────────────────────

    def _greet(self) -> None:
        transcript_text, spoken_text = random.choice(_GREETINGS)
        self._transcript.add_message("nova", transcript_text)
        threading.Thread(
            target=lambda: self._tts.speak(spoken_text),
            daemon=True,
        ).start()

    # ── Tray ─────────────────────────────────────────────────────────

    def _setup_tray(self) -> None:
        self._tray = TrayIcon(on_show=self._show_window, on_quit=self._quit)
        self._tray.start()

    def _show_window(self) -> None:
        self.after(0, lambda: (self.deiconify(), self.lift(), self.focus_force()))

    def _hide_to_tray(self) -> None:
        self.withdraw()

    # ── Lifecycle ─────────────────────────────────────────────────────

    def _on_close(self) -> None:
        self._status.set_listening_mode(False)
        self._hide_to_tray()

    def _quit(self) -> None:
        self._pipeline.stop()
        self._tts.stop()
        self._tray.stop()
        self.after(0, self.destroy)

    def run(self) -> None:
        self.mainloop()

