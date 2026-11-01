"""Local rotating-file logging setup."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from focuspilot.config import AppConfig


def configure_logging(config: AppConfig) -> None:
    """Configure one rotating log file in the user's local app data directory."""
    config.ensure_directories()
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    if any(
        isinstance(handler, RotatingFileHandler)
        and getattr(handler, "baseFilename", None) == str(config.log_path.resolve())
        for handler in root_logger.handlers
    ):
        return

    handler = RotatingFileHandler(
        config.log_path,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root_logger.addHandler(handler)
