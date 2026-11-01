"""PySide application composition and lifecycle."""

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from focuspilot.config import load_config
from focuspilot.logging_config import configure_logging
from focuspilot.storage.db import create_database
from focuspilot.storage.repositories import Repository
from focuspilot.system.autostart import AUTOSTART_FLAG
from focuspilot.system.single_instance import SingleInstance
from focuspilot.system.tray import TrayController
from focuspilot.ui.consent_dialog import ConsentDialog
from focuspilot.ui.main_window import MainWindow

logger = logging.getLogger(__name__)


def _prune_old_activity(repository: Repository) -> None:
    """Apply the retention setting; a corrupt value must never stop the app starting."""
    retention = repository.get_setting("retention", "90 days")
    if retention == "Keep forever":
        return
    try:
        days = int(retention.split()[0])
    except (ValueError, IndexError):
        logger.warning("Ignoring invalid retention setting %r", retention)
        return
    repository.prune_segments_before(datetime.now(UTC) - timedelta(days=days))


def _apply_palette(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = app.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#f5f7f2"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#eef2e9"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#17231f"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#17231f"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#17231f"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#8fbd62"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#17231f"))
    app.setPalette(palette)


def run(argv: Sequence[str] | None = None) -> int:
    """Create the application, show its dashboard, and run its event loop."""
    arguments = list(argv) if argv is not None else sys.argv
    started_with_windows = AUTOSTART_FLAG in arguments
    config = load_config()
    configure_logging(config)
    logger.info("Starting FocusPilot (autostart=%s)", started_with_windows)

    app = QApplication([item for item in arguments if item != AUTOSTART_FLAG])
    app.setApplicationName("FocusPilot")
    app.setQuitOnLastWindowClosed(False)
    _apply_palette(app)

    instance = SingleInstance(config.data_dir / "focuspilot.lock")
    if not instance.acquire():
        logger.info("FocusPilot is already running; asked it to show itself")
        return 0

    if not TrayController.is_available():
        logger.error("No system tray is available")
        QMessageBox.critical(
            None,
            "FocusPilot",
            "The Windows system tray is unavailable. FocusPilot cannot start.",
        )
        instance.release()
        return 1

    engine, session_factory = create_database(config.database_path)
    repository = Repository(session_factory)
    _prune_old_activity(repository)
    user_id = repository.ensure_user()
    window = MainWindow(config, engine, repository, user_id)
    tray = TrayController(app, window)
    window.notifier = tray.notify
    instance.activation_requested.connect(tray.show_window)
    tray.show()
    window.show()
    window.raise_()
    window.activateWindow()

    def shutdown() -> None:
        window.request_quit()
        instance.release()
        engine.dispose()
        logger.info("FocusPilot stopped")

    app.aboutToQuit.connect(shutdown)

    if repository.get_setting("consent_accepted", "false") != "true":
        consent = ConsentDialog(window)
        if consent.exec() != QDialog.DialogCode.Accepted or not consent.accept_check.isChecked():
            shutdown()
            return 0
        repository.set_setting("consent_accepted", "true")
        repository.set_setting("gemini_consent", str(consent.ai_check.isChecked()).lower())

    interrupted = repository.active_session()
    if interrupted is not None:
        answer = QMessageBox.question(
            window,
            "Resume your previous session?",
            f'"{interrupted.goal_text}" was active when FocusPilot last closed. Resume it?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            window.resume_interrupted(interrupted)
        else:
            repository.set_session_status(interrupted.id, "ended")
    else:
        # Every app launch starts by setting a visible intention and allowed app list.
        QTimer.singleShot(0, window.prompt_for_session)
    window._refresh_all()
    return app.exec()
