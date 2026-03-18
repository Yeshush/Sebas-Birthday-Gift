"""Loguru logging setup for JobScraper."""

import sys
from pathlib import Path

from loguru import logger


def configure_logging(log_file: Path | None = None, level: str = "INFO") -> None:
    """Configure loguru: clean console output + optional rotating file log."""
    logger.remove()

    # Console: human-readable, no timestamps (they clutter CLI output)
    logger.add(
        sys.stderr,
        level=level,
        format="<level>{message}</level>",
        colorize=True,
    )

    if log_file:
        logger.add(
            log_file,
            level="DEBUG",
            rotation="10 MB",
            retention="30 days",
            encoding="utf-8",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message}",
        )


# Default: console only at INFO
configure_logging()
