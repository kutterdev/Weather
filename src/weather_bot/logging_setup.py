"""Logging setup.

Diagnostics go to a rotating file. Structured event records go to SQLite via
the db.run_log table (written by the modules that produce them, not here).
"""

import logging
from logging.handlers import RotatingFileHandler

from .config import settings


def configure_logging(component: str = "weather_bot") -> logging.Logger:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    log_path = settings.log_dir / f"{component}.log"

    root = logging.getLogger()
    if getattr(root, "_weather_bot_configured", False):
        return logging.getLogger(component)

    root.setLevel(settings.log_level.upper())

    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    file_handler = RotatingFileHandler(
        log_path, maxBytes=10_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    root.addHandler(stream)

    root._weather_bot_configured = True  # type: ignore[attr-defined]
    return logging.getLogger(component)
