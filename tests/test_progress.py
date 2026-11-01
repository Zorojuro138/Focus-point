from datetime import date, datetime, timedelta

from focuspilot.metrics.achievements import (
    SessionFacts,
    current_streak,
    level_progress,
    load_achievement_defs,
    newly_earned,
    xp_for_session,
)
from focuspilot.metrics.coach import session_advice, top_distractions
from focuspilot.metrics.scoring import SessionMetrics
from focuspilot.storage.models import UsageSegment


def _metrics(**overrides) -> SessionMetrics:
    values = dict(
        active_s=1800,
        focus_s=1500,
        off_task_s=0,
        idle_s=0,
        switches=2,
        longest_focus_streak_s=1500,
        score=88,
    )
    values.update(overrides)
    return SessionMetrics(**values)


def test_xp_rewards_focus_completion_and_high_scores() -> None:
    assert xp_for_session(_metrics(), planned_minutes=30, planned=True) == 25 + 50 + 25
    assert xp_for_session(_metrics(score=60), planned_minutes=60, planned=True) == 25
    assert xp_for_session(_metrics(), planned_minutes=0, planned=False) == 25 + 25


def test_level_n_needs_300_times_n_xp() -> None:
    assert level_progress(0) == (1, 0, 300)
    assert level_progress(299) == (1, 299, 300)
    assert level_progress(300) == (2, 0, 600)
    assert level_progress(900) == (3, 0, 900)


def test_streak_counts_consecutive_days_and_tolerates_an_unfinished_today() -> None:
    today = date(2026, 11, 1)
    days = {today - timedelta(days=offset): 3600 for offset in (1, 2, 3)}

    assert current_streak(days, today) == 3  # today not done yet, streak is alive
    days[today] = 3600
    assert current_streak(days, today) == 4
    days[today - timedelta(days=2)] = 100  # a weak day breaks it
    assert current_streak(days, today) == 2


def test_achievements_unlock_from_real_numbers() -> None:
    facts = SessionFacts(
        metrics=_metrics(longest_focus_streak_s=95 * 60, active_s=100 * 60),
        nudges=0,
        planned=True,
        started_local=datetime(2026, 11, 1, 7, 15),
        streak_days=7,
    )

    earned = set(newly_earned(facts, already=set()))
    assert earned == {
        "first_focus",
        "deep_work",
        "early_bird",
        "seven_day_streak",
        "distraction_slayer",
    }
    assert newly_earned(facts, already=earned) == []


def test_a_few_seconds_does_not_unlock_first_focus() -> None:
    facts = SessionFacts(_metrics(active_s=20), 0, True, datetime(2026, 11, 1, 15, 0), 0)

    assert "first_focus" not in newly_earned(facts, set())
    assert "distraction_slayer" not in newly_earned(facts, set())


def test_every_achievement_definition_has_a_rule_or_live_award() -> None:
    codes = {item.code for item in load_achievement_defs()}
    handled = {
        "first_focus",
        "deep_work",
        "early_bird",
        "seven_day_streak",
        "distraction_slayer",
        "comeback",
    }

    assert codes == handled


def _segment(app: str, label: str, seconds: int) -> UsageSegment:
    now = datetime.now()
    return UsageSegment(
        session_id="s",
        process_name=app,
        window_title="",
        started_at=now,
        ended_at=now,
        duration_s=seconds,
        idle_s=0,
        category="x",
        on_task_score=0.1,
        label=label,
    )


def test_top_distractions_ranks_apps_by_off_task_time() -> None:
    result = top_distractions(
        [
            _segment("a.exe", "off_task", 300),
            _segment("b.exe", "off_task", 120),
            _segment("c.exe", "off_task", 20),
            _segment("code.exe", "on_task", 900),
        ]
    )

    assert result == [("a.exe", 300), ("b.exe", 120)]


def test_advice_only_uses_real_numbers() -> None:
    text = session_advice(
        _metrics(score=55), planned_minutes=30, drift_count=1, distractions=[("chrome.exe", 360)]
    )

    assert "chrome" in text and "6 min" in text
    assert session_advice(
        _metrics(active_s=60), planned_minutes=30, drift_count=0, distractions=[]
    ).startswith("That was a very short session")
