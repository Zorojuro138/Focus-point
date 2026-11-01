import pytest

from focuspilot.session.goal_parser import parse_goal


def test_parses_goal_category_and_hour_duration() -> None:
    parsed = parse_goal("Study DSA for 2 hours")

    assert parsed.text == "Study DSA for 2 hours"
    assert parsed.category == "study"
    assert parsed.duration_minutes == 120


def test_uses_duration_button_fallback_and_neutral_category() -> None:
    parsed = parse_goal("Finish a personal project", fallback_minutes=90)

    assert parsed.category == "other"
    assert parsed.duration_minutes == 90


def test_parses_minute_duration() -> None:
    assert parse_goal("Write for 45 min").duration_minutes == 45


@pytest.mark.parametrize(
    ("text", "minutes"),
    [
        ("Study 1 hour 30 minutes", 90),
        ("Code for 1h30m", 90),
        ("Read for 1.5 hours", 90),
        ("Debug 2 hrs", 120),
        ("Write for 1 hour and 15 min", 75),
    ],
)
def test_parses_compound_and_decimal_durations(text: str, minutes: int) -> None:
    assert parse_goal(text).duration_minutes == minutes


def test_duration_is_clamped_to_a_sane_range() -> None:
    assert parse_goal("Study 1 min").duration_minutes == 5
    assert parse_goal("Study 99 hours").duration_minutes == 720


@pytest.mark.parametrize(
    ("text", "category"),
    [
        ("Get ready for tomorrow", "other"),  # "ready" is not "read"
        ("Classify images", "other"),  # "classify" is not "class"
        ("Reading a chapter", "research"),
        ("Write my report", "writing"),
        ("Reply to emails", "communication"),
        ("Watch a movie", "gaming"),
    ],
)
def test_category_uses_whole_words(text: str, category: str) -> None:
    assert parse_goal(text).category == category
