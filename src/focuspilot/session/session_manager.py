"""Focus-session state machine and persistence orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from focuspilot.metrics.scoring import SessionMetrics, calculate_metrics
from focuspilot.storage.models import FocusSession, UsageSegment
from focuspilot.storage.repositories import Repository


@dataclass(frozen=True, slots=True)
class SessionSummary:
    """Session result shown after finishing a focus block."""

    goal: str
    metrics: SessionMetrics
    started_at: datetime
    ended_at: datetime


class SessionManager:
    """Coordinates a single active or paused session."""

    def __init__(self, repository: Repository, user_id: int) -> None:
        self._repository = repository
        self._user_id = user_id
        self.session: FocusSession | None = None
        self.state = "idle"
        self._nudge_count = 0

    def start(
        self,
        *,
        goal_text: str,
        goal_category: str,
        planned_minutes: int,
        strictness: str,
        planned: bool = True,
        allowed_apps: list[str] | None = None,
    ) -> FocusSession:
        if self.state in {"active", "paused"}:
            raise RuntimeError("End the current session before starting another.")
        self.session = self._repository.start_session(
            user_id=self._user_id,
            goal_text=goal_text,
            goal_category=goal_category,
            planned_minutes=planned_minutes,
            strictness=strictness,
            planned=planned,
            allowed_apps=allowed_apps,
        )
        self.state = "active"
        self._nudge_count = 0
        return self.session

    def restore(self, session: FocusSession) -> None:
        """Restore an interrupted session after the user explicitly chooses resume."""
        self.session = session
        self._user_id = session.user_id or self._user_id
        self._repository.set_session_status(session.id, "active")
        self.state = "active"
        self._nudge_count = 0

    def pause(self) -> None:
        if self.state == "active" and self.session is not None:
            self._repository.set_session_status(self.session.id, "paused")
            self.state = "paused"

    def resume(self) -> None:
        if self.state == "paused" and self.session is not None:
            self._repository.set_session_status(self.session.id, "active")
            self.state = "active"

    def record_segment(self, **values: object) -> None:
        if self.session is not None and self.state == "active":
            self._repository.add_segment(session_id=self.session.id, **values)

    def record_drift(self) -> None:
        self._nudge_count += 1

    @property
    def drift_count(self) -> int:
        """How many nudges were shown during the current session."""
        return self._nudge_count

    def end(self, segments: list[UsageSegment]) -> SessionSummary | None:
        if self.session is None:
            return None
        session = self.session
        metrics = calculate_metrics(
            segments,
            planned_minutes=session.planned_minutes,
            planned=session.planned,
            drift_count=self._nudge_count,
        )
        now = datetime.now(UTC)
        self._repository.finish_session(session.id, metrics.score)
        summary = SessionSummary(session.goal_text, metrics, session.started_at, now)
        self.session = None
        self.state = "ended"
        return summary
