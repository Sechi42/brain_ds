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

        self.assertEqual(graph.nodes[0].card_sections[0].content, "Legacy")
        self.assertEqual(graph.nodes[0].card_sections[0].icon, "note")
        self.assertEqual(graph.nodes[0].card_sections[0].order, 2)


if __name__ == "__main__":
    unittest.main()
