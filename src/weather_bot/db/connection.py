"""SQLite connection helpers.

We use the stdlib sqlite3 module. For the cadences in this project (hourly
forecasts, 15-minute snapshots) it is more than enough. WAL mode lets the
reporting CLI read while the scheduler writes.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from ..config import settings

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def get_db_path() -> Path:
    return settings.db_path


def init_db(db_path: Path | None = None) -> Path:
    """Create the database file and apply schema. Idempotent."""
    path = db_path or settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return path


@contextmanager
def connect(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection with row_factory set and FK on."""
    path = db_path or settings.db_path
    conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
