"""Merge foreground samples into durable, privacy-limited usage segments."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from focuspilot.ai.rules import Classification
from focuspilot.session.session_manager import SessionManager
from focuspilot.tracking.active_window import WindowSample

IDLE_THRESHOLD_S = 120.0
IDLE_SUSPECT_S = 30.0
MAX_GAP_S = 5.0


class UsageRecorder:
    """Accumulate stable-window samples and persist compact SQLite segments."""

    def __init__(
        self,
        manager: SessionManager,
        classify: Callable[[WindowSample], Classification],
        *,
        flush_seconds: int = 30,
    ) -> None:
        self._manager = manager
        self._classify = classify
        self._flush_seconds = flush_seconds
        self._key: tuple[str, str] | None = None
        self._started_at: datetime | None = None
        self._last_at: datetime | None = None
        self._duration_s = 0.0
        self._idle_s = 0.0
        self._was_idle = False
        self._classification: Classification | None = None

    def _elapsed(self, sample: WindowSample) -> float:
        assert self._last_at is not None
        return max(0.0, min((sample.ts - self._last_at).total_seconds(), MAX_GAP_S))

    def _credit(self, sample: WindowSample, elapsed: float) -> None:
        """Add ``elapsed`` seconds to the open segment as active or idle time."""
        idle_now = sample.idle_s >= IDLE_THRESHOLD_S
        if idle_now and not self._was_idle:
            # The user went idle some time ago, but we only notice once the threshold
            # is crossed. Move the time they were already away out of "active".
            already_idle = max(0.0, sample.idle_s - elapsed)
            moved = min(self._duration_s, already_idle)
            self._duration_s -= moved
            self._idle_s += moved
        self._was_idle = idle_now
        if idle_now:
            self._idle_s += elapsed
        else:
            self._duration_s += elapsed

    def consume(self, sample: WindowSample) -> None:
        """Add a sample, rolling the current segment on a window, app or label change."""
        key = (sample.process_name.casefold(), sample.window_title)
        classification = self._classify(sample)
        changed = self._key != key or (
            self._classification is not None and classification.label != self._classification.label
        )
        if changed:
            if self._key is not None and self._last_at is not None:
                # The time since the previous sample still belonged to the previous
                # window, so credit it there before closing that segment.
                self._credit(sample, self._elapsed(sample))
                self._last_at = sample.ts
            self.flush()
            self._key = key
            self._started_at = sample.ts
            self._last_at = sample.ts
            self._classification = classification
            self._was_idle = sample.idle_s >= IDLE_THRESHOLD_S
            return

        self._credit(sample, self._elapsed(sample))
        self._last_at = sample.ts
        # While the user *might* be away (quiet, but not yet idle for 2 minutes) keep the
        # time in memory: if they turn out to be away, it is moved to idle, which is
        # impossible once the rows are written.
        maybe_away = IDLE_SUSPECT_S <= sample.idle_s < IDLE_THRESHOLD_S
        if self._duration_s + self._idle_s >= self._flush_seconds and not maybe_away:
            self.flush(keep_open=True)

    def flush(self, *, keep_open: bool = False) -> None:
        """Persist the accumulated segment and optionally continue the same window."""
        if (
            self._key is not None
            and self._started_at is not None
            and self._last_at is not None
            and self._classification is not None
            and self._duration_s + self._idle_s > 0
        ):
            session = self._manager.session
            if session is not None:
                self._manager.record_segment(
                    user_id=session.user_id,
                    process_name=self._key[0],
                    window_title=self._key[1],
                    started_at=self._started_at,
                    ended_at=self._last_at,
                    duration_s=round(self._duration_s),
                    idle_s=round(self._idle_s),
                    category=self._classification.category,
                    on_task_score=self._classification.score,
                    label=(
                        "idle"
                        if self._duration_s == 0 and self._classification.label != "break"
                        else self._classification.label
                    ),
                )
        self._duration_s = 0.0
        self._idle_s = 0.0
        if keep_open:
            self._started_at = self._last_at
        else:
            self._key = None
            self._started_at = None
            self._last_at = None
            self._classification = None
            self._was_idle = False
