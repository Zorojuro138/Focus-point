"""XP, levels, streaks and achievements: a sense of progress built from real numbers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from importlib.resources import files

from focuspilot.metrics.scoring import SessionMetrics

STREAK_MIN_FOCUS_S = 60 * 60
LEVEL_STEP_XP = 300


@dataclass(frozen=True, slots=True)
class AchievementDef:
    """A definition loaded from ``data/achievements.json``."""

    code: str
    title: str
    description: str


@dataclass(frozen=True, slots=True)
class SessionFacts:
    """Everything achievement rules may look at for one finished session."""

    metrics: SessionMetrics
    nudges: int
    planned: bool
    started_local: datetime
    streak_days: int


def load_achievement_defs() -> list[AchievementDef]:
    """Load the packaged achievement list."""
    raw = files("focuspilot").joinpath("data", "achievements.json").read_text(encoding="utf-8")
    return [
        AchievementDef(str(item["code"]), str(item["title"]), str(item["description"]))
        for item in json.loads(raw)
    ]


def xp_for_session(metrics: SessionMetrics, *, planned_minutes: int, planned: bool) -> int:
    """1 XP per focused minute, +50 for finishing a planned block, +25 for a score of 85+."""
    xp = metrics.focus_s // 60
    if planned and planned_minutes > 0 and metrics.focus_s >= 0.8 * planned_minutes * 60:
        xp += 50
    if metrics.score >= 85:
        xp += 25
    return xp


def level_progress(total_xp: int) -> tuple[int, int, int]:
    """Return ``(level, xp_into_level, xp_needed_for_next)``; level n needs 300*n XP."""
    level = 1
    remaining = max(0, total_xp)
    needed = LEVEL_STEP_XP
    while remaining >= needed:
        remaining -= needed
        level += 1
        needed = LEVEL_STEP_XP * level
    return level, remaining, needed


def current_streak(
    focus_by_day: dict[date, int], today: date, minimum_s: int = STREAK_MIN_FOCUS_S
) -> int:
    """Consecutive days with enough focus, ending today (or yesterday if today is open)."""
    day = today if focus_by_day.get(today, 0) >= minimum_s else today - timedelta(days=1)
    streak = 0
    while focus_by_day.get(day, 0) >= minimum_s:
        streak += 1
        day -= timedelta(days=1)
    return streak


def newly_earned(facts: SessionFacts, already: set[str]) -> list[str]:
    """Return achievement codes this session unlocks (``comeback`` is awarded live)."""
    metrics = facts.metrics
    earned: list[str] = []
    if metrics.active_s >= 60:
        earned.append("first_focus")
    if metrics.longest_focus_streak_s >= 90 * 60 and facts.nudges == 0:
        earned.append("deep_work")
    if facts.started_local.hour < 8:
        earned.append("early_bird")
    if facts.streak_days >= 7:
        earned.append("seven_day_streak")
    if facts.nudges == 0 and metrics.active_s >= 10 * 60:
        earned.append("distraction_slayer")
    return [code for code in earned if code not in already]
