import pytest

from focuspilot.ai.rules import (
    classify_activity,
    derive_override_pattern,
    goal_keywords,
    infer_category,
)


def test_classifies_goal_related_app_as_on_task() -> None:
    result = classify_activity(
        goal_category="coding",
        process_name="Code.exe",
        window_title="lesson.py - Visual Studio Code",
    )

    assert result.label == "on_task"
    assert result.category == "coding"


def test_uses_neutral_for_unknown_apps() -> None:
    result = classify_activity(
        goal_category="study",
        process_name="unknown.exe",
        window_title="Untitled",
    )

    assert result.label == "neutral"


@pytest.mark.parametrize(
    ("process", "title"),
    [
        ("chrome.exe", "YouTube - Google Chrome"),
        ("chrome.exe", "Instagram - Google Chrome"),
        ("msedge.exe", "Netflix - Microsoft Edge"),
        ("firefox.exe", "(3) Facebook - Mozilla Firefox"),
        ("chrome.exe", "r/memes - Reddit - Google Chrome"),
    ],
)
def test_distractions_inside_a_browser_are_off_task_for_a_coding_goal(
    process: str, title: str
) -> None:
    result = classify_activity(goal_category="coding", process_name=process, window_title=title)

    assert result.label == "off_task"


def test_unknown_web_page_is_neutral_not_on_task() -> None:
    result = classify_activity(
        goal_category="coding", process_name="chrome.exe", window_title="Some page - Google Chrome"
    )

    assert result.label == "neutral"


def test_work_sites_in_a_browser_are_on_task_for_study() -> None:
    result = classify_activity(
        goal_category="study",
        process_name="chrome.exe",
        window_title="Two Sum - LeetCode - Google Chrome",
    )

    assert result.label == "on_task"


@pytest.mark.parametrize(
    ("process", "title", "expected"),
    [
        ("explorer.exe", "Digital Photos", "other"),  # contains "git" but is not git
        ("notepad.exe", "password list.txt - Notepad", "other"),  # contains "word"
        ("chrome.exe", "Knowledge base - Google Chrome", "browsing"),  # contains "edge"
        ("Code.exe", "main.py - Visual Studio Code", "coding"),
        ("Discord.exe", "#general - Discord", "social"),
    ],
)
def test_category_matching_uses_whole_words(process: str, title: str, expected: str) -> None:
    assert infer_category(process, title) == expected


def test_goal_keyword_in_title_rescues_an_educational_video() -> None:
    result = classify_activity(
        goal_category="study",
        goal_text="Study DSA",
        process_name="chrome.exe",
        window_title="Binary Tree Traversal DSA Lecture - YouTube - Google Chrome",
    )
    unrelated = classify_activity(
        goal_category="study",
        goal_text="Study DSA",
        process_name="chrome.exe",
        window_title="Funny cats - YouTube - Google Chrome",
    )

    assert result.label == "on_task"
    assert unrelated.label == "off_task"


def test_unknown_goal_does_not_call_real_work_off_task() -> None:
    work = classify_activity(
        goal_category="other", process_name="Code.exe", window_title="app.py - Visual Studio Code"
    )
    play = classify_activity(
        goal_category="other", process_name="chrome.exe", window_title="YouTube - Google Chrome"
    )

    assert work.label == "on_task"
    assert play.label == "off_task"


def test_override_wins_over_rules() -> None:
    result = classify_activity(
        goal_category="coding",
        process_name="Spotify.exe",
        window_title="Lo-fi beats",
        override_label="on_task",
    )

    assert result.label == "on_task"


def test_browser_override_is_limited_to_the_site_not_the_whole_browser() -> None:
    assert derive_override_pattern("chrome.exe", "Lecture 3 - YouTube - Google Chrome") == "youtube"
    assert derive_override_pattern("Spotify.exe", "Lo-fi beats") == ""
    assert (
        derive_override_pattern("chrome.exe", "Tab - Example Blog - Google Chrome")
        == "example blog"
    )


def test_goal_keywords_drop_filler_words() -> None:
    assert goal_keywords("Study DSA for 2 hours") == frozenset({"dsa"})
