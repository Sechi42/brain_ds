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

    def test_query_edges_filters_order_limit_and_cursor(self) -> None:
        self.edges.save_edges(
            "graph-e",
            [
                {"source": "A", "target": "B", "label": "uses", "weight": 0.2, "edge_id": "e-3", "evidence_ids": ["ev"]},
                {"source": "A", "target": "C", "label": "uses", "weight": 0.8, "edge_id": "e-2", "evidence_ids": []},
                {"source": "B", "target": "C", "label": "depends-on", "weight": 0.6, "edge_id": "e-1", "evidence_ids": ["ev"]},
            ],
        )

        first_page = self.edges.query_edges(
            "graph-e",
            labels=["uses"],
            min_weight=0.1,
            max_weight=0.9,
            has_evidence=True,
            order_by="label_edge_id",
            limit=1,
        )
        second_page = self.edges.query_edges(
            "graph-e",
            labels=["uses"],
            min_weight=0.1,
            max_weight=0.9,
            has_evidence=True,
            order_by="label_edge_id",
            limit=1,
            cursor=(first_page[-1].label, first_page[-1].edge_id),
        )

        self.assertEqual([edge.edge_id for edge in first_page], ["e-3"])
        self.assertEqual(second_page, [])

    def test_query_edges_orders_by_label_then_edge_id(self) -> None:
        self.edges.save_edges(
            "graph-e",
            [
                {"source": "A", "target": "B", "label": "uses", "edge_id": "z"},
                {"source": "A", "target": "C", "label": "depends-on", "edge_id": "m"},
                {"source": "B", "target": "C", "label": "uses", "edge_id": "a"},
            ],
        )

        ordered = self.edges.query_edges("graph-e", order_by="label_edge_id")

        self.assertEqual([edge.edge_id for edge in ordered], ["m", "a", "z"])
