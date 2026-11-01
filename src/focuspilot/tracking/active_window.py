"""Foreground-window sampling for Windows."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime

from focuspilot.core.clock import utc_now
from focuspilot.tracking.idle import idle_seconds


@dataclass(frozen=True, slots=True)
class WindowSample:
    """A privacy-limited foreground app sample."""

    process_name: str
    window_title: str
    pid: int
    ts: datetime
    idle_s: float
    page_title: str = ""
    page_url: str = ""


def sample_foreground_window() -> WindowSample | None:
    """Read the active title and executable name without recording input or content.

    Returns ``None`` when there is no foreground window to read (the secure desktop,
    the lock screen, a window that just closed). That is normal, not an error.
    """
    if sys.platform != "win32":
        raise OSError("Foreground-window tracking is only available on Windows.")

    import psutil
    import pywintypes
    import win32gui
    import win32process

    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return None
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        title = win32gui.GetWindowText(hwnd) or "Untitled window"
    except pywintypes.error:
        return None  # the window disappeared between the calls
    try:
        process_name = psutil.Process(pid).name()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        process_name = "Unknown app"
    return WindowSample(process_name, title, pid, utc_now(), idle_seconds())
