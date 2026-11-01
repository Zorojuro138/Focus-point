"""Transparent focus scoring and session metrics."""

from __future__ import annotations

from dataclasses import dataclass

from focuspilot.storage.models import UsageSegment


@dataclass(frozen=True, slots=True)
class SessionMetrics:
    """Calculated session totals."""

    active_s: int
    focus_s: int
    off_task_s: int
    idle_s: int
    switches: int
    longest_focus_streak_s: int
    score: int


def calculate_metrics(
    segments: list[UsageSegment],
    *,
    planned_minutes: int,
    planned: bool = True,
    drift_count: int = 0,
) -> SessionMetrics:
    """Compute score from observed segment values using the product specification."""
    active = sum(max(0, segment.duration_s) for segment in segments if segment.label != "break")
    idle = sum(max(0, segment.idle_s) for segment in segments)
    focus = round(
        sum(
            max(0, segment.duration_s)
            * (1 if segment.label == "on_task" else 0.5 if segment.label == "neutral" else 0)
            for segment in segments
            if segment.label != "break"
        )
    )
    off_task = sum(
        max(0, segment.duration_s) for segment in segments if segment.label == "off_task"
    )
    distinct_apps = [segment.process_name for segment in segments if segment.duration_s > 10]
    switches = sum(
        left != right for left, right in zip(distinct_apps, distinct_apps[1:], strict=False)
    )
    # Longest focus streak: on-task time, tolerating gaps of up to 60 s (a quick glance
    # at chat should not erase an hour of work). Planned breaks neither extend nor break it.
    streak = 0
    longest = 0
    gap = 0
    for segment in segments:
        if segment.label == "break":
            continue
        if segment.label == "on_task":
            streak += max(0, segment.duration_s)
            gap = 0
            longest = max(longest, streak)
        else:
            gap += max(0, segment.duration_s) + max(0, segment.idle_s)
            if gap > 60:
                streak = 0

    if active == 0:
        raw_score = 0.0
    else:
        focus_ratio = focus / active
        switches_per_hour = switches / (active / 3600)
        switch_penalty = min(0.15, 0.01 * max(0, switches_per_hour - 10))
        drift_penalty = min(0.15, 0.03 * drift_count)
        streak_bonus = min(0.10, (longest / 60) / 300)
        completion = min(1.0, focus / max(planned_minutes * 60, 1)) if planned else 0.0
        raw_score = 100 * max(
            0.0,
            min(
                1.0,
                0.60 * focus_ratio
                + 0.25 * completion
                + streak_bonus
                - switch_penalty
                - drift_penalty,
            ),
        )
    if not planned:
        raw_score = min(raw_score, 80)
    return SessionMetrics(active, focus, off_task, idle, switches, longest, round(raw_score))
