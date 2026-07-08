"""
cognitive_load.py
-----------------
Phase 3B focus-awareness message selection.

Selects supportive reminders for sustained focus based on the current
continuous-work milestone and the time of day.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

DEFAULT_MILESTONES_MINUTES = (90, 180, 240, 300)
DEFAULT_TIME_OF_DAY_WEIGHTS = {
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
}


@dataclass(frozen=True)
class MessageTemplate:
    mood: str
    text: str


_MESSAGE_LIBRARY: tuple[tuple[MessageTemplate, ...], ...] = (
    (
        MessageTemplate(
            "calm",
            "You have been focused for {duration}. A short reset can make the next block cleaner.",
        ),
        MessageTemplate(
            "analytical",
            "{duration} of sustained attention is meaningful. A brief break can improve the next pass.",
        ),
        MessageTemplate(
            "energetic",
            "{duration} in. Good work. Step away for a few minutes, then come back sharp.",
        ),
        MessageTemplate(
            "encouraging",
            "{duration} of real focus is already a win. Keep the momentum with a short reset.",
        ),
    ),
    (
        MessageTemplate(
            "calm",
            "{duration} of deep work is a lot. A short break can help your concentration hold.",
        ),
        MessageTemplate(
            "analytical",
            "At the {duration} mark, a reset is usually efficient. Return with better signal and less noise.",
        ),
        MessageTemplate(
            "energetic",
            "{duration} down. You have built serious momentum. Take a quick break and protect it.",
        ),
        MessageTemplate(
            "encouraging",
            "{duration} of focus is substantial. Give your mind a small pause and come back strong.",
        ),
    ),
    (
        MessageTemplate(
            "calm",
            "{duration} of concentration deserves a break. The next stretch will benefit from it.",
        ),
        MessageTemplate(
            "analytical",
            "{duration} of effort is enough evidence for a reset. A short pause is the rational move.",
        ),
        MessageTemplate(
            "energetic",
            "{duration} in, and you are still going. Step away briefly, then re-engage with fresh energy.",
        ),
        MessageTemplate(
            "encouraging",
            "{duration} of focus is not trivial. A short rest will help you keep the quality high.",
        ),
    ),
    (
        MessageTemplate(
            "calm",
            "{duration} is a heavy lift. Step away for a proper break before the next block.",
        ),
        MessageTemplate(
            "analytical",
            "At {duration}, recovery matters. A break now will improve what comes next.",
        ),
        MessageTemplate(
            "energetic",
            "{duration} down. Strong work. Take a longer break and return with more force.",
        ),
        MessageTemplate(
            "encouraging",
            "{duration} of focus is real output. Protect it by letting your mind recover.",
        ),
    ),
)


class CognitiveLoadMessenger:
    """Selects phase 3B reminder copy with time-of-day weighting."""

    def __init__(self, config: dict, rng: Optional[random.Random] = None) -> None:
        self._config = config
        self._rng = rng or random.Random()
        self._last_message: Optional[str] = None

    def milestone_for_elapsed_seconds(self, active_elapsed_seconds: int) -> Optional[int]:
        milestones = self._milestones_minutes()
        active_minutes = active_elapsed_seconds // 60
        for milestone in reversed(milestones):
            if active_minutes >= milestone:
                return milestone
        return None

    def select_message(self, milestone_minutes: int, when: Optional[datetime] = None) -> str:
        milestone_index = self._milestone_index(milestone_minutes)
        templates = _MESSAGE_LIBRARY[milestone_index]
        current_hour = (when or datetime.now()).hour
        mood_weights = self._mood_weights(current_hour)
        duration_label = self._format_duration(milestone_minutes)

        candidates = [template for template in templates if mood_weights.get(template.mood, 0) > 0]
        if not candidates:
            candidates = list(templates)

        message = self._choose_non_repeating(candidates, mood_weights, duration_label)
        self._last_message = message
        return message

    def _section(self) -> dict:
        section = self._config.get("cognitive_load", {})
        return section if isinstance(section, dict) else {}

    def _milestones_minutes(self) -> tuple[int, ...]:
        section = self._section()
        raw_milestones = section.get("milestones_minutes", DEFAULT_MILESTONES_MINUTES)
        milestones: list[int] = []

        if isinstance(raw_milestones, (list, tuple)):
            for value in raw_milestones:
                try:
                    milestone = int(value)
                except (TypeError, ValueError):
                    continue
                if milestone > 0:
                    milestones.append(milestone)

        return tuple(milestones) if milestones else DEFAULT_MILESTONES_MINUTES

    def _milestone_index(self, milestone_minutes: int) -> int:
        milestones = self._milestones_minutes()
        try:
            return milestones.index(milestone_minutes)
        except ValueError:
            return max(0, len(milestones) - 1)

    def _choose_non_repeating(
        self,
        templates: list[MessageTemplate],
        mood_weights: dict[str, int],
        duration_label: str,
    ) -> str:
        candidates = templates
        if self._last_message and len(candidates) > 1:
            non_repeating = [template for template in candidates if template.text != self._last_message]
            if non_repeating:
                candidates = non_repeating

        weights = [max(1, mood_weights.get(template.mood, 1)) for template in candidates]
        chosen = self._rng.choices(candidates, weights=weights, k=1)[0]

        if chosen.text == self._last_message and len(candidates) > 1:
            alternatives = [template for template in candidates if template.text != self._last_message]
            if alternatives:
                alt_weights = [max(1, mood_weights.get(template.mood, 1)) for template in alternatives]
                chosen = self._rng.choices(alternatives, weights=alt_weights, k=1)[0]

        return chosen.text.format(duration=duration_label)

    def _mood_weights(self, hour: int) -> dict[str, int]:
        section = self._section()
        raw_weights = section.get("time_of_day_weights", DEFAULT_TIME_OF_DAY_WEIGHTS)

        if not isinstance(raw_weights, dict):
            raw_weights = DEFAULT_TIME_OF_DAY_WEIGHTS

        if hour < 12:
            period = "morning"
        elif hour < 17:
            period = "afternoon"
        else:
            period = "evening"

        period_weights = raw_weights.get(period, DEFAULT_TIME_OF_DAY_WEIGHTS[period])
        weights: dict[str, int] = {}
        if isinstance(period_weights, dict):
            for mood, default_value in DEFAULT_TIME_OF_DAY_WEIGHTS[period].items():
                try:
                    weights[mood] = max(int(period_weights.get(mood, default_value)), 0)
                except (TypeError, ValueError):
                    weights[mood] = default_value
        else:
            weights = dict(DEFAULT_TIME_OF_DAY_WEIGHTS[period])
        return weights

    @staticmethod
    def _format_duration(minutes: int) -> str:
        if minutes % 60 == 0:
            hours = minutes // 60
            return f"{hours} hour" + ("s" if hours != 1 else "")
        return f"{minutes} minutes"