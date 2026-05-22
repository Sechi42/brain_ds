import sqlite3
import unittest

from brain_ds.store.errors import IncompatibleStoreError, MigrationFailedError
from brain_ds.store.migrations import MIGRATIONS, apply_pending


class TestMigrations(unittest.TestCase):
    def test_fresh_store_reports_version_one(self):
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)

        applied = apply_pending(conn)
        version = conn.execute(
            "SELECT value FROM store_meta WHERE key = 'schema_version'"
        ).fetchone()[0]

        self.assertEqual(applied, [1])
        self.assertEqual(version, "1")

    def test_second_connect_is_noop(self):
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)

        first = apply_pending(conn)
        second = apply_pending(conn)

        self.assertEqual(first, [1])
        self.assertEqual(second, [])

    def test_forward_version_raises_incompatible(self):
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)

        conn.execute("CREATE TABLE store_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute(
            "INSERT INTO store_meta(key, value) VALUES('schema_version', ?)",
            (str(len(MIGRATIONS) + 1),),
        )

        with self.assertRaises(IncompatibleStoreError):
            apply_pending(conn)

    def test_migration_failure_rolls_back(self):
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)

        conn.execute("CREATE TABLE store_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")

        def bad_migration(connection: sqlite3.Connection) -> None:
            connection.execute("CREATE TABLE should_rollback(id INTEGER PRIMARY KEY)")
            raise RuntimeError("boom")

        from brain_ds.store import migrations as migrations_module

        original = migrations_module.MIGRATIONS
        migrations_module.MIGRATIONS = (bad_migration,)
        try:
            with self.assertRaises(MigrationFailedError):
                apply_pending(conn)
        finally:
            migrations_module.MIGRATIONS = original

        table_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='should_rollback'"
        ).fetchone()
        self.assertIsNone(table_exists)


if __name__ == "__main__":
    unittest.main()
