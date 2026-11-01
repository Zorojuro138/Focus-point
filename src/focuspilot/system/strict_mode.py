"""Foreground-app allowlist enforcement for explicitly opted-in strict sessions."""

from __future__ import annotations

import logging
from pathlib import Path

import psutil

logger = logging.getLogger(__name__)

# Keep essential shell, security, and recovery surfaces usable during strict sessions.
_PROTECTED_APPS = frozenset(
    {
        "applicationframehost.exe",
        "csrss.exe",
        "dwm.exe",
        "explorer.exe",
        "lockapp.exe",
        "logonui.exe",
        "runtimebroker.exe",
        "searchhost.exe",
        "sechealthui.exe",
        "securityhealthsystray.exe",
        "services.exe",
        "sihost.exe",
        "smartscreen.exe",
        "startmenuexperiencehost.exe",
        "shellexperiencehost.exe",
        "systemsettings.exe",
        "taskmgr.exe",
        "textinputhost.exe",
        "useroobe.exe",
        "windows.security.exe",
        "winlogon.exe",
    }
)


def normalize_app_name(value: str) -> str:
    """Compare selected executable names without relying on user-entered casing."""
    return Path(value.strip().strip('"')).name.casefold()


def is_allowed_app(process_name: str, allowed_apps: tuple[str, ...] | list[str]) -> bool:
    """Return true for a selected app or an essential Windows control surface."""
    name = normalize_app_name(process_name)
    if name in _PROTECTED_APPS:
        return True
    return bool(name) and any(normalize_app_name(item) == name for item in allowed_apps)


def close_unapproved_app(pid: int, process_name: str) -> bool:
    """Ask foreground windows to close gracefully; never force-kill or elevate."""
    if is_allowed_app(process_name, []):
        return False
    try:
        process = psutil.Process(pid)
        if process.name().casefold() != normalize_app_name(process_name):
            return False
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as error:
        logger.warning("Could not close unapproved foreground app %s: %s", process_name, error)
        return False
    try:
        import pywintypes
        import win32con
        import win32gui
        import win32process

        posted = False

        def close_window(hwnd: int, _lparam: int) -> bool:
            nonlocal posted
            try:
                _thread_id, window_pid = win32process.GetWindowThreadProcessId(hwnd)
                if window_pid == pid and win32gui.IsWindowVisible(hwnd):
                    posted = bool(win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)) or posted
            except pywintypes.error as error:
                logger.warning("Could not close a window for %s: %s", process_name, error)
            return True

        win32gui.EnumWindows(close_window, 0)
        if not posted:
            logger.warning("No visible window accepted a close request for %s", process_name)
        return posted
    except (OSError, RuntimeError) as error:
        logger.warning("Could not request a graceful close for %s: %s", process_name, error)
        return False
