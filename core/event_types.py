"""
event_types.py
--------------
Signal state constants, enums, and the SessionRecord dataclass.
All other modules import from here — never define signal strings inline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


# ---------------------------------------------------------------------------
# Signal states
# ---------------------------------------------------------------------------

class WindowSignal(str, Enum):
    DISTRACTING = "DISTRACTING"
    NEUTRAL = "NEUTRAL"


class IdleSignal(str, Enum):
    IDLE = "IDLE"
    ACTIVE = "ACTIVE"


class GazeSignal(str, Enum):
    LOOKING = "LOOKING"
    NOT_LOOKING = "NOT_LOOKING"
    UNAVAILABLE = "UNAVAILABLE"
    TOGGLED_OFF = "TOGGLED_OFF"


# ---------------------------------------------------------------------------
# Session tier
# ---------------------------------------------------------------------------

class SessionTier(str, Enum):
    CONFIRMED = "confirmed"
    UNCONFIRMED = "unconfirmed"


# ---------------------------------------------------------------------------
# SessionRecord dataclass
# ---------------------------------------------------------------------------

@dataclass
class SessionRecord:
    """Represents a single doomscroll session to be written to the DB."""

    started_at: datetime
    ended_at: datetime
    site: str                        # matched domain or app name
    app_name: str                    # process name of the foreground window
    tier: SessionTier
    window_signal: bool
    idle_signal: bool
    gaze_signal: bool
    gaze_status: GazeSignal

    @property
    def duration_seconds(self) -> int:
        delta = self.ended_at - self.started_at
        return max(0, int(delta.total_seconds()))

    def signals_triggered_json(self) -> str:
        """Returns the signals_triggered field as a JSON string."""
        import json
        return json.dumps({
            "window": int(self.window_signal),
            "idle": int(self.idle_signal),
            "gaze": int(self.gaze_signal),
        })
