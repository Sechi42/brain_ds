"""RED tests for edge repository behavior."""

from __future__ import annotations

import sqlite3
import unittest

from brain_ds.store.migrations import apply_pending, configure_connection
from brain_ds.store.repository import EdgeRepository, GraphMetaRepository


class EdgeRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        configure_connection(self.conn)
        apply_pending(self.conn)
        self.meta = GraphMetaRepository(self.conn)
        self.edges = EdgeRepository(self.conn)
        self.meta.save_graph_meta(
            graph_id="graph-e",
            workspace_root="/tmp/ws",
            workspace_path="/tmp/ws/project-e",
            project="project-e",
            org="org-e",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at="",
        )

    def tearDown(self) -> None:
        self.conn.close()

    def test_query_edges_by_source_and_target(self) -> None:
        self.edges.save_edges(
            "graph-e",
            [
                {"source": "A", "target": "B", "label": "rel", "edge_id": "A->B#1"},
                {"source": "C", "target": "B", "label": "rel", "edge_id": "C->B#1"},
            ],
        )

        by_source = self.edges.query_edges("graph-e", source="A")
        by_target = self.edges.query_edges("graph-e", target="B")

        self.assertEqual([edge.edge_id for edge in by_source], ["A->B#1"])
        self.assertEqual(len(by_target), 2)

    def test_synthesizes_edge_id_when_missing(self) -> None:
        self.edges.save_edges("graph-e", [{"source": "N1", "target": "N2", "label": "rel"}])

        edges = self.edges.query_edges("graph-e", source="N1")

        self.assertEqual(edges[0].edge_id, "N1->N2#1")

    def test_weight_nullable(self) -> None:
        self.edges.save_edges(
            "graph-e",
            [{"source": "N2", "target": "N3", "label": "rel", "weight": None}],
        )

        edge = self.edges.query_edges("graph-e", source="N2")[0]
        self.assertIsNone(edge.weight)
