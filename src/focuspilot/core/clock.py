"""Injectable wall clock used by time-sensitive application logic."""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return the current UTC time."""
    return datetime.now(UTC)
