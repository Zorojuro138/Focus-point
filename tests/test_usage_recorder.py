from datetime import UTC, datetime, timedelta

from focuspilot.ai.rules import Classification
from focuspilot.session.session_manager import SessionManager
from focuspilot.storage.db import create_database
from focuspilot.storage.repositories import Repository
from focuspilot.tracking.active_window import WindowSample
from focuspilot.tracking.usage_recorder import UsageRecorder


def test_recorder_merges_windows_and_keeps_idle_out_of_active_time(tmp_path) -> None:
    engine, factory = create_database(tmp_path / "recorder.db")
    repository = Repository(factory)
    manager = SessionManager(repository, repository.ensure_user())
    session = manager.start(
        goal_text="Study",
        goal_category="study",
        planned_minutes=30,
        strictness="normal",
    )
    recorder = UsageRecorder(
        manager,
        lambda sample: Classification(0.9, "on_task", "study", "test rule"),
    )
    start = datetime.now(UTC)
    recorder.consume(WindowSample("browser.exe", "Lesson", 1, start, 0))
    recorder.consume(WindowSample("browser.exe", "Lesson", 1, start + timedelta(seconds=2), 0))
    recorder.consume(WindowSample("code.exe", "Notes", 2, start + timedelta(seconds=4), 0))
    recorder.consume(WindowSample("code.exe", "Notes", 2, start + timedelta(seconds=6), 120))
    recorder.flush()

    segments = repository.session_segments(session.id)
    assert len(segments) == 2
    # The 2 s between the last browser sample and the switch still belong to the browser.
    assert segments[0].duration_s == 4
    assert segments[1].duration_s == 0
    assert segments[1].idle_s == 2
    assert segments[1].label == "idle"
    engine.dispose()


def _recorder(tmp_path, label="on_task"):
    engine, factory = create_database(tmp_path / "r.db")
    repository = Repository(factory)
    manager = SessionManager(repository, repository.ensure_user())
    session = manager.start(
        goal_text="Study", goal_category="study", planned_minutes=30, strictness="normal"
    )
    state = {"label": label}
    recorder = UsageRecorder(
        manager, lambda sample: Classification(0.5, state["label"], "study", "test")
    )
    return engine, repository, session, recorder, state


def test_time_before_going_idle_is_not_counted_as_active(tmp_path) -> None:
    engine, repository, session, recorder, _ = _recorder(tmp_path)
    start = datetime.now(UTC)
    # 2 minutes of "activity" while the user was actually already away.
    for step in range(0, 125, 2):
        idle = max(0, step - 0)  # idle counter grows from the first sample
        recorder.consume(
            WindowSample("video.exe", "Movie", 1, start + timedelta(seconds=step), idle)
        )
    recorder.flush()

    total = repository.session_segments(session.id)
    assert sum(item.duration_s for item in total) < 10
    assert sum(item.idle_s for item in total) > 110
    engine.dispose()


def test_label_change_in_same_window_starts_new_segment(tmp_path) -> None:
    """A planned break starting mid-window must not be recorded as ordinary time."""
    engine, repository, session, recorder, state = _recorder(tmp_path)
    start = datetime.now(UTC)
    for step in (0, 2, 4):
        recorder.consume(WindowSample("chrome.exe", "Page", 1, start + timedelta(seconds=step), 0))
    state["label"] = "break"
    for step in (6, 8, 10):
        recorder.consume(WindowSample("chrome.exe", "Page", 1, start + timedelta(seconds=step), 0))
    recorder.flush()

    labels = [item.label for item in repository.session_segments(session.id)]
    assert labels == ["on_task", "break"]
    engine.dispose()
