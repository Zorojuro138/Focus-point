"""Asynchronous AI work, with deduplication to keep free-tier usage modest."""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import TypeVar

from PySide6.QtCore import QObject, Signal

from focuspilot.ai.gemini import BrowserPage, GeminiClient
from focuspilot.ai.rules import Classification

logger = logging.getLogger(__name__)
_Result = TypeVar("_Result")


class AIService(QObject):
    """Run cloud requests off the UI thread and cache page judgments for ten minutes."""

    classification_ready = Signal(str, str, object)
    classification_failed = Signal(str)
    chat_ready = Signal(str)
    chat_failed = Signal(str)

    def __init__(self, api_key_provider: Callable[[], str], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._api_key_provider = api_key_provider
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="focuspilot-ai")
        self._cache: dict[tuple[str, str, str], tuple[datetime, Classification]] = {}
        self._pending: set[tuple[str, str, str]] = set()
        self._lock = Lock()

    def classify_page(self, *, goal: str, page: BrowserPage) -> None:
        key = (goal, page.title, page.url)
        now = datetime.now(UTC)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None and now - cached[0] < timedelta(minutes=10):
                self.classification_ready.emit(page.url, page.title, cached[1])
                return
            if key in self._pending:
                return
            self._pending.add(key)
        self._submit(
            key,
            lambda: GeminiClient(self._api_key_provider()).classify_page(goal=goal, page=page),
            lambda result: self._on_classification(key, page, result),
        )

    def chat(
        self,
        *,
        goal: str,
        message: str,
        history: list[tuple[str, str]],
        page: BrowserPage | None,
    ) -> None:
        self._submit(
            None,
            lambda: GeminiClient(self._api_key_provider()).chat(
                goal=goal, message=message, history=history, page=page
            ),
            lambda result: self.chat_ready.emit(result),
        )

    def _submit(
        self,
        key: tuple[str, str, str] | None,
        work: Callable[[], _Result],
        on_success: Callable[[_Result], None],
    ) -> None:
        future: Future[_Result] = self._executor.submit(work)

        def finish(completed: Future[_Result]) -> None:
            try:
                result = completed.result()
            except Exception as error:
                logger.info("AI request unavailable: %s", error)
                if key is not None:
                    with self._lock:
                        self._pending.discard(key)
                (self.chat_failed if key is None else self.classification_failed).emit(str(error))
                return
            on_success(result)

        future.add_done_callback(finish)

    def _on_classification(
        self,
        key: tuple[str, str, str],
        page: BrowserPage,
        result: Classification,
    ) -> None:
        with self._lock:
            self._pending.discard(key)
            self._cache[key] = (datetime.now(UTC), result)
            if len(self._cache) > 256:
                oldest = min(self._cache, key=lambda item: self._cache[item][0])
                self._cache.pop(oldest, None)
        self.classification_ready.emit(page.url, page.title, result)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
