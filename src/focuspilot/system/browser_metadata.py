"""Loopback-only bridge for the optional Chrome/Edge metadata extension."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from time import time

from PySide6.QtCore import QObject, Signal

from focuspilot.ai.gemini import BrowserPage, sanitize_page_url

logger = logging.getLogger(__name__)
PORT = 43821
MAX_BODY = 8192
_EXTENSION_ORIGIN = re.compile(r"^chrome-extension://[a-p]{32}$")


class BrowserMetadataBridge(QObject):
    """Thread-safe Qt signal bridge for current-page metadata."""

    metadata_received = Signal(str, str, str, float)


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class BrowserMetadataServer:
    """Accept title and redacted URL metadata from an installed browser extension."""

    def __init__(self, is_monitoring: Callable[[], bool]) -> None:
        self.bridge = BrowserMetadataBridge()
        self._is_monitoring = is_monitoring
        self._server: _Server | None = None
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._server is not None:
            return
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format: str, *args: object) -> None:
                logger.debug("Browser metadata bridge: %s", args[0] if args else "request")

            def _cors(self) -> None:
                origin = self.headers.get("Origin", "")
                if _EXTENSION_ORIGIN.fullmatch(origin):
                    self.send_header("Access-Control-Allow-Origin", origin)
                    self.send_header("Vary", "Origin")
                    self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                    self.send_header("Access-Control-Allow-Headers", "Content-Type")
                    self.send_header("Access-Control-Max-Age", "600")

            def _reply(self, status: int, payload: dict[str, object]) -> None:
                content = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self._cors()
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

            def do_OPTIONS(self) -> None:
                if not _EXTENSION_ORIGIN.fullmatch(self.headers.get("Origin", "")):
                    self._reply(403, {"error": "extension origin required"})
                    return
                self.send_response(204)
                self._cors()
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self) -> None:
                if self.path != "/v1/state":
                    self._reply(404, {"error": "not found"})
                    return
                if not _EXTENSION_ORIGIN.fullmatch(self.headers.get("Origin", "")):
                    self._reply(403, {"error": "extension origin required"})
                    return
                self._reply(200, {"monitoring": owner._is_monitoring()})

            def do_POST(self) -> None:
                if self.path != "/v1/tab":
                    self._reply(404, {"error": "not found"})
                    return
                if not _EXTENSION_ORIGIN.fullmatch(self.headers.get("Origin", "")):
                    self._reply(403, {"error": "extension origin required"})
                    return
                if self.headers.get_content_type() != "application/json":
                    self._reply(415, {"error": "JSON required"})
                    return
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if size < 1 or size > MAX_BODY:
                        raise ValueError("invalid body size")
                    payload = json.loads(self.rfile.read(size))
                    if not isinstance(payload, dict):
                        raise ValueError("JSON object required")
                    title = payload.get("title", "")
                    raw_url = payload.get("url", "")
                    browser = payload.get("browser", "")
                    if (
                        not isinstance(title, str)
                        or not isinstance(raw_url, str)
                        or browser not in {"chrome.exe", "msedge.exe"}
                    ):
                        raise ValueError("invalid page metadata")
                    url = sanitize_page_url(raw_url)
                    if not url:
                        raise ValueError("invalid page metadata")
                except (ValueError, TypeError, json.JSONDecodeError) as error:
                    self._reply(400, {"error": str(error)})
                    return
                if owner._is_monitoring():
                    owner.bridge.metadata_received.emit(title[:300], url, browser, time())
                self._reply(200, {"accepted": True})

        self._server = _Server(("127.0.0.1", PORT), Handler)
        self._thread = Thread(
            target=self._server.serve_forever, name="focuspilot-browser", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        server, thread = self._server, self._thread
        self._server = None
        self._thread = None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=2)


def current_page(
    title: str, url: str, browser: str, received_at: float, window_title: str = ""
) -> BrowserPage | None:
    """Return fresh browser metadata, or no context when it is stale."""
    if time() - received_at > 20:
        return None
    if browser not in {"chrome.exe", "msedge.exe"}:
        return None
    if window_title and title.casefold() not in window_title.casefold():
        return None
    safe_url = sanitize_page_url(url)
    return BrowserPage(title=title[:300], url=safe_url, browser=browser) if safe_url else None
