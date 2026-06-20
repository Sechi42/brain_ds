"""Read-only PostgreSQL connector.

Connects via psycopg v3 (``pip install brain_ds[postgres]``). Enforces
read-only access through three layers of defense in depth:

1. ``conn.read_only = True`` — psycopg v3 connection attribute
2. ``SET default_transaction_read_only = on`` — session-level Postgres guard
3. ``SET statement_timeout = '10s'`` — prevents runaway queries
4. ``_validate_select_only(sql)`` — reuse from sqlite_connector for the
   query() SELECT-only guard (same regex, same semantics)

Row caps (matching sqlite_connector):
  - query() cap:   200 rows (``_QUERY_ROW_CAP`` from sqlite_connector)
  - preview() cap: 50 rows

Path sandbox: not applicable for Postgres (no file path). Credentials
are held in-memory only and never written to logs or responses (INV-1).
``describe()`` deliberately excludes ``password`` from its output.

list_containers() returns user schemas only (excludes ``pg_*`` and
``information_schema``).
"""
from __future__ import annotations

from typing import Any

from brain_ds.connectors.sqlite_connector import (
    _QUERY_ROW_CAP,
    _PREVIEW_ROW_CAP,
    _validate_select_only,
)

from .base import ReadOnlyConnector

# Install hint raised when psycopg is not installed.
_PSYCOPG_HINT = (
    "psycopg is not installed. "
    "Run `pip install brain_ds[postgres]` to enable Postgres exploration."
)


def _lazy_psycopg():
    """Import psycopg lazily; raise ImportError with install hint if absent."""
    try:
        import psycopg  # type: ignore[import-untyped]
        return psycopg
    except ImportError as exc:
        raise ImportError(_PSYCOPG_HINT) from exc


# Schemas to exclude from list_containers()
_SYSTEM_SCHEMA_PREFIXES = ("pg_",)
_SYSTEM_SCHEMA_NAMES = frozenset({"information_schema"})


def _is_user_schema(schema_name: str) -> bool:
    """Return True if the schema is a user-visible (non-system) schema."""
    if schema_name in _SYSTEM_SCHEMA_NAMES:
        return False
    for prefix in _SYSTEM_SCHEMA_PREFIXES:
        if schema_name.startswith(prefix):
            return False
    return True


class PostgresConnector(ReadOnlyConnector):
    """Read-only connector for PostgreSQL databases.

    Implements the ``ReadOnlyConnector`` ABC plus a ``query()`` method that
    mirrors ``SQLiteConnector.query()`` for use by ``query_source`` in
    ``brain_ds/mcp/tools.py``.

    Connection params dict (all keys required unless noted):
      - host     : database host
      - port     : database port (int)
      - username : login user
      - password : login password (never logged or returned)
      - database : database name (always from handle metadata — INV-2)
      - sslmode  : e.g. ``"require"`` or ``"disable"``
    """

    def __init__(self, params: dict[str, Any]) -> None:
        self._params = params

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _open(self):
        """Open a read-only psycopg v3 connection.

        Caller is responsible for closing the connection (or using it as a
        context manager).

        Read-only enforcement (defense in depth):
          1. ``conn.read_only = True``
          2. ``SET default_transaction_read_only = on``
          3. ``SET statement_timeout = '10s'``
        """
        psycopg = _lazy_psycopg()

        p = self._params
        conn = psycopg.connect(
            host=p.get("host", "localhost"),
            port=int(p.get("port", 5432)),
            user=p.get("username", ""),
            password=p.get("password", ""),
            dbname=p.get("database", ""),
            sslmode=p.get("sslmode", "require"),
            autocommit=False,
        )
        # Layer 1: psycopg v3 read-only attribute
        conn.read_only = True
        # Layer 2 + 3: session-level Postgres settings
        conn.execute("SET default_transaction_read_only = on")
        conn.execute("SET statement_timeout = '10s'")
        return conn

    # ------------------------------------------------------------------
    # ReadOnlyConnector ABC
    # ------------------------------------------------------------------

    def describe(self) -> dict[str, Any]:
        """Return source-level metadata. Never includes credentials."""
        conn = self._open()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT version()")
                row = cur.fetchone()
                pg_version = row[0] if row else "unknown"
        finally:
            conn.close()

        return {
            "kind": "postgres",
            "host": self._params.get("host", ""),
            "port": self._params.get("port", 5432),
            "database": self._params.get("database", ""),
            "pg_version": pg_version,
            "description": (
                f"PostgreSQL database '{self._params.get('database', '')}' "
                f"at {self._params.get('host', '')}:{self._params.get('port', 5432)}"
            ),
            # INV-1: password is deliberately absent
        }

    def list_containers(self) -> list[str]:
        """Return user-visible schema names (excludes pg_* and information_schema)."""
        conn = self._open()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT schema_name FROM information_schema.schemata "
                    "ORDER BY schema_name"
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        return [row[0] for row in rows if _is_user_schema(row[0])]

    def list_tables(self, container: str) -> list[str]:
        """Return table and view names in the given schema."""
        conn = self._open()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = %s "
                    "AND table_type IN ('BASE TABLE', 'VIEW') "
                    "ORDER BY table_name",
                    (container,),
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        return [row[0] for row in rows]

    def get_table_schema(self, container: str, table: str) -> dict[str, Any]:
        """Return column schema + row count estimate for a table or view.

        Row count comes from ``pg_class.reltuples`` (statistical estimate;
        may be -1 for very new tables).
        """
        conn = self._open()
        try:
            with conn.cursor() as cur:
                # Column info
                cur.execute(
                    "SELECT column_name, data_type "
                    "FROM information_schema.columns "
                    "WHERE table_schema = %s AND table_name = %s "
                    "ORDER BY ordinal_position",
                    (container, table),
                )
                col_rows = cur.fetchall()

            # Row count estimate from pg_class (cheaper than COUNT(*))
            with conn.cursor() as cur2:
                cur2.execute(
                    "SELECT reltuples::bigint FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE c.relname = %s AND n.nspname = %s",
                    (table, container),
                )
                est_row = cur2.fetchone()
                row_count_estimate = int(est_row[0]) if est_row else -1

            # Sample first row for each column
            sample_map: dict[str, str | None] = {}
            try:
                with conn.cursor() as cur3:
                    cur3.execute(
                        f'SELECT * FROM "{container}"."{table}" LIMIT 1'  # noqa: S608
                    )
                    sample_row = cur3.fetchone()
                    if sample_row and col_rows:
                        for i, (col_name, _) in enumerate(col_rows):
                            val = sample_row[i] if i < len(sample_row) else None
                            sample_map[col_name] = str(val) if val is not None else None
            except Exception:
                pass
        finally:
            conn.close()

        columns = [
            {
                "name": col_name,
                "type": data_type or "text",
                "sample": sample_map.get(col_name),
                "meaning": "",
            }
            for col_name, data_type in col_rows
        ]

        return {
            "columns": columns,
            "row_count_estimate": row_count_estimate,
        }

    def preview(self, container: str, table: str, limit: int = 5) -> dict[str, Any]:
        """Return up to min(limit, 50) rows from the table."""
        capped = min(max(1, limit), _PREVIEW_ROW_CAP)

        conn = self._open()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f'SELECT * FROM "{container}"."{table}" LIMIT %s',  # noqa: S608
                    (capped + 1,),
                )
                col_names = [desc[0] for desc in cur.description] if cur.description else []
                rows = cur.fetchall()
        finally:
            conn.close()

        truncated = len(rows) > capped
        data_rows = rows[:capped]
        return {
            "columns": col_names,
            "rows": [dict(zip(col_names, row)) for row in data_rows],
            "truncated": truncated,
        }

    # ------------------------------------------------------------------
    # query() — SELECT-only, 200-row cap (mirrors SQLiteConnector.query)
    # ------------------------------------------------------------------

    def query(self, sql: str, limit: int = _QUERY_ROW_CAP) -> dict[str, Any]:
        """Execute a SELECT-only query and return results.

        Parameters
        ----------
        sql:
            A single SELECT or WITH...SELECT statement. Any other statement
            type raises ValueError (same guard as SQLiteConnector).
        limit:
            Maximum rows to return; silently capped at 200.

        Returns
        -------
        dict with keys: columns (list[str]), rows (list[dict]), truncated (bool)
        """
        _validate_select_only(sql)
        capped = min(max(1, limit), _QUERY_ROW_CAP)

        conn = self._open()
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                col_names = [desc[0] for desc in cur.description] if cur.description else []
                rows = cur.fetchmany(capped + 1)
        except ValueError:
            conn.close()
            raise
        except Exception as exc:
            conn.close()
            raise ValueError(f"Query failed: {exc}") from exc
        finally:
            try:
                conn.close()
            except Exception:
                pass

        truncated = len(rows) > capped
        data_rows = rows[:capped]
        return {
            "columns": col_names,
            "rows": [dict(zip(col_names, row)) for row in data_rows],
            "truncated": truncated,
        }
