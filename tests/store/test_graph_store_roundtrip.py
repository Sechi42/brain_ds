"""RED tests for GraphStore orchestrator roundtrip behavior."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from brain_ds.ontology.graph_model import Edge, EvidenceRecord, Graph, Node
from brain_ds.store.errors import GraphNotFoundError, IncompatibleStoreError, StoreError
from brain_ds.store.graph_store import GraphStore


class GraphStoreRoundtripTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "graph.db"
        self.store = GraphStore(str(self.db_path))

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def _sample_graph(self) -> Graph:
        return Graph(
            schema_version="2.0.0",
            org="acme",
            generated_at="2026-05-21T12:00:00+00:00",
            nodes=[
                Node(
                    id="n-1",
                    label="Root task",
                    type="Task",
                    details={"status": "open"},
                    supertype="Work",
                    evidence_ids=["ev-1"],
                    editable_fields=["details.status"],
                    layout_hint={"x": 0.1, "y": 0.2},
                    depth=0,
                ),
                Node(
                    id="n-2",
                    label="Child task",
                    type="Task",
                    details={"status": "blocked"},
                    supertype="Work",
                    parent_id="n-1",
                    depth=1,
                ),
            ],
            edges=[
                Edge(
                    source="n-1",
                    target="n-2",
                    label="depends-on",
                    reasons=["child blocked by parent"],
                    evidence_ids=["ev-1"],
                    edge_id="e-1",
                )
            ],
            evidence=[
                EvidenceRecord(
                    id="ev-1",
                    type="note",
                    source="jira",
                    content="Blocking note",
                    provenance={"ticket": "ABC-1"},
                    timestamp="2026-05-21T11:00:00+00:00",
                )
            ],
        )

    def test_import_json_then_export_json_matches_input(self) -> None:
        source = self._sample_graph().to_dict()

        graph_id = self.store.import_json(source, workspace_root=self.temp_dir.name)
        exported = self.store.export_json(graph_id)

        self.assertEqual(exported, source)

    def test_save_graph_then_load_graph_matches_dataclass(self) -> None:
        graph = self._sample_graph()

        graph_id = self.store.save_graph(graph)
        loaded = self.store.load_graph(graph_id)

        self.assertEqual(loaded, graph)

    def test_save_graph_is_idempotent_on_graph_id(self) -> None:
        graph = self._sample_graph()

        graph_id = self.store.save_graph(graph, graph_id="graph-123")
        first = self.store.load_graph(graph_id)
        graph.nodes[0].details["status"] = "done"
        same_graph_id = self.store.save_graph(graph, graph_id="graph-123")
        second = self.store.load_graph(same_graph_id)

        self.assertEqual(graph_id, "graph-123")
        self.assertEqual(same_graph_id, "graph-123")
        self.assertNotEqual(first.nodes[0].details["status"], second.nodes[0].details["status"])

    def test_load_unknown_graph_raises_not_found(self) -> None:
        with self.assertRaises(GraphNotFoundError):
            self.store.load_graph("missing")

    def test_close_is_idempotent(self) -> None:
        self.store.close()

        self.store.close()

    def test_context_manager_closes_on_exit(self) -> None:
        with GraphStore(str(self.db_path)) as store:
            graph_id = store.save_graph(self._sample_graph())
            self.assertIsInstance(graph_id, str)

        with self.assertRaises(StoreError):
            store.list_graphs()

    def test_read_only_mode_blocks_writes(self) -> None:
        graph_id = self.store.save_graph(self._sample_graph())
        self.assertIsInstance(graph_id, str)
        self.store.close()

        read_only_store = GraphStore(str(self.db_path), read_only=True)
        try:
            with self.assertRaises(StoreError):
                read_only_store.save_graph(self._sample_graph(), graph_id=graph_id)
        finally:
            read_only_store.close()

    def test_query_nodes_filters_by_type_and_parent_id(self) -> None:
        graph_id = self.store.save_graph(self._sample_graph())
        self.store.node_repo.save_nodes(
            graph_id,
            [
                {"id": "Epic-1", "label": "Epic", "type": "Epic", "details": {}},
                {
                    "id": "Task-1",
                    "label": "Task 1",
                    "type": "Task",
                    "parent_id": "Epic-1",
                    "details": {},
                },
                {
                    "id": "Task-2",
                    "label": "Task 2",
                    "type": "Task",
                    "parent_id": "other-parent",
                    "details": {},
                },
                {"id": "other-parent", "label": "Other", "type": "Epic", "details": {}},
            ],
        )

        rows = self.store.query_nodes(graph_id, type="Task", parent_id="Epic-1")
        self.assertEqual([row.id for row in rows], ["Task-1"])

    def test_file_backed_connection_uses_wal_mode_and_close_is_safe(self) -> None:
        graph_id = self.store.save_graph(self._sample_graph())
        self.assertIsInstance(graph_id, str)

        journal_mode = self.store.conn.execute("PRAGMA journal_mode").fetchone()[0]
        self.assertEqual(str(journal_mode).lower(), "wal")

        self.store.close()
        self.store.close()

        wal_path = Path(f"{self.db_path}-wal")
        if wal_path.exists():
            self.assertEqual(wal_path.stat().st_size, 0)

    def test_read_only_mode_raises_on_stale_schema_version(self) -> None:
        stale_path = Path(self.temp_dir.name) / "stale.db"
        writer = GraphStore(str(stale_path))
        writer.conn.execute(
            "INSERT OR REPLACE INTO store_meta(key, value) VALUES('schema_version', '0')"
        )
        writer.conn.commit()
        writer.close()

        store = None
        try:
            with self.assertRaises(IncompatibleStoreError):
                store = GraphStore(str(stale_path), read_only=True)
        finally:
            if store is not None:
                store.close()
