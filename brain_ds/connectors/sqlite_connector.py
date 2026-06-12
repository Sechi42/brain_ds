"""Read-only SQLite connector.

Opens databases with sqlite3 URI mode=ro (immutable when supported) and
enforces PRAGMA query_only=ON as defense-in-depth. The query() method
accepts only single SELECT or WITH...SELECT statements.

Path sandbox: the database file path must be validated via
validate_path_within_root before constructing this connector.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from .base import ReadOnlyConnector

# Maximum rows returned by query()
_QUERY_ROW_CAP = 200
# Maximum rows returned by preview()
_PREVIEW_ROW_CAP = 50

# Statements that are clearly prohibited even inside a WITH clause.
_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|ATTACH|DETACH|PRAGMA)\b",
    re.IGNORECASE,
)

# Strip single-line comments (-- ...) and block comments (/* ... */)
_COMMENT_RE = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)


def _strip_comments(sql: str) -> str:
    return _COMMENT_RE.sub(" ", sql)


def _validate_select_only(sql: str) -> None:
    """Raise ValueError if sql is not a single SELECT or WITH...SELECT."""
    cleaned = _strip_comments(sql).strip()

    # Check for multiple statements (trailing semicolons allowed at end only)
    # sqlite3.complete_statement returns True when statement is complete.
    # We split on ';' and ensure only one non-empty statement exists.
    parts = [p.strip() for p in cleaned.rstrip(";").split(";") if p.strip()]
    if len(parts) != 1:
        raise ValueError("Only a single SELECT statement is allowed (no multiple statements)")

    statement = parts[0]

    # Must start with SELECT or WITH (for CTEs)
    first_word = statement.split()[0].upper() if statement.split() else ""
    if first_word not in ("SELECT", "WITH"):
        raise ValueError(f"Only SELECT/WITH...SELECT statements are allowed, got: {first_word!r}")

    # Forbid write keywords anywhere in the statement
    match = _FORBIDDEN_KEYWORDS.search(statement)
    if match:
        raise ValueError(f"Forbidden keyword in query: {match.group(0)!r}")


class SQLiteConnector(ReadOnlyConnector):
    """Read-only connector for SQLite database files.

    Opens the database using sqlite3 URI mode=ro. Additionally sets
    PRAGMA query_only=ON on every connection as defense-in-depth.

    The query() method enforces SELECT-only access via:
      1. Regex-based statement validation (no INSERT/UPDATE/DELETE/etc.)
      2. Single-statement enforcement (no semicolon-delimited batches)
      3. Read-only connection + PRAGMA query_only=ON (sqlite enforced)

    Google Sheets exploration is NOT supported here. Export to CSV first and
    use CsvConnector, or delegate to MCP Google Drive read tools.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path).resolve()
        if not self._path.exists():
            raise FileNotFoundError(f"SQLite database not found: {self._path}")

    def _open(self) -> sqlite3.Connection:
        """Open a read-only connection. Caller is responsible for closing it."""
        uri = f"file:{self._path.as_posix()}?mode=ro&immutable=1"
        try:
            conn = sqlite3.connect(uri, uri=True)
        except sqlite3.OperationalError:
            # immutable=1 may fail on some platforms; fall back to mode=ro
            uri = f"file:{self._path.as_posix()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
        conn.execute("PRAGMA query_only = ON")
        conn.row_factory = sqlite3.Row
        return conn

    def describe(self) -> dict[str, Any]:
        conn = self._open()
        try:
            row = conn.execute("SELECT sqlite_version()").fetchone()
            version = row[0] if row else "unknown"
        finally:
            conn.close()
        return {
            "kind": "sqlite",
            "path": str(self._path),
            "description": f"SQLite database at {self._path.name}",
            "sqlite_version": version,
            "size_bytes": self._path.stat().st_size,
        }

    def list_containers(self) -> list[str]:
        """Return attached schema names (always includes 'main')."""
        conn = self._open()
        try:
            rows = conn.execute("PRAGMA database_list").fetchall()
        finally:
            conn.close()
        return [row[1] for row in rows]  # column 1 is the schema name

    def list_tables(self, container: str) -> list[str]:
        """Return table and view names in the given schema."""
        schema = container if container != "main" else "main"
        conn = self._open()
        try:
            rows = conn.execute(
                f"SELECT name FROM \"{schema}\".sqlite_master "  # noqa: S608
                "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            ).fetchall()
        finally:
            conn.close()
        return [row[0] for row in rows]

    def get_table_schema(self, container: str, table: str) -> dict[str, Any]:
        """Return column schema for a table, including sample values."""
        schema = container if container != "main" else "main"
        conn = self._open()
        try:
            # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
            info_rows = conn.execute(
                f'PRAGMA "{schema}".table_info("{table}")'
            ).fetchall()

            # Fetch first row for samples
            try:
                sample_row = conn.execute(
                    f'SELECT * FROM "{schema}"."{table}" LIMIT 1'  # noqa: S608
                ).fetchone()
            except sqlite3.Error:
                sample_row = None

            # Estimate row count
            try:
                count_row = conn.execute(
                    f'SELECT COUNT(*) FROM "{schema}"."{table}"'  # noqa: S608
                ).fetchone()
                row_count = count_row[0] if count_row else -1
            except sqlite3.Error:
                row_count = -1
        finally:
            conn.close()

        columns = []
        for info in info_rows:
            col_name = info[1]
            col_type = info[2] or "TEXT"
            sample = None
            if sample_row is not None:
                try:
                    val = sample_row[col_name]
                    sample = str(val) if val is not None else None
                except (IndexError, KeyError):
                    pass
            columns.append({
                "name": col_name,
                "type": col_type,
                "sample": sample,
                "meaning": "",
            })

        return {
            "columns": columns,
            "row_count_estimate": row_count,
        }

    def preview(self, container: str, table: str, limit: int = 5) -> dict[str, Any]:
        """Return up to min(limit, 50) rows from the table."""
        capped = min(max(1, limit), _PREVIEW_ROW_CAP)
        schema = container if container != "main" else "main"

        conn = self._open()
        try:
            rows = conn.execute(
                f'SELECT * FROM "{schema}"."{table}" LIMIT {capped + 1}'  # noqa: S608
            ).fetchall()
        finally:
            conn.close()

        truncated = len(rows) > capped
        data_rows = rows[:capped]
        columns = list(data_rows[0].keys()) if data_rows else []
        return {
            "columns": columns,
            "rows": [dict(row) for row in data_rows],
            "truncated": truncated,
        }

    def query(self, sql: str, limit: int = _QUERY_ROW_CAP) -> dict[str, Any]:
        """Execute a SELECT-only query and return results.

        Parameters
        ----------
        sql:
            A single SELECT or WITH...SELECT statement. Comments are stripped
            before validation. Any other statement type raises ValueError.
        limit:
            Maximum rows to return; capped at 200.

        Returns
        -------
        dict with keys: columns (list[str]), rows (list[dict]), truncated (bool)
        """
        _validate_select_only(sql)
        capped = min(max(1, limit), _QUERY_ROW_CAP)

        conn = self._open()
        try:
            try:
                rows = conn.execute(sql).fetchmany(capped + 1)
            except sqlite3.Error as exc:
                raise ValueError(f"Query failed: {exc}") from exc
        finally:
            conn.close()

        truncated = len(rows) > capped
        data_rows = rows[:capped]
        columns = list(data_rows[0].keys()) if data_rows else []
        return {
            "columns": columns,
            "rows": [dict(row) for row in data_rows],
            "truncated": truncated,
        }
