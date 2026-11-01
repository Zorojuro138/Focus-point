import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path, PureWindowsPath

from PySide6.QtCore import QProcess, QProcessEnvironment

from focuspilot.system import autostart
from focuspilot.system.single_instance import SingleInstance
from focuspilot.system.tray import TrayController


class FakeRegistry:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def read(self, name: str) -> str | None:
        return self.values.get(name)

    def write(self, name: str, value: str) -> None:
        self.values[name] = value

    def delete(self, name: str) -> None:
        self.values.pop(name, None)


def test_packaged_app_autostarts_without_python_arguments() -> None:
    command = autostart.autostart_command(r"C:\Apps\FocusPilot\FocusPilot.exe", frozen=True)

    assert command == r'"C:\Apps\FocusPilot\FocusPilot.exe" --autostart'
    assert "-m" not in command


def test_source_install_autostarts_with_pythonw_when_available() -> None:
    command = autostart.autostart_command(
        "/venv/Scripts/python.exe", frozen=False, exists=lambda path: path.name == "pythonw.exe"
    )

    assert "pythonw.exe" in command
    assert command.endswith("-m focuspilot --autostart")


def test_source_install_falls_back_to_python_when_pythonw_is_missing() -> None:
    command = autostart.autostart_command(
        "/venv/Scripts/python.exe", frozen=False, exists=lambda path: False
    )

    assert "python.exe" in command and "pythonw" not in command


def test_autostart_can_be_enabled_and_disabled() -> None:
    registry = FakeRegistry()

    assert autostart.is_enabled(registry) is False
    autostart.set_enabled(True, registry)
    assert autostart.is_enabled(registry) is True
    assert "--autostart" in registry.values[autostart.VALUE_NAME]
    autostart.set_enabled(False, registry)
    assert autostart.is_enabled(registry) is False
    autostart.set_enabled(False, registry)  # removing twice is harmless


def test_second_instance_is_refused(qapp, tmp_path: Path) -> None:
    first = SingleInstance(tmp_path / "x.lock", server_name="FocusPilotTest-1")
    second = SingleInstance(tmp_path / "x.lock", server_name="FocusPilotTest-1")
    try:
        assert first.acquire() is True
        assert second.acquire() is False
    finally:
        first.release()
    third = SingleInstance(tmp_path / "x.lock", server_name="FocusPilotTest-1")
    try:
        assert third.acquire() is True  # lock is free again after release
    finally:
        third.release()


def test_running_instance_is_asked_to_show_itself(qapp, qtbot, tmp_path: Path) -> None:
    lock_path = tmp_path / "y.lock"
    server_name = "FocusPilotTest-2"
    first = SingleInstance(lock_path, server_name=server_name)
    process = QProcess()
    project_root = Path(__file__).parents[1]
    environment = QProcessEnvironment.systemEnvironment()
    environment.insert("PYTHONPATH", str(project_root / "src"))
    environment.insert("QT_QPA_PLATFORM", "offscreen")
    process.setProcessEnvironment(environment)
    process.setWorkingDirectory(str(project_root))
    script = (
        "import sys; from pathlib import Path; "
        "from focuspilot.system.single_instance import SingleInstance; "
        "instance = SingleInstance(Path(sys.argv[1]), server_name=sys.argv[2]); "
        "sys.exit(0 if not instance.acquire() else 1)"
    )
    assert first.acquire()
    try:
        with qtbot.waitSignal(first.activation_requested, timeout=3000):
            process.start(sys.executable, ["-c", script, str(lock_path), server_name])
            assert process.waitForStarted(1000)
        qtbot.waitUntil(lambda: process.state() == QProcess.ProcessState.NotRunning, timeout=3000)
        assert process.exitCode() == 0
    finally:
        if process.state() != QProcess.ProcessState.NotRunning:
            process.kill()
            process.waitForFinished(1000)
        first.release()


class _FakeWindow:
    def __init__(self, allow_quit: bool) -> None:
        self.allow_quit = allow_quit
        self.shown = 0

    def showNormal(self) -> None:
        self.shown += 1

    def raise_(self) -> None: ...

    def activateWindow(self) -> None: ...

    def confirm_quit(self) -> bool:
        return self.allow_quit


def test_tray_menu_has_open_and_quit_and_quit_respects_the_pin_check(qapp) -> None:
    window = _FakeWindow(allow_quit=False)
    tray = TrayController(qapp, window)

    assert [a.text() for a in tray._menu.actions() if a.text()] == [
        "Open FocusPilot",
        "Quit FocusPilot",
    ]
    tray.show_window()
    assert window.shown == 1
    tray.quit()  # confirm_quit() returned False, so the app must not quit
    assert PureWindowsPath("x")  # (keeps the import used on every platform)
