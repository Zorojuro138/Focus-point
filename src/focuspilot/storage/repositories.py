"""Database operations for sessions, activity, settings, and reports."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import case, delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from focuspilot.storage.models import (
    Achievement,
    ActivityOverride,
    ChildEvent,
    ChildProfile,
    DailyStats,
    FocusSession,
    Nudge,
    Setting,
    UsageSegment,
    User,
)


def _local_day_start(day: date) -> datetime:
    local_tz = datetime.now().astimezone().tzinfo
    return datetime.combine(day, time.min, tzinfo=local_tz).astimezone(UTC)


def _local_date(value: datetime) -> date:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value
    return aware.astimezone().date()


class Repository:
    """Small transactional repository for app-local data."""

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def get_setting(self, key: str, default: str = "") -> str:
        with self._sessions() as db:
            row = db.get(Setting, key)
            return default if row is None else row.value

    def set_setting(self, key: str, value: str) -> None:
        with self._sessions.begin() as db:
            row = db.get(Setting, key)
            if row is None:
                db.add(Setting(key=key, value=value))
            else:
                row.value = value

    def ensure_user(self, name: str = "Me") -> int:
        with self._sessions.begin() as db:
            user = db.scalar(select(User).where(User.role == "self").limit(1))
            if user is None:
                user = User(name=name, role="self")
                db.add(user)
                db.flush()
            return user.id

    def start_session(
        self,
        *,
        user_id: int,
        goal_text: str,
        goal_category: str,
        planned_minutes: int,
        strictness: str,
        planned: bool = True,
        allowed_apps: list[str] | None = None,
    ) -> FocusSession:
        row = FocusSession(
            id=str(uuid4()),
            user_id=user_id,
            goal_text=goal_text,
            goal_category=goal_category,
            planned_minutes=planned_minutes,
            strictness=strictness,
            planned=planned,
            allowed_apps_json=json.dumps(allowed_apps or []),
            status="active",
        )
        with self._sessions.begin() as db:
            db.add(row)
        return row

    def set_session_status(self, session_id: str, status: str) -> None:
        with self._sessions.begin() as db:
            row = db.get(FocusSession, session_id)
            if row is None:
                raise LookupError(f"Unknown session: {session_id}")
            row.status = status

    def add_segment(self, **values: Any) -> None:
        with self._sessions.begin() as db:
            db.add(UsageSegment(**values))

    def add_nudge(self, *, session_id: str, level: int, reason: str) -> int:
        with self._sessions.begin() as db:
            row = Nudge(session_id=session_id, level=level, reason=reason)
            db.add(row)
            db.flush()
            return row.id

    def respond_to_nudge(self, nudge_id: int, response: str) -> None:
        with self._sessions.begin() as db:
            row = db.get(Nudge, nudge_id)
            if row is not None:
                row.user_response = response

    def save_override(
        self,
        *,
        user_id: int,
        process_name: str,
        title_pattern: str,
        label: str = "on_task",
    ) -> None:
        """Save a classification preference; a later choice replaces an earlier one."""
        process = process_name.casefold()
        pattern = title_pattern.casefold()
        with self._sessions.begin() as db:
            row = db.scalar(
                select(ActivityOverride).where(
                    ActivityOverride.user_id == user_id,
                    ActivityOverride.process_name == process,
                    ActivityOverride.title_pattern == pattern,
                )
            )
            if row is None:
                db.add(
                    ActivityOverride(
                        user_id=user_id,
                        process_name=process,
                        title_pattern=pattern,
                        label=label,
                    )
                )
            else:
                row.label = label

    def list_overrides(self, user_id: int) -> list[tuple[str, str, str]]:
        """Return ``(process, title_pattern, label)`` rules, most specific/newest first."""
        with self._sessions() as db:
            rows = db.scalars(
                select(ActivityOverride).where(
                    (ActivityOverride.user_id == user_id) | (ActivityOverride.user_id.is_(None))
                )
            ).all()
        ordered = sorted(rows, key=lambda row: (bool(row.title_pattern), row.id), reverse=True)
        return [
            (row.process_name.casefold(), row.title_pattern.casefold(), row.label)
            for row in ordered
        ]

    def matching_override(
        self,
        *,
        user_id: int,
        process_name: str,
        window_title: str,
    ) -> ActivityOverride | None:
        """Return the best matching rule: title-specific rules beat whole-app rules."""
        process = process_name.casefold()
        title = window_title.casefold()
        with self._sessions() as db:
            rows = db.scalars(
                select(ActivityOverride).where(
                    (ActivityOverride.user_id == user_id) | (ActivityOverride.user_id.is_(None))
                )
            ).all()
        candidates = [
            row
            for row in rows
            if row.process_name.casefold() == process
            and (not row.title_pattern or row.title_pattern.casefold() in title)
        ]
        candidates.sort(key=lambda row: (bool(row.title_pattern), row.id), reverse=True)
        return candidates[0] if candidates else None

    def session_segments(self, session_id: str) -> list[UsageSegment]:
        with self._sessions() as db:
            return list(
                db.scalars(
                    select(UsageSegment)
                    .where(UsageSegment.session_id == session_id)
                    .order_by(UsageSegment.started_at, UsageSegment.id)
                )
            )

    def finish_session(self, session_id: str, focus_score: float) -> None:
        with self._sessions.begin() as db:
            row = db.get(FocusSession, session_id)
            if row is None:
                raise LookupError(f"Unknown session: {session_id}")
            row.status = "ended"
            row.ended_at = datetime.now(UTC)
            row.focus_score = focus_score

    def recent_sessions(self, limit: int = 20, user_id: int | None = None) -> list[FocusSession]:
        query = select(FocusSession).where(FocusSession.status == "ended")
        if user_id is not None:
            query = query.where(FocusSession.user_id == user_id)
        with self._sessions() as db:
            return list(db.scalars(query.order_by(FocusSession.started_at.desc()).limit(limit)))

    def active_session(self) -> FocusSession | None:
        with self._sessions() as db:
            return db.scalar(
                select(FocusSession)
                .where(FocusSession.status.in_(("active", "paused")))
                .order_by(FocusSession.started_at.desc())
                .limit(1)
            )

    def summary(
        self, since: datetime | None = None, user_id: int | None = None
    ) -> dict[str, int | float]:
        since = since or _local_day_start(datetime.now().astimezone().date())
        segment_filter = [UsageSegment.started_at >= since]
        session_filter = [
            FocusSession.ended_at >= since,
            FocusSession.focus_score.is_not(None),
        ]
        if user_id is not None:
            segment_filter.append(UsageSegment.user_id == user_id)
            session_filter.append(FocusSession.user_id == user_id)
        with self._sessions() as db:
            row = db.execute(
                select(
                    func.coalesce(
                        func.sum(
                            case(
                                (UsageSegment.label != "break", UsageSegment.duration_s),
                                else_=0,
                            )
                        ),
                        0,
                    ),
                    func.coalesce(
                        func.sum(
                            UsageSegment.duration_s
                            * case(
                                (UsageSegment.label == "on_task", 1.0),
                                (UsageSegment.label == "neutral", 0.5),
                                else_=0.0,
                            )
                        ),
                        0,
                    ),
                    func.coalesce(func.sum(UsageSegment.idle_s), 0),
                    func.count(func.distinct(UsageSegment.session_id)),
                ).where(*segment_filter)
            ).one()
            score_values = db.scalars(select(FocusSession.focus_score).where(*session_filter)).all()
            return {
                "active_s": int(row[0]),
                "focus_s": int(row[1]),
                "idle_s": int(row[2]),
                "sessions": int(row[3]),
                "avg_score": (
                    sum(float(value) for value in score_values if value is not None)
                    / len(score_values)
                    if score_values
                    else 0.0
                ),
            }

    def weekly_summary(self, user_id: int | None = None) -> list[dict[str, int | str]]:
        today = date.today()
        start = _local_day_start(today - timedelta(days=6))
        query = select(UsageSegment).where(UsageSegment.started_at >= start)
        if user_id is not None:
            query = query.where(UsageSegment.user_id == user_id)
        with self._sessions() as db:
            rows = db.scalars(query).all()
        totals: dict[str, int] = {}
        for segment in rows:
            day = _local_date(segment.started_at).isoformat()
            if segment.label != "break":
                totals[day] = totals.get(day, 0) + segment.duration_s
        return [
            {
                "day": (today - timedelta(days=offset)).strftime("%a"),
                "active_s": totals.get((today - timedelta(days=offset)).isoformat(), 0),
            }
            for offset in range(6, -1, -1)
        ]

    def export_data(self) -> dict[str, list[dict[str, Any]]]:
        with self._sessions() as db:
            sessions = db.scalars(select(FocusSession).order_by(FocusSession.started_at)).all()
            segments = db.scalars(select(UsageSegment).order_by(UsageSegment.started_at)).all()
            nudges = db.scalars(select(Nudge).order_by(Nudge.shown_at)).all()
            settings = db.scalars(select(Setting).order_by(Setting.key)).all()
            overrides = db.scalars(select(ActivityOverride)).all()
            profiles = db.scalars(select(ChildProfile)).all()
            daily_stats = db.scalars(select(DailyStats).order_by(DailyStats.date)).all()
            achievements = db.scalars(select(Achievement)).all()
            child_events = db.scalars(select(ChildEvent).order_by(ChildEvent.at)).all()
        return {
            "sessions": [
                {
                    "id": item.id,
                    "goal": item.goal_text,
                    "category": item.goal_category,
                    "planned_minutes": item.planned_minutes,
                    "started_at": item.started_at.isoformat(),
                    "ended_at": item.ended_at.isoformat() if item.ended_at else None,
                    "focus_score": item.focus_score,
                    "status": item.status,
                    "allowed_apps": json.loads(item.allowed_apps_json or "[]"),
                }
                for item in sessions
            ],
            "usage_segments": [
                {
                    "session_id": item.session_id,
                    "process_name": item.process_name,
                    "window_title": item.window_title,
                    "started_at": item.started_at.isoformat(),
                    "ended_at": item.ended_at.isoformat(),
                    "duration_s": item.duration_s,
                    "idle_s": item.idle_s,
                    "label": item.label,
                }
                for item in segments
            ],
            "nudges": [
                {
                    "session_id": item.session_id,
                    "level": item.level,
                    "reason": item.reason,
                    "shown_at": item.shown_at.isoformat(),
                    "user_response": item.user_response,
                }
                for item in nudges
            ],
            "settings": [
                {"key": item.key, "value": item.value}
                for item in settings
                if item.key != "gemini_api_key"
            ],
            "overrides": [
                {
                    "process_name": item.process_name,
                    "title_pattern": item.title_pattern,
                    "label": item.label,
                    "created_at": item.created_at.isoformat(),
                }
                for item in overrides
            ],
            "family_profiles": [
                {
                    "age_band": item.age_band,
                    "daily_limit_min": item.daily_limit_min,
                    "bedtime_start": item.bedtime_start,
                    "bedtime_end": item.bedtime_end,
                    "allowlist": json.loads(item.allowlist_json),
                    "blocklist": json.loads(item.blocklist_json),
                    "strict_mode": item.strict_mode,
                }
                for item in profiles
            ],
            "daily_stats": [
                {
                    "date": item.date.isoformat(),
                    "active_s": item.active_s,
                    "focus_s": item.focus_s,
                    "off_task_s": item.off_task_s,
                    "idle_s": item.idle_s,
                    "sessions": item.sessions,
                    "avg_score": item.avg_score,
                }
                for item in daily_stats
            ],
            "achievements": [
                {"code": item.code, "unlocked_at": item.unlocked_at.isoformat()}
                for item in achievements
            ],
            "family_events": [
                {"type": item.type, "detail": item.detail, "at": item.at.isoformat()}
                for item in child_events
            ],
        }

    def delete_all_data(self) -> None:
        with self._sessions.begin() as db:
            for model in (
                UsageSegment,
                Nudge,
                ActivityOverride,
                ChildEvent,
                ChildProfile,
                Achievement,
                DailyStats,
                FocusSession,
                User,
                Setting,
            ):
                db.execute(delete(model))

    def prune_segments_before(self, cutoff: datetime) -> int:
        """Roll older raw activity into daily totals, then remove raw segments."""
        with self._sessions.begin() as db:
            segments = db.scalars(select(UsageSegment).where(UsageSegment.ended_at < cutoff)).all()
            grouped: dict[tuple[int | None, date], list[UsageSegment]] = {}
            for segment in segments:
                grouped.setdefault((segment.user_id, _local_date(segment.started_at)), []).append(
                    segment
                )
            for (user_id, day), day_segments in grouped.items():
                session_ids = {item.session_id for item in day_segments}
                if user_id is None:
                    stats = db.scalar(
                        select(DailyStats).where(
                            DailyStats.user_id.is_(None), DailyStats.date == day
                        )
                    )
                else:
                    stats = db.scalar(
                        select(DailyStats).where(
                            DailyStats.user_id == user_id, DailyStats.date == day
                        )
                    )
                if stats is None:
                    stats = DailyStats(user_id=user_id, date=day)
                    db.add(stats)
                    db.flush()
                old_sessions = stats.sessions
                stats.active_s += sum(
                    item.duration_s for item in day_segments if item.label != "break"
                )
                stats.idle_s += sum(item.idle_s for item in day_segments)
                stats.focus_s += round(
                    sum(
                        item.duration_s
                        * (1 if item.label == "on_task" else 0.5 if item.label == "neutral" else 0)
                        for item in day_segments
                        if item.label != "break"
                    )
                )
                stats.off_task_s += sum(
                    item.duration_s for item in day_segments if item.label == "off_task"
                )
                stats.sessions += len(session_ids)
                scores = db.scalars(
                    select(FocusSession.focus_score).where(
                        FocusSession.id.in_(session_ids),
                        FocusSession.focus_score.is_not(None),
                    )
                ).all()
                if scores:
                    stats.avg_score = (
                        stats.avg_score * old_sessions
                        + sum(float(value) for value in scores if value is not None)
                    ) / (old_sessions + len(scores))
            for segment in segments:
                db.delete(segment)
            return len(segments)

    def set_child_profile(
        self,
        *,
        name: str,
        pin_hash: str,
        age_band: str,
        daily_limit_min: int,
        bedtime_start: str,
        bedtime_end: str,
        allowlist: list[str],
        blocklist: list[str],
        strict_mode: bool,
    ) -> int:
        with self._sessions.begin() as db:
            child = db.scalar(select(User).where(User.role == "child").limit(1))
            if child is None:
                child = User(name=name, role="child")
                db.add(child)
                db.flush()
            child.name = name
            child.pin_hash = pin_hash
            profile = db.scalar(select(ChildProfile).where(ChildProfile.user_id == child.id))
            if profile is None:
                profile = ChildProfile(user_id=child.id)
                db.add(profile)
            profile.age_band = age_band
            profile.daily_limit_min = daily_limit_min
            profile.bedtime_start = bedtime_start
            profile.bedtime_end = bedtime_end
            profile.allowlist_json = json.dumps(allowlist)
            profile.blocklist_json = json.dumps(blocklist)
            profile.strict_mode = strict_mode
            return child.id

    def child_profile(self) -> tuple[User, ChildProfile] | None:
        with self._sessions() as db:
            result = db.execute(
                select(User, ChildProfile)
                .join(ChildProfile, ChildProfile.user_id == User.id)
                .where(User.role == "child")
                .limit(1)
            ).first()
            if result is None:
                return None
            db.expunge_all()
            return result[0], result[1]

    def add_child_event(self, child_id: int, event_type: str, detail: str) -> None:
        with self._sessions.begin() as db:
            db.add(ChildEvent(child_id=child_id, type=event_type, detail=detail))

    def child_daily_usage(self, child_id: int) -> int:
        start = _local_day_start(date.today())
        with self._sessions() as db:
            total = db.scalar(
                select(func.coalesce(func.sum(UsageSegment.duration_s), 0))
                .join(FocusSession, FocusSession.id == UsageSegment.session_id)
                .where(
                    FocusSession.user_id == child_id,
                    UsageSegment.started_at >= start,
                    UsageSegment.label != "break",
                )
            )
            return int(total or 0)

    def child_report(self, child_id: int) -> list[dict[str, Any]]:
        with self._sessions() as db:
            rows = db.scalars(
                select(FocusSession)
                .where(FocusSession.user_id == child_id)
                .order_by(FocusSession.started_at.desc())
                .limit(30)
            ).all()
            return [
                {
                    "goal": row.goal_text,
                    "started_at": row.started_at.isoformat(),
                    "status": row.status,
                    "score": row.focus_score,
                }
                for row in rows
            ]

    # ------------------------------------------------------------------ progress
    def daily_focus_seconds(self, user_id: int, days: int = 60) -> dict[date, int]:
        """Focused seconds per local day (neutral time counts half), newest ``days`` days."""
        start = _local_day_start(date.today() - timedelta(days=days - 1))
        totals: dict[date, float] = {}
        with self._sessions() as db:
            segments = db.scalars(
                select(UsageSegment).where(
                    UsageSegment.user_id == user_id, UsageSegment.started_at >= start
                )
            ).all()
            rolled = db.scalars(
                select(DailyStats).where(
                    DailyStats.user_id == user_id,
                    DailyStats.date >= date.today() - timedelta(days=days - 1),
                )
            ).all()
        for segment in segments:
            weight = {"on_task": 1.0, "neutral": 0.5}.get(segment.label, 0.0)
            day = _local_date(segment.started_at)
            totals[day] = totals.get(day, 0.0) + segment.duration_s * weight
        for stats in rolled:
            totals[stats.date] = totals.get(stats.date, 0.0) + stats.focus_s
        return {day: round(value) for day, value in totals.items()}

    def get_xp(self) -> int:
        """Return the XP earned so far (stored locally with the other settings)."""
        try:
            return max(0, int(self.get_setting("xp_total", "0")))
        except ValueError:
            return 0

    def add_xp(self, amount: int) -> int:
        """Add XP and return the new total."""
        total = self.get_xp() + max(0, amount)
        self.set_setting("xp_total", str(total))
        return total

    def unlocked_achievements(self, user_id: int) -> set[str]:
        with self._sessions() as db:
            return set(db.scalars(select(Achievement.code).where(Achievement.user_id == user_id)))

    def unlock_achievement(self, user_id: int, code: str) -> bool:
        """Unlock ``code`` once; return True only the first time."""
        with self._sessions.begin() as db:
            exists = db.scalar(
                select(Achievement.id).where(
                    Achievement.user_id == user_id, Achievement.code == code
                )
            )
            if exists is not None:
                return False
            db.add(Achievement(user_id=user_id, code=code))
            return True

    def ended_session_count(self, user_id: int) -> int:
        with self._sessions() as db:
            return int(
                db.scalar(
                    select(func.count())
                    .select_from(FocusSession)
                    .where(FocusSession.user_id == user_id, FocusSession.status == "ended")
                )
                or 0
            )
