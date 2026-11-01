"""Windows idle-time measurement; no keystrokes or mouse data are captured."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes


class _LastInputInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def idle_seconds() -> float:
    """Return seconds since the last input event using the documented Windows API."""
    if sys.platform != "win32":
        raise OSError("Idle-time measurement is only available on Windows.")
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    # Declare the real signatures: GetTickCount64 returns a 64-bit value and ctypes
    # would otherwise truncate it to a C int.
    user32.GetLastInputInfo.argtypes = [ctypes.POINTER(_LastInputInfo)]
    user32.GetLastInputInfo.restype = wintypes.BOOL
    kernel32.GetTickCount64.argtypes = []
    kernel32.GetTickCount64.restype = ctypes.c_uint64

    info = _LastInputInfo()
    info.cbSize = ctypes.sizeof(info)
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        raise ctypes.WinError()
    tick_count = int(kernel32.GetTickCount64())
    # dwTime is a 32-bit tick count that wraps every ~49 days.
    elapsed_ms = (tick_count - info.dwTime) & 0xFFFFFFFF
    return float(elapsed_ms) / 1000
