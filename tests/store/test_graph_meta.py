"""RED tests for graph metadata repository behavior."""

from __future__ import annotations

import sqlite3
import unittest

from brain_ds.store.errors import GraphNotFoundError
from brain_ds.store.migrations import apply_pending, configure_connection
from brain_ds.store.repository import GraphMetaRepository


class GraphMetaRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        configure_connection(self.conn)
        apply_pending(self.conn)
        self.repo = GraphMetaRepository(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_save_then_list_orders_by_updated_at_desc(self) -> None:
        self.repo.save_graph_meta(
            graph_id="graph-a",
            workspace_root="/tmp/ws",
            workspace_path="/tmp/ws/project-a",
            project="project-a",
            org="org-a",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=1,
            edge_count=0,
            imported_from=None,
            generated_at="2026-01-01T00:00:00+00:00",
        )
        self.repo.save_graph_meta(
            graph_id="graph-b",
            workspace_root="/tmp/ws",
            workspace_path="/tmp/ws/project-b",
            project="project-b",
            org="org-b",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=2,
            edge_count=1,
            imported_from="fixture.json",
            generated_at="2026-01-02T00:00:00+00:00",
        )

        rows = self.repo.list_graphs()
        self.assertEqual(len(rows), 2)

        older = "2026-01-01T00:00:00+00:00"
        newer = "2026-01-02T00:00:00+00:00"
        self.conn.execute("UPDATE graphs SET updated_at = ? WHERE id = ?", (older, "graph-a"))
        self.conn.execute("UPDATE graphs SET updated_at = ? WHERE id = ?", (newer, "graph-b"))
        self.conn.commit()

        ordered = self.repo.list_graphs()
        self.assertEqual([row.id for row in ordered], ["graph-b", "graph-a"])

    def test_delete_graph_cascades_children(self) -> None:
        self.repo.save_graph_meta(
            graph_id="graph-c",
            workspace_root="/tmp/ws",
            workspace_path="/tmp/ws/project-c",
            project="project-c",
            org="org-c",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=1,
            edge_count=0,
            imported_from=None,
            generated_at="",
        )
        self.conn.execute(
            """
            INSERT INTO nodes(
                graph_id, id, label, type, supertype, details, card_sections,
                editable_fields, evidence_ids, layout_hint, parent_id, depth,
                created_at, modified_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "graph-c",
                "n-1",
                "Node 1",
                "Task",
                "Work",
                "{}",
                "[]",
                "[]",
                "[]",
                "{}",
                None,
                0,
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )

        self.repo.delete_graph("graph-c")

        remaining = self.conn.execute(
            "SELECT COUNT(*) FROM nodes WHERE graph_id = 'graph-c'"
        ).fetchone()[0]
        self.assertEqual(remaining, 0)

    def test_delete_graph_twice_raises_not_found(self) -> None:
        self.repo.save_graph_meta(
            graph_id="graph-d",
            workspace_root="/tmp/ws",
            workspace_path="/tmp/ws/project-d",
            project="project-d",
            org="org-d",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at="",
        )
        self.repo.delete_graph("graph-d")

        with self.assertRaises(GraphNotFoundError):
            self.repo.delete_graph("graph-d")

    def test_list_graphs_tie_breaker_is_id_asc_when_updated_at_equal(self) -> None:
        self.repo.save_graph_meta(
            graph_id="graph-z",
            workspace_root="/tmp/ws",
            workspace_path="/tmp/ws/project-z",
            project="project-z",
            org="org-z",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at="",
        )
        self.repo.save_graph_meta(
            graph_id="graph-a",
            workspace_root="/tmp/ws",
            workspace_path="/tmp/ws/project-a",
            project="project-a",
            org="org-a",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at="",
        )

        tie_ts = "2026-01-01T00:00:00+00:00"
        self.conn.execute("UPDATE graphs SET updated_at = ? WHERE id IN (?, ?)", (tie_ts, "graph-z", "graph-a"))
        self.conn.commit()

        rows = self.repo.list_graphs()
        self.assertEqual([row.id for row in rows], ["graph-a", "graph-z"])
