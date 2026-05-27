"""Schema migration utilities for SQLite graph store."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Callable, Sequence

from .errors import IncompatibleStoreError, MigrationFailedError
from .schema import DDL_SCRIPT

Migration = Callable[[sqlite3.Connection], None]


def configure_connection(conn: sqlite3.Connection) -> None:
    """Apply required PRAGMA settings for the store connection."""
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")


def v1_initial_schema(conn: sqlite3.Connection) -> None:
    """Create all v1 tables and indices."""
    conn.executescript(DDL_SCRIPT)


def v2_tools_audit(conn: sqlite3.Connection) -> None:
    """Create audit log table for write-tool operations."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tools_audit(
            id INTEGER PRIMARY KEY,
            timestamp TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            input_hash TEXT NOT NULL,
            result_status TEXT NOT NULL,
            caller_id TEXT
        )
        """
    )


def v3_event_outbox(conn: sqlite3.Connection) -> None:
    """Create outbox table for cross-process event publication."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_outbox(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event TEXT NOT NULL,
            graph_id TEXT NOT NULL,
            payload TEXT,
            created_at TEXT NOT NULL,
            published INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_outbox_published
        ON event_outbox(published)
        """
    )


MIGRATIONS: Sequence[Migration] = (v1_initial_schema, v2_tools_audit, v3_event_outbox)


def _current_schema_version(conn: sqlite3.Connection) -> int:
    table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'store_meta'"
    ).fetchone()
    if table is None:
        return 0

    row = conn.execute(
        "SELECT value FROM store_meta WHERE key = 'schema_version'"
    ).fetchone()
    if row is None:
        return 0
    return int(row[0])


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO store_meta(key, value) VALUES('schema_version', ?)",
        (str(version),),
    )
    conn.execute(
        "INSERT OR REPLACE INTO store_meta(key, value) VALUES('last_migrated_at', ?)",
        (now,),
    )


def apply_pending(conn: sqlite3.Connection) -> list[int]:
    """Apply pending ordered migrations and return applied target versions."""
    latest = len(MIGRATIONS)
    current = _current_schema_version(conn)
    if current > latest:
        raise IncompatibleStoreError(
            f"Database schema version {current} is newer than supported {latest}"
        )

    applied: list[int] = []
    for i in range(current, latest):
        target_version = i + 1
        try:
            conn.execute("BEGIN")
            MIGRATIONS[i](conn)
            _set_schema_version(conn, target_version)
            conn.commit()
        except Exception as exc:  # pragma: no cover - exercised by tests
            conn.rollback()
            raise MigrationFailedError(target_version=target_version, original=exc) from exc
        applied.append(target_version)

    return applied
