import sqlite3
import unittest

from brain_ds.store.migrations import configure_connection, v1_initial_schema
from brain_ds.store.schema import INDICES, TABLES


class TestSchema(unittest.TestCase):
    def test_v1_creates_all_eight_tables(self):
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)

        v1_initial_schema(conn)
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

        self.assertTrue(set(TABLES).issubset(names))

    def test_v1_creates_all_indices(self):
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)

        v1_initial_schema(conn)
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }

        self.assertTrue(set(INDICES).issubset(names))

    def test_pragmas_set_on_connect(self):
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)

        configure_connection(conn)
        foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        synchronous = conn.execute("PRAGMA synchronous").fetchone()[0]

        self.assertEqual(foreign_keys, 1)
        self.assertEqual(journal_mode.lower(), "memory")
        self.assertEqual(synchronous, 1)


if __name__ == "__main__":
    unittest.main()
