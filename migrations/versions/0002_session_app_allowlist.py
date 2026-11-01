"""Persist the apps selected for each focus session."""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect

revision = "0002_session_app_allowlist"
down_revision = "0001_local_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("sessions")}
    if "allowed_apps_json" not in columns:
        op.execute(
            "ALTER TABLE sessions ADD COLUMN allowed_apps_json TEXT NOT NULL DEFAULT '[]'"
        )


def downgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("sessions")}
    if "allowed_apps_json" in columns:
        with op.batch_alter_table("sessions") as batch:
            batch.drop_column("allowed_apps_json")
