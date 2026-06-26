import sqlite3
import unittest

from brain_ds.store.errors import IncompatibleStoreError, MigrationFailedError
from brain_ds.store.migrations import MIGRATIONS, apply_pending
from brain_ds.store.schema import DDL_SCRIPT


class TestMigrations(unittest.TestCase):
    def test_fresh_store_reports_version_one(self):
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)

        applied = apply_pending(conn)
        version = conn.execute(
            "SELECT value FROM store_meta WHERE key = 'schema_version'"
        ).fetchone()[0]

        self.assertEqual(applied, list(range(1, len(MIGRATIONS) + 1)))
        self.assertEqual(version, str(len(MIGRATIONS)))

    def test_second_connect_is_noop(self):
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)

        first = apply_pending(conn)
        second = apply_pending(conn)

        self.assertEqual(first, list(range(1, len(MIGRATIONS) + 1)))
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

    def test_v3_migration_from_v2(self):
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)

        from brain_ds.store import migrations as migrations_module

        original = migrations_module.MIGRATIONS

        def legacy_v1_without_outbox(connection: sqlite3.Connection) -> None:
            connection.executescript(
                DDL_SCRIPT.split("CREATE TABLE IF NOT EXISTS event_outbox", 1)[0]
            )

        try:
            migrations_module.MIGRATIONS = (legacy_v1_without_outbox, original[1])
            first = apply_pending(conn)
            self.assertEqual(first, [1, 2])

            before = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='event_outbox'"
            ).fetchone()
            self.assertIsNone(before)

            migrations_module.MIGRATIONS = original
            second = apply_pending(conn)
            # v3 (event_outbox), v4 (nodes_fts), v5 (graphs.hidden),
            # v6 (confidence_ledger), v7 (node_fact_descriptors),
            # v8 (pending_questions) are applied
            self.assertEqual(second, [3, 4, 5, 6, 7, 8])
        finally:
            migrations_module.MIGRATIONS = original

        columns = conn.execute("PRAGMA table_info(event_outbox)").fetchall()
        column_names = {row[1] for row in columns}
        self.assertEqual(
            column_names,
            {"id", "event", "graph_id", "payload", "created_at", "published"},
        )

        nodes_fts = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='nodes_fts'"
        ).fetchone()
        self.assertIsNotNone(nodes_fts)

        fts_columns = conn.execute("PRAGMA table_info(nodes_fts)").fetchall()
        self.assertEqual([row[1] for row in fts_columns], ["graph_id", "node_id", "label", "details_text", "sections_text"])


    def test_v7_migration_adds_node_fact_descriptor_columns(self):
        """v7 must add fact descriptor columns and latest schema stays current."""
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)

        applied = apply_pending(conn)
        version = conn.execute(
            "SELECT value FROM store_meta WHERE key = 'schema_version'"
        ).fetchone()[0]
        self.assertEqual(int(version), len(MIGRATIONS), f"Expected latest schema version, got {version}")
        self.assertIn(7, applied)

        # All four descriptor columns must be present in confidence_ledger
        cols = {row[1] for row in conn.execute("PRAGMA table_info(confidence_ledger)").fetchall()}
        for col in ("fact_label", "fact_path", "fact_value", "fact_subject_type"):
            self.assertIn(col, cols, f"Column '{col}' missing from confidence_ledger after v7")

        # Idempotency: second apply_pending is a no-op and columns still there
        second = apply_pending(conn)
        self.assertEqual(second, [])
        cols_after = {row[1] for row in conn.execute("PRAGMA table_info(confidence_ledger)").fetchall()}
        for col in ("fact_label", "fact_path", "fact_value", "fact_subject_type"):
            self.assertIn(col, cols_after, f"Column '{col}' missing after idempotency re-run")

        # Existing rows (NULL descriptors) are still retrievable
        conn.execute(
            "INSERT INTO graphs(id, workspace_root, workspace_path, project, org, "
            "schema_version, contract_version, node_count, edge_count, "
            "created_at, updated_at) VALUES "
            "('g1','/','/','p','o','7','1',0,0,'2026-01-01','2026-01-01')"
        )
        conn.execute(
            "INSERT INTO confidence_ledger"
            "(graph_id, target_type, target_id, status, captured_at, provenance) "
            "VALUES ('g1','edge','e1','inferred','2026-01-01','seed')"
        )
        row = conn.execute(
            "SELECT fact_label, fact_path, fact_value, fact_subject_type "
            "FROM confidence_ledger WHERE target_id='e1'"
        ).fetchone()
        self.assertIsNone(row[0], "fact_label should default to NULL for existing rows")
        self.assertIsNone(row[1], "fact_path should default to NULL for existing rows")
        self.assertIsNone(row[2], "fact_value should default to NULL for existing rows")
        self.assertIsNone(row[3], "fact_subject_type should default to NULL for existing rows")


if __name__ == "__main__":
    unittest.main()
