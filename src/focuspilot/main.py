"""FocusPilot command-line entry point."""

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence
from types import TracebackType

from focuspilot.app import run


def _handle_uncaught_exception(
    exception_type: type[BaseException],
    exception: BaseException,
    traceback: TracebackType | None,
) -> None:
    logging.getLogger("focuspilot").critical(
        "Uncaught application exception",
        exc_info=(exception_type, exception, traceback),
    )
    sys.__excepthook__(exception_type, exception, traceback)


def main(argv: Sequence[str] | None = None) -> int:
    """Start FocusPilot and return its process exit code."""
    sys.excepthook = _handle_uncaught_exception
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
