"""Lightweight, predictable parsing of focus-session intent."""

from __future__ import annotations

import re
from dataclasses import dataclass

MIN_MINUTES = 5
MAX_MINUTES = 12 * 60


@dataclass(frozen=True, slots=True)
class ParsedGoal:
    """The normalized goal category and duration inferred from user text."""

    text: str
    category: str
    duration_minutes: int | None


# Whole-word matching only ("ready" must not look like "read", "classify" like "class").
_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "coding": (
        "code",
        "coding",
        "coded",
        "program",
        "programming",
        "develop",
        "developing",
        "debug",
        "debugging",
        "leetcode",
        "hackathon",
        "app",
        "website",
        "frontend",
        "backend",
    ),
    "study": (
        "study",
        "studying",
        "learn",
        "learning",
        "homework",
        "exam",
        "exams",
        "revise",
        "revision",
        "class",
        "lecture",
        "lectures",
        "assignment",
        "notes",
        "syllabus",
        "dsa",
    ),
    "writing": ("write", "writing", "essay", "draft", "report", "blog", "article", "thesis"),
    "design": ("design", "designing", "draw", "drawing", "illustrate", "prototype", "ui", "ux"),
    "video": ("edit video", "video edit", "video editing", "editing video", "film", "footage"),
    "research": ("research", "read", "reading", "investigate", "paper", "papers", "survey"),
    "communication": ("email", "emails", "reply", "inbox", "meeting", "call"),
    "gaming": (
        "game",
        "games",
        "gaming",
        "break",
        "relax",
        "leisure",
        "watch",
        "movie",
        "netflix",
        "music",
        "play",
    ),
}

_NUMBER = r"(\d+(?:\.\d+)?)"
_HOURS = r"(?:hours?|hrs?|h)"
_MINUTES = r"(?:minutes?|mins?|m)"
_COMPOUND = re.compile(rf"\b{_NUMBER}\s*{_HOURS}\s*(?:and\s*)?{_NUMBER}\s*{_MINUTES}\b")
_SINGLE = re.compile(rf"\b{_NUMBER}\s*({_HOURS}|{_MINUTES})\b")


def _contains_word(text: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None


def _parse_duration(lowered: str) -> int | None:
    """Return minutes from phrases like '2 hours', '45 min', '1h30m' or '1.5 hrs'."""
    compound = _COMPOUND.search(lowered)
    if compound:
        minutes = round(float(compound.group(1)) * 60 + float(compound.group(2)))
    else:
        single = _SINGLE.search(lowered)
        if not single:
            return None
        amount = float(single.group(1))
        minutes = round(amount * 60) if single.group(2).startswith("h") else round(amount)
    return max(MIN_MINUTES, min(MAX_MINUTES, minutes))


def parse_goal(text: str, fallback_minutes: int = 60) -> ParsedGoal:
    """Parse common natural-language duration phrases and broad activity categories."""
    normalized = " ".join(text.split())
    lowered = normalized.casefold()
    category = next(
        (
            candidate
            for candidate, keywords in _CATEGORY_KEYWORDS.items()
            if any(_contains_word(lowered, keyword) for keyword in keywords)
        ),
        "other",
    )
    duration = _parse_duration(lowered)
    if duration is None and fallback_minutes > 0:
        duration = fallback_minutes
    return ParsedGoal(normalized, category, duration)
