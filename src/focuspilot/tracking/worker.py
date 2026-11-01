"""Background foreground-window polling worker."""

from __future__ import annotations

import logging

from PySide6.QtCore import QMetaObject, QObject, Qt, QThread, QTimer, Signal, Slot

from focuspilot.tracking.active_window import sample_foreground_window

logger = logging.getLogger(__name__)

# pywin32 only exists on Windows; importing it lazily keeps this module importable
# (and testable) everywhere, while still catching its errors on Windows.
try:
    import pywintypes

    _SAMPLING_ERRORS: tuple[type[BaseException], ...] = (OSError, RuntimeError, pywintypes.error)
except ImportError:  # pragma: no cover - non-Windows development machines
    _SAMPLING_ERRORS = (OSError, RuntimeError)


class TrackingWorker(QObject):
    """Poll Windows in a dedicated thread and emit privacy-limited samples."""

    sample_ready = Signal(object)
    tracking_error = Signal(str)
    finished = Signal()

    def __init__(self, interval_ms: int = 2000) -> None:
        super().__init__()
        self._interval_ms = interval_ms
        self._timer: QTimer | None = None
        self._last_error = ""

    @Slot()
    def start(self) -> None:
        self._timer = QTimer(self)
        self._timer.setInterval(self._interval_ms)
        self._timer.timeout.connect(self._poll)
        self._poll()
        self._timer.start()

    @Slot()
    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()
        self.finished.emit()

    @Slot()
    def _poll(self) -> None:
        try:
            sample = sample_foreground_window()
        except _SAMPLING_ERRORS as error:
            message = str(error)
            # Log a failure once, not every two seconds, so the log stays readable.
            if message != self._last_error:
                logger.exception("Could not sample foreground window")
                self._last_error = message
                self.tracking_error.emit(message)
            return
        self._last_error = ""
        if sample is not None:
            self.sample_ready.emit(sample)


class TrackingThread:
    """Owns the polling worker and its Qt thread lifecycle (single use)."""

    def __init__(self, interval_ms: int = 2000) -> None:
        self.thread = QThread()
        self.worker = TrackingWorker(interval_ms)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.start)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)

    def start(self) -> None:
        """Start the background polling loop."""
        self.thread.start()

    def stop(self, timeout_ms: int = 3000) -> None:
        """Stop the worker safely and wait briefly for its thread to finish."""
        if not self.thread.isRunning():
            return
        QMetaObject.invokeMethod(self.worker, "stop", Qt.ConnectionType.QueuedConnection)
        if not self.thread.wait(timeout_ms):
            logger.warning("Tracking thread did not stop within %d ms", timeout_ms)
