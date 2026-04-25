"""
GAAIA Desktop Widget — macOS/Windows/Linux system tray app.

Provides quick-access actions from the menu bar:
  • Analyze My Screen   — screenshot → vision LLM → popup
  • Explain Clipboard   — clipboard text → LLM → popup
  • Open GAAIA          — launch browser to localhost:3000
  • Quit

Requires: pystray + Pillow (both already in pyproject.toml).
Run:  python -m gaaia.desktop.widgets.menu_bar
"""
from __future__ import annotations

import json
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont

GAAIA_API = "http://127.0.0.1:8765"
TOKEN_FILE = Path.home() / ".gaaia" / "widget_token.json"
_token_cache: str | None = None


# ── Auth ──────────────────────────────────────────────────────────────────────

def _load_cached_token() -> str | None:
    try:
        data = json.loads(TOKEN_FILE.read_text())
        return data.get("token")
    except Exception:
        return None


def _save_token(token: str) -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps({"token": token}))


def _get_token() -> str | None:
    global _token_cache
    if _token_cache:
        return _token_cache
    cached = _load_cached_token()
    if cached:
        _token_cache = cached
        return cached
    return None


def _login_dialog() -> str | None:
    """Show a small Tk login dialog and return a token, or None on cancel."""
    result: dict[str, str | None] = {"token": None}
    root = tk.Tk()
    root.title("GAAIA — Sign In")
    root.geometry("320x180")
    root.configure(bg="#0d0d14")
    root.attributes("-topmost", True)
    root.resizable(False, False)

    tk.Label(root, text="GAAIA", fg="#a78bfa", bg="#0d0d14", font=("Helvetica", 16, "bold")).pack(pady=(18, 2))
    tk.Label(root, text="Sign in to use the desktop widget", fg="#666688", bg="#0d0d14", font=("Helvetica", 10)).pack()

    frame = tk.Frame(root, bg="#0d0d14")
    frame.pack(pady=10, padx=20, fill=tk.X)

    tk.Label(frame, text="Username", fg="#888", bg="#0d0d14", font=("Helvetica", 9)).grid(row=0, column=0, sticky="w")
    user_var = tk.StringVar()
    tk.Entry(frame, textvariable=user_var, bg="#1a1a2e", fg="white", insertbackground="white",
             relief=tk.FLAT, font=("Helvetica", 11)).grid(row=1, column=0, sticky="ew", pady=(2, 6))

    tk.Label(frame, text="Password", fg="#888", bg="#0d0d14", font=("Helvetica", 9)).grid(row=2, column=0, sticky="w")
    pass_var = tk.StringVar()
    tk.Entry(frame, textvariable=pass_var, show="•", bg="#1a1a2e", fg="white", insertbackground="white",
             relief=tk.FLAT, font=("Helvetica", 11)).grid(row=3, column=0, sticky="ew", pady=(2, 0))
    frame.columnconfigure(0, weight=1)

    def _submit():
        try:
            resp = requests.post(
                f"{GAAIA_API}/auth/token",
                data={"username": user_var.get(), "password": pass_var.get()},
                timeout=5,
            )
            if resp.ok:
                tok = resp.json().get("access_token") or resp.cookies.get("gaaia_token")
                if tok:
                    result["token"] = tok
                    _save_token(tok)
                    root.destroy()
                    return
        except Exception:
            pass
        tk.Label(frame, text="Login failed", fg="#f87171", bg="#0d0d14", font=("Helvetica", 9)).grid(
            row=4, column=0, sticky="w", pady=(4, 0))

    btn_frame = tk.Frame(root, bg="#0d0d14")
    btn_frame.pack(pady=5)
    tk.Button(btn_frame, text="Sign In", command=_submit, bg="#7c3aed", fg="white",
              activebackground="#6d28d9", relief=tk.FLAT, padx=16, pady=5,
              font=("Helvetica", 10, "bold")).pack(side=tk.LEFT, padx=4)
    tk.Button(btn_frame, text="Cancel", command=root.destroy, bg="#1a1a2e", fg="#888",
              relief=tk.FLAT, padx=12, pady=5, font=("Helvetica", 10)).pack(side=tk.LEFT, padx=4)

    root.mainloop()
    return result["token"]


# ── Response window ───────────────────────────────────────────────────────────

class ResponseWindow:
    def __init__(self, title: str):
        self.root = tk.Tk()
        self.root.title(title)
        self.root.geometry("560x340+120+120")
        self.root.configure(bg="#0d0d14")
        self.root.attributes("-topmost", True)

        header = tk.Frame(self.root, bg="#0d0d14")
        header.pack(fill=tk.X, padx=12, pady=(12, 4))
        tk.Label(header, text="GAAIA", fg="#a78bfa", bg="#0d0d14",
                 font=("Helvetica", 12, "bold")).pack(side=tk.LEFT)
        tk.Label(header, text=f" — {title}", fg="#555577", bg="#0d0d14",
                 font=("Helvetica", 11)).pack(side=tk.LEFT)

        self.text = tk.Text(
            self.root, bg="#0d0d14", fg="#d4d4e8",
            font=("Menlo", 12), wrap=tk.WORD,
            padx=14, pady=10, borderwidth=0, highlightthickness=0,
            insertbackground="#a78bfa",
        )
        scroll = tk.Scrollbar(self.root, command=self.text.yview, bg="#1a1a2e", troughcolor="#0d0d14")
        self.text.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 4), pady=4)
        self.text.pack(fill=tk.BOTH, expand=True, padx=(12, 0), pady=(0, 4))

        btn_frame = tk.Frame(self.root, bg="#0d0d14")
        btn_frame.pack(fill=tk.X, padx=12, pady=(0, 10))
        tk.Button(btn_frame, text="Copy", command=self._copy,
                  bg="#1e1e3a", fg="#a78bfa", activebackground="#2a2a4a",
                  relief=tk.FLAT, padx=12, pady=4, font=("Helvetica", 10)).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(btn_frame, text="Close", command=self.root.destroy,
                  bg="#1e1e3a", fg="#666688", activebackground="#2a2a4a",
                  relief=tk.FLAT, padx=12, pady=4, font=("Helvetica", 10)).pack(side=tk.LEFT)

    def _copy(self):
        content = self.text.get("1.0", tk.END).strip()
        self.root.clipboard_clear()
        self.root.clipboard_append(content)

    def append(self, text: str):
        self.text.insert(tk.END, text)
        self.text.see(tk.END)
        try:
            self.root.update()
        except Exception:
            pass

    def run(self):
        self.root.mainloop()


# ── Action helpers ────────────────────────────────────────────────────────────

def _ensure_token() -> str | None:
    global _token_cache
    tok = _get_token()
    if tok:
        return tok
    tok = _login_dialog()
    if tok:
        _token_cache = tok
    return tok


def _stream_to_window(endpoint: str, payload: dict[str, Any], window_title: str):
    token = _ensure_token()
    if not token:
        return

    win = ResponseWindow(window_title)
    win.append("Thinking…\n\n")

    def _fetch():
        try:
            with requests.post(
                f"{GAAIA_API}{endpoint}",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                cookies={"gaaia_token": token},
                stream=True,
                timeout=120,
            ) as resp:
                if resp.status_code == 401:
                    win.root.after(0, win.append, "\n\nSession expired — please sign in again.")
                    global _token_cache
                    _token_cache = None
                    TOKEN_FILE.unlink(missing_ok=True)
                    return
                for raw_line in resp.iter_lines():
                    line = raw_line if isinstance(raw_line, str) else raw_line.decode("utf-8", errors="replace")
                    if not line.startswith("data: "):
                        continue
                    try:
                        evt = json.loads(line[6:])
                        if evt.get("type") == "token":
                            win.root.after(0, win.append, evt["text"])
                        elif evt.get("type") in ("done", "error"):
                            if evt.get("type") == "error":
                                win.root.after(0, win.append, f"\n\nError: {evt.get('text','')}")
                            break
                    except Exception:
                        pass
        except Exception as exc:
            try:
                win.root.after(0, win.append, f"\n\nFailed to reach GAAIA: {exc}")
            except Exception:
                pass

    threading.Thread(target=_fetch, daemon=True).start()
    win.run()


# ── Menu actions ──────────────────────────────────────────────────────────────

def _capture_screen(_icon: Any, _item: Any):
    threading.Thread(
        target=_stream_to_window,
        args=("/screen/capture", {"question": ""}, "Screen Analysis"),
        daemon=True,
    ).start()


def _explain_clipboard(_icon: Any, _item: Any):
    threading.Thread(
        target=_stream_to_window,
        args=("/screen/clipboard", {"question": ""}, "Clipboard"),
        daemon=True,
    ).start()


def _open_gaaia(_icon: Any, _item: Any):
    webbrowser.open("http://localhost:3000/home")


# ── Icon ──────────────────────────────────────────────────────────────────────

def _make_icon() -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([2, 2, size - 2, size - 2], fill=(124, 58, 237, 255))
    # Draw "G" letter
    d.text((18, 16), "G", fill=(255, 255, 255, 255))
    return img


# ── Entry point ───────────────────────────────────────────────────────────────

def run():
    import pystray

    icon = pystray.Icon(
        name="gaaia",
        icon=_make_icon(),
        title="GAAIA",
        menu=pystray.Menu(
            pystray.MenuItem("Analyze My Screen", _capture_screen),
            pystray.MenuItem("Explain Clipboard", _explain_clipboard),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open GAAIA", _open_gaaia),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda i, _: i.stop()),
        ),
    )
    icon.run()


if __name__ == "__main__":
    run()
