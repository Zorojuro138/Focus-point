"""Database setup and lifecycle helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, inspect
from sqlalchemy.orm import Session, sessionmaker

from focuspilot.storage.models import Base


def _configure_sqlite(dbapi_connection: Any, _record: Any) -> None:
    """Make SQLite safer for a long-running desktop app."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=10000")
    finally:
        cursor.close()


def create_database(path: Path) -> tuple[Engine, sessionmaker[Session]]:
    """Create the local SQLite database and return its engine and session factory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{path.as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    event.listen(engine, "connect", _configure_sqlite)
    Base.metadata.create_all(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("sessions")}
    if "allowed_apps_json" not in columns:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE sessions ADD COLUMN allowed_apps_json TEXT NOT NULL DEFAULT '[]'"
            )
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def delete_database(engine: Engine, path: Path) -> None:
    """Dispose database connections and delete the database plus SQLite sidecars."""
    engine.dispose()
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        candidate.unlink(missing_ok=True)
