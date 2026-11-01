"""Reusable dashboard cards and weekly-usage chart."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class Card(QFrame):
    """Rounded surface for a dashboard section."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)


class MetricCard(Card):
    """A compact label/value/trend summary."""

    def __init__(self, label: str, value: str, hint: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)
        title = QLabel(label.upper())
        title.setObjectName("eyebrow")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("metricValue")
        hint_label = QLabel(hint)
        hint_label.setObjectName("muted")
        layout.addWidget(title)
        layout.addWidget(self.value_label)
        layout.addWidget(hint_label)


class FocusHero(Card):
    """Primary dashboard hero with daily focus goal and start action."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("focusHero")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        left = QVBoxLayout()
        self.greeting = QLabel("Make room for what matters.")
        self.greeting.setObjectName("heroTitle")
        self.subtitle = QLabel("Start a session and give your time an intention.")
        self.subtitle.setObjectName("heroSubtitle")
        left.addWidget(self.greeting)
        left.addWidget(self.subtitle)
        left.addSpacing(15)
        self.start_button = QPushButton("＋   Start a focus session")
        self.start_button.setObjectName("primaryButton")
        self.start_button.setCursor(Qt.CursorShape.PointingHandCursor)
        left.addWidget(self.start_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(left, 1)
        self.ring = QProgressBar()
        self.ring.setObjectName("focusRing")
        self.ring.setRange(0, 100)
        self.ring.setValue(0)
        self.ring.setFormat("%p%")
        self.ring.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ring.setFixedSize(112, 112)
        layout.addWidget(self.ring)


class WeeklyChart(Card):
    """Small dependency-free bar chart for the last seven days."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._values: list[dict[str, int | str]] = []
        self.setMinimumHeight(190)

    def set_values(self, values: list[dict[str, int | str]]) -> None:
        self._values = values
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.contentsRect().adjusted(16, 14, -16, -14)
        max_value = max((int(row["active_s"]) for row in self._values), default=0)
        baseline = rect.bottom() - 24
        available = max(1, baseline - rect.top() - 20)
        count = max(1, len(self._values))
        slot = rect.width() / count
        bar_width = min(28.0, slot * 0.48)
        for index, row in enumerate(self._values):
            seconds = int(row["active_s"])
            height = available * seconds / max(max_value, 3600)
            x = rect.left() + slot * index + (slot - bar_width) / 2
            y = baseline - height
            color = self.palette().highlight().color()
            color.setAlpha(220 if seconds else 55)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(int(x), int(y), int(bar_width), int(max(5, height)), 6, 6)
            painter.setPen(QPen(self.palette().color(self.foregroundRole())))
            painter.drawText(
                int(rect.left() + slot * index),
                baseline + 18,
                int(slot),
                16,
                Qt.AlignmentFlag.AlignHCenter,
                str(row["day"]),
            )
        painter.end()


class PageHeader(QWidget):
    """Consistent title and supporting copy."""

    def __init__(self, title: str, subtitle: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        description = QLabel(subtitle)
        description.setObjectName("muted")
        layout.addWidget(heading)
        layout.addWidget(description)
