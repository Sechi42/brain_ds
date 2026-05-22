"""RED tests for node repository behavior."""

from __future__ import annotations

import sqlite3
import unittest

from brain_ds.store.migrations import apply_pending, configure_connection
from brain_ds.store.repository import GraphMetaRepository, NodeRepository


class NodeRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        configure_connection(self.conn)
        apply_pending(self.conn)
        self.meta = GraphMetaRepository(self.conn)
        self.nodes = NodeRepository(self.conn)
        self.meta.save_graph_meta(
            graph_id="graph-n",
            workspace_root="/tmp/ws",
            workspace_path="/tmp/ws/project-n",
            project="project-n",
            org="org-n",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at="",
        )

    def tearDown(self) -> None:
        self.conn.close()

    def test_query_nodes_by_type_and_supertype(self) -> None:
        self.nodes.save_nodes(
            "graph-n",
            [
                {
                    "id": "n-1",
                    "label": "Task node",
                    "type": "Task",
                    "supertype": "Work",
                    "details": {"k": "v"},
                },
                {
                    "id": "n-2",
                    "label": "Person node",
                    "type": "Person",
                    "supertype": "Actor",
                    "details": {},
                },
            ],
        )

        by_type = self.nodes.query_nodes("graph-n", type="Task")
        by_supertype = self.nodes.query_nodes("graph-n", supertype="Actor")

        self.assertEqual([node.id for node in by_type], ["n-1"])
        self.assertEqual([node.id for node in by_supertype], ["n-2"])

    def test_query_nodes_by_type_and_parent_id(self) -> None:
        self.nodes.save_nodes(
            "graph-n",
            [
                {
                    "id": "epic-1",
                    "label": "Epic",
                    "type": "Epic",
                    "details": {},
                },
                {
                    "id": "task-1",
                    "label": "Task 1",
                    "type": "Task",
                    "parent_id": "epic-1",
                    "details": {},
                },
                {
                    "id": "task-2",
                    "label": "Task 2",
                    "type": "Task",
                    "parent_id": "epic-2",
                    "details": {},
                },
                {
                    "id": "epic-2",
                    "label": "Epic 2",
                    "type": "Epic",
                    "details": {},
                },
            ],
        )

        rows = self.nodes.query_nodes("graph-n", type="Task", parent_id="epic-1")

        self.assertEqual([row.id for row in rows], ["task-1"])

    def test_modified_at_bumps_on_resave(self) -> None:
        self.nodes.save_nodes(
            "graph-n",
            [{"id": "n-3", "label": "Node", "type": "Task", "details": {"v": "1"}}],
        )
        first = self.nodes.query_nodes("graph-n", type="Task")[0].modified_at

        self.nodes.save_nodes(
            "graph-n",
            [{"id": "n-3", "label": "Node", "type": "Task", "details": {"v": "2"}}],
        )
        second = self.nodes.query_nodes("graph-n", type="Task")[0].modified_at

        self.assertNotEqual(first, second)

    def test_parent_id_python_validation_raises_on_missing_parent(self) -> None:
        with self.assertRaises(ValueError):
            self.nodes.save_nodes(
                "graph-n",
                [
                    {
                        "id": "n-4",
                        "label": "Orphan",
                        "type": "Task",
                        "parent_id": "does-not-exist",
                        "details": {},
                    }
                ],
            )
