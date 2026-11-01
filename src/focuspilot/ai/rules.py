"""Fast deterministic classification rules with no network or model dependency.

How an activity is judged (cheapest signal first):

1. A saved user override always wins.
2. The *app* is identified from its executable name; browsers are identified by the
   *site* named in the window title (a browser window is never "research" by itself).
3. If the window title mentions a keyword from the session goal, it is on-task, even on
   a site that is normally a distraction (for example a YouTube lecture on your topic).
4. Otherwise the app/site category is compared with the goal category.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True, slots=True)
class Classification:
    """A local rule-based activity judgement."""

    score: float
    label: str
    category: str
    reason: str


_BROWSERS = frozenset(
    {"chrome", "msedge", "firefox", "brave", "opera", "opera_gx", "vivaldi", "arc", "iexplore"}
)
_BROWSER_LABELS = (
    "google chrome",
    "microsoft edge",
    "mozilla firefox",
    "brave",
    "opera",
    "vivaldi",
)

# Executable name (without ".exe") -> category. Exact names avoid substring accidents
# such as "git" matching "Digital Photos" or "word" matching "password".
_PROCESS_CATEGORIES: dict[str, frozenset[str]] = {
    "coding": frozenset(
        {
            "code",
            "code - insiders",
            "cursor",
            "devenv",
            "pycharm",
            "pycharm64",
            "idea64",
            "webstorm64",
            "clion64",
            "rider64",
            "studio64",
            "sublime_text",
            "notepad++",
            "windowsterminal",
            "wt",
            "powershell",
            "pwsh",
            "cmd",
            "githubdesktop",
            "gitkraken",
            "postman",
            "anaconda-navigator",
            "spyder",
        }
    ),
    "writing": frozenset({"winword", "notion", "obsidian", "onenote", "wordpad", "typora"}),
    "design": frozenset(
        {"figma", "photoshop", "illustrator", "indesign", "blender", "inkscape", "krita", "canva"}
    ),
    "video": frozenset(
        {"premiere pro", "adobe premiere pro", "resolve", "afterfx", "capcut", "obs64", "vegas"}
    ),
    "study": frozenset({"anki", "acrord32", "acrobat", "sumatrapdf"}),
    "gaming": frozenset(
        {
            "steam",
            "steamwebhelper",
            "epicgameslauncher",
            "valorant",
            "valorant-win64-shipping",
            "minecraft",
            "minecraftlauncher",
            "robloxplayerbeta",
            "riotclientservices",
            "leagueclient",
        }
    ),
    "social": frozenset({"discord", "whatsapp", "telegram", "signal"}),
    "entertainment": frozenset({"spotify", "vlc", "wmplayer", "itunes", "musicbee", "netflix"}),
    "communication": frozenset({"teams", "ms-teams", "zoom", "slack", "outlook", "olk", "skype"}),
    "other": frozenset(
        {
            "explorer",
            "notepad",
            "calc",
            "calculatorapp",
            "taskmgr",
            "systemsettings",
            "searchhost",
            "lockapp",
            "shellexperiencehost",
            "applicationframehost",
            "snippingtool",
            "mspaint",
        }
    ),
}
_PROCESS_TO_CATEGORY = {
    name: category for category, names in _PROCESS_CATEGORIES.items() for name in names
}

# Whole-word hints looked up in the window title: the site in a browser tab, or the
# app name for programs whose executable is not recognised. Order matters: distraction
# sites are listed first so "YouTube - Google Chrome" is never mistaken for research.
_TITLE_CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "social",
        (
            "instagram",
            "facebook",
            "twitter",
            "tiktok",
            "snapchat",
            "reddit",
            "whatsapp",
            "telegram",
            "discord",
            "messenger",
            "pinterest",
            "threads",
        ),
    ),
    (
        "entertainment",
        (
            "youtube",
            "netflix",
            "prime video",
            "hotstar",
            "disney+",
            "twitch",
            "spotify",
            "jiocinema",
            "crunchyroll",
            "hulu",
            "zee5",
            "sonyliv",
        ),
    ),
    ("gaming", ("steam", "epic games", "roblox", "minecraft", "valorant", "chess.com", "poki")),
    (
        "coding",
        (
            "github",
            "gitlab",
            "stack overflow",
            "stackoverflow",
            "leetcode",
            "geeksforgeeks",
            "hackerrank",
            "codeforces",
            "codechef",
            "w3schools",
            "mdn web docs",
            "replit",
            "codepen",
            "kaggle",
            "google colab",
            "colab",
            "jupyter",
            "hugging face",
            "visual studio code",
            "visual studio",
            "pycharm",
            "intellij",
            "android studio",
        ),
    ),
    (
        "study",
        (
            "coursera",
            "udemy",
            "khan academy",
            "nptel",
            "edx",
            "unacademy",
            "swayam",
            "google classroom",
            "moodle",
            "brilliant",
            "duolingo",
        ),
    ),
    (
        "research",
        (
            "wikipedia",
            "google scholar",
            "arxiv",
            "researchgate",
            "britannica",
            "chatgpt",
            "claude",
            "gemini",
            "perplexity",
        ),
    ),
    ("writing", ("google docs", "overleaf", "grammarly", "notion")),
    ("design", ("figma", "canva", "behance", "dribbble")),
    ("communication", ("gmail", "outlook", "google meet", "zoom", "microsoft teams", "slack")),
)

_PRODUCTIVE = frozenset({"coding", "study", "writing", "design", "research", "video"})
_DISTRACTING = frozenset({"social", "entertainment", "gaming"})

_RELATED: dict[str, set[str]] = {
    "coding": {"coding", "study", "research", "writing"},
    "study": {"study", "coding", "research", "writing"},
    "writing": {"writing", "study", "research", "coding"},
    "design": {"design", "research", "writing"},
    "research": {"research", "study", "coding", "writing", "design", "video"},
    "video": {"video", "design", "research"},
    "gaming": {"gaming", "entertainment", "social"},
    "social": {"social", "communication"},
    "entertainment": {"entertainment", "gaming", "social"},
    "communication": {"communication", "social"},
}

_GOAL_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "into",
        "that",
        "this",
        "about",
        "some",
        "my",
        "to",
        "of",
        "on",
        "in",
        "at",
        "an",
        "a",
        "study",
        "studying",
        "learn",
        "learning",
        "write",
        "writing",
        "read",
        "reading",
        "work",
        "working",
        "finish",
        "complete",
        "session",
        "focus",
        "hour",
        "hours",
        "hrs",
        "min",
        "mins",
        "minutes",
        "minute",
        "practice",
        "do",
        "doing",
        "make",
        "build",
        "project",
        "task",
        "homework",
        "class",
    }
)


@lru_cache(maxsize=1024)
def _word_pattern(token: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])")


def _has_word(token: str, text: str) -> bool:
    """Return whether ``token`` appears in ``text`` as a whole word or phrase."""
    return _word_pattern(token).search(text) is not None


def _process_stem(process_name: str) -> str:
    name = process_name.casefold().strip()
    return name[:-4] if name.endswith(".exe") else name


def _title_category(title: str) -> str | None:
    for category, keywords in _TITLE_CATEGORIES:
        if any(_has_word(keyword, title) for keyword in keywords):
            return category
    return None


def infer_category(process_name: str, window_title: str) -> str:
    """Infer a broad app category from its executable and visible title."""
    stem = _process_stem(process_name)
    title = window_title.casefold()
    if stem in _BROWSERS:
        return _title_category(title) or "browsing"
    if stem in _PROCESS_TO_CATEGORY:
        return _PROCESS_TO_CATEGORY[stem]
    return _title_category(title) or "other"


def goal_keywords(goal_text: str) -> frozenset[str]:
    """Return the distinctive words of a goal (for example ``dsa`` or ``python``)."""
    words = re.findall(r"[a-z0-9+#.]+", goal_text.casefold())
    return frozenset(
        word.strip(".")
        for word in words
        if len(word.strip(".")) >= 3
        and not word.strip(".").isdigit()
        and word.strip(".") not in _GOAL_STOPWORDS
    )


def derive_override_pattern(process_name: str, window_title: str) -> str:
    """Return the title fragment an "I'm on task" override should be limited to.

    Marking one YouTube tab as on-task must not whitelist all of Chrome, so for browsers
    the override is tied to the site (or page) in the title. Other apps return ``""``,
    meaning the whole app.
    """
    if _process_stem(process_name) not in _BROWSERS:
        return ""
    title = window_title.casefold()
    for _, keywords in _TITLE_CATEGORIES:
        for keyword in keywords:
            if _has_word(keyword, title):
                return keyword
    parts = [part.strip() for part in re.split(r"\s[-–—|]\s", title) if part.strip()]
    parts = [part for part in parts if not any(label in part for label in _BROWSER_LABELS)]
    return parts[-1] if parts else title.strip()


def classify_activity(
    *,
    goal_category: str,
    process_name: str,
    window_title: str,
    override_label: str | None = None,
    goal_text: str = "",
) -> Classification:
    """Classify a sample conservatively; ambiguous apps remain neutral."""
    category = infer_category(process_name, window_title)
    if override_label is not None:
        scores = {"on_task": 0.95, "neutral": 0.5, "off_task": 0.05}
        label = override_label if override_label in scores else "neutral"
        return Classification(scores[label], label, category, "Your saved app preference")

    title = window_title.casefold()
    keywords = goal_keywords(goal_text)
    if keywords and any(_has_word(keyword, title) for keyword in keywords):
        return Classification(0.85, "on_task", category, "Window title mentions your goal")

    if category == "communication":
        return Classification(0.5, "neutral", category, "Communication can support many goals")
    if category == "browsing":
        if goal_category == "research":
            return Classification(0.7, "on_task", category, "Browsing fits a research goal")
        return Classification(0.5, "neutral", category, "Can't tell what this web page is")
    if category == "other":
        return Classification(0.5, "neutral", category, "Not enough context to judge this app")

    if goal_category in _RELATED:
        if category in _RELATED[goal_category]:
            return Classification(0.9, "on_task", category, "App category relates to your goal")
        return Classification(0.1, "off_task", category, "App category differs from your goal")

    # The goal's category is unknown ("other"): don't call real work off-task.
    if category in _PRODUCTIVE:
        return Classification(0.7, "on_task", category, "Looks like productive work")
    if category in _DISTRACTING:
        return Classification(0.25, "off_task", category, "Usually a distraction from work")
    return Classification(0.5, "neutral", category, "Not enough context to judge this app")
