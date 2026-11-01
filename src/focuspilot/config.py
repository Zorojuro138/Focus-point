"""Application paths and configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Resolved paths used by the application."""

    data_dir: Path

    @property
    def database_path(self) -> Path:
        """Return the path reserved for the local SQLite database."""
        return self.data_dir / "focuspilot.db"

    @property
    def log_path(self) -> Path:
        """Return the path used for the application log."""
        return self.data_dir / "logs" / "focuspilot.log"

    def ensure_directories(self) -> None:
        """Create the local data and log directories."""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)


def load_config(
    environ: dict[str, str] | None = None,
    home: Path | None = None,
) -> AppConfig:
    """Resolve the per-user data directory, with injectable environment for tests."""
    variables = os.environ if environ is None else environ
    local_app_data = variables.get("LOCALAPPDATA")
    base_dir = (
        Path(local_app_data) if local_app_data else (home or Path.home()) / "AppData" / "Local"
    )
    return AppConfig(data_dir=base_dir / "FocusPilot")
