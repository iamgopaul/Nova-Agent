from __future__ import annotations

import ctypes
import ctypes.util
import threading
from collections.abc import Callable

from pynput import keyboard as kb


def _is_accessibility_trusted() -> bool:
    """Return True if this process has macOS Accessibility permission."""
    try:
        lib = ctypes.cdll.LoadLibrary(
            ctypes.util.find_library("ApplicationServices") or ""
        )
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(lib.AXIsProcessTrusted())
    except Exception:
        return True  # non-macOS or API unavailable — assume ok

# Maps config key names → sets of pynput Key variants
_MODIFIERS: dict[str, set] = {
    "ctrl":  {kb.Key.ctrl,  kb.Key.ctrl_l,  kb.Key.ctrl_r},
    "alt":   {kb.Key.alt,   kb.Key.alt_l,   kb.Key.alt_r},
    "shift": {kb.Key.shift, kb.Key.shift_l, kb.Key.shift_r},
    "cmd":   {kb.Key.cmd,   kb.Key.cmd_l,   kb.Key.cmd_r},
}

_SPECIALS: dict[str, kb.Key] = {
    "space": kb.Key.space,
    "esc":   kb.Key.esc,
    "enter": kb.Key.enter,
    "tab":   kb.Key.tab,
    **{f"f{n}": getattr(kb.Key, f"f{n}") for n in range(1, 13)},
}


def _parse(hotkey_str: str) -> list[set]:
    """
    Parse '<ctrl>+<space>' → [{'ctrl variants'}, {Key.space}].
    Each group is a set of pynput keys that count as "that slot".
    """
    groups: list[set] = []
    for part in hotkey_str.split("+"):
        part = part.strip().strip("<>").lower()
        if part in _MODIFIERS:
            groups.append(_MODIFIERS[part])
        elif part in _SPECIALS:
            groups.append({_SPECIALS[part]})
        else:
            groups.append({kb.KeyCode.from_char(part)})
    return groups


class PTTListener:
    """
    Global push-to-talk listener.

    on_activate fires when ALL hotkey keys are held down simultaneously.
    on_deactivate fires when ANY key in the combo is released.

    Both callbacks run in a short-lived daemon thread so they can do
    blocking work (recording, inference) without blocking the key listener.

    NOTE: macOS requires Accessibility permission for pynput.
    System Settings → Privacy & Security → Accessibility → add Terminal.app
    """

    def __init__(self, hotkey_str: str = "<ctrl>+<space>") -> None:
        self._groups = _parse(hotkey_str)
        self._pressed: set[int] = set()   # indices of currently-held groups
        self._active = False
        self._on_activate: Callable[[], None] | None = None
        self._on_deactivate: Callable[[], None] | None = None
        self._listener: kb.Listener | None = None

    def start(
        self,
        on_activate: Callable[[], None],
        on_deactivate: Callable[[], None],
    ) -> None:
        self._on_activate = on_activate
        self._on_deactivate = on_deactivate
        if not _is_accessibility_trusted():
            print(
                "\n[GAIA] Push-to-talk disabled — Accessibility permission not granted.\n"
                "  To enable voice: System Settings → Privacy & Security → Accessibility\n"
                "  → add Terminal.app (or your terminal), then restart GAAIA.\n"
                "  Mic button live voice mode still works in the meantime.\n"
            )
            return
        try:
            self._listener = kb.Listener(
                on_press=self._on_press,
                on_release=self._on_release,
            )
            self._listener.daemon = True
            self._listener.start()
        except Exception as exc:
            print(f"\n[GAIA] Hotkey listener error: {exc} — text input still works.\n")

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()

    # ── Internals ────────────────────────────────────────────────────

    def _slot(self, key) -> int | None:
        """Return the group index that `key` belongs to, or None."""
        for i, group in enumerate(self._groups):
            if key in group:
                return i
        return None

    def _on_press(self, key: kb.Key) -> None:
        idx = self._slot(key)
        if idx is not None:
            self._pressed.add(idx)
        if len(self._pressed) >= len(self._groups) and not self._active:
            self._active = True
            if self._on_activate:
                threading.Thread(target=self._on_activate, daemon=True).start()

    def _on_release(self, key: kb.Key) -> None:
        idx = self._slot(key)
        was_active = self._active
        if idx is not None:
            self._pressed.discard(idx)
        if was_active and len(self._pressed) < len(self._groups):
            self._active = False
            if self._on_deactivate:
                threading.Thread(target=self._on_deactivate, daemon=True).start()
