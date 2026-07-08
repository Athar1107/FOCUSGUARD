"""
idle_detector.py
----------------
Monitors global keyboard and mouse events to determine user activity/idle status.

Emits IdleSignal.IDLE when inactive for >= idle_threshold_seconds (default: 30s).
Emits IdleSignal.ACTIVE immediately on any user input event.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import threading
import time
from typing import Optional

from pynput import keyboard, mouse

from core.event_types import IdleSignal
from core.session_manager import SessionManager

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IdleStateSnapshot:
    """Thread-safe snapshot of the current idle detector state."""

    state: IdleSignal
    active_since_monotonic: float
    idle_since_monotonic: Optional[float]
    sampled_at_monotonic: float

    @property
    def active_duration_seconds(self) -> float:
        if self.state != IdleSignal.ACTIVE:
            return 0.0
        return max(0.0, self.sampled_at_monotonic - self.active_since_monotonic)

    @property
    def idle_duration_seconds(self) -> float:
        if self.state != IdleSignal.IDLE or self.idle_since_monotonic is None:
            return 0.0
        return max(0.0, self.sampled_at_monotonic - self.idle_since_monotonic)


class IdleDetector:
    """
    Background tracker that monitors mouse & keyboard events using pynput,
    maintains an active/idle state machine, and notifies the SessionManager.
    """

    def __init__(self, config: dict, session_manager: SessionManager) -> None:
        self._config = config
        self._session_manager = session_manager

        self._last_input_time = time.monotonic()
        self._active_since_time = self._last_input_time
        self._idle_since_time: Optional[float] = None
        self._current_state = IdleSignal.ACTIVE

        self._keyboard_listener: Optional[keyboard.Listener] = None
        self._mouse_listener: Optional[mouse.Listener] = None

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start global listeners and the background tick evaluation thread."""
        logger.info("IdleDetector starting")
        self._stop_event.clear()

        # Initialise state
        with self._lock:
            self._last_input_time = time.monotonic()
            self._active_since_time = self._last_input_time
            self._idle_since_time = None
            self._current_state = IdleSignal.ACTIVE

        # Start pynput global OS hook listeners
        self._keyboard_listener = keyboard.Listener(
            on_press=self._on_input,
            on_release=self._on_input,
        )
        self._mouse_listener = mouse.Listener(
            on_move=self._on_input,
            on_click=self._on_input,
            on_scroll=self._on_input,
        )

        self._keyboard_listener.start()
        self._mouse_listener.start()

        # Start background check thread (tick every 1s)
        self._thread = threading.Thread(
            target=self._run,
            name="IdleDetector",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop global listeners and join the evaluation thread."""
        logger.info("IdleDetector stopping")
        self._stop_event.set()

        if self._keyboard_listener:
            try:
                self._keyboard_listener.stop()
            except Exception as exc:
                logger.debug("Failed to stop keyboard listener cleanly: %s", exc)
            self._keyboard_listener = None

        if self._mouse_listener:
            try:
                self._mouse_listener.stop()
            except Exception as exc:
                logger.debug("Failed to stop mouse listener cleanly: %s", exc)
            self._mouse_listener = None

        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    # ------------------------------------------------------------------
    # Global input event callback
    # ------------------------------------------------------------------

    def _on_input(self, *args, **kwargs) -> None:
        """Triggered globally by keyboard presses or mouse clicks/moves."""
        state_to_emit = None
        with self._lock:
            self._last_input_time = time.monotonic()
            # If we were idle, transition back to active immediately
            if self._current_state == IdleSignal.IDLE:
                self._current_state = IdleSignal.ACTIVE
                self._active_since_time = self._last_input_time
                self._idle_since_time = None
                logger.debug("Activity detected — transitioning from IDLE to ACTIVE")
                state_to_emit = IdleSignal.ACTIVE

        # Emit outside the lock to prevent possible deadlock in callbacks
        if state_to_emit is not None:
            try:
                self._session_manager.on_idle_signal(state_to_emit)
            except Exception as exc:
                logger.error("Failed to forward ACTIVE signal: %s", exc)

    # ------------------------------------------------------------------
    # Background periodic evaluation
    # ------------------------------------------------------------------

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._check_idle()
            except Exception as exc:
                logger.error("IdleDetector periodic evaluation failed: %s", exc)

            # Wait 1 second or exit early if stopped
            self._stop_event.wait(timeout=1.0)

    def _check_idle(self) -> None:
        """Evaluate if the user has been inactive longer than the threshold."""
        # Re-read the latest configuration value every tick
        threshold = self._config.get("idle_threshold_seconds", 30)
        state_to_emit = None

        with self._lock:
            elapsed = time.monotonic() - self._last_input_time
            if elapsed >= threshold and self._current_state == IdleSignal.ACTIVE:
                self._current_state = IdleSignal.IDLE
                self._idle_since_time = time.monotonic()
                logger.debug("No input detected for %.1fs — transitioning to IDLE", elapsed)
                state_to_emit = IdleSignal.IDLE

        if state_to_emit is not None:
            try:
                self._session_manager.on_idle_signal(state_to_emit)
            except Exception as exc:
                logger.error("Failed to forward IDLE signal: %s", exc)

    def get_state_snapshot(self) -> IdleStateSnapshot:
        """Return a thread-safe snapshot of the current idle state."""
        with self._lock:
            return IdleStateSnapshot(
                state=self._current_state,
                active_since_monotonic=self._active_since_time,
                idle_since_monotonic=self._idle_since_time,
                sampled_at_monotonic=time.monotonic(),
            )
