import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox

from focuspilot.config import AppConfig
from focuspilot.storage.db import create_database
from focuspilot.storage.repositories import Repository
from focuspilot.ui.consent_dialog import ConsentDialog
from focuspilot.ui.main_window import MainWindow


def test_main_window_renders_opaque_dashboard_and_allows_navigation(qtbot, tmp_path) -> None:
    config = AppConfig(tmp_path)
    engine, factory = create_database(config.database_path)
    repository = Repository(factory)
    user_id = repository.ensure_user()
    window = MainWindow(config, engine, repository, user_id)
    qtbot.addWidget(window)

    assert window.windowTitle() == "FocusPilot"
    assert window.findChild(type(window.hero.start_button), "primaryButton") is not None
    assert window._tracking_badge.text() == "●  NOT TRACKING"
    assert window.child_toggle.isEnabled() is False
    assert not window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert window.palette().window().color().alpha() == 255
    screen = QApplication.primaryScreen()
    assert screen is not None
    assert screen.availableGeometry().contains(window.geometry().center())

    window._nav_buttons["Settings"].click()
    assert window.stack.currentWidget() is window._pages["Settings"]

    window.request_quit()
    engine.dispose()


def test_consent_dialog_checkbox_enables_accept_and_can_be_clicked(qtbot) -> None:
    dialog = ConsentDialog()
    qtbot.addWidget(dialog)
    dialog.show()

    buttons = dialog.findChild(QDialogButtonBox)
    assert buttons is not None
    accept = buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert accept is not None
    assert not accept.isEnabled()

    qtbot.mouseClick(dialog.accept_check, Qt.MouseButton.LeftButton)
    assert accept.isEnabled()
    qtbot.mouseClick(accept, Qt.MouseButton.LeftButton)
    assert dialog.result() == QDialog.DialogCode.Accepted


# ---------------------------------------------------------------- behaviour tests
import os as _os  # noqa: E402
from datetime import UTC, datetime, timedelta  # noqa: E402

from PySide6.QtWidgets import QMessageBox, QPushButton  # noqa: E402

from focuspilot.tracking.active_window import WindowSample  # noqa: E402
from focuspilot.ui.intent_dialog import IntentDialog  # noqa: E402


def _window(qtbot, tmp_path, goal="Write code", category="coding"):
    config = AppConfig(tmp_path)
    engine, factory = create_database(config.database_path)
    repository = Repository(factory)
    user_id = repository.ensure_user()
    window = MainWindow(config, engine, repository, user_id)
    qtbot.addWidget(window)
    window._start_tracking = lambda: None  # no real polling thread in tests
    session = window.manager.start(
        goal_text=goal, goal_category=category, planned_minutes=30, strictness="normal"
    )
    window._begin_tracking(session.started_at)
    return window, repository, engine, session


def _sample(app, title, seconds, pid=4242, idle=0.0):
    return WindowSample(
        app, title, pid, datetime(2026, 1, 1, 12, 0, tzinfo=UTC) + timedelta(seconds=seconds), idle
    )


def test_planned_break_is_recorded_as_break_not_as_distraction(qtbot, tmp_path) -> None:
    window, repository, engine, session = _window(qtbot, tmp_path)
    assert window.nudges.grant_break()

    for second in (0, 2, 4, 6):
        window._on_sample(_sample("chrome.exe", "YouTube - Google Chrome", second))
    window.recorder.flush()

    segments = repository.session_segments(session.id)
    assert segments and {item.label for item in segments} == {"break"}
    window.request_quit()
    engine.dispose()


def test_i_am_on_task_only_whitelists_that_site_not_the_whole_browser(qtbot, tmp_path) -> None:
    window, repository, engine, session = _window(qtbot, tmp_path)
    youtube = _sample("chrome.exe", "Lecture - YouTube - Google Chrome", 0)
    window._show_nudge(1, "Off-task activity for 2 min", youtube)
    dialog = window._nudge_dialog
    assert dialog is not None
    button = next(b for b in dialog.findChildren(QPushButton) if b.text() == "I'm on task")
    button.click()

    assert window._classify_sample(youtube).label == "on_task"
    instagram = _sample("chrome.exe", "Instagram - Google Chrome", 4)
    assert window._classify_sample(instagram).label == "off_task"
    window.request_quit()
    engine.dispose()


def test_own_windows_are_never_judged(qtbot, tmp_path) -> None:
    window, _, engine, _ = _window(qtbot, tmp_path)

    result = window._classify_sample(_sample("python.exe", "FocusPilot", 0, pid=_os.getpid()))

    assert result.label == "neutral"
    window.request_quit()
    engine.dispose()


def test_resumed_child_session_keeps_child_mode(qtbot, tmp_path) -> None:
    window, repository, engine, session = _window(qtbot, tmp_path)
    window.manager.end([])
    child_id = repository.set_child_profile(
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
    child_session = repository.start_session(
        user_id=child_id,
        goal_text="Homework",
        goal_category="study",
        planned_minutes=30,
        strictness="normal",
    )

    window.resume_interrupted(child_session)

    assert window._active_child_id == child_id
    assert window.manager.state == "active"
    window.request_quit()
    engine.dispose()


def test_child_cannot_pause_end_or_quit_without_the_parent_pin(
    qtbot, tmp_path, monkeypatch
) -> None:
    window, repository, engine, session = _window(qtbot, tmp_path)
    window._active_child_id = 99
    monkeypatch.setattr(window, "_verify_parent_pin", lambda prompt: False)

    window._toggle_pause()
    assert window.manager.state == "active"
    window._end_session(ask=True)
    assert window.manager.state == "active"
    assert window.confirm_quit() is False

    monkeypatch.setattr(window, "_verify_parent_pin", lambda prompt: True)
    window._toggle_pause()
    assert window.manager.state == "paused"
    engine.dispose()


def test_nudges_do_not_fire_while_the_user_is_away(qtbot, tmp_path) -> None:
    window, _, engine, _ = _window(qtbot, tmp_path)
    shown = []
    window._show_nudge = lambda *args: shown.append(args)

    for second in range(0, 600, 2):
        window._on_sample(_sample("chrome.exe", "YouTube - Google Chrome", second, idle=300.0))

    assert shown == []
    window.request_quit()
    engine.dispose()


def test_history_shows_local_time_not_utc(qtbot, tmp_path) -> None:
    window, repository, engine, session = _window(qtbot, tmp_path)
    window.manager.end([])

    stored = repository.recent_sessions(1, user_id=window.user_id)[0]
    window._refresh_history()

    expected = stored.started_at.astimezone().strftime("%a, %b %d · %I:%M %p")
    assert window.history_list.item(0).text().startswith(expected)
    window.request_quit()
    engine.dispose()


def test_intent_dialog_refuses_an_empty_goal(qtbot) -> None:
    dialog = IntentDialog()
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted

    dialog.goal.setText("Study DSA for 2 hours")
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    dialog.allowed_app_list.addItem("code.exe")
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.parsed_goal().duration_minutes == 120


def test_unselected_apps_are_off_task_and_strict_mode_closes_them(
    qtbot, tmp_path, monkeypatch
) -> None:
    window, _, engine, session = _window(qtbot, tmp_path)
    session.strictness = "strict"
    session.allowed_apps_json = '["code.exe"]'
    closed = []
    monkeypatch.setattr(
        "focuspilot.ui.main_window.close_unapproved_app",
        lambda pid, app: closed.append((pid, app)) or True,
    )
    monkeypatch.setattr(window, "_show_nudge", lambda *args: None)

    sample = _sample("spotify.exe", "Music - Spotify", 0, pid=7777)
    assert window._classify_sample(sample).label == "off_task"
    window._on_sample(sample)

    assert closed == [(7777, "spotify.exe")]
    assert window._strict_warning_process == "spotify.exe"
    window.request_quit()
    engine.dispose()


def test_finishing_a_session_awards_progress(qtbot, tmp_path, monkeypatch) -> None:
    window, repository, engine, session = _window(qtbot, tmp_path)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )
    start = datetime.now(UTC)
    repository.add_segment(
        session_id=session.id,
        user_id=window.user_id,
        process_name="code.exe",
        window_title="x",
        started_at=start,
        ended_at=start + timedelta(minutes=30),
        duration_s=1800,
        idle_s=0,
        category="coding",
        on_task_score=0.9,
        label="on_task",
    )

    window._end_session(ask=True)

    assert repository.get_xp() >= 30
    assert "first_focus" in repository.unlocked_achievements(window.user_id)
    assert window.level_label.text().startswith("Level 1")
    window.request_quit()
    engine.dispose()
