"""
tray_controller.py
------------------
System tray icon and menu using pystray.

Menu items:
  • FocusGuard — Status: Running  (disabled label)
  • ─────────────────────────────
  • Open Today's Digest
  • Open Application Log
  • ─────────────────────────────
  • Webcam: ON  /  Webcam: OFF    (toggle)
  • ─────────────────────────────
  • Quit
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

import pystray
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Icon generation (runtime — no PNG files needed)
# ---------------------------------------------------------------------------

def _make_icon(color: str = "#4CAF50", size: int = 64) -> Image.Image:
    """Generate a simple square icon with a rounded feel."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = 4
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=color,
    )
    return img


_ICON_ACTIVE = _make_icon("#4CAF50")      # green  — running normally
_ICON_WEBCAM_OFF = _make_icon("#FF9800")  # amber  — webcam toggled off
_ICON_ERROR = _make_icon("#F44336")       # red    — webcam unavailable


# ---------------------------------------------------------------------------
# TrayController
# ---------------------------------------------------------------------------

class TrayController:
    """
    Manages the pystray icon and menu.
    Runs pystray.Icon.run() on the main thread (required on macOS).
    """

    def __init__(
        self,
        config: dict,
        on_webcam_toggle: Callable[[bool], None],
        on_quit: Callable[[], None],
        on_open_digest: Optional[Callable[[], None]] = None,
        on_open_log: Optional[Callable[[], None]] = None,
    ) -> None:
        self._config = config
        self._on_webcam_toggle = on_webcam_toggle
        self._on_quit = on_quit
        self._on_open_digest = on_open_digest
        self._on_open_log = on_open_log

        self._webcam_enabled: bool = config.get("webcam_enabled", True)
        self._has_error: bool = False
        self._status_text: str = "Running"
        self._notification_lock = threading.Lock()

        self._icon: Optional[pystray.Icon] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> None:
        """
        Build and run the tray icon. Blocks the calling thread (main thread).
        Call this last in main.py after all other components are started.
        """
        self._icon = pystray.Icon(
            name="FocusGuard",
            icon=self._current_icon(),
            title=self._current_title(),
            menu=self._build_menu(),
        )
        logger.info("TrayController running")
        self._icon.run()

    def stop(self) -> None:
        """Stop the tray icon (called from quit handler)."""
        if self._icon:
            self._icon.stop()

    def set_error(self, message: str) -> None:
        """Show the error icon and update the tooltip."""
        self._has_error = True
        self._status_text = message
        self._refresh()

    def clear_error(self) -> None:
        """Clear the error state and restore the normal icon."""
        self._has_error = False
        self._status_text = "Running"
        self._refresh()

    def notify(self, message: str, title: str = "FocusGuard") -> None:
        """Show a native tray notification when the platform supports it."""
        with self._notification_lock:
            if self._icon is None:
                logger.debug("Skipping notification because tray icon is not ready")
                return
            self._icon.notify(message, title)

    def clear_notification(self) -> None:
        """Dismiss the current tray notification when the platform supports it."""
        with self._notification_lock:
            if self._icon is None:
                return
            self._icon.remove_notification()

    def set_webcam_state(self, enabled: bool) -> None:
        """Update the webcam state indicator without triggering the callback."""
        self._webcam_enabled = enabled
        self._refresh()

    # ------------------------------------------------------------------
    # Menu construction
    # ------------------------------------------------------------------

    def _build_menu(self) -> pystray.Menu:
        items = [
            pystray.MenuItem(
                lambda item: f"FocusGuard — {self._status_text}",
                action=None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
        ]

        # Add "Open Today's Digest" if provided
        if self._on_open_digest is not None:
            items.append(
                pystray.MenuItem("Open Today's Digest", action=self._handle_open_digest)
            )

        # Add "Open Application Log" if provided
        if self._on_open_log is not None:
            items.append(
                pystray.MenuItem("Open Application Log", action=self._handle_open_log)
            )

        items.extend([
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda item: (
                    "Webcam: ON ✓" if self._webcam_enabled else "Webcam: OFF"
                ),
                action=self._handle_webcam_toggle,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", action=self._handle_quit),
        ])

        return pystray.Menu(*items)

    # ------------------------------------------------------------------
    # Menu handlers
    # ------------------------------------------------------------------

    def _handle_open_digest(self, icon, item) -> None:
        if self._on_open_digest:
            logger.info("Open digest requested from tray")
            self._on_open_digest()

    def _handle_open_log(self, icon, item) -> None:
        if self._on_open_log:
            logger.info("Open application log requested from tray")
            self._on_open_log()

    def _handle_webcam_toggle(self, icon, item) -> None:
        self._webcam_enabled = not self._webcam_enabled
        logger.info("Webcam toggled: %s", "ON" if self._webcam_enabled else "OFF")
        self._on_webcam_toggle(self._webcam_enabled)
        self._refresh()

    def _handle_quit(self, icon, item) -> None:
        logger.info("Quit requested from tray")
        self._on_quit()

    # ------------------------------------------------------------------
    # Icon / title helpers
    # ------------------------------------------------------------------

    def _current_icon(self) -> Image.Image:
        if self._has_error:
            return _ICON_ERROR
        if not self._webcam_enabled:
            return _ICON_WEBCAM_OFF
        return _ICON_ACTIVE

    def _current_title(self) -> str:
        if self._has_error:
            return f"FocusGuard — {self._status_text}"
        webcam_str = "Webcam ON" if self._webcam_enabled else "Webcam OFF"
        return f"FocusGuard — {webcam_str}"

    def _refresh(self) -> None:
        """Update the icon image and tooltip without rebuilding the menu."""
        if self._icon:
            self._icon.icon = self._current_icon()
            self._icon.title = self._current_title()
            self._icon.menu = self._build_menu()
