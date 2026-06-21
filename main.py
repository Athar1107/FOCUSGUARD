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
  6. Initialise and start IdleDetector (background thread)
  7. Initialise and start FlaskServer (background thread)
    8. Initialise TrayController and run it on the main thread (blocks)
    9. Start WorkReminder to watch for extended active/idle stretches

Shutdown sequence (triggered by Quit in tray menu):
  1. Stop IdleDetector thread
  2. Stop ActivityMonitor thread
  3. Flush any open session in SessionManager
  4. Close DatabaseLayer
  5. Stop TrayController (exits pystray loop → main thread returns)
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import platform
import shutil
import sys
import time
from pathlib import Path

# Suppress noisy MediaPipe / TensorFlow internal C++ logs
os.environ.setdefault("GLOG_minloglevel", "3")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("MEDIAPIPE_DISABLE_GPU", "1")


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


class _UtcFormatter(logging.Formatter):
    converter = time.gmtime


def _build_file_formatter() -> logging.Formatter:
    return _UtcFormatter(
        "%(asctime)sZ | %(levelname)-8s | %(name)s:%(lineno)d | %(threadName)s | %(message)s",
        "%Y-%m-%dT%H:%M:%S",
    )

def setup_logging(data_dir: Path) -> None:
    log_path = data_dir / "focusguard.log"
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    for handler in list(root.handlers):
        root.removeHandler(handler)

    # Rotating file handler — max 5 MB, keep 2 backups
    fh = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=2, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_build_file_formatter())

    # Console handler — INFO and above
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        "%H:%M:%S",
    ))

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
        "idle_threshold_seconds": 7,
        "window_poll_interval_seconds": 2,
        "gaze_poll_interval_seconds": 3,
        "confirmation_window_secs": 7,
        "min_session_duration_seconds": 5,
        "work_hours_start": "09:00",
        "work_hours_end": "18:00",
        "webcam_enabled": True,
        "webcam_device_index": 0,
        "gaze_fps": 5,
        "gaze_retry_interval_secs": 30,
        "gaze_ear_closed_threshold": 0.20,
        "gaze_iris_offset_threshold": 0.40,
        "gaze_stable_frames": 2,
        "cognitive_load": {
            "milestones_minutes": [90, 180, 240, 300],
            "time_of_day_weights": {
                "morning": {
                    "calm": 4,
                    "analytical": 4,
                    "energetic": 1,
                    "encouraging": 1,
                },
                "afternoon": {
                    "calm": 1,
                    "analytical": 1,
                    "energetic": 4,
                    "encouraging": 4,
                },
                "evening": {
                    "calm": 5,
                    "analytical": 2,
                    "energetic": 1,
                    "encouraging": 2,
                },
            },
        },
        "flask_port": 5678,
        "end_of_day_time": "17:30",
        "launch_at_startup": True,
        "work_reminder_active_threshold_seconds": 3 * 60 * 60,
        "work_reminder_idle_threshold_seconds": 3 * 60 * 60,
        "work_reminder_active_auto_close_seconds": 5 * 60,
        "work_reminder_poll_interval_seconds": 30,
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
    # Store all runtime data (db, logs, reports) inside the project folder
    data_dir = PROJECT_ROOT / "data"
    data_dir.mkdir(exist_ok=True)
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

    # 6. Idle Detector
    from detectors.idle_detector import IdleDetector
    idle_detector = IdleDetector(
        config=config,
        session_manager=session_manager,
    )
    idle_detector.start()

    # 7. Flask server (browser extension bridge)
    from bridge.flask_server import FlaskServer
    flask_server = FlaskServer(config=config, url_state=url_state)
    try:
        flask_server.start()
    except Exception as exc:
        logger.warning("Flask server failed to start: %s — URL tracking unavailable", exc)

    # 8. Gaze Detector (Phase 2 — OpenCV + MediaPipe)
    from core.event_types import GazeSignal
    from detectors.gaze_detector import GazeDetector

    gaze_detector = GazeDetector(
        config=config,
        session_manager=session_manager,
        on_error=lambda msg: tray_ref[0].set_error(msg) if tray_ref[0] else None,
        on_error_cleared=lambda: tray_ref[0].clear_error() if tray_ref[0] else None,
    )
    # tray_ref is a list so the lambda can close over it before tray is created
    tray_ref: list = [None]
    gaze_detector.start()

    # 9. Report Generator
    from reporting.report_generator import ReportGenerator
    report_generator = ReportGenerator(
        db=db,
        config=config,
        project_root=PROJECT_ROOT,
    )

    # ------------------------------------------------------------------
    # Tray UI Callbacks
    # ------------------------------------------------------------------
    def on_quit() -> None:
        logger.info("Shutdown initiated")
        work_reminder.stop()
        gaze_detector.stop()
        idle_detector.stop()
        activity_monitor.stop()
        session_manager.flush()
        db.close()
        tray.stop()

    def on_webcam_toggle(enabled: bool) -> None:
        config["webcam_enabled"] = enabled
        if enabled:
            gaze_detector.enable()
            logger.info("Webcam toggled ON")
        else:
            gaze_detector.disable()
            logger.info("Webcam toggled OFF")

    def on_open_digest() -> None:
        try:
            report_generator.generate_and_open()
        except Exception as exc:
            logger.error("Failed to generate and open digest: %s", exc)

    def on_open_log() -> None:
        try:
            log_path = data_dir / "focusguard.log"
            if log_path.exists():
                if platform.system() == "Windows":
                    os.startfile(str(log_path))
                else:
                    import subprocess
                    cmd = "open" if platform.system() == "Darwin" else "xdg-open"
                    subprocess.run([cmd, str(log_path)])
            else:
                logger.warning("Log file does not exist at %s", log_path)
        except Exception as exc:
            logger.error("Failed to open log file: %s", exc)

    # ------------------------------------------------------------------
    # Tray controller — blocks main thread until Quit
    # ------------------------------------------------------------------
    from ui.tray_controller import TrayController
    tray = TrayController(
        config=config,
        on_webcam_toggle=on_webcam_toggle,
        on_quit=on_quit,
        on_open_digest=on_open_digest,
        on_open_log=on_open_log,
    )
    tray_ref[0] = tray  # give gaze_detector error callbacks access to tray

    from core.work_reminder import WorkReminder
    from core.cognitive_load import CognitiveLoadMessenger
    work_reminder = WorkReminder(
        config=config,
        idle_detector=idle_detector,
        tray=tray,
        cognitive_load=CognitiveLoadMessenger(config=config),
    )
    work_reminder.start()

    logger.info("All components started. FocusGuard is running in the system tray.")
    tray.run()  # blocks here

    logger.info("FocusGuard exited cleanly")


if __name__ == "__main__":
    main()
