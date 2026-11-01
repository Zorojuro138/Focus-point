from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, inspect, select

from focuspilot.storage.db import create_database
from focuspilot.storage.models import DailyStats
from focuspilot.storage.repositories import Repository


def test_session_and_usage_segment_round_trip(tmp_path) -> None:
    engine, factory = create_database(tmp_path / "focuspilot.db")
    repository = Repository(factory)
    user_id = repository.ensure_user()
    session = repository.start_session(
        user_id=user_id,
        goal_text="Study DSA",
        goal_category="study",
        planned_minutes=60,
        strictness="normal",
    )
    now = datetime.now(UTC)
    repository.add_segment(
        session_id=session.id,
        user_id=user_id,
        process_name="code.exe",
        window_title="lesson.py",
        started_at=now,
        ended_at=now,
        duration_s=120,
        idle_s=0,
        category="coding",
        on_task_score=0.9,
        label="on_task",
    )

    assert repository.session_segments(session.id)[0].duration_s == 120
    assert repository.summary()["active_s"] == 120
    assert repository.export_data()["sessions"][0]["goal"] == "Study DSA"
    engine.dispose()


def test_session_app_allowlist_is_persisted(tmp_path) -> None:
    engine, factory = create_database(tmp_path / "allowlist.db")
    repository = Repository(factory)
    user_id = repository.ensure_user()
    session = repository.start_session(
        user_id=user_id,
        goal_text="Study",
        goal_category="study",
        planned_minutes=30,
        strictness="strict",
        allowed_apps=["chrome.exe", "code.exe"],
    )

    restored = repository.active_session()

    assert restored is not None
    assert restored.id == session.id
    assert restored.allowed_apps_json == '["chrome.exe", "code.exe"]'
    assert repository.export_data()["sessions"][0]["allowed_apps"] == ["chrome.exe", "code.exe"]
    repository.set_setting("gemini_api_key", "protected-ciphertext")
    assert all(
        setting["key"] != "gemini_api_key" for setting in repository.export_data()["settings"]
    )
    engine.dispose()


def test_existing_database_gains_session_app_allowlist_column(tmp_path) -> None:
    path = tmp_path / "legacy.db"
    legacy_engine = create_engine(f"sqlite:///{path}")
    with legacy_engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE sessions (
                id VARCHAR(36) PRIMARY KEY,
                user_id INTEGER,
                goal_text TEXT NOT NULL DEFAULT '',
                goal_category VARCHAR(32) NOT NULL DEFAULT 'other',
                planned_minutes INTEGER NOT NULL DEFAULT 0,
                started_at DATETIME NOT NULL,
                ended_at DATETIME,
                focus_score FLOAT,
                status VARCHAR(16) NOT NULL DEFAULT 'active',
                strictness VARCHAR(16) NOT NULL DEFAULT 'normal',
                planned BOOLEAN NOT NULL DEFAULT 1
            )
            """
        )
    legacy_engine.dispose()

    engine, _factory = create_database(path)

    assert "allowed_apps_json" in {
        column["name"] for column in inspect(engine).get_columns("sessions")
    }
    engine.dispose()


def test_retention_rolls_old_segments_into_daily_totals(tmp_path) -> None:
    engine, factory = create_database(tmp_path / "retention.db")
    repository = Repository(factory)
    user_id = repository.ensure_user()
    session = repository.start_session(
        user_id=user_id,
        goal_text="Study",
        goal_category="study",
        planned_minutes=30,
        strictness="normal",
    )
    old = datetime.now(UTC) - timedelta(days=120)
    repository.add_segment(
        session_id=session.id,
        user_id=user_id,
        process_name="code.exe",
        window_title="study",
        started_at=old,
        ended_at=old + timedelta(seconds=600),
        duration_s=600,
        idle_s=0,
        category="study",
        on_task_score=0.9,
        label="on_task",
    )

    removed = repository.prune_segments_before(datetime.now(UTC) - timedelta(days=90))
    with factory() as db:
        stats = db.scalar(select(DailyStats))
    assert removed == 1
    assert stats is not None
    assert stats.active_s == 600
    assert stats.focus_s == 600
    assert repository.session_segments(session.id) == []
    engine.dispose()


def _repo(tmp_path, name="t.db"):
    engine, factory = create_database(tmp_path / name)
    return engine, Repository(factory)


def _segment(repository, session, user_id, label="on_task", seconds=600, when=None, app="code.exe"):
    when = when or datetime.now(UTC)
    repository.add_segment(
        session_id=session.id,
        user_id=user_id,
        process_name=app,
        window_title="x",
        started_at=when,
        ended_at=when + timedelta(seconds=seconds),
        duration_s=seconds,
        idle_s=0,
        category="coding",
        on_task_score=0.9,
        label=label,
    )


def test_datetimes_come_back_timezone_aware(tmp_path) -> None:
    engine, repository = _repo(tmp_path)
    user_id = repository.ensure_user()
    session = repository.start_session(
        user_id=user_id,
        goal_text="x",
        goal_category="study",
        planned_minutes=5,
        strictness="normal",
    )
    reread = repository.active_session()

    assert reread is not None
    assert reread.started_at.tzinfo is not None
    assert reread.started_at == session.started_at
    engine.dispose()


def test_a_later_override_replaces_an_earlier_one(tmp_path) -> None:
    engine, repository = _repo(tmp_path)
    uid = repository.ensure_user()
    repository.save_override(
        user_id=uid, process_name="Spotify.exe", title_pattern="", label="on_task"
    )
    repository.save_override(
        user_id=uid, process_name="spotify.exe", title_pattern="", label="off_task"
    )

    match = repository.matching_override(user_id=uid, process_name="Spotify.exe", window_title="x")
    assert match is not None and match.label == "off_task"
    assert len(repository.list_overrides(uid)) == 1
    engine.dispose()


def test_site_override_beats_app_override_and_does_not_leak_to_other_sites(tmp_path) -> None:
    engine, repository = _repo(tmp_path)
    uid = repository.ensure_user()
    repository.save_override(
        user_id=uid, process_name="chrome.exe", title_pattern="youtube", label="on_task"
    )

    youtube = repository.matching_override(
        user_id=uid, process_name="chrome.exe", window_title="Lecture - YouTube - Google Chrome"
    )
    instagram = repository.matching_override(
        user_id=uid, process_name="chrome.exe", window_title="Instagram - Google Chrome"
    )
    assert youtube is not None and youtube.label == "on_task"
    assert instagram is None
    engine.dispose()


def test_dashboard_numbers_exclude_other_users(tmp_path) -> None:
    engine, repository = _repo(tmp_path)
    parent = repository.ensure_user()
    child = repository.set_child_profile(
        name="Kid",
        pin_hash="x",
        age_band="8-10",
        daily_limit_min=60,
        bedtime_start="20:00",
        bedtime_end="07:00",
        allowlist=[],
        blocklist=[],
        strict_mode=False,
    )
    mine = repository.start_session(
        user_id=parent, goal_text="a", goal_category="study", planned_minutes=5, strictness="normal"
    )
    theirs = repository.start_session(
        user_id=child, goal_text="b", goal_category="study", planned_minutes=5, strictness="normal"
    )
    _segment(repository, mine, parent, seconds=300)
    _segment(repository, theirs, child, seconds=900)

    assert repository.summary(user_id=parent)["active_s"] == 300
    assert repository.summary(user_id=child)["active_s"] == 900
    assert repository.summary()["active_s"] == 1200
    assert sum(int(row["active_s"]) for row in repository.weekly_summary(user_id=parent)) == 300
    engine.dispose()


def test_break_time_is_not_counted_towards_the_childs_daily_limit(tmp_path) -> None:
    engine, repository = _repo(tmp_path)
    repository.ensure_user()
    child = repository.set_child_profile(
        name="Kid",
        pin_hash="x",
        age_band="8-10",
        daily_limit_min=60,
        bedtime_start="20:00",
        bedtime_end="07:00",
        allowlist=[],
        blocklist=[],
        strict_mode=False,
    )
    session = repository.start_session(
        user_id=child, goal_text="b", goal_category="study", planned_minutes=5, strictness="normal"
    )
    _segment(repository, session, child, seconds=300)
    _segment(repository, session, child, label="break", seconds=300)

    assert repository.child_daily_usage(child) == 300
    engine.dispose()


def test_daily_focus_seconds_and_streak_inputs(tmp_path) -> None:
    engine, repository = _repo(tmp_path)
    uid = repository.ensure_user()
    session = repository.start_session(
        user_id=uid, goal_text="a", goal_category="study", planned_minutes=5, strictness="normal"
    )
    _segment(repository, session, uid, label="on_task", seconds=600)
    _segment(repository, session, uid, label="neutral", seconds=600)
    _segment(repository, session, uid, label="off_task", seconds=600)

    today = datetime.now().astimezone().date()
    assert repository.daily_focus_seconds(uid)[today] == 900
    engine.dispose()


def test_xp_and_achievements_are_awarded_once(tmp_path) -> None:
    engine, repository = _repo(tmp_path)
    uid = repository.ensure_user()

    assert repository.add_xp(40) == 40
    assert repository.add_xp(-5) == 40
    assert repository.unlock_achievement(uid, "first_focus") is True
    assert repository.unlock_achievement(uid, "first_focus") is False
    assert repository.unlocked_achievements(uid) == {"first_focus"}
    engine.dispose()


def test_foreign_keys_are_enforced(tmp_path) -> None:
    import pytest
    from sqlalchemy.exc import IntegrityError

    engine, repository = _repo(tmp_path)
    with pytest.raises(IntegrityError):
        repository.add_nudge(session_id="does-not-exist", level=1, reason="x")
    engine.dispose()
