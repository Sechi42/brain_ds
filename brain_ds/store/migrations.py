"""Schema migration utilities for SQLite graph store."""

from __future__ import annotations

import json
import sqlite3
import unicodedata
from datetime import datetime, timezone
from typing import Callable, Sequence

from .errors import IncompatibleStoreError, MigrationFailedError
from .schema import DDL_SCRIPT


def _normalize_text(text: str) -> str:
    """Lowercase + strip accents for accent-insensitive FTS indexing."""
    nfd = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn").lower()


def _extract_text_from_json(json_str: str | None) -> str:
    """Extract plain text from a JSON string (details or card_sections)."""
    if not json_str:
        return ""
    try:
        obj = json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return str(json_str or "")
    if isinstance(obj, dict):
        return " ".join(str(v) for v in obj.values() if v is not None)
    if isinstance(obj, list):
        parts: list[str] = []
        for item in obj:
            if isinstance(item, dict):
                parts.extend(str(v) for v in item.values() if v is not None)
            else:
                parts.append(str(item))
        return " ".join(parts)
    return str(obj)

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


def v4_fts5_nodes(conn: sqlite3.Connection) -> None:
    """Create FTS5 virtual table for accent-insensitive node full-text search.

    The table stores normalised (NFD-stripped, lowercase) versions of:
      - graph_id  (UNINDEXED — for filtering, not full-text search)
      - node_id   (UNINDEXED — primary key reference, not searched)
      - label
      - details_text  (JSON values flattened to plain text)
      - sections_text (card_sections JSON values flattened to plain text)

    We use a standard (non-content-less) FTS5 table so that UNINDEXED columns
    are physically stored and retrievable. The FTS index is maintained manually
    from NodeRepository upsert/delete paths (delete-then-insert on every write).
    This migration is idempotent (IF NOT EXISTS) and performs a one-time
    backfill when the table is empty after creation.
    """
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts
        USING fts5(
            graph_id UNINDEXED,
            node_id UNINDEXED,
            label,
            details_text,
            sections_text
        )
        """
    )

    # Check if backfill is needed (table empty after creation)
    count = conn.execute("SELECT COUNT(*) FROM nodes_fts").fetchone()[0]
    if count == 0:
        rows = conn.execute(
            "SELECT graph_id, id, label, details, card_sections FROM nodes"
        ).fetchall()
        for graph_id, node_id, label, details, sections in rows:
            conn.execute(
                "INSERT INTO nodes_fts(graph_id, node_id, label, details_text, sections_text) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    graph_id,
                    node_id,
                    _normalize_text(label or ""),
                    _normalize_text(_extract_text_from_json(details)),
                    _normalize_text(_extract_text_from_json(sections)),
                ),
            )


def v5_graphs_hidden(conn: sqlite3.Connection) -> None:
    """Add hidden column to graphs table for soft-delete (reversible hide).

    SQLite ALTER TABLE ADD COLUMN has no IF NOT EXISTS clause, so we guard
    idempotency by checking PRAGMA table_info before issuing the ALTER.
    """
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(graphs)").fetchall()}
    if "hidden" not in existing_cols:
        conn.execute("ALTER TABLE graphs ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0")


def v6_confidence_ledger(conn: sqlite3.Connection) -> None:
    """Create the append-only confidence_ledger table and its indices (v6).

    Purely additive: IF NOT EXISTS guards make this idempotent.
    The FK ON DELETE CASCADE ties ledger rows to the parent graph lifetime.
    PRAGMA foreign_keys=ON (set by configure_connection) activates the cascade.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS confidence_ledger (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            graph_id            TEXT NOT NULL,
            target_type         TEXT NOT NULL DEFAULT 'edge'
                                CHECK(target_type IN ('edge','node')),
            target_id           TEXT NOT NULL,
            status              TEXT NOT NULL
                                CHECK(status IN (
                                    'inferred','needs-confirmation',
                                    'confirmed','invalidated','abstain'
                                )),
            initial_confidence  REAL,
            current_confidence  REAL,
            relationship_label  TEXT,
            source_node_id      TEXT,
            target_node_id      TEXT,
            source_node_type    TEXT,
            target_node_type    TEXT,
            evidence_ids        TEXT,
            captured_by         TEXT,
            captured_at         TEXT NOT NULL,
            confirmed_at        TEXT,
            confirmed_by        TEXT,
            flagged_reason      TEXT,
            gold_rationale      TEXT,
            provenance          TEXT NOT NULL
                                CHECK(provenance IN ('seed','hand_labeled','generated')),
            FOREIGN KEY (graph_id) REFERENCES graphs(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ledger_graph_status
        ON confidence_ledger(graph_id, status)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ledger_latest
        ON confidence_ledger(graph_id, target_type, target_id, id)
        """
    )


MIGRATIONS: Sequence[Migration] = (
    v1_initial_schema,
    v2_tools_audit,
    v3_event_outbox,
    v4_fts5_nodes,
    v5_graphs_hidden,
    v6_confidence_ledger,
)


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
