"""RED tests for cluster repository behavior."""

from __future__ import annotations

import sqlite3
import unittest

from brain_ds.store.migrations import apply_pending, configure_connection
from brain_ds.store.repository import ClusterRepository, GraphMetaRepository, NodeRepository


class ClusterRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        configure_connection(self.conn)
        apply_pending(self.conn)
        self.meta = GraphMetaRepository(self.conn)
        self.nodes = NodeRepository(self.conn)
        self.repo = ClusterRepository(self.conn)
        self.meta.save_graph_meta(
            graph_id="graph-c",
            workspace_root="/tmp/ws",
            workspace_path="/tmp/ws/project-c",
            project="project-c",
            org="org-c",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at="",
        )
        self.nodes.save_nodes(
            "graph-c",
            [{"id": "node-1", "label": "N1", "type": "Task", "details": {}}],
        )

    def tearDown(self) -> None:
        self.conn.close()

    def test_save_cluster_and_member(self) -> None:
        self.repo.save_clusters(
            "graph-c",
            [{"id": "cluster-1", "name": "Main", "description": "desc"}],
        )
        self.repo.save_members(
            "graph-c",
            [{"cluster_id": "cluster-1", "node_id": "node-1", "weight": 0.5}],
        )

        clusters = self.repo.query_clusters("graph-c")
        members = self.repo.list_members("graph-c", cluster_id="cluster-1")

        self.assertEqual([cluster.id for cluster in clusters], ["cluster-1"])
        self.assertEqual([member.node_id for member in members], ["node-1"])

    def test_cluster_members_cascade_on_node_delete(self) -> None:
        self.repo.save_clusters("graph-c", [{"id": "cluster-2", "name": "Main"}])
        self.repo.save_members(
            "graph-c",
            [{"cluster_id": "cluster-2", "node_id": "node-1", "weight": None}],
        )

        self.nodes.delete_nodes("graph-c")

        members = self.repo.list_members("graph-c", cluster_id="cluster-2")
        self.assertEqual(members, [])

    def test_invalid_parent_cluster_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            self.repo.save_clusters(
                "graph-c",
                [{"id": "cluster-3", "name": "Child", "parent_id": "missing"}],
            )
