from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path

from brain_ds.mcp.tools import (
    TOOL_REGISTRY,
    add_edge,
    generate_brd,
    get_node,
    list_graphs,
    list_nodes,
    map_connections,
    run_elicit,
    search_graph,
    update_node,
)
from brain_ds.store.graph_store import GraphStore


class MCPToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "store.db"
        self.store = GraphStore(str(self.db_path))
        self.graph_id = "graph-tools"
        self.store.meta_repo.save_graph_meta(
            graph_id=self.graph_id,
            workspace_root=self.temp_dir.name,
            workspace_path=self.temp_dir.name,
            project="project-tools",
            org="org-tools",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at="",
        )
        self.store.upsert_node(
            self.graph_id,
            {
                "id": "N-1",
                "label": "Alpha Task",
                "type": "Task",
                "supertype": "Work",
                "parent_id": "ROOT",
                "details": {"summary": "Find mapping evidence"},
            },
        )
        self.store.upsert_node(
            self.graph_id,
            {
                "id": "N-2",
                "label": "Beta Note",
                "type": "Note",
                "supertype": "Knowledge",
                "parent_id": "ROOT",
                "details": {"summary": "Secondary"},
            },
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def _audit_count(self) -> int:
        row = self.store.conn.execute("SELECT COUNT(*) FROM tools_audit").fetchone()
        return int(row[0])

    def _last_outbox_event(self) -> tuple[str, str, str]:
        row = self.store.conn.execute(
            "SELECT event, graph_id, payload FROM event_outbox ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return (row[0], row[1], row[2])

    def test_list_nodes_filters_and_missing_graph_error(self) -> None:
        result = list_nodes(self.store, {"graph_id": self.graph_id, "type": "Task"})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "N-1")

        by_supertype = list_nodes(self.store, {"graph_id": self.graph_id, "supertype": "Knowledge"})
        self.assertEqual(len(by_supertype), 1)
        self.assertEqual(by_supertype[0]["id"], "N-2")

        by_parent = list_nodes(self.store, {"graph_id": self.graph_id, "parent_id": "ROOT"})
        self.assertEqual(len(by_parent), 2)

        by_empty_supertype = list_nodes(self.store, {"graph_id": self.graph_id, "supertype": "  "})
        self.assertEqual(len(by_empty_supertype), 2)

        by_empty_type = list_nodes(self.store, {"graph_id": self.graph_id, "type": ""})
        self.assertEqual(len(by_empty_type), 2)

        missing_graph = list_nodes(self.store, {"graph_id": "missing"})
        self.assertEqual(missing_graph["code"], -32000)
        self.assertEqual(missing_graph["message"], "Graph 'missing' not found")

    def test_get_node_returns_row_and_not_found_error(self) -> None:
        result = get_node(self.store, {"graph_id": self.graph_id, "node_id": "N-1"})
        self.assertEqual(result["id"], "N-1")

        missing = get_node(self.store, {"graph_id": self.graph_id, "node_id": "N-404"})
        self.assertEqual(missing["code"], -32000)
        self.assertEqual(missing["message"], "Node 'N-404' not found in graph 'graph-tools'")

    def test_search_graph_matches_substrings_and_validates_query_type(self) -> None:
        by_label = search_graph(self.store, {"graph_id": self.graph_id, "query": "alpha"})
        self.assertEqual([item["id"] for item in by_label], ["N-1"])

        by_type = search_graph(self.store, {"graph_id": self.graph_id, "query": "note"})
        self.assertEqual([item["id"] for item in by_type], ["N-2"])

        by_details = search_graph(self.store, {"graph_id": self.graph_id, "query": "mapping"})
        self.assertEqual([item["id"] for item in by_details], ["N-1"])

        no_match = search_graph(self.store, {"graph_id": self.graph_id, "query": "zzz"})
        self.assertEqual(no_match, [])

        missing_graph = search_graph(self.store, {"graph_id": "missing", "query": "x"})
        self.assertEqual(missing_graph["code"], -32000)
        self.assertEqual(missing_graph["message"], "Graph 'missing' not found")

        invalid = search_graph(self.store, {"graph_id": self.graph_id, "query": 42})
        self.assertEqual(invalid["code"], -32602)
        self.assertIn("Expected string for query", invalid["message"])

    def test_update_node_partial_update_audit_and_read_only_rejection(self) -> None:
        before = self.store.query_nodes(self.graph_id, type="Task")[0]
        before_audit = self._audit_count()

        updated = update_node(self.store, {"graph_id": self.graph_id, "node_id": "N-1", "label": "Renamed"})
        self.assertEqual(updated["label"], "Renamed")
        self.assertEqual(updated["type"], "Task")
        self.assertGreater(updated["modified_at"], before.modified_at)
        self.assertEqual(self._audit_count(), before_audit + 1)

        audit_row = self.store.conn.execute(
            "SELECT tool_name, result_status FROM tools_audit ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(audit_row[0], "update_node")
        self.assertEqual(audit_row[1], "ok")

        self.store.close()
        read_only = GraphStore(str(self.db_path), read_only=True)
        try:
            rejected = update_node(read_only, {"graph_id": self.graph_id, "node_id": "N-1", "label": "X"})
            self.assertEqual(rejected["code"], -32000)
            self.assertEqual(rejected["message"], "GraphStore is read-only")
        finally:
            read_only.close()

    def test_update_node_enqueues_node_created(self) -> None:
        created = update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "N-3",
                "label": "Gamma",
                "type": "Task",
                "supertype": "Work",
                "details": {"summary": "new"},
            },
        )
        self.assertEqual(created["id"], "N-3")

        event, graph_id, payload = self._last_outbox_event()
        self.assertEqual(event, "node.created")
        self.assertEqual(graph_id, self.graph_id)
        self.assertEqual(json.loads(payload)["id"], "N-3")

    def test_update_node_enqueues_node_updated(self) -> None:
        updated = update_node(self.store, {"graph_id": self.graph_id, "node_id": "N-1", "label": "Renamed"})
        self.assertEqual(updated["label"], "Renamed")

        event, graph_id, payload = self._last_outbox_event()
        self.assertEqual(event, "node.updated")
        self.assertEqual(graph_id, self.graph_id)
        self.assertEqual(json.loads(payload)["id"], "N-1")

    def test_update_node_card_sections_persists(self) -> None:
        updated = update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "N-1",
                "card_sections": [{"title": "Risks", "content": "Budget overrun", "icon": "", "order": 1}],
            },
        )
        self.assertIn("card_sections", updated)
        self.assertEqual(updated["card_sections"][0]["title"], "Risks")

        reread = get_node(self.store, {"graph_id": self.graph_id, "node_id": "N-1"})
        self.assertEqual(reread["card_sections"][0]["content"], "Budget overrun")

        event, graph_id, payload = self._last_outbox_event()
        self.assertEqual(event, "node.updated")
        self.assertEqual(graph_id, self.graph_id)
        self.assertEqual(json.loads(payload)["card_sections"][0]["title"], "Risks")

    def test_add_edge_success_and_missing_nodes_log_error(self) -> None:
        before = self._audit_count()
        created = add_edge(
            self.store,
            {
                "graph_id": self.graph_id,
                "source": "N-1",
                "target": "N-2",
                "label": "rel",
                "weight": 0.6,
            },
        )
        self.assertEqual(created["source"], "N-1")
        self.assertEqual(created["target"], "N-2")
        self.assertEqual(self._audit_count(), before + 1)

        ok_row = self.store.conn.execute(
            "SELECT tool_name, result_status FROM tools_audit ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(ok_row[0], "add_edge")
        self.assertEqual(ok_row[1], "ok")

        bad_source = add_edge(
            self.store,
            {"graph_id": self.graph_id, "source": "N-404", "target": "N-2", "label": "rel"},
        )
        self.assertEqual(bad_source["code"], -32000)
        self.assertEqual(bad_source["message"], "Source node 'N-404' not found")

        bad_target = add_edge(
            self.store,
            {"graph_id": self.graph_id, "source": "N-1", "target": "N-404", "label": "rel"},
        )
        self.assertEqual(bad_target["code"], -32000)
        self.assertEqual(bad_target["message"], "Target node 'N-404' not found")

        error_rows = self.store.conn.execute(
            "SELECT result_status FROM tools_audit WHERE tool_name='add_edge' ORDER BY id DESC LIMIT 2"
        ).fetchall()
        self.assertEqual(error_rows[0][0], "error")
        self.assertEqual(error_rows[1][0], "error")

    def test_add_edge_enqueues_edge_created(self) -> None:
        created = add_edge(
            self.store,
            {
                "graph_id": self.graph_id,
                "source": "N-1",
                "target": "N-2",
                "label": "rel",
            },
        )
        self.assertEqual(created["source"], "N-1")

        event, graph_id, payload = self._last_outbox_event()
        self.assertEqual(event, "edge.created")
        self.assertEqual(graph_id, self.graph_id)
        self.assertEqual(json.loads(payload)["source"], "N-1")

    def test_add_edge_enqueues_edge_updated(self) -> None:
        add_edge(
            self.store,
            {
                "graph_id": self.graph_id,
                "source": "N-1",
                "target": "N-2",
                "label": "rel",
            },
        )
        updated = add_edge(
            self.store,
            {
                "graph_id": self.graph_id,
                "source": "N-1",
                "target": "N-2",
                "label": "rel-2",
            },
        )
        self.assertEqual(updated["label"], "rel-2")

        event, graph_id, payload = self._last_outbox_event()
        self.assertEqual(event, "edge.updated")
        self.assertEqual(graph_id, self.graph_id)
        self.assertEqual(json.loads(payload)["label"], "rel-2")

    def test_agent_stubs_return_expected_error(self) -> None:
        elicit = run_elicit(self.store, {})
        self.assertEqual(elicit["code"], -32001)
        self.assertIn("commands/elicit-context.md", elicit["message"])

        mapped = map_connections(self.store, {})
        self.assertEqual(mapped["code"], -32001)
        self.assertIn("commands/map-connections.md", mapped["message"])

        brd = generate_brd(self.store, {})
        self.assertEqual(brd["code"], -32001)
        self.assertIn("commands/generate-brd.md", brd["message"])

    def test_list_graphs_empty_and_populated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            empty_store = GraphStore(str(Path(tmp) / "store.db"))
            try:
                empty = list_graphs(empty_store, {})
            finally:
                empty_store.close()
            self.assertEqual(empty, [])

        self.store.meta_repo.save_graph_meta(
            graph_id="graph-two",
            workspace_root=self.temp_dir.name,
            workspace_path=self.temp_dir.name,
            project="project-two",
            org="org-two",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=3,
            edge_count=1,
            imported_from=None,
            generated_at="",
        )

        populated = list_graphs(self.store, {})
        self.assertEqual(len(populated), 2)
        self.assertTrue(all("id" in graph for graph in populated))
        self.assertTrue(all("org" in graph for graph in populated))
        self.assertTrue(all("project" in graph for graph in populated))
        self.assertTrue(all("node_count" in graph for graph in populated))
        self.assertTrue(all("edge_count" in graph for graph in populated))

    def test_registry_has_nine_tools_and_reads_do_not_audit(self) -> None:
        names = sorted(TOOL_REGISTRY.keys())
        self.assertEqual(len(names), 9)
        self.assertEqual(
            names,
            [
                "add_edge",
                "generate_brd",
                "get_node",
                "list_graphs",
                "list_nodes",
                "map_connections",
                "run_elicit",
                "search_graph",
                "update_node",
            ],
        )

        self.assertTrue(TOOL_REGISTRY["run_elicit"]["requires_ai_agent"])
        self.assertTrue(TOOL_REGISTRY["map_connections"]["requires_ai_agent"])
        self.assertTrue(TOOL_REGISTRY["generate_brd"]["requires_ai_agent"])

        before = self._audit_count()
        list_nodes(self.store, {"graph_id": self.graph_id})
        get_node(self.store, {"graph_id": self.graph_id, "node_id": "N-1"})
        search_graph(self.store, {"graph_id": self.graph_id, "query": "alpha"})
        after = self._audit_count()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
