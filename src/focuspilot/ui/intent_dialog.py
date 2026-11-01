"""Session goal and duration dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from focuspilot.session.goal_parser import ParsedGoal, parse_goal


class IntentDialog(QDialog):
    """Collect a session goal, duration, and gentle/normal/strict preference."""

    def __init__(
        self,
        recent_goals: list[str] | None = None,
        default_strictness: str = "normal",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Start a focus session")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setModal(True)
        self.setWindowOpacity(1.0)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#f8faf6"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#17231f"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#17231f"))
        self.setPalette(palette)
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        heading = QLabel("What is this session for?")
        heading.setObjectName("dialogHeading")
        layout.addWidget(heading)
        layout.addWidget(QLabel("Set an intention. You can pause or stop any time."))

        form = QFormLayout()
        self.goal = QLineEdit()
        self.goal.setPlaceholderText("e.g. Study DSA, write my report, read a chapter")
        self.goal.setClearButtonEnabled(True)
        self.duration = QComboBox()
        for label, minutes in (
            ("30 minutes", 30),
            ("1 hour", 60),
            ("90 minutes", 90),
            ("2 hours", 120),
            ("3 hours", 180),
        ):
            self.duration.addItem(label, minutes)
        self.strictness = QComboBox()
        self.strictness.addItems(["Gentle", "Normal", "Strict"])
        self.strictness.setCurrentText(default_strictness.capitalize())
        form.addRow("Your intention", self.goal)
        form.addRow("Planned duration", self.duration)
        form.addRow("Nudge style", self.strictness)
        layout.addLayout(form)

        apps_heading = QLabel("Apps for this session")
        apps_heading.setStyleSheet("font-weight:700;")
        layout.addWidget(apps_heading)
        layout.addWidget(
            QLabel(
                "Choose a small set. Other apps get a nudge; Strict mode asks Windows "
                "to close them. Essential Windows controls stay available."
            )
        )
        self.allowed_app_list = QListWidget()
        self.allowed_app_list.setMaximumHeight(110)
        layout.addWidget(self.allowed_app_list)
        app_actions = QHBoxLayout()
        add_app = QPushButton("＋  Add app")
        add_app.setObjectName("secondaryButton")
        add_app.clicked.connect(self._add_app)
        remove_app = QPushButton("Remove selected")
        remove_app.setObjectName("secondaryButton")
        remove_app.clicked.connect(
            lambda: (
                self.allowed_app_list.takeItem(self.allowed_app_list.currentRow())
                if self.allowed_app_list.currentRow() >= 0
                else None
            )
        )
        app_actions.addWidget(add_app)
        app_actions.addWidget(remove_app)
        app_actions.addStretch()
        layout.addLayout(app_actions)

        self.recent = QComboBox()
        self.recent.addItem("Recent intentions…", "")
        for item in (recent_goals or [])[:5]:
            self.recent.addItem(item, item)
        self.recent.currentIndexChanged.connect(self._select_recent)
        layout.addWidget(self.recent)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Start session")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.adjustSize()
        if parent is not None:
            self.move(
                parent.x() + (parent.width() - self.width()) // 2,
                parent.y() + (parent.height() - self.height()) // 2,
            )

    def accept(self) -> None:
        """Require a goal and at least one intended app for every session."""
        if not self.goal.text().strip():
            self.goal.setPlaceholderText("Write a short goal to start (e.g. Study DSA)")
            self.goal.setStyleSheet("border: 1px solid #b84742;")
            self.goal.setFocus()
            return
        if not self.allowed_apps:
            self.allowed_app_list.setToolTip("Add at least one app for this focus session.")
            self.allowed_app_list.setStyleSheet("border: 1px solid #b84742;")
            return
        super().accept()

    def _add_app(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose an app for this session",
            "",
            "Windows applications (*.exe)",
        )
        if not path:
            return
        app_name = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        existing = {
            self.allowed_app_list.item(index).text().casefold()
            for index in range(self.allowed_app_list.count())
        }
        if app_name.casefold() not in existing:
            self.allowed_app_list.addItem(app_name)

    def _select_recent(self, index: int) -> None:
        text = self.recent.itemData(index)
        if text:
            self.goal.setText(str(text))

    def parsed_goal(self) -> ParsedGoal:
        """Return goal text, category, and parsed/fallback duration."""
        fallback = int(self.duration.currentData())
        parsed = parse_goal(self.goal.text(), fallback)
        return ParsedGoal(parsed.text, parsed.category, parsed.duration_minutes or fallback)

    @property
    def selected_strictness(self) -> str:
        """Return the chosen strictness in a normalized form."""
        return self.strictness.currentText().casefold()

    @property
    def allowed_apps(self) -> list[str]:
        """Return selected executable names without persisting install paths."""
        return [
            self.allowed_app_list.item(index).text()
            for index in range(self.allowed_app_list.count())
        ]
