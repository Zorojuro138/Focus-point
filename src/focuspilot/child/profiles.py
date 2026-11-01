"""Age-band defaults for parent-managed family profiles."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import TypedDict


class AgeProfile(TypedDict):
    """Suggested family policy values for an age band."""

    daily_limit_min: int
    bedtime_start: str
    bedtime_end: str
    allowlist: list[str]


def load_age_profiles() -> dict[str, AgeProfile]:
    """Load editable, informational age-band suggestions packaged with the app."""
    data = files("focuspilot").joinpath("data", "age_profiles.json").read_text(encoding="utf-8")
    parsed = json.loads(data)
    if not isinstance(parsed, dict):
        raise ValueError("Age-profile data must be a JSON object.")
    profiles: dict[str, AgeProfile] = {}
    for band, value in parsed.items():
        if (
            not isinstance(band, str)
            or not isinstance(value, dict)
            or not isinstance(value.get("daily_limit_min"), int)
            or not isinstance(value.get("bedtime_start"), str)
            or not isinstance(value.get("bedtime_end"), str)
            or not isinstance(value.get("allowlist"), list)
            or not all(isinstance(item, str) for item in value["allowlist"])
        ):
            raise ValueError(f"Invalid age-profile entry: {band!r}")
        profiles[band] = {
            "daily_limit_min": value["daily_limit_min"],
            "bedtime_start": value["bedtime_start"],
            "bedtime_end": value["bedtime_end"],
            "allowlist": value["allowlist"],
        }
    return profiles
