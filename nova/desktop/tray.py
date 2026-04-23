from __future__ import annotations

from collections.abc import Callable

from PIL import Image, ImageDraw


def _make_icon(size: int = 64, color: str = "#7dd3fc") -> Image.Image:
    """Generate a simple circular Nova tray icon programmatically."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
    draw.ellipse([2, 2, size - 2, size - 2], fill=(r, g, b, 255))

    # Simple "N" glyph
    m = size // 2
    s = size // 5
    draw.line([(m - s, m - s), (m - s, m + s)], fill=(255, 255, 255, 220), width=3)
    draw.line([(m - s, m - s), (m + s, m + s)], fill=(255, 255, 255, 220), width=3)
    draw.line([(m + s, m - s), (m + s, m + s)], fill=(255, 255, 255, 220), width=3)

    return img


class TrayIcon:
    """
    macOS system-tray icon via pystray.
    Runs in a daemon thread. Completely optional — the app works without it.
    """

    def __init__(
        self,
        on_show: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._on_show = on_show
        self._on_quit = on_quit
        self._icon = None

    def start(self) -> None:
        try:
            import pystray

            menu = pystray.Menu(
                pystray.MenuItem("Show Nova", self._show, default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", self._quit),
            )
            self._icon = pystray.Icon(
                "Nova", _make_icon(), "Nova", menu
            )
            # run_detached() doesn't require the main thread — safe alongside Tk
            self._icon.run_detached()
        except Exception:
            pass  # tray is optional; silently skip if unavailable

    def stop(self) -> None:
        try:
            if self._icon:
                self._icon.stop()
        except Exception:
            pass

    def _show(self, icon=None, item=None) -> None:
        self._on_show()

    def _quit(self, icon=None, item=None) -> None:
        self._on_quit()
