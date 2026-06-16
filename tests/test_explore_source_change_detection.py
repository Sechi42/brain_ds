"""Integration tests for explore_source change-detection wiring (Work-Unit E).

XC-2: explore_source against a fixture SQLite source that is mutated between
calls — first call (no baseline) -> new; after baseline written, identical
re-explore -> unchanged; schema mutated -> changed.

E-T2 emission guard: change_detection present ONLY at level==table, never at
the source/container levels.
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from brain_ds.mcp.tools import explore_source, get_node, update_node
from brain_ds.store.graph_store import GraphStore


class ExploreSourceChangeDetectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "store.db"
        self.store = GraphStore(str(self.db_path))
        self.graph_id = "g-cd"
        self.store.meta_repo.save_graph_meta(
            graph_id=self.graph_id,
            workspace_root=str(self.root),
            workspace_path=str(self.root),
            project="p",
            org="o",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at="",
        )
        # Fixture SQLite source inside the project root (sandbox-safe).
        self.source_path = self.root / "source.db"
        self._build_source(["id INTEGER", "name TEXT"])

        self.store.upsert_node(
            self.graph_id,
            {
                "id": "DS-1",
                "label": "Fixture DB",
                "type": "Data Source",
                "parent_id": "ROOT",
                "details": {"connection": {"kind": "sqlite", "path": str(self.source_path)}},
            },
        )

    def tearDown(self) -> None:
        try:
            self.store.close()
        except Exception:
            pass
        try:
            self.temp_dir.cleanup()
        except (PermissionError, OSError):
            # Windows may briefly hold the store.db handle; ignore on teardown.
            pass

    def _build_source(self, columns: list[str], table: str = "customers") -> None:
        if self.source_path.exists():
            self.source_path.unlink()
        conn = sqlite3.connect(self.source_path)
        try:
            conn.execute(f"CREATE TABLE {table} ({', '.join(columns)})")
            conn.commit()
        finally:
            conn.close()

    def _explore_table(self) -> dict:
        return explore_source(
            self.store,
            {"graph_id": self.graph_id, "node_id": "DS-1", "container": "main", "table": "customers"},
        )

    def _write_baseline(self, result: dict) -> None:
        # Simulate the documenter persisting the baseline to the GRAPH only.
        from brain_ds.connectors.change_detection import build_baseline

        cd = result["change_detection"]
        # Mirror the explore_source wiring: scope the single-table connector
        # schema under its real table name before computing the baseline.
        live_schema = {"tables": {result["table"]: {"columns": result["schema"].get("columns", [])}}}
        baseline = build_baseline(live_schema, last_documented_at="2026-06-16T00:00:00Z")
        # sanity: freshly computed hash matches the verdict block hash
        self.assertEqual(baseline["schema_hash"], cd["schema_hash"])
        node = get_node(self.store, {"graph_id": self.graph_id, "node_id": "DS-1"})
        details = dict(node.get("details") or {})
        details["schema_baseline"] = baseline
        update_node(self.store, {"graph_id": self.graph_id, "node_id": "DS-1", "details": details})

    def test_no_emit_at_source_and_container_levels(self) -> None:
        source_level = explore_source(self.store, {"graph_id": self.graph_id, "node_id": "DS-1"})
        self.assertEqual(source_level["level"], "source")
        self.assertNotIn("change_detection", source_level)

        container_level = explore_source(
            self.store, {"graph_id": self.graph_id, "node_id": "DS-1", "container": "main"}
        )
        self.assertEqual(container_level["level"], "container")
        self.assertNotIn("change_detection", container_level)

    def test_first_explore_is_new(self) -> None:
        result = self._explore_table()
        self.assertEqual(result["level"], "table")
        self.assertIn("change_detection", result)
        self.assertEqual(result["change_detection"]["verdict"], "new")
        self.assertIsNone(result["change_detection"]["delta"])

    def test_identical_reexplore_after_baseline_is_unchanged(self) -> None:
        first = self._explore_table()
        self._write_baseline(first)
        second = self._explore_table()
        self.assertEqual(second["change_detection"]["verdict"], "unchanged")
        self.assertIsNone(second["change_detection"]["delta"])

    def test_mutated_schema_after_baseline_is_changed_with_delta(self) -> None:
        first = self._explore_table()
        self._write_baseline(first)
        # Add a column to the live source.
        self._build_source(["id INTEGER", "name TEXT", "email TEXT"])
        third = self._explore_table()
        cd = third["change_detection"]
        self.assertEqual(cd["verdict"], "changed")
        self.assertIsNotNone(cd["delta"])
        added = [(c["table"], c["name"]) for c in cd["delta"]["added_columns"]]
        self.assertIn(("customers", "email"), added)

    def test_cosmetic_widening_stays_unchanged(self) -> None:
        # Baseline on varchar(100); re-explore reports varchar(255) -> unchanged.
        self._build_source(["id INTEGER", "name varchar(100)"])
        first = self._explore_table()
        self._write_baseline(first)
        self._build_source(["id INTEGER", "name varchar(255)"])
        second = self._explore_table()
        self.assertEqual(second["change_detection"]["verdict"], "unchanged")

    # --- Multi-table sources (real-world shape: one baseline entry per table) ---

    def _build_multitable_source(self) -> None:
        if self.source_path.exists():
            self.source_path.unlink()
        conn = sqlite3.connect(self.source_path)
        try:
            conn.execute("CREATE TABLE customers (id INTEGER, name TEXT)")
            conn.execute("CREATE TABLE orders (id INTEGER, customer_id INTEGER, total REAL)")
            conn.commit()
        finally:
            conn.close()

    def _explore(self, table: str) -> dict:
        return explore_source(
            self.store,
            {"graph_id": self.graph_id, "node_id": "DS-1", "container": "main", "table": table},
        )

    def _write_per_table_baseline(self, tables: tuple[str, ...]) -> None:
        # Mirror how the documenter persists a multi-table Data Source: a map of
        # {table_name: build_baseline(single_table_schema)} under schema_baseline.
        from brain_ds.connectors.change_detection import build_baseline

        node = get_node(self.store, {"graph_id": self.graph_id, "node_id": "DS-1"})
        details = dict(node.get("details") or {})
        per_table: dict[str, dict] = {}
        for table in tables:
            res = self._explore(table)
            live_schema = {"tables": {table: {"columns": res["schema"].get("columns", [])}}}
            per_table[table] = build_baseline(live_schema, last_documented_at="2026-06-16T00:00:00Z")
        details["schema_baseline"] = per_table
        update_node(
            self.store,
            {"graph_id": self.graph_id, "node_id": "DS-1", "details": details},
        )

    def test_multitable_per_table_baseline_is_unchanged(self) -> None:
        self._build_multitable_source()
        self._write_per_table_baseline(("customers", "orders"))
        self.assertEqual(self._explore("customers")["change_detection"]["verdict"], "unchanged")
        self.assertEqual(self._explore("orders")["change_detection"]["verdict"], "unchanged")

    def test_multitable_mutated_table_is_changed_others_unchanged(self) -> None:
        self._build_multitable_source()
        self._write_per_table_baseline(("customers", "orders"))
        # Mutate only `orders`: add a column.
        conn = sqlite3.connect(self.source_path)
        try:
            conn.execute("ALTER TABLE orders ADD COLUMN status TEXT")
            conn.commit()
        finally:
            conn.close()
        cd = self._explore("orders")["change_detection"]
        self.assertEqual(cd["verdict"], "changed")
        self.assertIsNotNone(cd["delta"])
        added = [(c["table"], c["name"]) for c in cd["delta"]["added_columns"]]
        self.assertIn(("orders", "status"), added)
        # `customers` was untouched -> still unchanged.
        self.assertEqual(self._explore("customers")["change_detection"]["verdict"], "unchanged")

    def test_prior_doc_no_baseline_is_unknown_baseline(self) -> None:
        # Node has card_sections (prior doc) but no schema_baseline key.
        update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "DS-1",
                "card_sections": [
                    {"title": "Overview", "content": "documented earlier", "icon": "info", "order": 1}
                ],
            },
        )
        result = self._explore_table()
        self.assertEqual(result["change_detection"]["verdict"], "unknown-baseline")
        self.assertIsNone(result["change_detection"]["delta"])


if __name__ == "__main__":
    unittest.main()
