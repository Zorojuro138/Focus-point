"""Primary FocusPilot desktop interface and user-facing app workflows."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QTime, QUrl
from PySide6.QtGui import QCloseEvent, QColor, QDesktopServices, QGuiApplication, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.engine import Engine

from focuspilot.ai.gemini import BrowserPage
from focuspilot.ai.rules import (
    Classification,
    classify_activity,
    derive_override_pattern,
    infer_category,
)
from focuspilot.ai.service import AIService
from focuspilot.child.parent_auth import ParentPinVerifier, hash_pin
from focuspilot.child.policy_engine import evaluate_child_policy, normalize_clock
from focuspilot.child.profiles import load_age_profiles
from focuspilot.config import AppConfig
from focuspilot.metrics.achievements import (
    SessionFacts,
    current_streak,
    level_progress,
    load_achievement_defs,
    newly_earned,
    xp_for_session,
)
from focuspilot.metrics.coach import session_advice, top_distractions
from focuspilot.nudge.nudge_engine import NudgeEngine
from focuspilot.session.session_manager import SessionManager, SessionSummary
from focuspilot.storage.db import delete_database
from focuspilot.storage.models import FocusSession, UsageSegment
from focuspilot.storage.repositories import Repository
from focuspilot.system import autostart
from focuspilot.system.browser_metadata import BrowserMetadataServer, current_page
from focuspilot.system.secrets import protect_secret, unprotect_secret
from focuspilot.system.strict_mode import close_unapproved_app, is_allowed_app
from focuspilot.tracking.active_window import WindowSample
from focuspilot.tracking.usage_recorder import IDLE_THRESHOLD_S, UsageRecorder
from focuspilot.tracking.worker import TrackingThread
from focuspilot.ui.consent_dialog import ConsentDialog
from focuspilot.ui.dashboard import Card, FocusHero, MetricCard, PageHeader, WeeklyChart
from focuspilot.ui.intent_dialog import IntentDialog

logger = logging.getLogger(__name__)


class _SettingsAttemptStore:
    """Persist PIN-attempt state in the settings table so a restart can't reset it."""

    def __init__(self, repository: Repository) -> None:
        self._repository = repository

    def get(self, key: str, default: str = "") -> str:
        return self._repository.get_setting(key, default)

    def put(self, key: str, value: str) -> None:
        self._repository.set_setting(key, value)


_CANVAS = QColor("#f5f7f2")
_INK = QColor("#17231f")


def _make_opaque(widget: QWidget, color: QColor = _CANVAS) -> None:
    """Avoid transparent native-window backdrops and paint a stable Qt surface."""
    widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
    widget.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)
    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    widget.setAutoFillBackground(True)
    palette = widget.palette()
    palette.setColor(QPalette.ColorRole.Window, color)
    palette.setColor(QPalette.ColorRole.Base, color)
    palette.setColor(QPalette.ColorRole.WindowText, _INK)
    palette.setColor(QPalette.ColorRole.Text, _INK)
    widget.setPalette(palette)
    if widget.isWindow():
        widget.setWindowOpacity(1.0)


_STYLE = """
QMainWindow, QWidget#appRoot { background-color: #f5f7f2; color: #17231f; }
QWidget { font-family: "Segoe UI"; font-size: 13px; }
QWidget#sidebar { background-color: #17231f; }
QWidget#mainContent, QStackedWidget, QScrollArea, QScrollArea QWidget#scrollContent {
  background-color: #f5f7f2; color: #17231f; border: 0;
}
QScrollArea QWidget#scrollViewport { background-color: #f5f7f2; }
QDialog { background-color: #f8faf6; color: #17231f; }
QLabel { color: #17231f; background-color: transparent; }
QLabel#muted { color: #69766d; }
QCheckBox { color: #17231f; background-color: transparent; spacing: 9px; }
QCheckBox::indicator { width: 18px; height: 18px; }
QCheckBox::indicator:unchecked {
  background-color: white; border: 1px solid #879389; border-radius: 4px;
}
QCheckBox::indicator:checked {
  background-color: #57923b; border: 1px solid #57923b; border-radius: 4px;
}
QPushButton { color: #17231f; }
QPushButton:disabled { color: #68746c; background-color: #e6e9e3; }
QLabel#brand { color: #f7faf4; font-size: 22px; font-weight: 800; }
QLabel#brandMark { color: #b7f36b; font-size: 22px; font-weight: 900; }
QLabel#sidebarCaption { color: #94a49a; font-size: 10px; font-weight: 700; }
QPushButton#navButton { text-align: left; color: #bcc7c0; padding: 11px 13px;
  border: 0; border-radius: 10px; background: transparent; font-weight: 600; }
QPushButton#navButton:hover { background: #26352d; color: white; }
QPushButton#navButton[selected="true"] { background: #2e4035; color: #c9f994; }
QLabel#pageTitle { font-size: 27px; font-weight: 800; letter-spacing: -0.5px; }
QLabel#muted { color: #77847c; }
QLabel#eyebrow { color: #7f8b82; font-size: 10px; font-weight: 800; letter-spacing: 1px; }
QLabel#metricValue { font-size: 25px; font-weight: 800; }
QFrame#card { background-color: #ffffff; border: 1px solid #e8ece5; border-radius: 18px; }
QFrame#focusHero { background-color: #17231f; border: 0; border-radius: 22px; }
QLabel#heroTitle { color: white; font-size: 23px; font-weight: 800; }
QLabel#heroSubtitle { color: #c1ccc4; }
QProgressBar#focusRing { border: 7px solid #36443b; border-radius: 56px;
  color: white; font-size: 21px; font-weight: 800; background-color: #17231f; }
QPushButton#primaryButton { color: #17231f; background-color: #b7f36b; padding: 12px 17px;
  border: 0; border-radius: 11px; font-weight: 800; }
QPushButton#primaryButton:hover { background-color: #c8fa8a; }
QPushButton#secondaryButton { color: #17231f; background-color: white; padding: 10px 15px;
  border: 1px solid #dfe5dc; border-radius: 10px; font-weight: 700; }
QPushButton#secondaryButton:hover { background-color: #f2f5ee; }
QPushButton#dangerButton { color: white; background-color: #b84742; padding: 10px 15px;
  border: 0; border-radius: 10px; font-weight: 700; }
QPushButton#dangerButton:hover { background-color: #a63c38; }
QLineEdit, QComboBox, QSpinBox, QTimeEdit {
  color: #17231f; background-color: white; selection-background-color: #57923b;
  selection-color: white; border: 1px solid #dfe5dc;
  border-radius: 9px; padding: 9px; min-height: 20px; }
QComboBox QAbstractItemView {
  color: #17231f; background-color: white; selection-background-color: #e6f3da;
}
QListWidget { color: #17231f; background-color: white; border: 0; }
QListWidget::item { color: #17231f; padding: 12px; border-bottom: 1px solid #eef0eb; }
QLabel#dialogHeading { font-size: 21px; font-weight: 800; }
QToolTip { color: white; background: #17231f; border: 0; padding: 5px; }
QProgressBar#xpBar { background-color: #e8ece5; border: 0; border-radius: 5px; }
QProgressBar#xpBar::chunk { background-color: #78a848; border-radius: 5px; }
"""


class MainWindow(QMainWindow):
    """Main window, local session workflows, and tracking lifecycle."""

    def __init__(
        self,
        config: AppConfig,
        engine: Engine,
        repository: Repository,
        user_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.engine = engine
        self.repository = repository
        self.user_id = user_id
        self.manager = SessionManager(repository, user_id)
        self.ai = AIService(self._gemini_api_key, self)
        self.ai.classification_ready.connect(self._ai_classification_ready)
        self.ai.classification_failed.connect(self._ai_classification_failed)
        self.ai.chat_ready.connect(self._ai_chat_ready)
        self.ai.chat_failed.connect(self._ai_chat_failed)
        self.browser_metadata = BrowserMetadataServer(lambda: self.manager.state == "active")
        self.browser_metadata.bridge.metadata_received.connect(self._receive_browser_metadata)
        self.tracker: TrackingThread | None = None
        self.recorder: UsageRecorder | None = None
        self.nudges = NudgeEngine()
        self.pin_verifier = ParentPinVerifier(store=_SettingsAttemptStore(repository))
        self.notifier: Callable[[str, str], None] | None = None
        self._own_pid = os.getpid()
        self._override_rules: list[tuple[str, str, str]] = []
        self._last_sample_ts: datetime | None = None
        self._comeback_deadline: datetime | None = None
        self._current_sample: WindowSample | None = None
        self._current_classification: Classification | None = None
        self._browser_page: BrowserPage | None = None
        self._browser_page_received = 0.0
        self._last_ai_page_key: tuple[str, str] | None = None
        self._ai_page_results: dict[tuple[str, str], Classification] = {}
        self._chat_history: list[tuple[str, str]] = []
        self._strict_warning_process = ""
        self._strict_close_failed = False
        self._active_started = datetime.now(UTC)
        self._active_elapsed = 0
        self._pause_started: datetime | None = None
        self._nudge_dialog: QDialog | None = None
        self._active_child_id: int | None = None
        self._quitting = False
        self._pages: dict[str, QWidget] = {}
        self._nav_buttons: dict[str, QPushButton] = {}

        self.setWindowTitle("FocusPilot")
        self.setWindowFlag(Qt.WindowType.Window, True)
        _make_opaque(self)
        self.setMinimumSize(900, 620)
        self.resize(1240, 820)
        self.setStyleSheet(_STYLE)
        self._build_shell()
        self._place_on_primary_screen()
        self._refresh_all()

    def _place_on_primary_screen(self) -> None:
        """Start on the primary display instead of a disconnected secondary monitor."""
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        self.setMinimumSize(min(900, available.width()), min(620, available.height()))
        width = min(max(self.width(), self.minimumWidth()), available.width())
        height = min(max(self.height(), self.minimumHeight()), available.height())
        self.resize(width, height)
        self.move(
            available.x() + (available.width() - width) // 2,
            available.y() + (available.height() - height) // 2,
        )

    def _build_shell(self) -> None:
        root = QWidget()
        root.setObjectName("appRoot")
        _make_opaque(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_sidebar())

        right = QWidget()
        right.setObjectName("mainContent")
        _make_opaque(right)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        self._topbar = self._build_topbar()
        right_layout.addWidget(self._topbar)
        self.stack = QStackedWidget()
        _make_opaque(self.stack)
        right_layout.addWidget(self.stack, 1)
        outer.addWidget(right, 1)
        self.setCentralWidget(root)
        self._build_pages()
        self._show_page("Overview")

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        _make_opaque(sidebar, QColor("#17231f"))
        sidebar_palette = sidebar.palette()
        sidebar_palette.setColor(QPalette.ColorRole.WindowText, QColor("#f7faf4"))
        sidebar_palette.setColor(QPalette.ColorRole.Text, QColor("#f7faf4"))
        sidebar.setPalette(sidebar_palette)
        sidebar.setFixedWidth(220)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(17, 24, 17, 18)
        layout.setSpacing(8)
        brand = QHBoxLayout()
        mark = QLabel("✳")
        mark.setObjectName("brandMark")
        title = QLabel("focuspilot")
        title.setObjectName("brand")
        brand.addWidget(mark)
        brand.addWidget(title)
        brand.addStretch()
        layout.addLayout(brand)
        layout.addSpacing(26)
        caption = QLabel("YOUR SPACE")
        caption.setObjectName("sidebarCaption")
        layout.addWidget(caption)
        for label in ("Overview", "Focus session", "Insights", "AI coach", "Settings"):
            button = QPushButton(self._nav_text(label))
            button.setObjectName("navButton")
            button.setProperty("selected", False)
            button.clicked.connect(lambda checked=False, name=label: self._show_page(name))
            self._nav_buttons[label] = button
            layout.addWidget(button)
        layout.addSpacing(12)
        family_caption = QLabel("FAMILY")
        family_caption.setObjectName("sidebarCaption")
        layout.addWidget(family_caption)
        child_button = QPushButton("  ♧   Parent controls")
        child_button.setObjectName("navButton")
        child_button.clicked.connect(lambda: self._show_page("Parent controls"))
        self._nav_buttons["Parent controls"] = child_button
        layout.addWidget(child_button)
        layout.addStretch()
        local = QLabel("●  Your data, your choice")
        local.setStyleSheet("color:#b7f36b; font-weight:700; padding:8px;")
        layout.addWidget(local)
        version = QLabel("FOCUS PILOT  ·  0.1")
        version.setObjectName("sidebarCaption")
        layout.addWidget(version)
        return sidebar

    @staticmethod
    def _nav_text(label: str) -> str:
        icons = {
            "Overview": "◫",
            "Focus session": "◎",
            "Insights": "⌁",
            "AI coach": "✦",
            "Settings": "⚙",
        }
        return f"  {icons[label]}   {label}"

    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet("background:#ffffff; border-bottom:1px solid #e8ece5;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(26, 13, 26, 13)
        self._top_context = QLabel("Your focus, at a glance")
        self._top_context.setStyleSheet("font-weight:700;")
        layout.addWidget(self._top_context)
        layout.addStretch()
        self._tracking_badge = QLabel("●  NOT TRACKING")
        self._tracking_badge.setStyleSheet(
            "color:#77847c; background:#f0f3ed; padding:8px 11px; border-radius:12px; "
            "font-size:10px; font-weight:800;"
        )
        layout.addWidget(self._tracking_badge)
        return bar

    def _build_pages(self) -> None:
        self._pages = {
            "Overview": self._build_overview(),
            "Focus session": self._build_focus_page(),
            "Insights": self._build_insights_page(),
            "AI coach": self._build_ai_page(),
            "Settings": self._build_settings_page(),
            "Parent controls": self._build_parent_page(),
        }
        for page in self._pages.values():
            self.stack.addWidget(page)

    def _page(self, content: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("scrollViewport")
        _make_opaque(scroll)
        _make_opaque(scroll.viewport())
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        return scroll

    @staticmethod
    def _content_layout(title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
        content = QWidget()
        content.setObjectName("scrollContent")
        _make_opaque(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(30, 27, 30, 32)
        layout.setSpacing(19)
        layout.addWidget(PageHeader(title, subtitle))
        return content, layout

    def _build_overview(self) -> QWidget:
        content, layout = self._content_layout(
            "Good to see you.", "Your time is yours. FocusPilot helps you spend it with intention."
        )
        self.hero = FocusHero()
        self.hero.start_button.clicked.connect(self._start_session)
        layout.addWidget(self.hero)

        metrics = QHBoxLayout()
        metrics.setSpacing(13)
        self.metric_focus = MetricCard("Focus today", "0m", "Intentional screen time")
        self.metric_sessions = MetricCard("Sessions", "0", "Completed today")
        self.metric_score = MetricCard("Average score", "—", "Build your baseline")
        self.metric_idle = MetricCard("Idle time", "0m", "Excluded after 2 minutes")
        for card in (self.metric_focus, self.metric_sessions, self.metric_score, self.metric_idle):
            metrics.addWidget(card, 1)
        layout.addLayout(metrics)

        row = QHBoxLayout()
        row.setSpacing(14)
        chart_card = Card()
        chart_layout = QVBoxLayout(chart_card)
        chart_layout.setContentsMargins(18, 15, 18, 8)
        chart_header = QHBoxLayout()
        chart_title = QLabel("Your week")
        chart_title.setStyleSheet("font-size:16px;font-weight:800;")
        self.chart_total = QLabel("Last 7 days")
        self.chart_total.setObjectName("muted")
        chart_header.addWidget(chart_title)
        chart_header.addStretch()
        chart_header.addWidget(self.chart_total)
        chart_layout.addLayout(chart_header)
        self.weekly_chart = WeeklyChart()
        chart_layout.addWidget(self.weekly_chart)
        row.addWidget(chart_card, 3)

        tip = Card()
        tip_layout = QVBoxLayout(tip)
        tip_layout.setContentsMargins(19, 17, 19, 17)
        tip_title = QLabel("A gentle reminder")
        tip_title.setStyleSheet("font-size:15px;font-weight:800;")
        tip_icon = QLabel("✦")
        tip_icon.setStyleSheet("color:#78a848;font-size:22px;")
        tip_layout.addWidget(tip_icon)
        tip_layout.addWidget(tip_title)
        tip_layout.addWidget(
            QLabel(
                "A clear intention makes it easier to notice when your attention "
                "wanders. Start small, and take breaks when you need them."
            ),
            1,
        )
        local_label = QLabel("Your data stays on this device.")
        local_label.setObjectName("muted")
        tip_layout.addWidget(local_label)
        row.addWidget(tip, 2)
        layout.addLayout(row)

        activity_card = Card()
        activity_layout = QVBoxLayout(activity_card)
        activity_layout.setContentsMargins(18, 15, 18, 16)
        activity_head = QHBoxLayout()
        activity_label = QLabel("RECENT SESSIONS")
        activity_label.setObjectName("eyebrow")
        activity_head.addWidget(activity_label)
        activity_head.addStretch()
        view_all = QPushButton("View history  →")
        view_all.setObjectName("secondaryButton")
        view_all.clicked.connect(lambda: self._show_page("Insights"))
        activity_head.addWidget(view_all)
        activity_layout.addLayout(activity_head)
        self.recent_list = QListWidget()
        self.recent_list.setMaximumHeight(210)
        activity_layout.addWidget(self.recent_list)
        layout.addWidget(activity_card)
        layout.addStretch()
        return self._page(content)

    def _build_focus_page(self) -> QWidget:
        content, layout = self._content_layout(
            "Focus session", "One intention at a time. Pause whenever you need to."
        )
        self.session_card = Card()
        card_layout = QVBoxLayout(self.session_card)
        card_layout.setContentsMargins(24, 22, 24, 22)
        self.session_state = QLabel("No session in progress")
        self.session_state.setObjectName("eyebrow")
        self.session_goal = QLabel("Ready when you are.")
        self.session_goal.setStyleSheet("font-size:24px;font-weight:800;")
        self.session_timer = QLabel("00:00:00")
        self.session_timer.setStyleSheet("font-size:48px;font-weight:800;color:#24392d;")
        self.session_activity = QLabel("Activity tracking is off.")
        self.session_activity.setObjectName("muted")
        self.session_ai_status = QLabel("AI browser checks are optional.")
        self.session_ai_status.setObjectName("muted")
        controls = QHBoxLayout()
        self.pause_button = QPushButton("Pause")
        self.pause_button.setObjectName("secondaryButton")
        self.pause_button.clicked.connect(self._toggle_pause)
        self.end_button = QPushButton("End session")
        self.end_button.setObjectName("dangerButton")
        self.end_button.clicked.connect(lambda: self._end_session(ask=True))
        self.focus_start_button = QPushButton("Start a session")
        self.focus_start_button.setObjectName("primaryButton")
        self.focus_start_button.clicked.connect(self._start_session)
        controls.addWidget(self.focus_start_button)
        controls.addWidget(self.pause_button)
        controls.addWidget(self.end_button)
        controls.addStretch()
        card_layout.addWidget(self.session_state)
        card_layout.addWidget(self.session_goal)
        card_layout.addWidget(self.session_timer)
        card_layout.addWidget(self.session_activity)
        card_layout.addWidget(self.session_ai_status)
        card_layout.addSpacing(10)
        card_layout.addLayout(controls)
        layout.addWidget(self.session_card)
        privacy = Card()
        privacy_layout = QVBoxLayout(privacy)
        privacy_layout.setContentsMargins(20, 17, 20, 17)
        privacy_heading = QLabel("WHAT IS RECORDED")
        privacy_heading.setObjectName("eyebrow")
        privacy_layout.addWidget(privacy_heading)
        privacy_layout.addWidget(
            QLabel(
                "Local history stores the foreground app, visible title, timestamps, and idle "
                "time. The optional browser extension shares only title and URL path; no "
                "screenshots, page contents, keystrokes, or passwords."
            )
        )
        layout.addWidget(privacy)
        layout.addStretch()
        self._update_session_controls()
        return self._page(content)

    def _build_insights_page(self) -> QWidget:
        content, layout = self._content_layout(
            "Your insights", "A simple, private record of how your focus is growing."
        )
        self.history_summary = MetricCard("Focus today", "0m", "Tracked active time")
        layout.addWidget(self.history_summary)

        progress_card = Card()
        progress_layout = QVBoxLayout(progress_card)
        progress_layout.setContentsMargins(18, 16, 18, 16)
        progress_heading = QLabel("PROGRESS")
        progress_heading.setObjectName("eyebrow")
        self.level_label = QLabel("Level 1")
        self.level_label.setStyleSheet("font-size:20px;font-weight:800;")
        self.xp_bar = QProgressBar()
        self.xp_bar.setObjectName("xpBar")
        self.xp_bar.setTextVisible(False)
        self.xp_bar.setFixedHeight(10)
        self.streak_label = QLabel("Focus streak: 0 days")
        self.streak_label.setObjectName("muted")
        self.achievement_list = QListWidget()
        self.achievement_list.setMaximumHeight(250)
        progress_layout.addWidget(progress_heading)
        progress_layout.addWidget(self.level_label)
        progress_layout.addWidget(self.xp_bar)
        progress_layout.addWidget(self.streak_label)
        progress_layout.addSpacing(8)
        progress_layout.addWidget(self.achievement_list)
        layout.addWidget(progress_card)

        history_card = Card()
        history_layout = QVBoxLayout(history_card)
        history_layout.setContentsMargins(18, 16, 18, 16)
        history_heading = QLabel("SESSION HISTORY")
        history_heading.setObjectName("eyebrow")
        history_layout.addWidget(history_heading)
        self.history_list = QListWidget()
        history_layout.addWidget(self.history_list)
        layout.addWidget(history_card)
        layout.addStretch()
        return self._page(content)

    def _build_ai_page(self) -> QWidget:
        content, layout = self._content_layout(
            "Your AI coach", "A friendly check-in for your goal—never a secret screen watcher."
        )
        privacy = Card()
        privacy_layout = QVBoxLayout(privacy)
        privacy_layout.setContentsMargins(20, 16, 20, 16)
        privacy_title = QLabel("✦  GEMINI FREE · METADATA ONLY")
        privacy_title.setObjectName("eyebrow")
        privacy_layout.addWidget(privacy_title)
        privacy_layout.addWidget(
            QLabel(
                "During a focus session, FocusPilot may send your goal, browser tab title, "
                "and website plus page path to Gemini Free for a relevance check. URL "
                "queries and fragments are removed. No screenshots, page contents, or "
                "keystrokes are sent. Chat messages are sent only when you press Send."
            )
        )
        layout.addWidget(privacy)

        chat_card = Card()
        chat_layout = QVBoxLayout(chat_card)
        chat_layout.setContentsMargins(18, 16, 18, 16)
        chat_heading = QLabel("Chat with your focus coach")
        chat_heading.setStyleSheet("font-size:17px;font-weight:800;")
        self.ai_chat = QPlainTextEdit()
        self.ai_chat.setReadOnly(True)
        self.ai_chat.setPlaceholderText("Try: “Help me break my goal into a 25-minute first step.”")
        self.ai_chat.setMinimumHeight(240)
        self.ai_chat_entry = QLineEdit()
        self.ai_chat_entry.setPlaceholderText("Ask for a small, practical next step…")
        self.ai_chat_entry.returnPressed.connect(self._send_chat_message)
        send = QPushButton("Send  →")
        send.setObjectName("primaryButton")
        send.clicked.connect(self._send_chat_message)
        chat_input = QHBoxLayout()
        chat_input.addWidget(self.ai_chat_entry, 1)
        chat_input.addWidget(send)
        self.ai_chat_status = QLabel("Set up a free Gemini API key in Settings to begin.")
        self.ai_chat_status.setObjectName("muted")
        chat_layout.addWidget(chat_heading)
        chat_layout.addWidget(self.ai_chat)
        chat_layout.addLayout(chat_input)
        chat_layout.addWidget(self.ai_chat_status)
        layout.addWidget(chat_card)
        layout.addStretch()
        return self._page(content)

    def _build_settings_page(self) -> QWidget:
        content, layout = self._content_layout(
            "Settings", "Tune your focus space and choose what stays on this device."
        )
        privacy = Card()
        privacy_layout = QVBoxLayout(privacy)
        privacy_layout.setContentsMargins(20, 18, 20, 18)
        privacy_layout.addWidget(QLabel("Privacy & consent"))
        privacy_layout.addWidget(
            QLabel(
                "App history stays on this PC. During sessions, the optional browser "
                "extension shares only the active tab title and URL path with FocusPilot. "
                "Gemini receives only the data described on the AI coach page. No screenshots."
            )
        )
        self.reset_consent_button = QPushButton("Review tracking consent")
        self.reset_consent_button.setObjectName("secondaryButton")
        self.reset_consent_button.clicked.connect(self._review_consent)
        privacy_layout.addWidget(self.reset_consent_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(privacy)

        ai_card = Card()
        ai_layout = QVBoxLayout(ai_card)
        ai_layout.setContentsMargins(20, 18, 20, 18)
        ai_layout.addWidget(QLabel("Gemini Free AI"))
        ai_layout.addWidget(
            QLabel(
                "Create a free Gemini API key in Google AI Studio. The key is encrypted "
                "for your Windows account. FocusPilot uses only the configured free-tier "
                "model and never switches to a paid model. Before saving, use a Google "
                "project with billing disabled; FocusPilot cannot verify your provider's "
                "billing settings."
            )
        )
        self.gemini_consent_check = QCheckBox(
            "Allow Gemini Free to receive session goals and browser title/URL paths. "
            "Chat is sent only when I press Send."
        )
        self.gemini_consent_check.setChecked(
            self.repository.get_setting("gemini_consent", "false") == "true"
        )
        self.gemini_consent_check.toggled.connect(
            lambda checked: self.repository.set_setting("gemini_consent", str(checked).lower())
        )
        ai_layout.addWidget(self.gemini_consent_check)
        key_row = QHBoxLayout()
        self.gemini_key_input = QLineEdit()
        self.gemini_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.gemini_key_input.setPlaceholderText("Paste a Gemini API key")
        self.gemini_key_input.setClearButtonEnabled(True)
        save_key = QPushButton("Save key")
        save_key.setObjectName("primaryButton")
        save_key.clicked.connect(self._save_gemini_key)
        clear_key = QPushButton("Remove key")
        clear_key.setObjectName("secondaryButton")
        clear_key.clicked.connect(self._remove_gemini_key)
        get_key = QPushButton("Get free key")
        get_key.setObjectName("secondaryButton")
        get_key.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://aistudio.google.com/apikey"))
        )
        key_row.addWidget(self.gemini_key_input, 1)
        key_row.addWidget(save_key)
        key_row.addWidget(clear_key)
        key_row.addWidget(get_key)
        ai_layout.addLayout(key_row)
        self.gemini_key_status = QLabel(self._gemini_key_status())
        self.gemini_key_status.setObjectName("muted")
        ai_layout.addWidget(self.gemini_key_status)
        layout.addWidget(ai_card)

        preferences = Card()
        form = QFormLayout(preferences)
        form.setContentsMargins(20, 18, 20, 18)
        self.strictness_setting = QComboBox()
        self.strictness_setting.addItems(["Gentle", "Normal", "Strict"])
        self.strictness_setting.setCurrentText(
            self.repository.get_setting("strictness", "Normal").capitalize()
        )
        self.strictness_setting.currentTextChanged.connect(
            lambda value: self.repository.set_setting("strictness", value.casefold())
        )
        self.frequency_setting = QComboBox()
        self.frequency_setting.addItem("Gentle · 3 minutes", "gentle")
        self.frequency_setting.addItem("Balanced · 90 seconds", "balanced")
        self.frequency_setting.addItem("Frequent · 1 minute", "frequent")
        frequency = self.repository.get_setting("nudge_frequency", "balanced")
        self.frequency_setting.setCurrentIndex(max(0, self.frequency_setting.findData(frequency)))
        self.frequency_setting.currentIndexChanged.connect(
            lambda index: self.repository.set_setting(
                "nudge_frequency", str(self.frequency_setting.itemData(index))
            )
        )
        quiet_start = QTimeEdit()
        quiet_start.setDisplayFormat("HH:mm")
        quiet_start.setTime(
            QTime.fromString(self.repository.get_setting("quiet_start", "22:00"), "HH:mm")
        )
        quiet_end = QTimeEdit()
        quiet_end.setDisplayFormat("HH:mm")
        quiet_end.setTime(
            QTime.fromString(self.repository.get_setting("quiet_end", "07:00"), "HH:mm")
        )
        quiet_start.timeChanged.connect(
            lambda value: self.repository.set_setting("quiet_start", value.toString("HH:mm"))
        )
        quiet_end.timeChanged.connect(
            lambda value: self.repository.set_setting("quiet_end", value.toString("HH:mm"))
        )
        self.retention_setting = QComboBox()
        self.retention_setting.addItems(["30 days", "90 days", "180 days", "Keep forever"])
        self.retention_setting.setCurrentText(self.repository.get_setting("retention", "90 days"))
        self.retention_setting.currentTextChanged.connect(self._set_retention)
        form.addRow("Default nudge style", self.strictness_setting)
        form.addRow("Nudge frequency", self.frequency_setting)
        form.addRow("Quiet hours start", quiet_start)
        form.addRow("Quiet hours end", quiet_end)
        form.addRow("Raw activity retention", self.retention_setting)
        layout.addWidget(preferences)

        data_card = Card()
        data_layout = QVBoxLayout(data_card)
        data_layout.setContentsMargins(20, 18, 20, 18)
        data_layout.addWidget(QLabel("Your local data"))
        data_layout.addWidget(
            QLabel("Export sessions and activity as JSON, or permanently clear local data.")
        )
        actions = QHBoxLayout()
        export_button = QPushButton("Export my data")
        export_button.setObjectName("secondaryButton")
        export_button.clicked.connect(self._export_data)
        delete_button = QPushButton("Delete all data")
        delete_button.setObjectName("dangerButton")
        delete_button.clicked.connect(self._delete_data)
        actions.addWidget(export_button)
        actions.addWidget(delete_button)
        actions.addStretch()
        data_layout.addLayout(actions)
        layout.addWidget(data_card)

        startup = Card()
        startup_layout = QVBoxLayout(startup)
        startup_layout.setContentsMargins(20, 18, 20, 18)
        startup_layout.addWidget(QLabel("Start FocusPilot with Windows"))
        startup_layout.addWidget(
            QLabel(
                "Optional. FocusPilot opens visibly; tracking still requires your "
                "consent and a session."
            )
        )
        self.autostart_check = QCheckBox("Launch FocusPilot when I sign in")
        self.autostart_check.setChecked(autostart.is_enabled())
        self.autostart_check.toggled.connect(self._set_autostart)
        startup_layout.addWidget(self.autostart_check)
        layout.addWidget(startup)
        layout.addStretch()
        return self._page(content)

    def _build_parent_page(self) -> QWidget:
        content, layout = self._content_layout(
            "Parent controls",
            "Transparent family settings. Monitoring is always visible to the child.",
        )
        notice = Card()
        notice_layout = QVBoxLayout(notice)
        notice_layout.setContentsMargins(20, 18, 20, 18)
        notice_title = QLabel("A visible, family-managed mode")
        notice_title.setStyleSheet("font-size:16px;font-weight:800;")
        notice_layout.addWidget(notice_title)
        notice_layout.addWidget(
            QLabel(
                "Child Mode records activity only during a visible focus session, "
                "shows a child notice, "
                "and offers gentle time-limit and bedtime reminders. It does not secretly monitor, "
                "terminate apps, or lock the computer."
            )
        )
        layout.addWidget(notice)
        setup = Card()
        setup_layout = QVBoxLayout(setup)
        setup_layout.setContentsMargins(20, 18, 20, 18)
        self.child_status = QLabel("No child profile set up")
        setup_layout.addWidget(self.child_status)
        self.child_manage = QPushButton("Set up family profile")
        self.child_manage.setObjectName("primaryButton")
        self.child_manage.clicked.connect(self._manage_child_profile)
        setup_layout.addWidget(self.child_manage, 0, Qt.AlignmentFlag.AlignLeft)
        self.child_toggle = QCheckBox("Use Child Mode for the next focus session")
        self.child_toggle.setChecked(self.repository.get_setting("child_mode", "false") == "true")
        self.child_toggle.toggled.connect(self._set_child_mode)
        setup_layout.addWidget(self.child_toggle)
        layout.addWidget(setup)
        report_card = Card()
        report_layout = QVBoxLayout(report_card)
        report_layout.setContentsMargins(20, 18, 20, 18)
        report_layout.addWidget(QLabel("Recent family sessions"))
        self.child_report = QListWidget()
        self.child_report.setMaximumHeight(220)
        report_layout.addWidget(self.child_report)
        layout.addWidget(report_card)
        layout.addStretch()
        return self._page(content)

    def _show_page(self, name: str) -> None:
        if name not in self._pages:
            return
        self.stack.setCurrentWidget(self._pages[name])
        for label, button in self._nav_buttons.items():
            button.setProperty("selected", label == name)
            button.style().unpolish(button)
            button.style().polish(button)
        self._top_context.setText(
            {
                "Overview": "Your focus, at a glance",
                "Focus session": "A little space to focus",
                "Insights": "Your progress, over time",
                "Settings": "Set things up your way",
                "Parent controls": "Family settings, kept transparent",
            }[name]
        )
        if name == "Parent controls":
            self._refresh_child_page()

    def _refresh_all(self) -> None:
        today = self.repository.summary(user_id=self.user_id)
        focus_minutes = int(today["focus_s"]) // 60
        active_minutes = int(today["active_s"]) // 60
        self.metric_focus.value_label.setText(self._format_minutes(focus_minutes))
        self.metric_sessions.value_label.setText(str(today["sessions"]))
        self.metric_score.value_label.setText(
            f"{round(float(today['avg_score']))}/100" if float(today["avg_score"]) else "—"
        )
        self.metric_idle.value_label.setText(self._format_minutes(int(today["idle_s"]) // 60))
        self.hero.ring.setValue(min(100, round(focus_minutes / 60 * 100)))
        self.chart_total.setText(f"{active_minutes // 60}h {active_minutes % 60:02}m tracked")
        self.weekly_chart.set_values(self.repository.weekly_summary(user_id=self.user_id))
        self.history_summary.value_label.setText(self._format_minutes(focus_minutes))
        self._refresh_history()
        self._refresh_progress()
        self._refresh_child_page()
        self._update_session_controls()

    @staticmethod
    def _format_minutes(minutes: int) -> str:
        return f"{minutes // 60}h {minutes % 60:02}m" if minutes >= 60 else f"{minutes}m"

    def _refresh_history(self) -> None:
        self.recent_list.clear()
        self.history_list.clear()
        sessions = self.repository.recent_sessions(20, user_id=self.user_id)
        for item in sessions:
            # Stored in UTC; show the user's own clock time.
            stamp = item.started_at.astimezone().strftime("%a, %b %d · %I:%M %p")
            goal = item.goal_text or "Unplanned session"
            score = f" · {round(item.focus_score)}/100" if item.focus_score is not None else ""
            line = f"{stamp}     {goal}     {score}"
            self.recent_list.addItem(line)
            self.history_list.addItem(line)
        if not sessions:
            self.recent_list.addItem("Your completed focus sessions will appear here.")
            self.history_list.addItem("No completed sessions yet. Start your first focus block.")

    def _refresh_progress(self) -> None:
        total_xp = self.repository.get_xp()
        level, into, needed = level_progress(total_xp)
        self.level_label.setText(f"Level {level}  ·  {total_xp} XP")
        self.xp_bar.setRange(0, needed)
        self.xp_bar.setValue(into)
        streak = current_streak(self.repository.daily_focus_seconds(self.user_id), date.today())
        self.streak_label.setText(
            f"Focus streak: {streak} day{'s' if streak != 1 else ''}  ·  "
            f"{needed - into} XP to level {level + 1}"
        )
        unlocked = self.repository.unlocked_achievements(self.user_id)
        self.achievement_list.clear()
        for definition in load_achievement_defs():
            mark = "✓" if definition.code in unlocked else "○"
            self.achievement_list.addItem(
                f"{mark}  {definition.title}  —  {definition.description}"
            )

    def _start_session(self) -> None:
        if self.manager.state in {"active", "paused"}:
            self._show_page("Focus session")
            return
        if self.repository.get_setting("consent_accepted", "false") != "true":
            if not self._ask_consent():
                return

        child_mode = self.repository.get_setting("child_mode", "false") == "true"
        child_record = self.repository.child_profile() if child_mode else None
        session_user_id = child_record[0].id if child_record is not None else self.user_id
        try:
            recent = json.loads(self.repository.get_setting("recent_goals", "[]"))
        except json.JSONDecodeError:
            recent = []
        dialog = IntentDialog(
            recent,
            self.repository.get_setting("strictness", "normal"),
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        parsed = dialog.parsed_goal()
        if not parsed.text:
            return

        # Only now (after the user confirmed) change any state.
        self._active_child_id = child_record[0].id if child_record is not None else None
        if self._active_child_id is not None:
            self.repository.set_setting("last_child_notice", "")
        self.manager = SessionManager(self.repository, session_user_id)
        session = self.manager.start(
            goal_text=parsed.text,
            goal_category=parsed.category,
            planned_minutes=parsed.duration_minutes or 60,
            strictness=dialog.selected_strictness,
            allowed_apps=dialog.allowed_apps,
        )
        recent = [parsed.text] + [item for item in recent if item != parsed.text]
        self.repository.set_setting("recent_goals", json.dumps(recent[:5]))
        self._begin_tracking(session.started_at)
        self._show_page("Focus session")
        self._refresh_all()

    def prompt_for_session(self) -> None:
        """Ask "What is this session for?" (used when FocusPilot starts with Windows)."""
        if self.manager.state not in {"active", "paused"}:
            self.showNormal()
            self.raise_()
            self.activateWindow()
            self._start_session()

    def resume_interrupted(self, session: FocusSession) -> None:
        """Resume a session that was active when FocusPilot last closed."""
        child = self.repository.child_profile()
        is_child = child is not None and child[0].id == session.user_id
        self._active_child_id = session.user_id if is_child else None
        self.manager = SessionManager(self.repository, session.user_id or self.user_id)
        self.manager.restore(session)
        # Count only time that was actually tracked, not the time the app was closed.
        tracked = sum(
            segment.duration_s + segment.idle_s
            for segment in self.repository.session_segments(session.id)
        )
        self._begin_tracking(datetime.now(UTC) - timedelta(seconds=tracked))
        self._show_page("Focus session")
        self._refresh_all()

    def _begin_tracking(self, started_at: datetime) -> None:
        """Reset per-session state and start the visible activity monitor."""
        session = self.manager.session
        owner = (session.user_id if session else None) or self.user_id
        self._override_rules = self.repository.list_overrides(owner)
        self.recorder = UsageRecorder(self.manager, self._classify_sample)
        self.nudges = NudgeEngine(self._nudge_threshold())
        self._active_started = started_at
        self._active_elapsed = 0
        self._last_sample_ts = None
        self._comeback_deadline = None
        self._current_sample = None
        self._current_classification = None
        self._browser_page = None
        self._browser_page_received = 0.0
        self._last_ai_page_key = None
        self._strict_warning_process = ""
        self._strict_close_failed = False
        self._start_tracking()

    def _ask_consent(self) -> bool:
        dialog = ConsentDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.accept_check.isChecked():
            return False
        self.repository.set_setting("consent_accepted", "true")
        self.repository.set_setting("gemini_consent", str(dialog.ai_check.isChecked()).lower())
        return True

    def _start_tracking(self) -> None:
        try:
            self.browser_metadata.start()
        except OSError as error:
            logger.warning("Browser metadata bridge unavailable: %s", error)
            self.session_activity.setText(
                "Browser helper unavailable. App nudges still work; AI page checks are off."
            )
        self.tracker = TrackingThread()
        self.tracker.worker.sample_ready.connect(self._on_sample)
        self.tracker.worker.tracking_error.connect(self._tracking_error)
        self.tracker.start()
        self._tracking_badge.setText(
            "●  CHILD MODE · MONITORING ON"
            if self._active_child_id is not None
            else "●  TRACKING · SESSION ACTIVE"
        )
        self._tracking_badge.setStyleSheet(
            "color:#385c2a; background:#e9f5dc; padding:8px 11px; border-radius:12px; "
            "font-size:10px; font-weight:800;"
        )

    def _stop_tracking(self) -> None:
        self.browser_metadata.stop()
        self._browser_page = None
        if self.recorder is not None:
            self.recorder.flush()
        if self.tracker is not None:
            self.tracker.stop()
            self.tracker = None
        self._tracking_badge.setText("●  NOT TRACKING")
        self._tracking_badge.setStyleSheet(
            "color:#77847c; background:#f0f3ed; padding:8px 11px; border-radius:12px; "
            "font-size:10px; font-weight:800;"
        )

    def _classify_sample(self, sample: WindowSample) -> Classification:
        session = self.manager.session
        if session is None:
            return Classification(0.5, "neutral", "other", "No active session")
        if self.nudges.break_remaining_s > 0:
            # A planned break is recorded as a break, so it never counts against the user.
            return Classification(0.5, "break", "break", "Planned five-minute break")
        if sample.pid == self._own_pid:
            return Classification(0.5, "neutral", "other", "FocusPilot itself")
        process = sample.process_name.casefold()
        title = sample.window_title.casefold()
        override_label = next(
            (
                label
                for rule_process, pattern, label in self._override_rules
                if rule_process == process and (not pattern or pattern in title)
            ),
            None,
        )
        if sample.page_url and sample.page_title:
            ai_result = self._ai_page_results.get((sample.page_url, sample.page_title))
            if ai_result is not None:
                return ai_result
        judgement = classify_activity(
            goal_category=session.goal_category,
            process_name=sample.process_name,
            window_title=(
                f"{sample.page_title} {sample.page_url}"
                if sample.page_title
                else sample.window_title
            ),
            override_label=override_label,
            goal_text=session.goal_text,
        )
        allowed_apps = self._session_allowed_apps(session)
        if allowed_apps and not is_allowed_app(sample.process_name, allowed_apps):
            return Classification(
                0.05, "off_task", judgement.category, "This app is not on your session list"
            )
        return judgement

    def _on_sample(self, value: object) -> None:
        if self.manager.state != "active" or not isinstance(value, WindowSample):
            return
        sample = value
        if sample.process_name.casefold() in {
            "chrome.exe",
            "msedge.exe",
            "firefox.exe",
            "brave.exe",
            "opera.exe",
            "vivaldi.exe",
        }:
            page = current_page(
                self._browser_page.title if self._browser_page else "",
                self._browser_page.url if self._browser_page else "",
                self._browser_page.browser if self._browser_page else "",
                self._browser_page_received,
                sample.window_title,
            )
            if page is not None:
                sample = replace(sample, page_title=page.title, page_url=page.url)
                if page.browser == sample.process_name.casefold():
                    self._request_page_judgment(page)
        session = self.manager.session
        if (
            session is not None
            and session.strictness == "strict"
            and self._session_allowed_apps(session)
            and not is_allowed_app(sample.process_name, self._session_allowed_apps(session))
        ):
            if sample.pid != self._own_pid:
                process = sample.process_name.casefold()
                closed = close_unapproved_app(sample.pid, sample.process_name)
                self._strict_close_failed = not closed
                if process != self._strict_warning_process:
                    if self.notifier is not None:
                        self.notifier(
                            "Strict focus",
                            (
                                f"Asked Windows to close {sample.process_name}."
                                if closed
                                else f"Could not close {sample.process_name}; switch back manually."
                            ),
                        )
                    self._strict_warning_process = process
        elapsed = 2.0
        if self._last_sample_ts is not None:
            elapsed = max(0.0, min((sample.ts - self._last_sample_ts).total_seconds(), 5.0))
        self._last_sample_ts = sample.ts
        self._current_sample = sample
        classification = self._classify_sample(sample)
        self._current_classification = classification
        if self.recorder is not None:
            self.recorder.consume(sample)
        self._active_elapsed = max(
            self._active_elapsed,
            int((sample.ts - self._active_started).total_seconds()),
        )
        self._check_comeback(sample, classification)
        # Someone who has stepped away is not "drifting", whatever is on screen.
        label = "neutral" if sample.idle_s >= IDLE_THRESHOLD_S else classification.label
        decision = self.nudges.on_sample(
            label=label,
            elapsed_s=elapsed,
            strictness=self.manager.session.strictness if self.manager.session else "normal",
            meeting=(
                classification.category == "communication"
                or self._is_quiet_hours(sample.ts.astimezone())
            ),
            now=sample.ts,
        )
        if decision is not None:
            self._show_nudge(decision.level, decision.reason, sample)
        self._check_child_policy(sample)
        self._update_session_controls()

    @staticmethod
    def _session_allowed_apps(session: FocusSession) -> list[str]:
        try:
            apps = json.loads(session.allowed_apps_json or "[]")
        except json.JSONDecodeError:
            logger.warning("Ignoring invalid app allowlist for session %s", session.id)
            return []
        if not isinstance(apps, list):
            return []
        return [app for app in apps if isinstance(app, str)]

    def _receive_browser_metadata(
        self, title: str, url: str, browser: str, received_at: float
    ) -> None:
        if self.manager.state == "active":
            self._browser_page = BrowserPage(title=title, url=url, browser=browser)
            self._browser_page_received = received_at

    def _request_page_judgment(self, page: BrowserPage) -> None:
        session = self.manager.session
        if (
            session is None
            or self.repository.get_setting("gemini_consent", "false") != "true"
            or not self.repository.get_setting("gemini_api_key", "")
            or not any(
                app.casefold() in {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe"}
                for app in self._session_allowed_apps(session)
            )
        ):
            return
        key = (page.url, page.title)
        if key == self._last_ai_page_key or key in self._ai_page_results:
            return
        self._last_ai_page_key = key
        self.ai.classify_page(goal=session.goal_text, page=page)

    def _ai_classification_ready(self, url: str, title: str, result: object) -> None:
        if not isinstance(result, Classification):
            logger.error("Gemini returned an unexpected classification type")
            return
        key = (url, title)
        self._ai_page_results[key] = result
        if (
            self._current_sample is not None
            and self._current_sample.page_url == url
            and self._current_sample.page_title == title
        ):
            self._current_classification = result
            self.session_activity.setText(f"AI coach: {result.reason}")

    def _ai_classification_failed(self, message: str) -> None:
        if self.manager.state == "active":
            self.session_ai_status.setText(
                f"AI page check unavailable; using local rules. {message}"
            )

    def _ai_chat_failed(self, message: str) -> None:
        self.ai_chat_status.setText(message)

    def _gemini_api_key(self) -> str:
        protected = self.repository.get_setting("gemini_api_key", "")
        return unprotect_secret(protected) if protected else ""

    def _gemini_key_status(self) -> str:
        return (
            "A Gemini key is saved encrypted for this Windows account."
            if self.repository.get_setting("gemini_api_key", "")
            else "No AI key configured. Local focus rules continue to work."
        )

    def _save_gemini_key(self) -> None:
        key = self.gemini_key_input.text().strip()
        if not key:
            self.gemini_key_status.setText("Paste a Gemini API key first.")
            return
        try:
            self.repository.set_setting("gemini_api_key", protect_secret(key))
        except (RuntimeError, OSError, ValueError) as error:
            self.gemini_key_status.setText(f"Could not protect this key: {error}")
            return
        self.gemini_key_input.clear()
        self.gemini_key_status.setText(self._gemini_key_status())
        self.ai_chat_status.setText("Gemini Free is ready. Start a session or send a message.")

    def _remove_gemini_key(self) -> None:
        self.repository.set_setting("gemini_api_key", "")
        self.gemini_key_input.clear()
        self.gemini_key_status.setText("Gemini key removed from FocusPilot.")

    def _send_chat_message(self) -> None:
        message = self.ai_chat_entry.text().strip()
        if not message:
            return
        if self.repository.get_setting("gemini_consent", "false") != "true":
            self.ai_chat_status.setText("Allow Gemini Free in Settings before using the AI coach.")
            return
        if not self.repository.get_setting("gemini_api_key", ""):
            self.ai_chat_status.setText("Add a free Gemini API key in Settings first.")
            return
        self.ai_chat_entry.clear()
        self._chat_history.append(("user", message))
        self.ai_chat.appendPlainText(f"You: {message}")
        self.ai_chat_status.setText("Your coach is thinking…")
        session = self.manager.session
        page = None
        if (
            self.manager.state == "active"
            and self._browser_page is not None
            and self._current_sample is not None
        ):
            page = current_page(
                self._browser_page.title,
                self._browser_page.url,
                self._browser_page.browser,
                self._browser_page_received,
                self._current_sample.window_title,
            )
            if page is not None and page.browser != self._current_sample.process_name.casefold():
                page = None
        self.ai.chat(
            goal=session.goal_text if session is not None else "",
            message=message,
            history=list(self._chat_history[:-1]),
            page=page,
        )

    def _ai_chat_ready(self, response: str) -> None:
        self._chat_history.append(("assistant", response))
        self.ai_chat.appendPlainText(f"FocusPilot: {response}")
        self.ai_chat_status.setText("Ready when you are.")

    def _check_comeback(self, sample: WindowSample, classification: Classification) -> None:
        """Unlock "Comeback" when the user is back on task within 30 s of a nudge."""
        if self._comeback_deadline is None:
            return
        if sample.ts > self._comeback_deadline:
            self._comeback_deadline = None
        elif classification.label == "on_task":
            self._comeback_deadline = None
            self._unlock_achievement("comeback")

    def _tracking_error(self, message: str) -> None:
        logger.error("Tracking issue: %s", message)
        self.session_activity.setText(f"Tracking is unavailable: {message}")

    def _check_child_policy(self, sample: WindowSample) -> None:
        if self._active_child_id is None:
            return
        profile_data = self.repository.child_profile()
        if profile_data is None:
            return
        child, profile = profile_data
        decision = evaluate_child_policy(
            daily_usage_s=self.repository.child_daily_usage(child.id),
            daily_limit_min=profile.daily_limit_min,
            bedtime_start=profile.bedtime_start,
            bedtime_end=profile.bedtime_end,
            now=sample.ts.astimezone(),
            process_name=sample.process_name,
            allowlist_json=profile.allowlist_json,
            blocklist_json=profile.blocklist_json,
            category=infer_category(sample.process_name, sample.window_title),
            window_title=sample.window_title,
            exempt=sample.pid == self._own_pid,
        )
        if decision.status != "allowed":
            notice_key = f"{decision.status}:{sample.process_name.casefold()}"
            if notice_key != self.repository.get_setting("last_child_notice", ""):
                self.repository.set_setting("last_child_notice", notice_key)
                self.repository.add_child_event(child.id, decision.status, sample.process_name)
                if decision.status == "limit_reached":
                    self._end_session(ask=False)
                    self._show_notice("Family time limit", decision.message)
                else:
                    self._show_notice("Family reminder", decision.message)
        else:
            self.repository.set_setting("last_child_notice", "")

    def _show_notice(self, title: str, text: str) -> None:
        """Show a message without blocking the event loop (samples keep arriving)."""
        box = QMessageBox(QMessageBox.Icon.Information, title, text, QMessageBox.StandardButton.Ok)
        box.setParent(self, box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        box.open()

    def _verify_parent_pin(self, prompt: str) -> bool:
        """Ask for the parent PIN. Always True when no family profile exists."""
        profile_data = self.repository.child_profile()
        if profile_data is None:
            return True
        dialog = QDialog(self)
        dialog.setWindowTitle("Parent verification")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(prompt))
        pin = QLineEdit()
        pin.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(pin)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        if self.pin_verifier.verify(pin.text(), profile_data[0].pin_hash or ""):
            return True
        locked = self.pin_verifier.locked_seconds
        QMessageBox.warning(
            self,
            "Not verified",
            f"Too many attempts. Try again in {locked} seconds."
            if locked
            else "That parent PIN did not match.",
        )
        return False

    def confirm_quit(self) -> bool:
        """Quit from the tray; during a Child Mode session this needs the parent PIN."""
        if self._active_child_id is not None and self.manager.state in {"active", "paused"}:
            if not self._verify_parent_pin(
                "Enter the parent PIN to quit FocusPilot during a Child Mode session."
            ):
                return False
        self.request_quit()
        return True

    def _show_nudge(self, level: int, reason: str, sample: WindowSample) -> None:
        if self._nudge_dialog is not None and self._nudge_dialog.isVisible():
            return
        session = self.manager.session
        if session is None:
            return
        self.manager.record_drift()
        self._comeback_deadline = sample.ts + timedelta(seconds=30)
        nudge_id = self.repository.add_nudge(
            session_id=session.id,
            level=level,
            reason=reason,
        )
        if level == 1 and self.notifier is not None:
            self.notifier("FocusPilot", f"You planned to: {session.goal_text}. Back to it?")
        dialog = QDialog(self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.setWindowTitle("A gentle check-in")
        # Always on top: a nudge hidden behind the very window causing the drift is useless.
        dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        dialog.setMinimumWidth(390)
        layout = QVBoxLayout(dialog)
        heading = QLabel("Take a breath" if level >= 3 else "A quick check-in")
        heading.setObjectName("dialogHeading")
        layout.addWidget(heading)
        layout.addWidget(QLabel(f"You planned to: {session.goal_text}"))
        layout.addWidget(QLabel(f"{reason}. Want to return to your intention?"))
        if level >= 3:
            layout.addWidget(QLabel("What is the one thing you need to finish first?"))
        actions = QHBoxLayout()
        back = QPushButton("Back to my goal")
        back.setObjectName("primaryButton")
        more = QPushButton("5 more minutes")
        more.setObjectName("secondaryButton")
        more.setEnabled(self.nudges.break_tokens < 3)
        on_task = QPushButton("I'm on task")
        on_task.setObjectName("secondaryButton")
        actions.addWidget(back)
        actions.addWidget(more)
        actions.addWidget(on_task)
        layout.addLayout(actions)

        def finish(response: str) -> None:
            self.repository.respond_to_nudge(nudge_id, response)
            if response == "disagreed":
                owner = session.user_id or self.user_id
                self.repository.save_override(
                    user_id=owner,
                    process_name=sample.process_name,
                    # Limit the rule to this site/app, not to all of Chrome.
                    title_pattern=derive_override_pattern(sample.process_name, sample.window_title),
                    label="on_task",
                )
                self._override_rules = self.repository.list_overrides(owner)
            elif response == "snoozed":
                if self.nudges.grant_break():
                    if self.recorder is not None:
                        self.recorder.flush(keep_open=True)
                else:
                    QMessageBox.information(
                        self,
                        "Break tokens used",
                        "All three five-minute break tokens have been used for this session.",
                    )
            dialog.close()

        back.clicked.connect(lambda: finish("returned_to_task"))
        more.clicked.connect(lambda: finish("snoozed"))
        on_task.clicked.connect(lambda: finish("disagreed"))
        dialog.finished.connect(lambda: setattr(self, "_nudge_dialog", None))
        self._nudge_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _toggle_pause(self) -> None:
        if self.manager.state == "active":
            if self._active_child_id is not None and not self._verify_parent_pin(
                "Enter the parent PIN to pause this Child Mode session."
            ):
                return
            self._stop_tracking()
            self.manager.pause()
            self._pause_started = datetime.now(UTC)
        elif self.manager.state == "paused":
            if self._pause_started is not None:
                self._active_started += datetime.now(UTC) - self._pause_started
            self.manager.resume()
            self._pause_started = None
            self._last_sample_ts = None
            self._start_tracking()
        self._update_session_controls()

    def _end_session(self, *, ask: bool) -> None:
        if self.manager.state not in {"active", "paused"}:
            return
        if ask:
            if self._active_child_id is not None and not self._verify_parent_pin(
                "Enter the parent PIN to end this Child Mode session."
            ):
                return
            answer = QMessageBox.question(
                self,
                "End this session?",
                "Finish your focus session and save its summary?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._stop_tracking()
        session = self.manager.session
        segments = self.repository.session_segments(session.id) if session else []
        drift_count = self.manager.drift_count
        summary = self.manager.end(segments)
        is_child = self._active_child_id is not None
        self._active_child_id = None
        self._comeback_deadline = None
        extra = ""
        if summary is not None and session is not None:
            extra = self._advice_and_progress(session, summary, segments, drift_count, is_child)
        self._show_session_summary(summary, extra)
        self._refresh_all()
        self._show_page("Overview")

    def _advice_and_progress(
        self,
        session: FocusSession,
        summary: SessionSummary,
        segments: list[UsageSegment],
        drift_count: int,
        is_child: bool,
    ) -> str:
        """Build the coaching text, and (for your own sessions) award XP and achievements."""
        metrics = summary.metrics
        lines: list[str] = []
        if not is_child:
            xp = xp_for_session(
                metrics, planned_minutes=session.planned_minutes, planned=session.planned
            )
            total = self.repository.add_xp(xp)
            level, into, needed = level_progress(total)
            streak = current_streak(self.repository.daily_focus_seconds(self.user_id), date.today())
            lines.append(f"+{xp} XP  ·  Level {level} ({into}/{needed})")
            if streak:
                lines.append(f"Focus streak: {streak} day{'s' if streak != 1 else ''}")
            facts = SessionFacts(
                metrics=metrics,
                nudges=drift_count,
                planned=session.planned,
                started_local=session.started_at.astimezone(),
                streak_days=streak,
            )
            titles = {item.code: item.title for item in load_achievement_defs()}
            unlocked = [
                titles.get(code, code)
                for code in newly_earned(facts, self.repository.unlocked_achievements(self.user_id))
                if self.repository.unlock_achievement(self.user_id, code)
            ]
            if unlocked:
                lines.append("Unlocked: " + ", ".join(unlocked))
        advice = session_advice(
            metrics,
            planned_minutes=session.planned_minutes,
            drift_count=drift_count,
            distractions=top_distractions(segments),
        )
        return "\n".join(lines) + ("\n\n" if lines else "") + advice

    def _unlock_achievement(self, code: str) -> None:
        """Unlock a live achievement (own sessions only) and tell the user."""
        if self._active_child_id is not None:
            return
        if self.repository.unlock_achievement(self.user_id, code):
            title = next(
                (item.title for item in load_achievement_defs() if item.code == code), code
            )
            if self.notifier is not None:
                self.notifier("Achievement unlocked", title)
            self._refresh_progress()

    def _show_session_summary(self, summary: SessionSummary | None, extra: str = "") -> None:
        if summary is None:
            return
        metrics = summary.metrics
        QMessageBox.information(
            self,
            "Session complete",
            f"{summary.goal}\n\n"
            f"Focus score: {metrics.score}/100\n"
            f"Active time: {self._format_minutes(metrics.active_s // 60)}\n"
            f"Focused time: {self._format_minutes(metrics.focus_s // 60)}\n"
            f"Idle time: {self._format_minutes(metrics.idle_s // 60)}\n\n{extra}",
        )

    def _update_session_controls(self) -> None:
        state = self.manager.state
        session = self.manager.session
        active = state == "active"
        paused = state == "paused"
        self.pause_button.setVisible(active or paused)
        self.pause_button.setText("Pause" if active else "Resume")
        self.end_button.setVisible(active or paused)
        self.focus_start_button.setVisible(not active and not paused)
        self.hero.start_button.setText(
            "  Continue session" if active or paused else "＋   Start a focus session"
        )
        if session is None:
            self.session_state.setText("NO ACTIVE SESSION")
            self.session_goal.setText("Ready when you are.")
            self.session_activity.setText("Activity tracking is off.")
            self.session_ai_status.setText("AI browser checks are optional.")
            self.session_timer.setText("00:00:00")
            self._tracking_badge.setText("●  NOT TRACKING")
            return
        if self._active_child_id is not None:
            self.session_state.setText(
                "CHILD MODE · MONITORING ON · SESSION PAUSED"
                if paused
                else "CHILD MODE · MONITORING ON · SESSION IN PROGRESS"
            )
        else:
            self.session_state.setText("SESSION PAUSED" if paused else "SESSION IN PROGRESS")
        self.session_goal.setText(session.goal_text)
        self.session_timer.setText(self._format_elapsed(self._active_elapsed))
        if session.strictness == "strict" and self._session_allowed_apps(session):
            apps = ", ".join(self._session_allowed_apps(session))
            status = f"STRICT MODE · Allowed: {apps} · Windows safety controls stay available."
            if self._strict_close_failed:
                status += " Close this app manually to continue."
            self.session_ai_status.setText(status)
        elif self.repository.get_setting(
            "gemini_consent", "false"
        ) == "true" and self.repository.get_setting("gemini_api_key", ""):
            self.session_ai_status.setText(
                "GEMINI FREE · Page checks use only the goal, page title, and URL path."
            )
        else:
            self.session_ai_status.setText(
                "AI page checks off · Add a key and opt in under Settings."
            )
        sample = self._current_sample
        if paused:
            self.session_activity.setText("Paused. No activity is being recorded.")
        elif sample is not None:
            label = (
                self._current_classification.label if self._current_classification else "neutral"
            )
            self.session_activity.setText(
                f"Now using {sample.process_name} · {label.replace('_', ' ')}"
            )
        else:
            self.session_activity.setText("Starting the visible activity monitor…")

    @staticmethod
    def _format_elapsed(seconds: int) -> str:
        hours, remainder = divmod(max(seconds, 0), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02}:{minutes:02}:{seconds:02}"

    def _refresh_child_page(self) -> None:
        if not hasattr(self, "child_status"):
            return
        profile = self.repository.child_profile()
        if profile is None:
            self.child_status.setText("No child profile set up.")
            self.child_manage.setText("Set up family profile")
            self.child_toggle.setEnabled(False)
            self.child_toggle.blockSignals(True)
            self.child_toggle.setChecked(False)
            self.child_toggle.blockSignals(False)
            self.child_report.clear()
            self.child_report.addItem("Set up a profile to see family sessions.")
            return
        child, policy = profile
        self.child_status.setText(
            f"Profile: {child.name} · {policy.age_band} · "
            f"{policy.daily_limit_min} min daily plan · PIN protected"
        )
        self.child_manage.setText("Edit family profile")
        self.child_toggle.setEnabled(True)
        self.child_toggle.blockSignals(True)
        self.child_toggle.setChecked(self.repository.get_setting("child_mode", "false") == "true")
        self.child_toggle.blockSignals(False)
        self.child_report.clear()
        for item in self.repository.child_report(child.id):
            started = datetime.fromisoformat(str(item["started_at"])).astimezone()
            self.child_report.addItem(
                f"{started:%d %b %H:%M}  ·  {item['goal']}  ·  {item['status']}"
            )
        if self.child_report.count() == 0:
            self.child_report.addItem("No family sessions recorded yet.")

    def _manage_child_profile(self) -> None:
        profile_data = self.repository.child_profile()
        if profile_data is not None and not self._verify_parent_pin(
            "Enter the existing parent PIN to continue."
        ):
            return
        old_policy = profile_data[1] if profile_data is not None else None
        dialog = QDialog(self)
        dialog.setWindowTitle("Family profile settings")
        dialog.setMinimumWidth(420)
        form = QFormLayout(dialog)
        name = QLineEdit(profile_data[0].name if profile_data else "")
        name.setPlaceholderText("Child's first name")
        pin = QLineEdit()
        pin.setEchoMode(QLineEdit.EchoMode.Password)
        pin.setPlaceholderText(
            "4–12 digit parent PIN" if old_policy is None else "New PIN (leave blank to keep)"
        )
        pin_again = QLineEdit()
        pin_again.setEchoMode(QLineEdit.EchoMode.Password)
        pin_again.setPlaceholderText("Type the PIN again")
        age = QComboBox()
        defaults = load_age_profiles()
        age.addItems(list(defaults))
        if old_policy:
            age.setCurrentText(old_policy.age_band)
        limit = QSpinBox()
        limit.setRange(15, 720)
        limit.setSuffix(" minutes")
        limit.setValue(old_policy.daily_limit_min if old_policy else 120)
        bedtime_start = QLineEdit(old_policy.bedtime_start if old_policy else "21:00")
        bedtime_end = QLineEdit(old_policy.bedtime_end if old_policy else "07:00")
        allowlist = QLineEdit(
            ", ".join(json.loads(old_policy.allowlist_json)) if old_policy else ""
        )
        allowlist.setPlaceholderText("e.g. study, design, chrome (empty = everything)")
        blocklist = QLineEdit(
            ", ".join(json.loads(old_policy.blocklist_json)) if old_policy else ""
        )
        blocklist.setPlaceholderText("e.g. discord, steam, gaming")
        if old_policy is None:
            initial_defaults = defaults[age.currentText()]
            limit.setValue(initial_defaults["daily_limit_min"])
            bedtime_start.setText(initial_defaults["bedtime_start"])
            bedtime_end.setText(initial_defaults["bedtime_end"])
            allowlist.setText(", ".join(initial_defaults["allowlist"]))

            def set_age_defaults(age_band: str) -> None:
                values = defaults[age_band]
                limit.setValue(values["daily_limit_min"])
                bedtime_start.setText(values["bedtime_start"])
                bedtime_end.setText(values["bedtime_end"])
                allowlist.setText(", ".join(values["allowlist"]))

            age.currentTextChanged.connect(set_age_defaults)
        child_consent = QCheckBox(
            "I am the parent/guardian and have explained visible tracking to the child."
        )
        child_consent.setChecked(old_policy is not None)
        form.addRow("Child's first name", name)
        form.addRow("Parent PIN", pin)
        form.addRow("Confirm PIN", pin_again)
        form.addRow("Age band", age)
        form.addRow("Daily screen-time plan", limit)
        form.addRow("Screen-free time starts", bedtime_start)
        form.addRow("Screen-free time ends", bedtime_end)
        form.addRow("Allowed apps or topics", allowlist)
        form.addRow("Apps to remind about", blocklist)
        form.addRow("", child_consent)
        form.addRow(
            "",
            QLabel(
                "Names match the app (chrome), its type (study, coding, writing, design, "
                "research, video, gaming, social, entertainment) or the window title. "
                "FocusPilot shows a visible reminder; it never secretly blocks or closes an app."
            ),
        )
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if not name.text().strip() or not child_consent.isChecked():
            QMessageBox.warning(
                self,
                "Family consent required",
                "Enter a name and confirm that the child has been told about visible tracking.",
            )
            return
        try:
            if pin.text() != pin_again.text():
                raise ValueError("The two PIN entries do not match.")
            pin_hash = (
                hash_pin(pin.text())
                if pin.text()
                else (profile_data[0].pin_hash if profile_data else None)
            )
            if pin_hash is None:
                raise ValueError("A parent PIN is required.")
            start_text = normalize_clock(bedtime_start.text())
            end_text = normalize_clock(bedtime_end.text())
        except ValueError as error:
            QMessageBox.warning(self, "Check the settings", str(error))
            return
        child_id = self.repository.set_child_profile(
            name=name.text().strip(),
            pin_hash=pin_hash,
            age_band=age.currentText(),
            daily_limit_min=limit.value(),
            bedtime_start=start_text,
            bedtime_end=end_text,
            allowlist=[item.strip() for item in allowlist.text().split(",") if item.strip()],
            blocklist=[item.strip() for item in blocklist.text().split(",") if item.strip()],
            strict_mode=False,
        )
        self.repository.set_setting("child_consent", "true")
        self.repository.set_setting("child_user_id", str(child_id))
        self._refresh_child_page()

    def _export_data(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export FocusPilot data", "focuspilot-export.json", "JSON files (*.json)"
        )
        if not path:
            return
        try:
            Path(path).write_text(
                json.dumps(self.repository.export_data(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as error:
            QMessageBox.critical(self, "Export failed", str(error))
            return
        QMessageBox.information(self, "Export complete", "Your local data was exported.")

    def _set_retention(self, value: str) -> None:
        self.repository.set_setting("retention", value)
        if value == "Keep forever":
            return
        try:
            days = int(value.split()[0])
        except (ValueError, IndexError):
            return
        removed = self.repository.prune_segments_before(datetime.now(UTC) - timedelta(days=days))
        if removed:
            logger.info("Rolled up and removed %d old activity segments", removed)

    def _nudge_threshold(self) -> int:
        frequency = self.repository.get_setting("nudge_frequency", "balanced")
        return {"gentle": 180, "balanced": 90, "frequent": 60}.get(frequency, 90)

    def _clock_setting(self, key: str, default: str) -> time:
        """Read an ``HH:MM`` setting; a corrupt value falls back to the default."""
        for value in (self.repository.get_setting(key, default), default):
            try:
                return datetime.strptime(value, "%H:%M").time()
            except ValueError:
                continue
        return time(0, 0)

    def _is_quiet_hours(self, now: datetime) -> bool:
        start = self._clock_setting("quiet_start", "22:00")
        end = self._clock_setting("quiet_end", "07:00")
        current = now.time()
        if start == end:
            return False
        return start <= current < end if start < end else current >= start or current < end

    def _delete_data(self) -> None:
        answer = QMessageBox.warning(
            self,
            "Delete all FocusPilot data?",
            "This permanently deletes sessions, activity history, settings, and family profiles.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._stop_tracking()
        delete_database(self.engine, self.config.database_path)
        QMessageBox.information(
            self,
            "Data deleted",
            "All FocusPilot data was deleted. Restart FocusPilot to create a fresh local database.",
        )
        self.request_quit()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _review_consent(self) -> None:
        if self.manager.state in {"active", "paused"}:
            QMessageBox.warning(
                self,
                "Finish your session first",
                "End the active session before changing tracking consent.",
            )
            return
        self.repository.set_setting("consent_accepted", "false")
        self._ask_consent()

    def _set_child_mode(self, enabled: bool) -> None:
        if enabled and self.repository.child_profile() is None:
            self.child_toggle.blockSignals(True)
            self.child_toggle.setChecked(False)
            self.child_toggle.blockSignals(False)
            QMessageBox.information(
                self,
                "Set up a profile first",
                "Create a parent-protected child profile before enabling Child Mode.",
            )
            return
        if not enabled and not self._verify_parent_pin(
            "Enter the parent PIN to switch off Child Mode."
        ):
            self.child_toggle.blockSignals(True)
            self.child_toggle.setChecked(True)
            self.child_toggle.blockSignals(False)
            return
        self.repository.set_setting("child_mode", str(enabled).lower())

    def request_quit(self) -> None:
        """Stop capture and allow the process to quit from the tray menu."""
        self._quitting = True
        self._stop_tracking()
        self.browser_metadata.stop()
        self.ai.shutdown()

    def _set_autostart(self, enabled: bool) -> None:
        try:
            autostart.set_enabled(enabled)
        except OSError as error:
            logger.exception("Could not update Windows autostart")
            QMessageBox.warning(self, "Autostart not changed", str(error))
            self.autostart_check.blockSignals(True)
            self.autostart_check.setChecked(not enabled)
            self.autostart_check.blockSignals(False)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Hide to the tray on window close; explicit Quit (or Windows sign-out) ends it."""
        gui_app = QGuiApplication.instance()
        if isinstance(gui_app, QGuiApplication) and gui_app.isSavingSession():
            # Windows is signing out or shutting down: never block it.
            self.request_quit()
            event.accept()
            return
        if not self._quitting:
            self.hide()
            event.ignore()
            return
        self._stop_tracking()
        event.accept()
