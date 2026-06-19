from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from brain_ds.ontology.entity_types import EntityType
from brain_ds.ontology.graph_model import Graph, Node
from brain_ds.ontology.relationship_types import RelationshipType
from brain_ds.store.errors import GraphAlreadyExistsError
from brain_ds.store.graph_store import GraphStore


class GraphStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "store.db"
        self.store = GraphStore(str(self.db_path))

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def _graph_meta(self, graph_id: str):
        return next(meta for meta in self.store.list_graphs() if meta.id == graph_id)

    def test_create_graph_creates_empty_meta(self) -> None:
        graph_id = self.store.create_graph(
            "logitrans",
            name="Logitrans",
            project="brain-ds",
            workspace_root=self.temp_dir.name,
            workspace_path=self.temp_dir.name,
        )

        self.assertEqual(graph_id, "logitrans")
        meta = self._graph_meta("logitrans")
        self.assertEqual(meta.org, "Logitrans")
        self.assertEqual(meta.node_count, 0)
        self.assertEqual(meta.edge_count, 0)
        self.assertEqual(self.store.query_nodes("logitrans"), [])

    def test_create_graph_on_existing_raises_error(self) -> None:
        self.store.create_graph("logitrans", workspace_root=self.temp_dir.name, workspace_path=self.temp_dir.name)
        self.store.upsert_node(
            "logitrans",
            {"id": "N-1", "label": "Warehouse", "type": "Data Source", "details": {"owner": "ops"}},
        )

        with self.assertRaises(GraphAlreadyExistsError):
            self.store.create_graph("logitrans", workspace_root=self.temp_dir.name, workspace_path=self.temp_dir.name)

        self.assertEqual(len(self.store.query_nodes("logitrans")), 1)
        meta = self._graph_meta("logitrans")
        self.assertEqual(meta.node_count, 1)

    def test_import_json_with_graph_id(self) -> None:
        graph = Graph(
            org="Logitrans",
            nodes=[
                Node(
                    id="ds-1",
                    label="ERP",
                    type=EntityType.DATA_SOURCE,
                    details={"summary": "system of record"},
                )
            ],
            edges=[],
        )

        graph_id = self.store.import_json(graph.to_dict(), graph_id="logitrans")

        self.assertEqual(graph_id, "logitrans")
        self.assertEqual(len(self.store.query_nodes("logitrans")), 1)
        self.assertEqual(self._graph_meta("logitrans").node_count, 1)

    def test_upsert_node_bumps_graph_count(self) -> None:
        self.store.create_graph("logitrans", workspace_root=self.temp_dir.name, workspace_path=self.temp_dir.name)

        self.store.upsert_node(
            "logitrans",
            {"id": "N-1", "label": "ERP", "type": "Data Source", "details": {"owner": "ops"}},
        )
        self.assertEqual(self._graph_meta("logitrans").node_count, 1)

        self.store.upsert_node(
            "logitrans",
            {"id": "N-2", "label": "CRM", "type": "Data Source", "details": {"owner": "sales"}},
        )
        self.assertEqual(self._graph_meta("logitrans").node_count, 2)

    def test_upsert_edge_bumps_graph_count(self) -> None:
        self.store.create_graph("logitrans", workspace_root=self.temp_dir.name, workspace_path=self.temp_dir.name)
        self.store.upsert_node(
            "logitrans",
            {"id": "N-1", "label": "ERP", "type": "Data Source", "details": {"owner": "ops"}},
        )
        self.store.upsert_node(
            "logitrans",
            {"id": "N-2", "label": "CRM", "type": "Data Source", "details": {"owner": "sales"}},
        )

        self.store.upsert_edge(
            "logitrans",
            {"source": "N-1", "target": "N-2", "label": RelationshipType.DEPENDS_ON.value},
        )
        self.assertEqual(self._graph_meta("logitrans").edge_count, 1)

        self.store.upsert_edge(
            "logitrans",
            {
                "source": "N-2",
                "target": "N-1",
                "label": RelationshipType.OWNS.value,
                "edge_id": "E-2",
            },
        )
        self.assertEqual(self._graph_meta("logitrans").edge_count, 2)

    def test_load_graph_skips_edges_with_unknown_relationship_label(self) -> None:
        # MCP add_edge / outbox writes persist rows without ontology validation,
        # so the read path must tolerate a free-text label instead of blanking
        # the whole graph (regression: viewer rendered empty for LogiTrans).
        self.store.create_graph("logitrans", workspace_root=self.temp_dir.name, workspace_path=self.temp_dir.name)
        self.store.upsert_node(
            "logitrans",
            {"id": "N-1", "label": "ERP", "type": "Data Source", "details": {"owner": "ops"}},
        )
        self.store.upsert_node(
            "logitrans",
            {"id": "N-2", "label": "CRM", "type": "Data Source", "details": {"owner": "sales"}},
        )
        self.store.upsert_edge(
            "logitrans",
            {"source": "N-1", "target": "N-2", "label": RelationshipType.DEPENDS_ON.value},
        )
        self.store.upsert_edge(
            "logitrans",
            {"source": "N-2", "target": "N-1", "label": "validates live MCP edge", "edge_id": "E-bad"},
        )

        graph = self.store.load_graph("logitrans")

        self.assertEqual(len(graph.edges), 1)
        self.assertEqual(graph.edges[0].label, RelationshipType.DEPENDS_ON)

    def test_load_graph_tolerates_legacy_body_key_in_card_sections(self) -> None:
        self.store.create_graph("logitrans", workspace_root=self.temp_dir.name, workspace_path=self.temp_dir.name)
        self.store.upsert_node(
            "logitrans",
            {
                "id": "N-1",
                "label": "ERP",
                "type": "Data Source",
                "details": {"owner": "ops"},
                "card_sections": [{"title": "Overview", "content": "Current", "icon": "", "order": 1}],
            },
        )
        self.store.conn.execute(
            "UPDATE nodes SET card_sections = ? WHERE graph_id = ? AND id = ?",
            (json.dumps([{"title": "Overview", "body": "Legacy", "icon": "note", "order": 2}]), "logitrans", "N-1"),
        )
        self.store.conn.commit()

        graph = self.store.load_graph("logitrans")
        self.assertIsNotNone(graph.nodes[0].card_sections)
        assert graph.nodes[0].card_sections is not None

        self.assertEqual(graph.nodes[0].card_sections[0].content, "Legacy")
        self.assertEqual(graph.nodes[0].card_sections[0].icon, "note")
        self.assertEqual(graph.nodes[0].card_sections[0].order, 2)


# ---------------------------------------------------------------------------
# PR3 — T3.1: hide_graph / list_graphs hidden filter / delete_graph hard path
# ---------------------------------------------------------------------------

class TestGraphStoreHideAndDelete(unittest.TestCase):
    """T3.1: hide_graph excludes from list_graphs; delete_graph hard-deletes."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "store.db"
        self.store = GraphStore(str(self.db_path))

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def _create_graph(self, name: str) -> str:
        from brain_ds.ontology import Graph
        g = Graph.from_v1({"nodes": [], "edges": [], "org": name})
        return self.store.save_graph(g, workspace_root=self.temp_dir.name)

    def test_hide_graph_excludes_from_list_graphs(self) -> None:
        """T3.1: After hide_graph, list_graphs must not return that graph_id."""
        graph_id = self._create_graph("HiddenOrg")
        # Confirm it's visible first
        ids_before = [g.id for g in self.store.list_graphs()]
        self.assertIn(graph_id, ids_before)

        self.store.hide_graph(graph_id)

        ids_after = [g.id for g in self.store.list_graphs()]
        self.assertNotIn(graph_id, ids_after)

    def test_hide_graph_data_still_in_store(self) -> None:
        """T3.1: Hidden graph row still exists — data survives (reversible)."""
        graph_id = self._create_graph("SoftRemoved")
        self.store.hide_graph(graph_id)

        # Direct SQL confirms row exists
        row = self.store.conn.execute(
            "SELECT hidden FROM graphs WHERE id = ?", (graph_id,)
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 1)

    def test_migration_idempotent_hidden_column(self) -> None:
        """T3.2: Running v5_graphs_hidden twice must not raise (idempotency guard)."""
        from brain_ds.store.migrations import v5_graphs_hidden
        # First run already happened during store init (schema v5)
        # Running again must be a no-op, not raise OperationalError
        try:
            v5_graphs_hidden(self.store.conn)
        except Exception as exc:  # noqa: BLE001
            self.fail(f"v5_graphs_hidden raised on second run: {exc}")

    def test_fresh_store_has_hidden_column(self) -> None:
        """T3.3: Fresh store (DDL) must include hidden column on graphs table."""
        cols = [
            row[1]
            for row in self.store.conn.execute("PRAGMA table_info(graphs)").fetchall()
        ]
        self.assertIn("hidden", cols)

    def test_hide_nonexistent_graph_raises(self) -> None:
        """T3.4: hide_graph on unknown id must raise GraphNotFoundError."""
        from brain_ds.store.errors import GraphNotFoundError
        with self.assertRaises(GraphNotFoundError):
            self.store.hide_graph("does-not-exist")

    def test_delete_graph_hard_removes_row(self) -> None:
        """T3.5: delete_graph (hard) must remove the row entirely (CASCADE)."""
        graph_id = self._create_graph("ToDelete")
        self.store.delete_graph(graph_id)

        row = self.store.conn.execute(
            "SELECT id FROM graphs WHERE id = ?", (graph_id,)
        ).fetchone()
        self.assertIsNone(row)

    def test_hidden_graphs_excluded_when_two_graphs(self) -> None:
        """T3.1 multi: only non-hidden graphs appear in list_graphs."""
        visible_id = self._create_graph("Visible")
        hidden_id = self._create_graph("Hidden")
        self.store.hide_graph(hidden_id)

        ids = [g.id for g in self.store.list_graphs()]
        self.assertIn(visible_id, ids)
        self.assertNotIn(hidden_id, ids)


if __name__ == "__main__":
    unittest.main()
