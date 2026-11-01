from datetime import UTC, datetime

from focuspilot.metrics.scoring import calculate_metrics
from focuspilot.storage.models import UsageSegment


def _segment(duration: int, label: str, app: str = "code.exe") -> UsageSegment:
    now = datetime.now(UTC)
    return UsageSegment(
        session_id="session",
        process_name=app,
        window_title="editor",
        started_at=now,
        ended_at=now,
        duration_s=duration,
        idle_s=0,
        category="coding",
        on_task_score=0.9 if label == "on_task" else 0.5,
        label=label,
    )


def test_neutral_time_counts_as_half_focused_time() -> None:
    metrics = calculate_metrics(
        [_segment(60, "on_task"), _segment(60, "neutral", "browser.exe")],
        planned_minutes=2,
    )

    assert metrics.active_s == 120
    assert metrics.focus_s == 90
    assert metrics.score <= 100


def test_unplanned_score_is_capped_at_80() -> None:
    metrics = calculate_metrics(
        [_segment(3600, "on_task")],
        planned_minutes=0,
        planned=False,
    )

    assert metrics.score <= 80


def test_planned_break_time_does_not_change_focus_score() -> None:
    normal = calculate_metrics(
        [_segment(600, "on_task")],
        planned_minutes=10,
    )
    with_break = calculate_metrics(
        [_segment(600, "on_task"), _segment(300, "break", "browser.exe")],
        planned_minutes=10,
    )

    assert with_break.active_s == normal.active_s
    assert with_break.focus_s == normal.focus_s
    assert with_break.score == normal.score


def test_short_glance_away_does_not_break_the_focus_streak() -> None:
    metrics = calculate_metrics(
        [_segment(600, "on_task"), _segment(30, "off_task", "chat.exe"), _segment(600, "on_task")],
        planned_minutes=30,
    )

    assert metrics.longest_focus_streak_s == 1200


def test_long_distraction_does_break_the_focus_streak() -> None:
    metrics = calculate_metrics(
        [_segment(600, "on_task"), _segment(120, "off_task", "chat.exe"), _segment(600, "on_task")],
        planned_minutes=30,
    )

    assert metrics.longest_focus_streak_s == 600
