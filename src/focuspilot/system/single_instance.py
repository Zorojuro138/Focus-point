"""Allow only one FocusPilot per user, and bring the running one to the front.

Without this, "start with Windows" plus a manual launch gives two trays, two trackers
and two writers fighting over the same SQLite file.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance(QObject):
    """Holds a lock file and a local socket for the lifetime of the app."""

    activation_requested = Signal()

    def __init__(
        self, lock_path: Path, server_name: str = "FocusPilot", parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = QLockFile(str(lock_path))
        self._server_name = server_name
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_connection)

    def acquire(self) -> bool:
        """Return True if this is the only instance; otherwise ask the other to show."""
        if not self._lock.tryLock(0):
            self._ask_running_instance_to_show()
            return False
        QLocalServer.removeServer(self._server_name)  # clear a stale socket from a crash
        self._server.listen(self._server_name)
        return True

    def release(self) -> None:
        """Release the lock and stop listening."""
        self._server.close()
        self._lock.unlock()

    def _ask_running_instance_to_show(self) -> None:
        socket = QLocalSocket()
        socket.connectToServer(self._server_name)
        if socket.waitForConnected(500):
            socket.write(b"show")
            socket.waitForBytesWritten(500)
            socket.disconnectFromServer()

    def _on_connection(self) -> None:
        connection = self._server.nextPendingConnection()
        if connection is None:
            return
        connection.readyRead.connect(self.activation_requested.emit)
        connection.disconnected.connect(connection.deleteLater)
