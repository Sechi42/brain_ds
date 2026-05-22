from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from brain_ds.store.graph_store import GraphStore
from brain_ds.store.migrations import v2_tools_audit


class StoreMigrationAuditTests(unittest.TestCase):
    def test_tools_audit_table_exists_with_expected_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "audit.db"
            store = GraphStore(str(db_path), read_only=False)
            try:
                rows = store.conn.execute("PRAGMA table_info('tools_audit')").fetchall()
            finally:
                store.close()

        column_names = [row[1] for row in rows]
        self.assertEqual(
            column_names,
            ["id", "timestamp", "tool_name", "input_hash", "result_status", "caller_id"],
        )

    def test_v2_tools_audit_migration_is_idempotent(self) -> None:
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)

        v2_tools_audit(conn)
        v2_tools_audit(conn)

        count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='tools_audit'"
        ).fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
