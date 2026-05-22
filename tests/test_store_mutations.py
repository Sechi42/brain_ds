from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from brain_ds.store.errors import StoreError
from brain_ds.store.graph_store import GraphStore


class StoreMutationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "store.db"
        self.store = GraphStore(str(self.db_path))
        self.graph_id = "graph-mut"
        self.store.meta_repo.save_graph_meta(
            graph_id=self.graph_id,
            workspace_root=self.temp_dir.name,
            workspace_path=self.temp_dir.name,
            project="project-mut",
            org="org-mut",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at="",
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def test_node_repository_upsert_inserts_new_node(self) -> None:
        self.store.node_repo.upsert_node(
            self.graph_id,
            {
                "id": "N-1",
                "label": "Original",
                "type": "Task",
                "details": {"status": "todo"},
            },
        )

        row = self.store.node_repo.query_nodes(self.graph_id, type="Task")[0]
        self.assertEqual(row.id, "N-1")
        self.assertEqual(row.label, "Original")
        self.assertEqual(row.details, {"status": "todo"})

    def test_node_repository_upsert_partially_updates_existing_node(self) -> None:
        self.store.node_repo.save_nodes(
            self.graph_id,
            [{"id": "N-1", "label": "Old", "type": "Task", "details": {"v": 1}}],
        )
        initial = self.store.node_repo.query_nodes(self.graph_id, type="Task")[0]

        self.store.node_repo.upsert_node(self.graph_id, {"id": "N-1", "label": "New"})

        updated = self.store.node_repo.query_nodes(self.graph_id, type="Task")[0]
        self.assertEqual(updated.label, "New")
        self.assertEqual(updated.type, "Task")
        self.assertGreater(updated.modified_at, initial.modified_at)

    def test_edge_repository_upsert_inserts_new_edge(self) -> None:
        self.store.edge_repo.upsert_edge(
            self.graph_id,
            {
                "source": "A",
                "target": "B",
                "label": "rel",
            },
        )

        edge = self.store.edge_repo.query_edges(self.graph_id, source="A")[0]
        self.assertEqual(edge.source, "A")
        self.assertEqual(edge.target, "B")
        self.assertEqual(edge.label, "rel")

    def test_edge_repository_upsert_updates_existing_edge_by_edge_id(self) -> None:
        self.store.edge_repo.save_edges(
            self.graph_id,
            [{"edge_id": "E-1", "source": "A", "target": "B", "label": "rel", "weight": 0.2}],
        )

        self.store.edge_repo.upsert_edge(self.graph_id, {"edge_id": "E-1", "weight": 0.8})

        edge = self.store.edge_repo.query_edges(self.graph_id, source="A")[0]
        self.assertEqual(edge.edge_id, "E-1")
        self.assertEqual(edge.weight, 0.8)

    def test_graph_store_wrappers_enforce_read_only(self) -> None:
        self.store.close()
        read_only = GraphStore(str(self.db_path), read_only=True)
        try:
            with self.assertRaises(StoreError):
                read_only.upsert_node(self.graph_id, {"id": "N-1", "label": "x", "type": "Task"})
            with self.assertRaises(StoreError):
                read_only.upsert_edge(self.graph_id, {"source": "A", "target": "B", "label": "rel"})
            with self.assertRaises(StoreError):
                read_only.log_audit("update_node", {"graph_id": self.graph_id}, "ok")
        finally:
            read_only.close()

    def test_graph_store_wrappers_pass_through_to_repositories(self) -> None:
        self.store.upsert_node(self.graph_id, {"id": "N-1", "label": "Node", "type": "Task"})
        node = self.store.node_repo.query_nodes(self.graph_id, type="Task")[0]
        self.assertEqual(node.id, "N-1")

        self.store.upsert_edge(
            self.graph_id,
            {"edge_id": "E-1", "source": "N-1", "target": "N-2", "label": "rel", "weight": 0.7},
        )
        edge = self.store.edge_repo.query_edges(self.graph_id, source="N-1")[0]
        self.assertEqual(edge.edge_id, "E-1")
        self.assertEqual(edge.weight, 0.7)

    def test_log_audit_hashes_sorted_input_and_stores_status(self) -> None:
        payload = {"b": 2, "a": 1}
        self.store.log_audit("update_node", payload, "ok", caller_id="caller-1")

        row = self.store.conn.execute(
            "SELECT tool_name, input_hash, result_status, caller_id FROM tools_audit ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertIsNotNone(row)
        expected_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        self.assertEqual(row[0], "update_node")
        self.assertEqual(row[1], expected_hash)
        self.assertEqual(row[2], "ok")
        self.assertEqual(row[3], "caller-1")
        self.assertNotEqual(row[1], json.dumps(payload))

    def test_log_audit_only_allows_ok_or_error_status(self) -> None:
        with self.assertRaises(ValueError):
            self.store.log_audit("update_node", {"x": 1}, "pending")


if __name__ == "__main__":
    unittest.main()
