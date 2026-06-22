from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from brain_ds.store.graph_store import GraphStore
from brain_ds.store.migrations import MIGRATIONS, apply_pending, v2_tools_audit


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


# ---------------------------------------------------------------------------
# Task 2.4 — migration caching guard (RED before task 2.5 GREEN)
# ---------------------------------------------------------------------------


class MigrationCachingGuardTests(unittest.TestCase):
    """GraphStore MUST skip apply_pending when the schema is already current.

    The spec requirement: 'The GraphStore SQLite open/migrate entrypoint MUST
    run schema setup at most once per process when schema is unchanged.'

    RED phase: this test fails until graph_store.py caches the schema version
    per process/path (task 2.5 GREEN).
    """

    def test_repeated_opens_call_apply_pending_at_most_once(self) -> None:
        """Opening GraphStore N times against a fully-migrated DB must invoke
        apply_pending() at most once (the first open); subsequent opens must
        skip it entirely because the schema is already current.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "cache_test.db")

            call_count = 0
            original_apply_pending = apply_pending

            def counting_apply_pending(conn: sqlite3.Connection) -> list[int]:
                nonlocal call_count
                call_count += 1
                return original_apply_pending(conn)

            n_opens = 5

            with patch(
                "brain_ds.store.graph_store.apply_pending",
                side_effect=counting_apply_pending,
            ):
                stores = []
                try:
                    for _ in range(n_opens):
                        stores.append(GraphStore(db_path))
                finally:
                    for s in stores:
                        s.close()

            self.assertLessEqual(
                call_count,
                1,
                msg=(
                    f"apply_pending was called {call_count} times for {n_opens} opens "
                    f"against the same already-migrated DB; expected at most 1 call."
                ),
            )

    def test_apply_pending_called_exactly_once_on_first_open(self) -> None:
        """The first open of a brand-new DB must invoke apply_pending once."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "fresh.db")

            call_count = 0
            original_apply_pending = apply_pending

            def counting_apply_pending(conn: sqlite3.Connection) -> list[int]:
                nonlocal call_count
                call_count += 1
                return original_apply_pending(conn)

            with patch(
                "brain_ds.store.graph_store.apply_pending",
                side_effect=counting_apply_pending,
            ):
                store = GraphStore(db_path)
                try:
                    pass
                finally:
                    store.close()

            self.assertEqual(
                call_count,
                1,
                msg=f"apply_pending must be called exactly once on first open, got {call_count}",
            )


# ---------------------------------------------------------------------------
# Cache fix (folded PR2 WARNING fix) — mtime invalidation (RED before fix)
# ---------------------------------------------------------------------------


class MigrationCacheMtimeInvalidationTests(unittest.TestCase):
    """_migrated_paths must be invalidated when the DB file is replaced at the same path.

    PR2 WARNING: the cache key was (canonical_path -> version) only.  If a DB
    file is deleted and recreated at the same path (e.g. a test that rebuilds
    the store, or a backup restore while the MCP server is running), the cache
    wrongly says "already migrated" and apply_pending is skipped, leaving the
    new DB without tables.

    Fix: key by (path -> (version, mtime)).  On cache hit, compare
    Path(path).stat().st_mtime; if it differs, invalidate and re-run.

    CRITICAL: this test MUST reuse the SAME path across reopens to exercise the
    actual cache hit.  The PR2 guard tests used unique TemporaryDirectory() per
    test, which never hit the cache across test boundaries.
    """

    def setUp(self) -> None:
        # A single temp dir shared across open/delete/recreate within one test.
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def test_cache_invalidated_after_db_deleted_and_recreated_at_same_path(self) -> None:
        """Cache must re-run apply_pending when the DB file is replaced at the same path.

        Steps:
        1. Open GraphStore at path P → apply_pending runs (call 1).
        2. Close and delete the DB file.
        3. Open GraphStore at the same path P again (new file created) →
           apply_pending MUST run again (call 2) because mtime changed.
           Without the mtime fix, the cache wrongly skips apply_pending and the
           new DB has no tables, causing OperationalError at query time.
        """
        db_path = str(Path(self._tmp.name) / "reused_path.db")

        call_count = 0
        original_apply_pending = apply_pending

        def counting_apply_pending(conn: sqlite3.Connection) -> list[int]:
            nonlocal call_count
            call_count += 1
            return original_apply_pending(conn)

        with patch(
            "brain_ds.store.graph_store.apply_pending",
            side_effect=counting_apply_pending,
        ):
            # First open — populates cache.
            store = GraphStore(db_path)
            store.close()

            call_count_after_first_open = call_count

            # Delete the DB file — simulates store rebuild / backup restore.
            Path(db_path).unlink()

            # Reopen at the SAME path — this is a brand-new DB file.
            # apply_pending MUST run again because the file's mtime changed.
            store2 = GraphStore(db_path)
            store2.close()

        self.assertEqual(
            call_count_after_first_open,
            1,
            msg=f"Expected exactly 1 call after first open, got {call_count_after_first_open}",
        )
        self.assertEqual(
            call_count,
            2,
            msg=(
                f"apply_pending should have been called twice (first open + recreated DB), "
                f"but was called {call_count} times. "
                f"The cache did not detect the DB file replacement (mtime not checked)."
            ),
        )

    def test_cache_still_skips_when_same_file_reopened(self) -> None:
        """Cache MUST skip apply_pending when the same (unmodified) DB file is reopened.

        This is the existing happy-path that MUST NOT regress after the mtime fix.
        """
        db_path = str(Path(self._tmp.name) / "stable_path.db")

        call_count = 0
        original_apply_pending = apply_pending

        def counting_apply_pending(conn: sqlite3.Connection) -> list[int]:
            nonlocal call_count
            call_count += 1
            return original_apply_pending(conn)

        with patch(
            "brain_ds.store.graph_store.apply_pending",
            side_effect=counting_apply_pending,
        ):
            # First open — populates cache.
            store = GraphStore(db_path)
            store.close()

            # Second open — same file, same mtime → cache must skip.
            store2 = GraphStore(db_path)
            store2.close()

        self.assertLessEqual(
            call_count,
            1,
            msg=(
                f"apply_pending was called {call_count} times for an unmodified DB reopened "
                f"at the same path; expected at most 1 call (cache should have skipped)."
            ),
        )


if __name__ == "__main__":
    unittest.main()
