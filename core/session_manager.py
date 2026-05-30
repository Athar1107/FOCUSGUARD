"""
session_manager.py
------------------
Three-signal state machine and session lifecycle.

Receives signal updates from:
  - ActivityMonitor  → on_window_signal()
  - IdleDetector     → on_idle_signal()
  - GazeDetector     → on_gaze_signal()

Applies confirmation logic:
  Tier 2 (confirmed)   = DISTRACTING + IDLE + LOOKING
  Tier 1 (unconfirmed) = DISTRACTING + IDLE + (NOT_LOOKING | UNAVAILABLE | TOGGLED_OFF)

Writes completed sessions to DatabaseLayer.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from core.database_layer import DatabaseLayer
from core.event_types import (
    GazeSignal,
    IdleSignal,
    SessionRecord,
    SessionTier,
    WindowSignal,
)

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Thread-safe state machine that tracks the three detection signals
    and manages the open/close lifecycle of doomscroll session records.
    """

    def __init__(self, db: DatabaseLayer, config: dict) -> None:
        self._db = db
        self._config = config
        self._lock = threading.Lock()

        # Current signal states
        self._window_signal = WindowSignal.NEUTRAL
        self._window_site = ""
        self._window_app = ""
        self._idle_signal = IdleSignal.ACTIVE
        self._gaze_signal = GazeSignal.TOGGLED_OFF  # default until gaze detector starts

        # Active session tracking
        self._active_session_start: Optional[datetime] = None
        self._active_session_tier: Optional[SessionTier] = None
        self._active_session_site = ""
        self._active_session_app = ""
        self._active_session_gaze = GazeSignal.TOGGLED_OFF

        logger.info("SessionManager initialised")

    # ------------------------------------------------------------------
    # Signal handlers — called from detector threads
    # ------------------------------------------------------------------

    def on_window_signal(
        self,
        state: WindowSignal,
        site_or_app: str = "",
        app_name: str = "",
        source: str = "window_title",
    ) -> None:
        with self._lock:
            self._window_signal = state
            self._window_site = site_or_app
            self._window_app = app_name
            self._evaluate()

    def on_idle_signal(self, state: IdleSignal) -> None:
        with self._lock:
            self._idle_signal = state
            self._evaluate()

    def on_gaze_signal(self, state: GazeSignal) -> None:
        with self._lock:
            self._gaze_signal = state
            self._evaluate()

    # ------------------------------------------------------------------
    # Core evaluation logic
    # ------------------------------------------------------------------

    def _evaluate(self) -> None:
        """
        Re-evaluate the current signal state and open/close sessions.
        Must be called with self._lock held.
        """
        confirmed = (
            self._window_signal == WindowSignal.DISTRACTING
            and self._idle_signal == IdleSignal.IDLE
            and self._gaze_signal == GazeSignal.LOOKING
        )
        unconfirmed = (
            self._window_signal == WindowSignal.DISTRACTING
            and self._idle_signal == IdleSignal.IDLE
            and self._gaze_signal
            in (GazeSignal.NOT_LOOKING, GazeSignal.UNAVAILABLE, GazeSignal.TOGGLED_OFF)
        )

        target_tier: Optional[SessionTier] = None
        if confirmed:
            target_tier = SessionTier.CONFIRMED
        elif unconfirmed:
            target_tier = SessionTier.UNCONFIRMED

        if self._active_session_start is None:
            # No session open — open one if conditions are met
            if target_tier is not None:
                self._open_session(target_tier)
        else:
            # Session is open
            if target_tier is None:
                # Conditions no longer met — close the session
                self._close_session()
            elif target_tier != self._active_session_tier:
                # Tier changed (e.g. Tier 1 → Tier 2 on gaze becoming LOOKING)
                # Close the current session and open a new one at the new tier
                self._close_session()
                self._open_session(target_tier)

    def _open_session(self, tier: SessionTier) -> None:
        """Open a new session record. Lock must be held."""
        self._active_session_start = datetime.now(timezone.utc)
        self._active_session_tier = tier
        self._active_session_site = self._window_site
        self._active_session_app = self._window_app
        self._active_session_gaze = self._gaze_signal
        logger.debug(
            "Session opened: tier=%s site=%s",
            tier.value,
            self._window_site,
        )

    def _close_session(self) -> None:
        """Close the active session and write it to the DB. Lock must be held."""
        if self._active_session_start is None:
            return

        ended_at = datetime.now(timezone.utc)
        record = SessionRecord(
            started_at=self._active_session_start,
            ended_at=ended_at,
            site=self._active_session_site,
            app_name=self._active_session_app,
            tier=self._active_session_tier,  # type: ignore[arg-type]
            window_signal=True,
            idle_signal=True,
            gaze_signal=(self._active_session_gaze == GazeSignal.LOOKING),
            gaze_status=self._active_session_gaze,
        )

        min_duration = self._config.get("min_session_duration_seconds", 10)
        if record.duration_seconds < min_duration:
            logger.debug(
                "Session discarded (too short: %ds < %ds)",
                record.duration_seconds,
                min_duration,
            )
        else:
            try:
                self._db.write_session(record)
            except Exception as exc:
                logger.error("Failed to persist session: %s", exc)

        # Reset active session state
        self._active_session_start = None
        self._active_session_tier = None
        self._active_session_site = ""
        self._active_session_app = ""
        self._active_session_gaze = GazeSignal.TOGGLED_OFF

    # ------------------------------------------------------------------
    # Graceful shutdown
    # ------------------------------------------------------------------

    def flush(self) -> None:
        """Close any open session on app shutdown."""
        with self._lock:
            if self._active_session_start is not None:
                logger.info("Flushing open session on shutdown")
                self._close_session()
