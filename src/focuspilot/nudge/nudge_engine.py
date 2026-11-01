"""Debounced escalation state for gentle, local focus nudges."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class NudgeDecision:
    """A suggested nudge level and a short explanation."""

    level: int
    reason: str


class NudgeEngine:
    """Escalate only after sustained off-task time and respect cooldowns."""

    def __init__(self, first_nudge_s: int = 90) -> None:
        self.first_nudge_s = first_nudge_s
        self.off_task_s = 0.0
        self.on_task_s = 0.0
        self.last_nudge: datetime | None = None
        self.level = 0
        self.break_tokens = 0
        self.break_remaining_s = 0.0
        self._neutral_s = 0.0

    def on_sample(
        self,
        *,
        label: str,
        elapsed_s: float,
        strictness: str,
        meeting: bool = False,
        now: datetime | None = None,
    ) -> NudgeDecision | None:
        """Return the next reminder after sustained drift or continued escalation."""
        strictness = strictness.casefold()
        if self.break_remaining_s > 0:
            self.break_remaining_s = max(0.0, self.break_remaining_s - elapsed_s)
            return None
        if label == "on_task":
            self.on_task_s += elapsed_s
            self._neutral_s = 0
            if self.on_task_s >= 300:
                self._reset_drift()
            return None
        self.on_task_s = 0
        if label == "neutral" or meeting:
            self._neutral_s += elapsed_s
            if self._neutral_s > 20:
                self._reset_drift()
            return None
        if label != "off_task":
            return None

        self._neutral_s = 0
        self.off_task_s += elapsed_s
        desired = (
            3
            if self.off_task_s >= 720 or (strictness == "strict" and self.off_task_s >= 300)
            else 2
            if self.off_task_s >= 300
            else 1
            if self.off_task_s >= self.first_nudge_s
            else 0
        )
        if desired <= self.level:
            return None
        if desired == 2 and self.level == 0 and strictness != "strict":
            desired = 1

        cooldown = 300 if self.level == 1 else 600 if self.level == 2 else 0
        if (
            self.last_nudge is not None
            and now is not None
            and (now - self.last_nudge).total_seconds() < cooldown
        ):
            return None
        self.level = desired
        self.last_nudge = now
        return NudgeDecision(desired, f"Off-task activity for {round(self.off_task_s / 60)} min")

    def _reset_drift(self) -> None:
        self.off_task_s = 0
        self.level = 0
        self.last_nudge = None
        self._neutral_s = 0

    def grant_break(self) -> bool:
        """Allow at most three five-minute break tokens per session."""
        if self.break_tokens >= 3:
            return False
        self.break_tokens += 1
        self.break_remaining_s = 300
        self._reset_drift()
        return True
