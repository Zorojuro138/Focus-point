"""Short, honest coaching text built only from the user's own session numbers."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from focuspilot.metrics.scoring import SessionMetrics
from focuspilot.storage.models import UsageSegment


def top_distractions(segments: Iterable[UsageSegment], limit: int = 3) -> list[tuple[str, int]]:
    """Return ``(app, off_task_seconds)`` for the apps that pulled the most time away."""
    totals: dict[str, int] = defaultdict(int)
    for segment in segments:
        if segment.label == "off_task":
            totals[segment.process_name] += max(0, segment.duration_s)
    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    return [(name, seconds) for name, seconds in ranked if seconds >= 60][:limit]


def _app_label(process_name: str) -> str:
    name = process_name.removesuffix(".exe").removesuffix(".EXE")
    return name or process_name


def session_advice(
    metrics: SessionMetrics,
    *,
    planned_minutes: int,
    drift_count: int,
    distractions: list[tuple[str, int]],
) -> str:
    """Return up to three sentences: one win, then the most useful next step."""
    active_min = metrics.active_s // 60
    streak_min = metrics.longest_focus_streak_s // 60
    tips: list[str] = []

    if metrics.active_s < 5 * 60:
        return (
            "That was a very short session, so there isn't much to learn from it yet. "
            "Try one 25-minute block with a single, small goal."
        )

    if metrics.score >= 85:
        tips.append("Excellent focus. You stayed with your intention almost the whole time.")
    elif metrics.score >= 70:
        tips.append("Solid session. You made real space for your goal.")
    elif metrics.score >= 50:
        tips.append("A mixed session, which is normal. Your attention wandered but you kept going.")
    else:
        tips.append("A tough one. Make the next goal smaller and more specific.")

    if streak_min >= 20:
        tips.append(f"Your longest unbroken stretch was {streak_min} min. Build on that.")

    if distractions:
        name, seconds = distractions[0]
        tips.append(
            f"Your biggest pull was {_app_label(name)} ({max(1, seconds // 60)} min). "
            "Close it before your next session."
        )
    elif drift_count >= 3:
        tips.append(f"You were nudged {drift_count} times; try silencing notifications first.")
    elif metrics.switches / max(active_min / 60, 0.1) > 20:
        tips.append("You switched apps a lot. Keeping one window per task makes focus easier.")
    elif metrics.idle_s > 0.25 * (metrics.active_s + metrics.idle_s):
        tips.append("There was a lot of idle time. Pause the session when you step away.")

    if planned_minutes and metrics.focus_s < 0.5 * planned_minutes * 60 and len(tips) < 3:
        tips.append(
            f"You focused for {metrics.focus_s // 60} of {planned_minutes} planned minutes."
        )
    return " ".join(tips[:3])
