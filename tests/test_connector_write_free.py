"""Security regression guard for the read-only connector capability boundary.

Work-Unit E SECURITY GUARD (E-REQ-SEC-1/2/3):

- E-REQ-SEC-2: ReadOnlyConnector and all concrete implementations expose NO
  write/execute/mutate method in their public surface. The permitted public
  method set is fixed; any additional public method fails this test.
- E-REQ-SEC-3: SELECT-only enforcement in the SQLite query path remains intact;
  representative forbidden keywords (DDL/DML/admin) are rejected, never executed.
- E-REQ-SEC-1: the change-detection path persists the baseline ONLY to the
  brain_ds graph (update_node) — there is no connector write method to invoke,
  which this test proves structurally.

These connectors are already write-free (mode=ro, PRAGMA query_only=ON, no write
methods), so this guard SHOULD pass the first time it runs. A failure means an
unexpected regression — a write path was introduced.
"""

from __future__ import annotations

import inspect
import sqlite3
import tempfile
import unittest
from pathlib import Path

from brain_ds.connectors import CsvConnector, ReadOnlyConnector, SQLiteConnector

# The full permitted public surface of a read-only connector. `query` is the
# SELECT-only path (SQLite). Anything outside this set that is public (no
# leading underscore) must fail the guard.
PERMITTED_PUBLIC_METHODS = frozenset(
    {"describe", "list_containers", "list_tables", "get_table_schema", "preview", "query"}
)

# Tokens that signal a mutation capability. No public method name may contain
# any of these.
FORBIDDEN_NAME_TOKENS = ("write", "execute", "mutate", "insert", "update", "delete", "drop", "create", "alter")


def _public_methods(cls: type) -> set[str]:
    names: set[str] = set()
    for name, member in inspect.getmembers(cls):
        if name.startswith("_"):
            continue
        if callable(member):
            names.add(name)
    return names


class ConnectorWriteFreeTests(unittest.TestCase):
    CONNECTOR_CLASSES = (ReadOnlyConnector, SQLiteConnector, CsvConnector)

    def test_public_surface_is_subset_of_permitted(self) -> None:
        for cls in self.CONNECTOR_CLASSES:
            with self.subTest(connector=cls.__name__):
                public = _public_methods(cls)
                offending = public - PERMITTED_PUBLIC_METHODS
                self.assertEqual(
                    offending,
                    set(),
                    f"{cls.__name__} exposes non-permitted public methods: {sorted(offending)}",
                )

    def test_no_method_name_signals_mutation(self) -> None:
        for cls in self.CONNECTOR_CLASSES:
            for name in _public_methods(cls):
                lowered = name.lower()
                for token in FORBIDDEN_NAME_TOKENS:
                    with self.subTest(connector=cls.__name__, method=name, token=token):
                        self.assertNotIn(
                            token,
                            lowered,
                            f"{cls.__name__}.{name} name signals a mutation capability ({token!r})",
                        )

    def test_base_class_defines_no_write_abstractmethod(self) -> None:
        # The ABC itself must not declare any write/execute abstract method.
        abstract = set(getattr(ReadOnlyConnector, "__abstractmethods__", frozenset()))
        offending = abstract - PERMITTED_PUBLIC_METHODS
        self.assertEqual(offending, set(), f"ReadOnlyConnector declares unexpected abstract methods: {sorted(offending)}")


class SqliteSelectOnlyEnforcementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "src.db"
        conn = sqlite3.connect(self.path)
        try:
            conn.execute("CREATE TABLE foo (id INTEGER, name TEXT)")
            conn.execute("INSERT INTO foo VALUES (1, 'a')")
            conn.commit()
        finally:
            conn.close()
        self.connector = SQLiteConnector(self.path)

    def tearDown(self) -> None:
        try:
            self.temp_dir.cleanup()
        except (PermissionError, OSError):
            pass

    def test_select_is_allowed(self) -> None:
        result = self.connector.query("SELECT * FROM foo")
        self.assertEqual(result["rows"][0]["name"], "a")

    def test_forbidden_keywords_are_rejected(self) -> None:
        # One representative per category: DDL, DML, admin.
        forbidden = [
            "DROP TABLE foo",
            "CREATE TABLE bar (x INTEGER)",
            "ALTER TABLE foo ADD COLUMN x INTEGER",
            "INSERT INTO foo VALUES (2, 'b')",
            "UPDATE foo SET name = 'z'",
            "DELETE FROM foo",
            "ATTACH DATABASE 'x.db' AS x",
            "DETACH DATABASE x",
            "PRAGMA writable_schema = ON",
        ]
        for stmt in forbidden:
            with self.subTest(statement=stmt):
                with self.assertRaises(ValueError):
                    self.connector.query(stmt)

    def test_forbidden_statement_does_not_mutate_source(self) -> None:
        # The row count must be unchanged after a rejected DROP/INSERT attempt.
        before = self.connector.query("SELECT COUNT(*) AS n FROM foo")["rows"][0]["n"]
        with self.assertRaises(ValueError):
            self.connector.query("INSERT INTO foo VALUES (99, 'x')")
        after = self.connector.query("SELECT COUNT(*) AS n FROM foo")["rows"][0]["n"]
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
