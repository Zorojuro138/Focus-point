"""SQLAlchemy models for FocusPilot's local-only SQLite database."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Dialect,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from focuspilot.core.clock import utc_now


class UTCDateTime(TypeDecorator[datetime]):
    """Store UTC and always hand back timezone-aware UTC datetimes.

    SQLite has no timezone support, so a plain ``UTCDateTime()`` returns
    *naive* values on re-read. Code that then formatted those values (history list,
    reports) showed UTC clock times as if they were local times.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            # A naive value is assumed to already be UTC (how rows were stored before).
            return value
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        moment: datetime = value
        return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


class Base(DeclarativeBase):
    """Base metadata for FocusPilot's tables."""


class User(Base):
    """Local FocusPilot user or parent/child profile."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="Me")
    role: Mapped[str] = mapped_column(String(16), default="self")
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pin_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    sessions: Mapped[list[FocusSession]] = relationship(back_populates="user")


class FocusSession(Base):
    """A planned or unplanned focus session."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    goal_text: Mapped[str] = mapped_column(Text, default="")
    goal_category: Mapped[str] = mapped_column(String(32), default="other")
    planned_minutes: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    focus_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    strictness: Mapped[str] = mapped_column(String(16), default="normal")
    planned: Mapped[bool] = mapped_column(Boolean, default=True)
    allowed_apps_json: Mapped[str] = mapped_column(Text, default="[]")

    user: Mapped[User | None] = relationship(back_populates="sessions")
    segments: Mapped[list[UsageSegment]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class UsageSegment(Base):
    """A continuous foreground-window interval."""

    __tablename__ = "usage_segments"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    process_name: Mapped[str] = mapped_column(String(260), default="")
    window_title: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    ended_at: Mapped[datetime] = mapped_column(UTCDateTime())
    duration_s: Mapped[int] = mapped_column(Integer, default=0)
    idle_s: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped[str] = mapped_column(String(32), default="other")
    on_task_score: Mapped[float] = mapped_column(Float, default=0.5)
    label: Mapped[str] = mapped_column(String(16), default="neutral")

    session: Mapped[FocusSession] = relationship(back_populates="segments")


class Nudge(Base):
    """A delivered focus reminder and the user's response."""

    __tablename__ = "nudges"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    level: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    shown_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    user_response: Mapped[str | None] = mapped_column(String(32), nullable=True)


class ActivityOverride(Base):
    """A user-created local classification rule."""

    __tablename__ = "overrides"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    process_name: Mapped[str] = mapped_column(String(260))
    title_pattern: Mapped[str] = mapped_column(Text, default="")
    label: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class DailyStats(Base):
    """Pre-aggregated local daily focus metrics."""

    __tablename__ = "daily_stats"
    __table_args__ = (UniqueConstraint("user_id", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    active_s: Mapped[int] = mapped_column(Integer, default=0)
    focus_s: Mapped[int] = mapped_column(Integer, default=0)
    off_task_s: Mapped[int] = mapped_column(Integer, default=0)
    idle_s: Mapped[int] = mapped_column(Integer, default=0)
    sessions: Mapped[int] = mapped_column(Integer, default=0)
    avg_score: Mapped[float] = mapped_column(Float, default=0)


class Achievement(Base):
    """An unlocked local achievement."""

    __tablename__ = "achievements"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    code: Mapped[str] = mapped_column(String(64))
    unlocked_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class ChildProfile(Base):
    """Parent-configured child limits and app policies."""

    __tablename__ = "child_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    age_band: Mapped[str] = mapped_column(String(24), default="11-13")
    daily_limit_min: Mapped[int] = mapped_column(Integer, default=120)
    bedtime_start: Mapped[str] = mapped_column(String(5), default="21:00")
    bedtime_end: Mapped[str] = mapped_column(String(5), default="07:00")
    allowlist_json: Mapped[str] = mapped_column(Text, default="[]")
    blocklist_json: Mapped[str] = mapped_column(Text, default="[]")
    strict_mode: Mapped[bool] = mapped_column(Boolean, default=False)


class ChildEvent(Base):
    """An auditable child-mode policy event."""

    __tablename__ = "child_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    type: Mapped[str] = mapped_column(String(32))
    detail: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class Setting(Base):
    """A persisted key/value setting."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
