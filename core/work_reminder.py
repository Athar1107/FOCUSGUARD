"""
work_reminder.py
----------------
Polls the idle detector and shows lightweight tray reminders when the user has
been continuously active or continuously idle for too long.

Phase 3B adds weighted cognitive-load reminders during sustained focus.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Optional

from core.cognitive_load import CognitiveLoadMessenger
from core.event_types import IdleSignal
from detectors.idle_detector import IdleDetector, IdleStateSnapshot
from ui.tray_controller import TrayController

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkReminderConfig:
    idle_threshold_seconds: int = 3 * 60 * 60
    active_auto_close_seconds: int = 5 * 60
    poll_interval_seconds: int = 30


class WorkReminder:
    """Shows non-modal tray notifications for extended active/idle stretches."""

    def __init__(
        self,
        config: dict,
        idle_detector: IdleDetector,
        tray: TrayController,
        cognitive_load: Optional[CognitiveLoadMessenger] = None,
    ) -> None:
        self._config = config
        self._idle_detector = idle_detector
        self._tray = tray
        self._cognitive_load = cognitive_load or CognitiveLoadMessenger()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="WorkReminder",
            daemon=True,
        )
        self._active_focus_start: Optional[float] = None
        self._active_focus_milestone: Optional[int] = None
        self._idle_notified_for_start: Optional[float] = None
        self._auto_close_timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        logger.info("WorkReminder starting")
        self._stop_event.clear()
        self._thread.start()

    def stop(self) -> None:
        logger.info("WorkReminder stopping")
        self._stop_event.set()
        self._cancel_auto_close_timer()
        self._safe_clear_notification()
        if self._thread.is_alive():
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._poll()
            except Exception as exc:
                logger.error("WorkReminder poll failed: %s", exc)

            interval = int(self._config.get("work_reminder_poll_interval_seconds", 30))
            self._stop_event.wait(timeout=max(1, interval))

    def _poll(self) -> None:
        snapshot = self._idle_detector.get_state_snapshot()
        thresholds = self._get_thresholds()

        if snapshot.state == IdleSignal.ACTIVE:
            self._handle_active_state(snapshot, thresholds)
        else:
            self._handle_idle_state(snapshot, thresholds)

    def _get_thresholds(self) -> WorkReminderConfig:
        return WorkReminderConfig(
            idle_threshold_seconds=int(
                self._config.get("work_reminder_idle_threshold_seconds", 3 * 60 * 60)
            ),
            active_auto_close_seconds=int(
                self._config.get("work_reminder_active_auto_close_seconds", 5 * 60)
            ),
            poll_interval_seconds=int(
                self._config.get("work_reminder_poll_interval_seconds", 30)
            ),
        )

    def _handle_active_state(
        self,
        snapshot: IdleStateSnapshot,
        thresholds: WorkReminderConfig,
    ) -> None:
        active_start = snapshot.active_since_monotonic
        active_elapsed = snapshot.active_duration_seconds
        milestone_minutes = self._cognitive_load.milestone_for_elapsed_seconds(active_elapsed)

        if self._idle_notified_for_start is not None:
            self._idle_notified_for_start = None
            self._safe_clear_notification()

        if self._active_focus_start != active_start:
            self._active_focus_start = active_start
            self._active_focus_milestone = None
            self._cancel_auto_close_timer()

        if milestone_minutes is None:
            return

        if self._active_focus_milestone != milestone_minutes:
            self._active_focus_milestone = milestone_minutes
            self._show_focus_reminder(milestone_minutes, thresholds)

    def _handle_idle_state(
        self,
        snapshot: IdleStateSnapshot,
        thresholds: WorkReminderConfig,
    ) -> None:
        idle_start = snapshot.idle_since_monotonic
        if idle_start is None:
            return

        idle_elapsed = snapshot.idle_duration_seconds

        self._cancel_auto_close_timer()

        if self._active_focus_milestone is not None:
            self._active_focus_start = None
            self._active_focus_milestone = None
            self._safe_clear_notification()

        if idle_elapsed >= thresholds.idle_threshold_seconds:
            if self._idle_notified_for_start != idle_start:
                self._idle_notified_for_start = idle_start
                self._safe_notify(
                    "You have been idle for 3 hours. Click to dismiss when you are ready to return.",
                    title="FocusGuard",
                )

    def _show_focus_reminder(self, milestone_minutes: int, thresholds: WorkReminderConfig) -> None:
        message = self._cognitive_load.select_message(milestone_minutes)
        logger.info(
            "Focus reminder triggered at %d minutes: %s",
            milestone_minutes,
            message,
        )
        self._safe_clear_notification()
        self._safe_notify(
            message,
            title="FocusGuard",
        )
        self._cancel_auto_close_timer()
        self._auto_close_timer = threading.Timer(
            thresholds.active_auto_close_seconds,
            self._dismiss_active_reminder,
        )
        self._auto_close_timer.daemon = True
        self._auto_close_timer.start()

    def _dismiss_active_reminder(self) -> None:
        with self._lock:
            if self._stop_event.is_set():
                return
            self._safe_clear_notification()
            self._auto_close_timer = None

    def _cancel_auto_close_timer(self) -> None:
        with self._lock:
            if self._auto_close_timer is not None:
                self._auto_close_timer.cancel()
                self._auto_close_timer = None

    def _safe_notify(self, message: str, title: str) -> None:
        try:
            self._tray.notify(message, title=title)
        except Exception as exc:
            logger.debug("Tray notification unavailable: %s", exc)

    def _safe_clear_notification(self) -> None:
        try:
            self._tray.clear_notification()
        except Exception as exc:
            logger.debug("Tray notification clear unavailable: %s", exc)