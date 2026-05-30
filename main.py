"""
main.py
-------
FocusGuard entry point.

Startup sequence:
  1. Resolve user data directory and set up logging
  2. Load (or create) config.json
  3. Initialise DatabaseLayer
  4. Initialise SessionManager
  5. Initialise and start ActivityMonitor (background thread)
  6. Initialise and start FlaskServer (background thread)
  7. Initialise TrayController and run it on the main thread (blocks)

Shutdown sequence (triggered by Quit in tray menu):
  1. Stop ActivityMonitor thread
  2. Flush any open session in SessionManager
  3. Close DatabaseLayer
  4. Stop TrayController (exits pystray loop → main thread returns)
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import platform
import shutil
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Resolve project root so relative imports work when run from any cwd
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# User data directory
# ---------------------------------------------------------------------------

def get_user_data_dir() -> Path:
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    data_dir = base / "focusguard"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging(data_dir: Path) -> None:
    log_path = data_dir / "focusguard.log"
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Rotating file handler — max 5 MB, keep 2 backups
    fh = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=2, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))

    # Console handler — INFO and above
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))

    root.addHandler(fh)
    root.addHandler(ch)


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.json"

def load_config(data_dir: Path) -> dict:
    """
    Load config from the user data directory.
    If absent, copy the bundled default config.json there first.
    If corrupt, reset to defaults and notify via log.
    """
    live_config_path = data_dir / "config.json"
    logger = logging.getLogger("main")

    if not live_config_path.exists():
        if DEFAULT_CONFIG_PATH.exists():
            shutil.copy(DEFAULT_CONFIG_PATH, live_config_path)
            logger.info("Copied default config to %s", live_config_path)
        else:
            logger.warning("No default config.json found — using hardcoded defaults")
            return _default_config()

    try:
        with open(live_config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        logger.info("Config loaded from %s", live_config_path)
        return config
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Config corrupt (%s) — resetting to defaults", exc)
        config = _default_config()
        _write_config(live_config_path, config)
        return config


def _default_config() -> dict:
    return {
        "distracting_sites": [
            "reddit.com", "twitter.com", "x.com", "instagram.com",
            "facebook.com", "youtube.com", "tiktok.com",
            "news.ycombinator.com", "bbc.com", "cnn.com",
            "theguardian.com", "nytimes.com", "dailymail.co.uk",
            "buzzfeed.com", "huffpost.com",
        ],
        "distracting_apps": [],
        "idle_threshold_seconds": 30,
        "window_poll_interval_seconds": 2,
        "gaze_poll_interval_seconds": 3,
        "confirmation_window_secs": 120,
        "min_session_duration_seconds": 10,
        "work_hours_start": "09:00",
        "work_hours_end": "18:00",
        "webcam_enabled": True,
        "webcam_device_index": 0,
        "gaze_fps": 5,
        "gaze_retry_interval_secs": 30,
        "flask_port": 5678,
        "end_of_day_time": "17:30",
        "launch_at_startup": True,
    }


def _write_config(path: Path, config: dict) -> None:
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    data_dir = get_user_data_dir()
    setup_logging(data_dir)
    logger = logging.getLogger("main")
    logger.info("FocusGuard starting — Python %s on %s", sys.version, platform.system())

    # 1. Load config
    config = load_config(data_dir)

    # 2. Database
    from core.database_layer import DatabaseLayer
    db = DatabaseLayer(db_path=data_dir / "focusguard.db")
    db.write_config_snapshot(config)
    db.sync_sites(config.get("distracting_sites", []))

    # 3. Session Manager
    from core.session_manager import SessionManager
    session_manager = SessionManager(db=db, config=config)

    # 4. Browser extension URL state (shared between Flask and ActivityMonitor)
    from bridge.url_state import UrlState
    url_state = UrlState()

    # 5. Activity Monitor
    from detectors.activity_monitor import ActivityMonitor
    activity_monitor = ActivityMonitor(
        config=config,
        session_manager=session_manager,
        url_state=url_state,
    )
    activity_monitor.start()

    # 6. Flask server (browser extension bridge)
    from bridge.flask_server import FlaskServer
    flask_server = FlaskServer(config=config, url_state=url_state)
    try:
        flask_server.start()
    except Exception as exc:
        logger.warning("Flask server failed to start: %s — URL tracking unavailable", exc)

    # 7. Gaze signal — default to TOGGLED_OFF for Phase 1 (no webcam yet)
    #    This means only Tier 1 (unconfirmed) sessions can be logged.
    from core.event_types import GazeSignal
    session_manager.on_gaze_signal(GazeSignal.TOGGLED_OFF)

    # ------------------------------------------------------------------
    # Shutdown callback (called from tray Quit)
    # ------------------------------------------------------------------
    def on_quit() -> None:
        logger.info("Shutdown initiated")
        activity_monitor.stop()
        session_manager.flush()
        db.close()
        tray.stop()

    def on_webcam_toggle(enabled: bool) -> None:
        config["webcam_enabled"] = enabled
        if enabled:
            # Phase 2 will start the GazeDetector here
            session_manager.on_gaze_signal(GazeSignal.TOGGLED_OFF)
            logger.info("Webcam toggled ON (gaze detector not yet implemented in Phase 1)")
        else:
            session_manager.on_gaze_signal(GazeSignal.TOGGLED_OFF)
            logger.info("Webcam toggled OFF")

    # ------------------------------------------------------------------
    # Tray controller — blocks main thread until Quit
    # ------------------------------------------------------------------
    from ui.tray_controller import TrayController
    tray = TrayController(
        config=config,
        on_webcam_toggle=on_webcam_toggle,
        on_quit=on_quit,
    )

    logger.info("All components started. FocusGuard is running in the system tray.")
    tray.run()  # blocks here

    logger.info("FocusGuard exited cleanly")


if __name__ == "__main__":
    main()
