"""System-tray entry point for FocusPilot."""

from __future__ import annotations

from typing import Protocol

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon


class TrayWindow(Protocol):
    """Window actions exposed to the system-tray controller."""

    def showNormal(self) -> None: ...

    def raise_(self) -> None: ...

    def activateWindow(self) -> None: ...

    def confirm_quit(self) -> bool: ...


class TrayController:
    """Owns the always-visible application tray icon and menu."""

    def __init__(self, app: QApplication, window: TrayWindow) -> None:
        self._app = app
        self._window = window
        self._icon = QIcon()
        style = app.style()
        if style is not None:
            self._icon = style.standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self._tray = QSystemTrayIcon(self._icon, app)
        self._tray.setToolTip("FocusPilot")

        # Keep a Python reference: the tray icon does not own its context menu.
        self._menu = QMenu()
        show_action = QAction("Open FocusPilot", self._menu)
        show_action.triggered.connect(self.show_window)
        self._menu.addAction(show_action)
        self._menu.addSeparator()
        quit_action = QAction("Quit FocusPilot", self._menu)
        quit_action.triggered.connect(self.quit)
        self._menu.addAction(quit_action)
        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)

    @staticmethod
    def is_available() -> bool:
        """Return whether the operating system provides a system tray."""
        return QSystemTrayIcon.isSystemTrayAvailable()

    def show(self) -> None:
        """Make the tray icon visible."""
        self._tray.show()

    def show_window(self) -> None:
        """Bring the dashboard to the front."""
        self._window.showNormal()
        self._window.raise_()
        self._window.activateWindow()

    def quit(self) -> None:
        """Quit, unless Child Mode needs the parent PIN first."""
        if self._window.confirm_quit():
            self._app.quit()

    def notify(self, title: str, message: str, *, msecs: int = 8000) -> None:
        """Show a Windows toast through the tray icon (may be hidden by Focus Assist)."""
        if self._tray.isVisible() and QSystemTrayIcon.supportsMessages():
            self._tray.showMessage(title, message, self._icon, msecs)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_window()
