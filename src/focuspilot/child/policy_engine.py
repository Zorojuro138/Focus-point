"""Transparent child-mode time and schedule policy checks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, time


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """A non-covert child-mode warning or policy result."""

    status: str
    message: str


def _parse_clock(value: str) -> time:
    try:
        hour, minute = value.strip().split(":", maxsplit=1)
        return time(int(hour), int(minute))
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError(f"Invalid 24-hour time: {value!r}") from error


def normalize_clock(value: str) -> str:
    """Return ``value`` as zero-padded ``HH:MM`` or raise ``ValueError``."""
    parsed = _parse_clock(value)
    return f"{parsed.hour:02d}:{parsed.minute:02d}"


def _load_rules(raw: str) -> list[str]:
    """Parse a stored JSON list defensively; a corrupt value means "no rule"."""
    try:
        parsed = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip().casefold() for item in parsed if str(item).strip()]


def _matches(rules: list[str], process_name: str, category: str, window_title: str) -> bool:
    """A rule matches the app name, its category (e.g. "study"), or the window title."""
    app = process_name.casefold()
    title = window_title.casefold()
    return any(rule in app or rule == category or rule in title for rule in rules)


def evaluate_child_policy(
    *,
    daily_usage_s: int,
    daily_limit_min: int,
    bedtime_start: str,
    bedtime_end: str,
    now: datetime,
    process_name: str,
    allowlist_json: str = "[]",
    blocklist_json: str = "[]",
    category: str = "",
    window_title: str = "",
    exempt: bool = False,
) -> PolicyDecision:
    """Return a visible warning for time limits, bedtime, or configured app rules.

    ``now`` must be local wall-clock time. ``exempt`` marks FocusPilot's own windows,
    which are never subject to the app lists.
    """
    allowlist = _load_rules(allowlist_json)
    blocklist = _load_rules(blocklist_json)
    if not exempt:
        if blocklist and _matches(blocklist, process_name, category, window_title):
            return PolicyDecision("app_warning", "This app is on your family's blocked list.")
        if allowlist and not _matches(allowlist, process_name, category, window_title):
            return PolicyDecision("allowlist_warning", "Ask a parent before using this app.")
    start = _parse_clock(bedtime_start)
    end = _parse_clock(bedtime_end)
    current = now.time()
    if start == end:
        in_bedtime = False  # identical times mean "no screen-free period"
    elif start < end:
        in_bedtime = start <= current < end
    else:
        in_bedtime = current >= start or current < end
    if in_bedtime:
        return PolicyDecision("bedtime_warning", "It's your family's screen-free time.")
    remaining = daily_limit_min * 60 - daily_usage_s
    if remaining <= 0:
        return PolicyDecision("limit_reached", "Today's family screen-time limit has been reached.")
    if remaining <= 120:
        return PolicyDecision("limit_warning", f"About {max(1, remaining // 60)} min left today.")
    return PolicyDecision("allowed", "Screen-time is within your family plan.")
