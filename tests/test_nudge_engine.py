from datetime import UTC, datetime, timedelta

from focuspilot.nudge.nudge_engine import NudgeEngine


def test_nudges_only_after_sustained_drift_and_resets_after_focus() -> None:
    engine = NudgeEngine()

    assert engine.on_sample(label="off_task", elapsed_s=60, strictness="normal") is None
    assert engine.on_sample(label="off_task", elapsed_s=30, strictness="normal").level == 1
    for _ in range(150):
        engine.on_sample(label="on_task", elapsed_s=2, strictness="normal")
    assert engine.off_task_s == 0


def test_break_tokens_are_limited_to_three() -> None:
    engine = NudgeEngine()

    assert [engine.grant_break() for _ in range(4)] == [True, True, True, False]


def test_neutral_blip_does_not_count_as_continuous_drift() -> None:
    engine = NudgeEngine()
    now = datetime.now(UTC)
    for _ in range(40):
        engine.on_sample(
            label="off_task",
            elapsed_s=2,
            strictness="normal",
            now=now,
        )
    for _ in range(11):
        engine.on_sample(
            label="neutral",
            elapsed_s=2,
            strictness="normal",
            now=now + timedelta(seconds=80),
        )
    assert engine.off_task_s == 0


def test_six_minutes_off_task_gives_one_toast_then_one_popup() -> None:
    engine = NudgeEngine()
    now = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    levels = []
    for second in range(0, 7 * 60, 2):
        decision = engine.on_sample(
            label="off_task",
            elapsed_s=2,
            strictness="Normal",
            now=now + timedelta(seconds=second),
        )
        if decision is not None:
            levels.append((decision.level, second))

    assert [level for level, _ in levels] == [1, 2]
    assert 88 <= levels[0][1] <= 94
    assert levels[1][1] - levels[0][1] >= 300  # five-minute cooldown after level 1


def test_strict_mode_reaches_the_overlay_once_the_cooldown_allows() -> None:
    engine = NudgeEngine()
    now = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    seen = set()
    for second in range(0, 8 * 60, 2):
        decision = engine.on_sample(
            label="off_task", elapsed_s=2, strictness="strict", now=now + timedelta(seconds=second)
        )
        if decision:
            seen.add(decision.level)

    assert 3 in seen


def test_break_pauses_nudges_and_clears_drift() -> None:
    engine = NudgeEngine()
    engine.on_sample(label="off_task", elapsed_s=80, strictness="normal")
    assert engine.grant_break()
    assert engine.off_task_s == 0
    assert engine.on_sample(label="off_task", elapsed_s=200, strictness="normal") is None
