"""Start-with-Windows support via the per-user Run registry key (no admin rights)."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "FocusPilot"
AUTOSTART_FLAG = "--autostart"


class RunRegistry(Protocol):
    """The three registry operations autostart needs (swappable in tests)."""

    def read(self, name: str) -> str | None: ...

    def write(self, name: str, value: str) -> None: ...

    def delete(self, name: str) -> None: ...


class WindowsRunRegistry:
    """``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`` access."""

    def read(self, name: str) -> str | None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, name)
        except FileNotFoundError:
            return None
        return str(value)

    def write(self, name: str, value: str) -> None:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

    def delete(self, name: str) -> None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, name)
        except FileNotFoundError:
            pass


def autostart_command(
    executable: str | None = None,
    *,
    frozen: bool | None = None,
    exists: Callable[[Path], bool] = Path.exists,
) -> str:
    """Return the command Windows should run at sign-in.

    A packaged build is launched directly. From source the old command always used
    ``python.exe`` (a console window flashing at every login) and, for a packaged
    build, passed ``-m focuspilot`` to FocusPilot.exe, which it does not understand.
    """
    exe = executable or sys.executable
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if is_frozen:
        return f'"{exe}" {AUTOSTART_FLAG}'
    path = Path(exe)
    pythonw = path.with_name("pythonw.exe")
    interpreter = pythonw if exists(pythonw) else path
    return f'"{interpreter}" -m focuspilot {AUTOSTART_FLAG}'


def is_enabled(registry: RunRegistry | None = None) -> bool:
    """Return whether FocusPilot is registered to start with Windows."""
    if registry is None:
        if sys.platform != "win32":
            return False
        registry = WindowsRunRegistry()
    try:
        return registry.read(VALUE_NAME) is not None
    except OSError:
        return False


def set_enabled(enabled: bool, registry: RunRegistry | None = None) -> None:
    """Add or remove the sign-in entry; raises ``OSError`` if Windows refuses."""
    if registry is None:
        if sys.platform != "win32":
            return
        registry = WindowsRunRegistry()
    if enabled:
        registry.write(VALUE_NAME, autostart_command())
    else:
        registry.delete(VALUE_NAME)
