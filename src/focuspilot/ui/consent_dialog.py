"""First-run, plain-language tracking consent."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class ConsentDialog(QDialog):
    """Require explicit consent before any foreground activity is recorded."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Your privacy comes first")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setModal(True)
        self.setWindowOpacity(1.0)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#f8faf6"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#f8faf6"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#17231f"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#17231f"))
        self.setPalette(palette)
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        heading = QLabel("A clear picture, never a secret one.")
        heading.setObjectName("dialogHeading")
        layout.addWidget(heading)
        tracked = QLabel(
            "When you start a focus session, FocusPilot records only the active "
            "app name, visible window title, timestamps, and whether your device "
            "has been idle for more than two minutes. Session history is stored "
            "in a local database on this PC."
        )
        tracked.setWordWrap(True)
        layout.addWidget(tracked)
        not_tracked = QLabel(
            "FocusPilot never captures keystrokes, screenshots, file contents, "
            "passwords, or page contents. The optional browser extension can send "
            "the active page title and URL path (not query strings) to the local app "
            "during a session. If you opt into Gemini Free, your goal and that "
            "metadata go to Google for relevance checks; chat goes only when you "
            "press Send. Google's free tier may use prompts to improve its products."
        )
        not_tracked.setWordWrap(True)
        layout.addWidget(not_tracked)
        self.accept_check = QCheckBox(
            "I understand and consent to local activity tracking during sessions."
        )
        layout.addWidget(self.accept_check)
        self.ai_check = QCheckBox("Allow the optional Gemini Free AI coach to use that data.")
        layout.addWidget(self.ai_check)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("I agree")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Not now")
        self.accept_check.toggled.connect(
            buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.adjustSize()
        if parent is not None:
            self.move(
                parent.x() + (parent.width() - self.width()) // 2,
                parent.y() + (parent.height() - self.height()) // 2,
            )
