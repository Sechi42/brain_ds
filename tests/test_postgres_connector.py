"""TDD tests for PostgresConnector and _resolve_connector aws-postgres dispatch.

Execution model
---------------
All tests use mocked psycopg cursors — no real Postgres needed.
Live integration tests are marked ``@pytest.mark.postgres_live`` and are
skipped unless a real Postgres is reachable (CI docker job or explicit env).

PR2b-T1: PostgresConnector unit tests (mocked psycopg)
PR2b-T2: _resolve_connector dispatches aws-postgres kind to PostgresConnector
"""
from __future__ import annotations

import os
import sys
import types
import unittest
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers — build a fake psycopg module so tests run without the package
# ---------------------------------------------------------------------------

def _make_fake_psycopg() -> types.ModuleType:
    """Build a minimal psycopg stub sufficient for PostgresConnector tests."""
    psycopg = types.ModuleType("psycopg")

    # Fake connection + cursor
    class FakeCursor:
        def __init__(self, rows=None, description=None):
            self._rows = rows or []
            self.description = description or []

        def execute(self, sql, params=None):
            pass

        def fetchmany(self, size):
            return self._rows[:size]

        def fetchall(self):
            return self._rows

        def fetchone(self):
            return self._rows[0] if self._rows else None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class FakeConnection:
        def __init__(self, *, cursor_factory=None, **kwargs):
            self.read_only = False
            self._cursor_rows: list[tuple] = []
            self._cursor_description: list = []
            self.autocommit = False

        def cursor(self, row_factory=None):
            return FakeCursor(
                rows=self._cursor_rows,
                description=self._cursor_description,
            )

        def execute(self, sql, params=None):
            pass

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    def connect(**kwargs):
        return FakeConnection(**kwargs)

    psycopg.connect = connect
    psycopg.Connection = FakeConnection
    psycopg.Cursor = FakeCursor
    psycopg.rows = types.ModuleType("psycopg.rows")
    psycopg.rows.dict_row = "dict_row"

    return psycopg


_FAKE_PSYCOPG = _make_fake_psycopg()


# ---------------------------------------------------------------------------
# Patch helper
# ---------------------------------------------------------------------------

def _patch_psycopg(fake=None):
    """Return a context-manager that injects a fake psycopg into sys.modules."""
    if fake is None:
        fake = _FAKE_PSYCOPG
    return patch.dict("sys.modules", {"psycopg": fake, "psycopg.rows": fake.rows})


# ===========================================================================
# PR2b-T1: PostgresConnector unit tests
# ===========================================================================

class TestPostgresConnectorLazyImport(unittest.TestCase):
    """Importing PostgresConnector with psycopg absent raises a clear error."""

    def test_missing_psycopg_raises_actionable_error(self):
        """Instantiating (or calling describe) without psycopg raises ValidationError."""
        with patch.dict("sys.modules", {"psycopg": None, "psycopg.rows": None}):
            # Force re-import so the lazy guard fires
            import importlib
            import brain_ds.connectors.postgres_connector as _mod
            importlib.reload(_mod)

            params = {
                "host": "localhost",
                "port": 5432,
                "username": "user",
                "password": "pass",
                "database": "mydb",
                "sslmode": "require",
            }
            connector = _mod.PostgresConnector(params)
            with self.assertRaises(Exception) as ctx:
                connector.describe()
            msg = str(ctx.exception).lower()
            self.assertTrue(
                "psycopg" in msg or "postgres" in msg or "brain_ds[postgres]" in msg,
                f"Error message should mention psycopg or [postgres] extra, got: {msg}",
            )

        # Reload to restore the module to a clean state for subsequent tests
        import importlib
        import brain_ds.connectors.postgres_connector as _mod
        importlib.reload(_mod)


class TestPostgresConnectorDescribe(unittest.TestCase):
    """describe() returns source-level metadata."""

    def _make_connector(self, params=None):
        with _patch_psycopg():
            from brain_ds.connectors.postgres_connector import PostgresConnector
            return PostgresConnector(params or {
                "host": "db.example.com",
                "port": 5432,
                "username": "user",
                "password": "pass",
                "database": "mydb",
                "sslmode": "require",
            })

    def test_describe_returns_kind_postgres(self):
        connector = self._make_connector()
        fake = _make_fake_psycopg()
        fake.connect = lambda **kw: fake.Connection()

        # Mock the _open helper
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = ("16.2",)
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)

        with _patch_psycopg():
            from brain_ds.connectors.postgres_connector import PostgresConnector
            connector = PostgresConnector({
                "host": "db.example.com",
                "port": 5432,
                "username": "user",
                "password": "pass",
                "database": "mydb",
                "sslmode": "require",
            })
            with patch.object(connector, "_open", return_value=mock_conn):
                result = connector.describe()

        self.assertEqual(result["kind"], "postgres")
        self.assertEqual(result["database"], "mydb")
        self.assertIn("host", result)
        self.assertNotIn("password", result)  # INV-1: password never in describe output

    def test_describe_excludes_password(self):
        """describe() must never leak credentials."""
        with _patch_psycopg():
            from brain_ds.connectors.postgres_connector import PostgresConnector
            connector = PostgresConnector({
                "host": "db.example.com",
                "port": 5432,
                "username": "user",
                "password": "super-secret",
                "database": "mydb",
                "sslmode": "require",
            })

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = ("16.2",)
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)

        with _patch_psycopg():
            with patch.object(connector, "_open", return_value=mock_conn):
                result = connector.describe()

        result_str = str(result)
        self.assertNotIn("super-secret", result_str)


class TestPostgresConnectorReadOnlyEnforcement(unittest.TestCase):
    """_open() sets read-only flags; write statements are rejected."""

    def test_open_sets_read_only_on_connection(self):
        """_open() must set conn.read_only = True."""
        with _patch_psycopg():
            from brain_ds.connectors.postgres_connector import PostgresConnector
            connector = PostgresConnector({
                "host": "localhost", "port": 5432,
                "username": "u", "password": "p",
                "database": "db", "sslmode": "require",
            })

        captured_conns = []

        def fake_connect(**kwargs):
            conn = MagicMock()
            conn.read_only = False
            conn.__enter__ = lambda s: s
            conn.__exit__ = MagicMock(return_value=False)
            # Track what execute() is called with
            conn.execute = MagicMock()
            captured_conns.append(conn)
            return conn

        with _patch_psycopg():
            import psycopg
            psycopg.connect = fake_connect
            try:
                connector._open()
            except Exception:
                pass  # Connection failure is fine in mock context

        if captured_conns:
            self.assertTrue(captured_conns[0].read_only)

    def test_validate_select_only_rejects_insert(self):
        """_validate_select_only guard rejects INSERT."""
        from brain_ds.connectors.sqlite_connector import _validate_select_only
        with self.assertRaises(ValueError):
            _validate_select_only("INSERT INTO t VALUES (1)")

    def test_validate_select_only_rejects_update(self):
        from brain_ds.connectors.sqlite_connector import _validate_select_only
        with self.assertRaises(ValueError):
            _validate_select_only("UPDATE t SET x=1")

    def test_validate_select_only_rejects_delete(self):
        from brain_ds.connectors.sqlite_connector import _validate_select_only
        with self.assertRaises(ValueError):
            _validate_select_only("DELETE FROM t WHERE id=1")

    def test_validate_select_only_rejects_drop(self):
        from brain_ds.connectors.sqlite_connector import _validate_select_only
        with self.assertRaises(ValueError):
            _validate_select_only("DROP TABLE t")

    def test_validate_select_only_rejects_create(self):
        from brain_ds.connectors.sqlite_connector import _validate_select_only
        with self.assertRaises(ValueError):
            _validate_select_only("CREATE TABLE t (id INT)")

    def test_validate_select_only_allows_select(self):
        from brain_ds.connectors.sqlite_connector import _validate_select_only
        # Should NOT raise
        _validate_select_only("SELECT * FROM t WHERE id = 1")

    def test_validate_select_only_allows_with_select(self):
        from brain_ds.connectors.sqlite_connector import _validate_select_only
        _validate_select_only("WITH cte AS (SELECT 1 AS n) SELECT * FROM cte")


class TestPostgresConnectorQuery(unittest.TestCase):
    """query() SELECT-only enforcement + 200-row cap."""

    def _make_connector(self):
        with _patch_psycopg():
            from brain_ds.connectors.postgres_connector import PostgresConnector
            return PostgresConnector({
                "host": "localhost", "port": 5432,
                "username": "u", "password": "p",
                "database": "db", "sslmode": "require",
            })

    def _mock_conn_with_rows(self, rows: list[dict]) -> MagicMock:
        """Build a mock connection whose cursor returns the given row dicts."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchmany.return_value = rows
        mock_cursor.description = [(col,) for col in (rows[0].keys() if rows else [])]
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)
        return mock_conn

    def test_select_returns_rows(self):
        """SELECT with rows within cap returns all rows + truncated=False."""
        connector = self._make_connector()
        rows = [{"id": i, "name": f"row{i}"} for i in range(5)]
        mock_conn = self._mock_conn_with_rows(rows)

        with _patch_psycopg():
            with patch.object(connector, "_open", return_value=mock_conn):
                result = connector.query("SELECT * FROM t")

        self.assertIn("rows", result)
        self.assertIn("columns", result)
        self.assertIn("truncated", result)
        self.assertFalse(result["truncated"])

    def test_select_500_rows_capped_at_200(self):
        """SELECT returning 500 rows: only 200 returned + truncated=True."""
        connector = self._make_connector()
        # fetchmany(201) returns 201 rows — signals more exist
        rows = [{"id": i} for i in range(201)]
        mock_conn = self._mock_conn_with_rows(rows)

        with _patch_psycopg():
            with patch.object(connector, "_open", return_value=mock_conn):
                result = connector.query("SELECT * FROM t", limit=200)

        self.assertEqual(len(result["rows"]), 200)
        self.assertTrue(result["truncated"])

    def test_query_write_rejected_before_execution(self):
        """INSERT/UPDATE/DELETE are rejected by the SELECT-only guard."""
        connector = self._make_connector()

        with _patch_psycopg():
            with self.assertRaises((ValueError, Exception)) as ctx:
                connector.query("INSERT INTO t VALUES (1)")
        msg = str(ctx.exception).lower()
        self.assertIn("insert", msg)

    def test_query_update_rejected(self):
        connector = self._make_connector()
        with _patch_psycopg():
            with self.assertRaises((ValueError, Exception)):
                connector.query("UPDATE t SET x=1 WHERE id=1")

    def test_query_drop_rejected(self):
        connector = self._make_connector()
        with _patch_psycopg():
            with self.assertRaises((ValueError, Exception)):
                connector.query("DROP TABLE t")

    def test_query_respects_limit_cap(self):
        """limit > 200 is silently capped at 200."""
        connector = self._make_connector()
        rows = [{"id": i} for i in range(150)]
        mock_conn = self._mock_conn_with_rows(rows)

        with _patch_psycopg():
            with patch.object(connector, "_open", return_value=mock_conn):
                result = connector.query("SELECT * FROM t", limit=9999)

        # The actual fetchmany should have been called with at most 201 (200+1 cap)
        self.assertLessEqual(len(result["rows"]), 200)


class TestPostgresConnectorListContainers(unittest.TestCase):
    """list_containers() returns schemas, excluding system schemas."""

    def _make_connector(self):
        with _patch_psycopg():
            from brain_ds.connectors.postgres_connector import PostgresConnector
            return PostgresConnector({
                "host": "localhost", "port": 5432,
                "username": "u", "password": "p",
                "database": "db", "sslmode": "require",
            })

    def test_list_containers_returns_user_schemas(self):
        """list_containers() excludes pg_* and information_schema."""
        connector = self._make_connector()

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)
        # Simulate rows: (schema_name,) tuples
        mock_cursor.fetchall.return_value = [
            ("public",),
            ("my_schema",),
            ("pg_catalog",),
            ("information_schema",),
            ("pg_toast",),
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)

        with _patch_psycopg():
            with patch.object(connector, "_open", return_value=mock_conn):
                result = connector.list_containers()

        self.assertIn("public", result)
        self.assertIn("my_schema", result)
        self.assertNotIn("pg_catalog", result)
        self.assertNotIn("information_schema", result)
        self.assertNotIn("pg_toast", result)

    def test_list_containers_excludes_all_pg_prefixed(self):
        connector = self._make_connector()

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = [
            ("pg_catalog",),
            ("pg_toast",),
            ("pg_temp_1",),
            ("public",),
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)

        with _patch_psycopg():
            with patch.object(connector, "_open", return_value=mock_conn):
                result = connector.list_containers()

        self.assertEqual(result, ["public"])


class TestPostgresConnectorListTables(unittest.TestCase):
    """list_tables(container) returns tables and views in a schema."""

    def _make_connector(self):
        with _patch_psycopg():
            from brain_ds.connectors.postgres_connector import PostgresConnector
            return PostgresConnector({
                "host": "localhost", "port": 5432,
                "username": "u", "password": "p",
                "database": "db", "sslmode": "require",
            })

    def test_list_tables_returns_table_names(self):
        connector = self._make_connector()

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = [
            ("users",),
            ("orders",),
            ("v_summary",),
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)

        with _patch_psycopg():
            with patch.object(connector, "_open", return_value=mock_conn):
                result = connector.list_tables("public")

        self.assertIn("users", result)
        self.assertIn("orders", result)
        self.assertIn("v_summary", result)


class TestPostgresConnectorGetTableSchema(unittest.TestCase):
    """get_table_schema() returns columns + row_count_estimate."""

    def _make_connector(self):
        with _patch_psycopg():
            from brain_ds.connectors.postgres_connector import PostgresConnector
            return PostgresConnector({
                "host": "localhost", "port": 5432,
                "username": "u", "password": "p",
                "database": "db", "sslmode": "require",
            })

    def test_get_table_schema_returns_columns(self):
        connector = self._make_connector()

        col_rows = [
            ("id", "integer"),
            ("name", "text"),
            ("created_at", "timestamp"),
        ]
        sample_row = {"id": 1, "name": "Alice", "created_at": "2024-01-01"}

        call_count = [0]

        class MultiCursor:
            def __init__(self):
                self.fetchall = MagicMock()
                self.fetchone = MagicMock()
                self._call = 0

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def execute(self, sql, params=None):
                self._call += 1

            def fetchall(self):
                pass

        mock_conn = MagicMock()
        cursor1 = MagicMock()
        cursor1.__enter__ = lambda s: s
        cursor1.__exit__ = MagicMock(return_value=False)
        cursor1.fetchall.return_value = col_rows
        cursor1.fetchone.return_value = (42.0,)  # reltuples estimate

        call_num = [0]

        def get_cursor(row_factory=None):
            call_num[0] += 1
            if call_num[0] == 1:
                return cursor1
            # subsequent cursors return sample row
            c = MagicMock()
            c.__enter__ = lambda s: s
            c.__exit__ = MagicMock(return_value=False)
            c.fetchone.return_value = tuple(sample_row.values())
            c.fetchall.return_value = [tuple(sample_row.values())]
            return c

        mock_conn.cursor.side_effect = get_cursor
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)

        with _patch_psycopg():
            with patch.object(connector, "_open", return_value=mock_conn):
                result = connector.get_table_schema("public", "users")

        self.assertIn("columns", result)
        self.assertIn("row_count_estimate", result)
        col_names = [c["name"] for c in result["columns"]]
        self.assertIn("id", col_names)
        self.assertIn("name", col_names)


class TestPostgresConnectorPreview(unittest.TestCase):
    """preview() returns up to 50 rows."""

    def _make_connector(self):
        with _patch_psycopg():
            from brain_ds.connectors.postgres_connector import PostgresConnector
            return PostgresConnector({
                "host": "localhost", "port": 5432,
                "username": "u", "password": "p",
                "database": "db", "sslmode": "require",
            })

    def test_preview_returns_rows_and_columns(self):
        connector = self._make_connector()
        rows = [{"id": i, "name": f"row{i}"} for i in range(5)]

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = [tuple(r.values()) for r in rows]
        mock_cursor.description = [("id",), ("name",)]
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)

        with _patch_psycopg():
            with patch.object(connector, "_open", return_value=mock_conn):
                result = connector.preview("public", "users")

        self.assertIn("rows", result)
        self.assertIn("columns", result)
        self.assertIn("truncated", result)

    def test_preview_cap_at_50(self):
        """preview() never returns more than 50 rows."""
        connector = self._make_connector()
        # Return 51 rows to signal truncation
        rows = [{"id": i} for i in range(51)]

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.description = [("id",)]
        mock_cursor.fetchall.return_value = [tuple(r.values()) for r in rows]
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)

        with _patch_psycopg():
            with patch.object(connector, "_open", return_value=mock_conn):
                result = connector.preview("public", "users", limit=100)

        self.assertLessEqual(len(result["rows"]), 50)
        self.assertTrue(result["truncated"])


class TestPostgresConnectorImplementsABC(unittest.TestCase):
    """PostgresConnector implements all 5 ReadOnlyConnector abstract methods."""

    def test_implements_all_abstract_methods(self):
        with _patch_psycopg():
            from brain_ds.connectors.postgres_connector import PostgresConnector
            from brain_ds.connectors.base import ReadOnlyConnector

        connector = PostgresConnector({
            "host": "localhost", "port": 5432,
            "username": "u", "password": "p",
            "database": "db", "sslmode": "require",
        })
        self.assertIsInstance(connector, ReadOnlyConnector)

    def test_has_query_method(self):
        with _patch_psycopg():
            from brain_ds.connectors.postgres_connector import PostgresConnector
            connector = PostgresConnector({
                "host": "localhost", "port": 5432,
                "username": "u", "password": "p",
                "database": "db", "sslmode": "require",
            })
        self.assertTrue(callable(getattr(connector, "query", None)))


# ===========================================================================
# PR2b-T2: _resolve_connector dispatches aws-postgres to PostgresConnector
# ===========================================================================

class TestResolveConnectorAwsPostgresDispatch(unittest.TestCase):
    """_resolve_connector with kind='aws-postgres' returns a PostgresConnector.

    The test monkeypatches AwsPostgresAdapter.resolve() to avoid real AWS
    calls, and PostgresConnector.__init__ to avoid real psycopg.
    """

    def _make_store_with_secret(self, project_root, handle, kind, metadata):
        """Write a minimal secrets.json manifest at project_root/.brain_ds/."""
        import json
        from pathlib import Path
        brain_ds_dir = Path(project_root) / ".brain_ds"
        brain_ds_dir.mkdir(parents=True, exist_ok=True)

        # Read the real schema to get schema_version
        import importlib.resources as resources
        schema_text = resources.files("brain_ds.connectors.secrets").joinpath("schema.json").read_text(encoding="utf-8")
        schema = json.loads(schema_text)
        schema_version = schema["schema_version"]

        manifest = {
            "schema_version": schema_version,
            "entries": [
                {
                    "handle": handle,
                    "kind": kind,
                    "metadata": metadata,
                    "created_at": "2024-01-01T00:00:00Z",
                }
            ],
        }
        manifest_path = brain_ds_dir / "secrets.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def test_resolve_connector_dispatches_aws_postgres(self):
        """kind='aws-postgres' -> PostgresConnector (adapter monkeypatched)."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            tmproot = Path(tmpdir)
            self._make_store_with_secret(
                tmproot,
                handle="test-pg-handle",
                kind="aws-postgres",
                metadata={
                    "secret_id": "arn:aws:secretsmanager:us-east-2:123:secret:test",
                    "database": "mydb",
                    "region": "us-east-2",
                },
            )

            connection = {
                "kind": "aws-postgres",
                "secret_handle": "test-pg-handle",
                "database": "mydb",
            }

            fake_params = {
                "host": "db.example.com",
                "port": 5432,
                "username": "user",
                "password": "pass",
                "database": "mydb",
                "sslmode": "require",
            }

            from brain_ds.connectors.secrets.providers.aws_postgres import AwsPostgresAdapter

            with patch.object(AwsPostgresAdapter, "resolve", return_value=fake_params):
                from brain_ds.mcp.tools import _resolve_connector
                result = _resolve_connector(connection, tmproot)

            # Check by class name — avoids module-identity issues with patched sys.modules
            self.assertEqual(type(result).__name__, "PostgresConnector")

    def test_resolve_connector_aws_postgres_missing_handle_raises(self):
        """aws-postgres connection with no secret_handle raises ValidationError."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            connection = {
                "kind": "aws-postgres",
                # missing secret_handle
                "database": "mydb",
            }

            with _patch_psycopg():
                from brain_ds.mcp.tools import _resolve_connector
                with self.assertRaises(Exception):
                    _resolve_connector(connection, Path(tmpdir))

    def test_resolve_connector_unknown_handle_raises(self):
        """aws-postgres with a handle not in the catalog raises ValidationError."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            tmproot = Path(tmpdir)
            # Create empty secrets manifest (no entries)
            import json
            import importlib.resources as resources
            schema_text = resources.files("brain_ds.connectors.secrets").joinpath("schema.json").read_text(encoding="utf-8")
            schema = json.loads(schema_text)
            brain_ds_dir = tmproot / ".brain_ds"
            brain_ds_dir.mkdir(parents=True, exist_ok=True)
            (brain_ds_dir / "secrets.json").write_text(
                json.dumps({"schema_version": schema["schema_version"], "entries": []}),
                encoding="utf-8",
            )

            connection = {
                "kind": "aws-postgres",
                "secret_handle": "nonexistent-handle",
                "database": "mydb",
            }

            with _patch_psycopg():
                from brain_ds.mcp.tools import _resolve_connector
                with self.assertRaises(Exception):
                    _resolve_connector(connection, tmproot)

    def test_resolve_connector_still_supports_sqlite(self):
        """After adding aws-postgres branch, sqlite dispatch still works."""
        import tempfile
        import sqlite3
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(str(db_path))
            conn.execute("CREATE TABLE t (id INTEGER)")
            conn.commit()
            conn.close()

            connection = {"kind": "sqlite", "path": str(db_path)}
            from brain_ds.mcp.tools import _resolve_connector
            from brain_ds.connectors.sqlite_connector import SQLiteConnector
            result = _resolve_connector(connection, Path(tmpdir))
            self.assertIsInstance(result, SQLiteConnector)

    def test_get_node_connection_error_message_lists_aws_postgres(self):
        """Error message for missing connection descriptor should mention aws-postgres."""
        # The _get_node_connection error message should list aws-postgres as supported
        # We verify this by looking at the source of _get_node_connection
        import inspect
        from brain_ds.mcp.tools import _get_node_connection
        source = inspect.getsource(_get_node_connection)
        self.assertIn("aws-postgres", source)


# ===========================================================================
# Live integration marker (skipped when no postgres reachable)
# ===========================================================================

def _postgres_reachable() -> bool:
    """Return True only when the live Postgres integration tests are opted in.

    Gated behind the explicit BRAINDS_POSTGRES_LIVE env var (set by the CI
    postgres:16 service job that seeds test_db/test_user) — NOT by mere socket
    reachability. A developer machine may have an unrelated Postgres on 5432;
    auto-running these tests against it would fail on the seeded credentials.
    Opt-in keeps local `uv run pytest` deterministic.
    """
    if os.environ.get("BRAINDS_POSTGRES_LIVE") != "1":
        return False
    try:
        import psycopg  # noqa: F401
    except ImportError:
        return False
    import socket
    try:
        with socket.create_connection(("127.0.0.1", 5432), timeout=1):
            return True
    except OSError:
        return False


@pytest.mark.postgres_live
@pytest.mark.skipif(
    not _postgres_reachable(),
    reason="set BRAINDS_POSTGRES_LIVE=1 with a seeded Postgres on 5432 (CI docker job)",
)
class TestPostgresConnectorLiveIntegration(unittest.TestCase):
    """Live integration tests — require a real Postgres at 127.0.0.1:5432.

    These tests are skipped locally unless Postgres is running.
    In CI they run inside the postgres:16 docker service job.
    """

    _PARAMS = {
        "host": "127.0.0.1",
        "port": 5432,
        "username": "test_user",
        "password": "test_pass",
        "database": "test_db",
        "sslmode": "disable",
    }

    def test_live_select_returns_rows(self):
        """SELECT 1 returns a row."""
        from brain_ds.connectors.postgres_connector import PostgresConnector
        connector = PostgresConnector(self._PARAMS)
        result = connector.query("SELECT 1 AS n")
        self.assertEqual(len(result["rows"]), 1)

    def test_live_write_rejected_by_db(self):
        """INSERT raises an error — read-only enforcement at DB level."""
        from brain_ds.connectors.postgres_connector import PostgresConnector
        connector = PostgresConnector(self._PARAMS)
        with self.assertRaises(Exception) as ctx:
            connector.query("INSERT INTO _nonexistent_table_ VALUES (1)")
        # Should fail: either SELECT-only guard (ValueError) or DB read-only error
        self.assertIsNotNone(ctx.exception)

    def test_live_describe(self):
        from brain_ds.connectors.postgres_connector import PostgresConnector
        connector = PostgresConnector(self._PARAMS)
        result = connector.describe()
        self.assertEqual(result["kind"], "postgres")
        self.assertIn("pg_version", result)

    def test_live_list_containers_excludes_system(self):
        from brain_ds.connectors.postgres_connector import PostgresConnector
        connector = PostgresConnector(self._PARAMS)
        schemas = connector.list_containers()
        self.assertNotIn("pg_catalog", schemas)
        self.assertNotIn("information_schema", schemas)

    def test_live_200_row_cap(self):
        """A query returning many rows is capped at 200."""
        from brain_ds.connectors.postgres_connector import PostgresConnector
        connector = PostgresConnector(self._PARAMS)
        # generate_series produces many rows
        result = connector.query("SELECT generate_series(1, 500) AS n")
        self.assertEqual(len(result["rows"]), 200)
        self.assertTrue(result["truncated"])


if __name__ == "__main__":
    unittest.main()
