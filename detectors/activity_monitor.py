"""
activity_monitor.py
-------------------
Polls the active foreground window every N seconds (default: 2s).

Signal sources (in priority order):
  1. URL from browser extension bridge (via url_state shared variable)
  2. Window title heuristic (fallback when extension is absent)
  3. Process name match against distracting_apps list

Emits WindowSignal.DISTRACTING or WindowSignal.NEUTRAL to SessionManager.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Optional
from urllib.parse import urlparse

import psutil

from core.event_types import WindowSignal
from core.session_manager import SessionManager

logger = logging.getLogger(__name__)

# Browser process names — used to decide whether to parse the window title
BROWSER_PROCESS_NAMES = frozenset({
    "chrome", "chrome.exe",
    "msedge", "msedge.exe",
    "firefox", "firefox.exe",
    "safari",
    "brave", "brave.exe",
    "opera", "opera.exe",
})

# Regex to extract a domain from a browser window title like:
#   "Reddit - Google Chrome"
#   "Twitter / X — Mozilla Firefox"
_TITLE_DOMAIN_RE = re.compile(
    r"(?:https?://)?([a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z]{2,})+)"
)


def _extract_domain_from_url(url: str) -> str:
    """Return the registered domain from a full URL string."""
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        host = parsed.hostname or ""
        # Strip leading 'www.' for matching
        return host.removeprefix("www.")
    except Exception:
        return ""


def _domain_matches(candidate: str, pattern: str) -> bool:
    """
    Case-insensitive, subdomain-aware domain match.
    pattern='reddit.com' matches 'reddit.com', 'www.reddit.com', 'old.reddit.com'
    """
    candidate = candidate.lower()
    pattern = pattern.lower()
    return candidate == pattern or candidate.endswith(f".{pattern}")


def _get_active_window_info() -> tuple[str, str, str]:
    """
    Return (window_title, process_name, process_exe) for the active window.
    Returns ('', '', '') on failure.
    """
    try:
        import pygetwindow as gw  # type: ignore
        win = gw.getActiveWindow()
        if win is None:
            return "", "", ""
        title = win.title or ""
    except Exception as exc:
        logger.debug("pygetwindow error: %s", exc)
        return "", "", ""

    # Resolve process name via psutil
    process_name = ""
    process_exe = ""
    try:
        import psutil
        for proc in psutil.process_iter(["pid", "name", "exe"]):
            try:
                # Match by checking if the process has a window with this title
                # psutil doesn't give us window handles directly; we use the
                # foreground PID on Windows via ctypes as a best-effort approach.
                pass
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # Simpler cross-platform approach: get foreground PID
        process_name, process_exe = _get_foreground_process_info()
    except Exception as exc:
        logger.debug("psutil error: %s", exc)

    return title, process_name, process_exe


def _get_foreground_process_info() -> tuple[str, str]:
    """
    Return (process_name, exe_path) for the current foreground process.
    Uses platform-specific APIs.
    """
    import platform
    system = platform.system()

    try:
        if system == "Windows":
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            proc = psutil.Process(pid.value)
            return proc.name(), proc.exe()

        elif system == "Darwin":
            # macOS: use NSWorkspace to get frontmost app
            try:
                from AppKit import NSWorkspace  # type: ignore
                app = NSWorkspace.sharedWorkspace().frontmostApplication()
                name = app.localizedName() or ""
                bundle = app.bundleURL()
                exe = str(bundle.path()) if bundle else ""
                return name, exe
            except ImportError:
                pass

    except (psutil.NoSuchProcess, psutil.AccessDenied, Exception) as exc:
        logger.debug("Foreground process lookup failed: %s", exc)

    return "", ""


class ActivityMonitor:
    """
    Background thread that polls the active window and emits window signals
    to the SessionManager.
    """

    def __init__(
        self,
        config: dict,
        session_manager: SessionManager,
        url_state=None,  # bridge.url_state.UrlState instance, injected at runtime
    ) -> None:
        self._config = config
        self._session_manager = session_manager
        self._url_state = url_state

        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="ActivityMonitor",
            daemon=True,
        )

    def start(self) -> None:
        logger.info("ActivityMonitor starting")
        self._thread.start()

    def stop(self) -> None:
        logger.info("ActivityMonitor stopping")
        self._stop_event.set()
        self._thread.join(timeout=5)

    # ------------------------------------------------------------------
    # Main poll loop
    # ------------------------------------------------------------------

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._poll()
            except Exception as exc:
                logger.error("ActivityMonitor poll error: %s", exc)

            interval = self._config.get("window_poll_interval_seconds", 2)
            self._stop_event.wait(timeout=interval)

    def _poll(self) -> None:
        """Single poll cycle: determine window/URL signal and emit to SessionManager."""
        # Re-read config on each cycle to pick up live changes
        distracting_sites: list[str] = self._config.get("distracting_sites", [])
        distracting_apps: list[str] = [
            a.lower() for a in self._config.get("distracting_apps", [])
        ]

        title, proc_name, proc_exe = _get_active_window_info()
        proc_name_lower = proc_name.lower()

        # --- Signal source 1: browser extension URL (authoritative) ---
        url_from_extension: Optional[str] = None
        if self._url_state is not None:
            url_from_extension = self._url_state.get_url()

        matched_site = ""
        source = "window_title"

        if url_from_extension:
            domain = _extract_domain_from_url(url_from_extension)
            for pattern in distracting_sites:
                if _domain_matches(domain, pattern):
                    matched_site = pattern
                    source = "url"
                    break

        # --- Signal source 2: window title heuristic (browser fallback) ---
        if not matched_site and proc_name_lower in BROWSER_PROCESS_NAMES:
            # Try to extract a domain from the window title
            matches = _TITLE_DOMAIN_RE.findall(title)
            for candidate in matches:
                domain = candidate.lower().removeprefix("www.")
                for pattern in distracting_sites:
                    if _domain_matches(domain, pattern):
                        matched_site = pattern
                        source = "window_title"
                        break
                if matched_site:
                    break

        # --- Signal source 3: distracting app by process name ---
        if not matched_site and proc_name_lower:
            for app_pattern in distracting_apps:
                if app_pattern in proc_name_lower:
                    matched_site = proc_name
                    source = "app"
                    break

        # --- Emit signal ---
        if matched_site:
            logger.debug(
                "DISTRACTING: site=%s proc=%s source=%s",
                matched_site, proc_name, source,
            )
            self._session_manager.on_window_signal(
                state=WindowSignal.DISTRACTING,
                site_or_app=matched_site,
                app_name=proc_name,
                source=source,
            )
        else:
            self._session_manager.on_window_signal(
                state=WindowSignal.NEUTRAL,
                site_or_app="",
                app_name=proc_name,
                source=source,
            )
