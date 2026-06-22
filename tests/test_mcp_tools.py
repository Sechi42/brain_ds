from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path
from typing import Any, cast

from brain_ds.mcp.security import ValidationError, validate_tool_input
from brain_ds.ontology.entity_types import EntityType
from brain_ds.ontology.relationship_types import RelationshipType
from brain_ds.mcp.tools import (
    TOOL_REGISTRY,
    add_edge,
    create_graph,
    explore_source,
    generate_brd,
    get_node,
    import_graph,
    list_data_sources,
    list_graphs,
    list_nodes,
    list_source_connections,
    list_workspaces,
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
        # B-1: bystander node N-3 + edge N-2→N-3 seeded for isolation regression tests
        self.store.upsert_node(
            self.graph_id,
            {
                "id": "N-3",
                "label": "Gamma Ref",
                "type": "Reference",
                "supertype": "Knowledge",
                "parent_id": "ROOT",
                "details": {"summary": "Bystander target"},
            },
        )
        self.store.upsert_edge(
            self.graph_id,
            {
                "source": "N-2",
                "target": "N-3",
                "label": "references",
                "weight": 0.9,
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
            "SELECT event, graph_id, payload FROM event_outbox WHERE event != 'tool.invoked' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return (row[0], row[1], row[2])

    def _create_import_store(self) -> tuple[tempfile.TemporaryDirectory[str], GraphStore, Path]:
        project_dir = tempfile.TemporaryDirectory()
        store_dir = Path(project_dir.name) / ".brain_ds"
        store_dir.mkdir(parents=True)
        store = GraphStore(str(store_dir / "store.db"))
        return project_dir, store, Path(project_dir.name)

    def _expect_rows(self, result: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
        self.assertIsInstance(result, list)
        return cast(list[dict[str, Any]], result)

    def _expect_error(self, result: list[dict[str, Any]] | dict[str, Any]) -> dict[str, Any]:
        self.assertIsInstance(result, dict)
        return cast(dict[str, Any], result)

    # B-1: bystander-preservation regression — update_node on N-1 must not mutate N-2 or the N-2→N-3 edge
    def test_update_node_preserves_unrelated_node_and_edge(self) -> None:
        update_node(
            self.store,
            {"graph_id": self.graph_id, "node_id": "N-1", "label": "Alpha-v2"},
        )
        # N-2 fields must be unchanged
        bystander = get_node(self.store, {"graph_id": self.graph_id, "node_id": "N-2"})
        self.assertEqual(bystander["label"], "Beta Note")
        self.assertEqual(bystander["type"], "Note")
        self.assertEqual(bystander["details"]["summary"], "Secondary")
        # Edge N-2→N-3 must still exist with original weight
        edge_rows = self.store.conn.execute(
            "SELECT weight, label FROM edges WHERE graph_id=? AND source=? AND target=?",
            (self.graph_id, "N-2", "N-3"),
        ).fetchall()
        self.assertEqual(len(edge_rows), 1)
        self.assertAlmostEqual(edge_rows[0][0], 0.9, places=4)
        self.assertEqual(edge_rows[0][1], "references")
        # Total node count must be 3 (N-1, N-2, N-3)
        node_count = self.store.conn.execute(
            "SELECT COUNT(*) FROM nodes WHERE graph_id=?", (self.graph_id,)
        ).fetchone()[0]
        self.assertEqual(node_count, 3)

    # B-2: updated node reflects new values
    def test_update_node_write_takes_effect(self) -> None:
        update_node(
            self.store,
            {"graph_id": self.graph_id, "node_id": "N-1", "label": "Alpha-v2"},
        )
        refreshed = get_node(self.store, {"graph_id": self.graph_id, "node_id": "N-1"})
        self.assertEqual(refreshed["label"], "Alpha-v2")

    def test_list_nodes_filters_and_missing_graph_error(self) -> None:
        result = self._expect_rows(list_nodes(self.store, {"graph_id": self.graph_id, "type": "Task"}))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "N-1")

        by_supertype = self._expect_rows(list_nodes(self.store, {"graph_id": self.graph_id, "supertype": "Knowledge"}))
        self.assertEqual(len(by_supertype), 2)  # N-2 (Beta Note) + N-3 (Gamma Ref) both Knowledge

        by_parent = self._expect_rows(list_nodes(self.store, {"graph_id": self.graph_id, "parent_id": "ROOT"}))
        self.assertEqual(len(by_parent), 3)  # N-1, N-2, N-3 all under ROOT

        by_empty_supertype = self._expect_rows(list_nodes(self.store, {"graph_id": self.graph_id, "supertype": "  "}))
        self.assertEqual(len(by_empty_supertype), 3)  # N-1, N-2, N-3

        by_empty_type = self._expect_rows(list_nodes(self.store, {"graph_id": self.graph_id, "type": ""}))
        self.assertEqual(len(by_empty_type), 3)  # N-1, N-2, N-3

        missing_graph = self._expect_error(list_nodes(self.store, {"graph_id": "missing"}))
        self.assertEqual(missing_graph["code"], -32000)
        self.assertEqual(missing_graph["message"], "Graph 'missing' not found")

    def test_get_node_returns_row_and_not_found_error(self) -> None:
        result = get_node(self.store, {"graph_id": self.graph_id, "node_id": "N-1"})
        self.assertEqual(result["id"], "N-1")

        missing = get_node(self.store, {"graph_id": self.graph_id, "node_id": "N-404"})
        self.assertEqual(missing["code"], -32000)
        self.assertEqual(missing["message"], "Node 'N-404' not found in graph 'graph-tools'")

    def test_search_graph_matches_substrings_and_validates_query_type(self) -> None:
        by_label = self._expect_rows(search_graph(self.store, {"graph_id": self.graph_id, "query": "alpha"}))
        self.assertEqual([item["id"] for item in by_label], ["N-1"])

        by_type = self._expect_rows(search_graph(self.store, {"graph_id": self.graph_id, "query": "note"}))
        self.assertEqual([item["id"] for item in by_type], ["N-2"])

        by_details = self._expect_rows(search_graph(self.store, {"graph_id": self.graph_id, "query": "mapping"}))
        self.assertEqual([item["id"] for item in by_details], ["N-1"])

        no_match = self._expect_rows(search_graph(self.store, {"graph_id": self.graph_id, "query": "zzz"}))
        self.assertEqual(no_match, [])

        missing_graph = self._expect_error(search_graph(self.store, {"graph_id": "missing", "query": "x"}))
        self.assertEqual(missing_graph["code"], -32000)
        self.assertEqual(missing_graph["message"], "Graph 'missing' not found")

        invalid = self._expect_error(search_graph(self.store, {"graph_id": self.graph_id, "query": 42}))
        self.assertEqual(invalid["code"], -32602)
        self.assertIn("Expected string for query", invalid["message"])

    def test_tool_registry_and_schema_inventory_match_twenty_four_tools(self) -> None:
        self.assertEqual(len(TOOL_REGISTRY), 24)

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
                "node_id": "N-new",
                "label": "Gamma",
                "type": "Task",
                "supertype": "Work",
                "details": {"summary": "new"},
            },
        )
        self.assertEqual(created["id"], "N-new")

        event, graph_id, payload = self._last_outbox_event()
        self.assertEqual(event, "node.created")
        self.assertEqual(graph_id, self.graph_id)
        self.assertEqual(json.loads(payload)["id"], "N-new")

    def test_update_node_enqueues_node_updated(self) -> None:
        updated = update_node(self.store, {"graph_id": self.graph_id, "node_id": "N-1", "label": "Renamed"})
        self.assertEqual(updated["label"], "Renamed")

        event, graph_id, payload = self._last_outbox_event()
        self.assertEqual(event, "node.updated")
        self.assertEqual(graph_id, self.graph_id)
        self.assertEqual(json.loads(payload)["id"], "N-1")

    def test_update_node_enqueues_tool_invoked_ok(self) -> None:
        update_node(self.store, {"graph_id": self.graph_id, "node_id": "N-1", "label": "Renamed"})

        row = self.store.conn.execute(
            "SELECT event, graph_id, payload FROM event_outbox WHERE event = 'tool.invoked' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "tool.invoked")
        self.assertEqual(row[1], self.graph_id)
        payload = json.loads(row[2])
        self.assertEqual(payload["tool"], "update_node")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["target_id"], "N-1")
        self.assertIn("N-1", payload["params_summary"])

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

    def test_update_node_rejects_unknown_card_section_key_and_keeps_store_clean(self) -> None:
        rejected = update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "N-1",
                "card_sections": [{"title": "Risks", "body": "Budget overrun", "icon": "", "order": 1}],
            },
        )

        self.assertEqual(rejected["code"], -32602)
        self.assertIn("body", rejected["message"])

        reread = get_node(self.store, {"graph_id": self.graph_id, "node_id": "N-1"})
        self.assertIsNone(reread.get("card_sections"))

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

    def test_add_edge_error_receipt(self) -> None:
        add_edge(
            self.store,
            {"graph_id": self.graph_id, "source": "N-404", "target": "N-2", "label": "rel"},
        )
        row = self.store.conn.execute(
            "SELECT event, graph_id, payload FROM event_outbox WHERE event = 'tool.invoked' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "tool.invoked")
        self.assertEqual(row[1], self.graph_id)
        payload = json.loads(row[2])
        self.assertEqual(payload["tool"], "add_edge")
        self.assertEqual(payload["status"], "error")
        self.assertIn("N-404", payload["params_summary"])

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

    # Task 1.9 — per-tool error tests (split from test_agent_stubs_return_expected_error).
    # Handlers still raise -32001 in PR1; tests stay GREEN until PR2-4 flip them.

    def test_run_elicit_returns_context(self) -> None:
        result = run_elicit(self.store, {})
        # Must not return an error code — R1 spec: no -32001.
        self.assertNotIn("code", result)
        # entity_types length matches live enum — R5.
        self.assertEqual(len(result["entity_types"]), len(list(EntityType)))
        # supertypes is a sorted list with entries.
        supertypes = result["supertypes"]
        self.assertIsInstance(supertypes, list)
        self.assertGreater(len(supertypes), 0)
        self.assertEqual(supertypes, sorted(supertypes))
        # expected_sections keys match entity type values.
        expected_keys = {e.value for e in EntityType}
        self.assertEqual(set(result["expected_sections"].keys()), expected_keys)
        # relationship_types length matches live enum — R5.
        self.assertEqual(len(result["relationship_types"]), len(list(RelationshipType)))
        # base_weights length matches live enum — R5.
        self.assertEqual(len(result["base_weights"]), len(list(RelationshipType)))
        # Category-2 keys are truthy.
        self.assertTrue(result["question_bank"])
        self.assertTrue(result["org_slug_rules"])
        self.assertTrue(result["node_id_format"])
        self.assertTrue(result["node_write_templates"])

    def test_map_connections_returns_context(self) -> None:
        from brain_ds.scoring.engine import ScoringEngine

        result = map_connections(self.store, {})
        # Must not return an error code — R2 spec: no -32001.
        self.assertNotIn("code", result)
        # entity_types length matches live enum — R5.
        self.assertEqual(len(result["entity_types"]), len(list(EntityType)))
        # connection_rules is truthy (non-empty).
        self.assertTrue(result["connection_rules"])
        # relationship_labels length matches live enum — R5.
        self.assertEqual(len(result["relationship_labels"]), len(list(RelationshipType)))
        # scoring_factors length matches ScoringEngine factor_weights — R2.
        self.assertEqual(len(result["scoring_factors"]), len(ScoringEngine().factor_weights))
        # B1 boundary: result MUST NOT contain computed connections or edges keys.
        self.assertNotIn("connections", result)
        self.assertNotIn("edges", result)

    def test_generate_brd_returns_context(self) -> None:
        result = generate_brd(self.store, {})
        # Must not return an error code — R3 spec: no -32001.
        self.assertNotIn("code", result)
        # entity_types length matches live enum — R5.
        self.assertEqual(len(result["entity_types"]), len(list(EntityType)))
        # brd_section_order has 14 entries — design contract.
        self.assertEqual(len(result["brd_section_order"]), 14)
        # section_rules is truthy (non-empty).
        self.assertTrue(result["section_rules"])
        # completeness_matrix_template is truthy.
        self.assertTrue(result["completeness_matrix_template"])
        # B1 boundary: result MUST NOT contain a computed brd or document key.
        self.assertNotIn("brd", result)
        self.assertNotIn("document", result)

    # Task 1.8 — schema validation tests (RED until Task 1.7 adds schemas to TOOL_SCHEMAS).

    def test_run_elicit_valid_input_passes_schema(self) -> None:
        result = validate_tool_input("run_elicit", {})
        self.assertIsInstance(result, dict)

    def test_map_connections_valid_input_passes_schema(self) -> None:
        result = validate_tool_input("map_connections", {})
        self.assertIsInstance(result, dict)

    def test_generate_brd_valid_input_passes_schema(self) -> None:
        result = validate_tool_input("generate_brd", {})
        self.assertIsInstance(result, dict)

    # Task S1 — negative-path schema tests: additionalProperties: False must reject unknown keys.

    def test_run_elicit_invalid_input_raises(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            validate_tool_input("run_elicit", {"bogus": 1})
        self.assertEqual(ctx.exception.code, -32602)

    def test_map_connections_invalid_input_raises(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            validate_tool_input("map_connections", {"bogus": 1})
        self.assertEqual(ctx.exception.code, -32602)

    def test_generate_brd_invalid_input_raises(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            validate_tool_input("generate_brd", {"bogus": 1})
        self.assertEqual(ctx.exception.code, -32602)

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

    def test_create_graph_tool(self) -> None:
        result = create_graph(
            self.store,
            {"graph_id": "logitrans", "name": "Logitrans", "project": "brain-ds"},
        )

        self.assertEqual(result["id"], "logitrans")
        self.assertEqual(result["org"], "Logitrans")
        self.assertEqual(result["node_count"], 0)
        self.assertEqual(result["edge_count"], 0)

    def test_create_graph_duplicate(self) -> None:
        create_graph(self.store, {"graph_id": "logitrans"})

        duplicate = create_graph(self.store, {"graph_id": "logitrans"})
        self.assertEqual(duplicate["code"], -32000)
        self.assertEqual(duplicate["message"], "Graph 'logitrans' already exists")

    def test_import_graph_tool(self) -> None:
        project_dir, store, project_root = self._create_import_store()
        try:
            payload = {
                "schema_version": "2.0.0",
                "org": "Logitrans",
                "generated_at": "",
                "nodes": [
                    {
                        "id": "ds-1",
                        "label": "ERP",
                        "type": "Data Source",
                        "details": {"owner": "ops"},
                        "supertype": "data",
                        "parent_id": None,
                        "depth": 0,
                    }
                ],
                "edges": [],
                "evidence": [],
            }
            source_path = project_root / "seed.json"
            source_path.write_text(json.dumps(payload), encoding="utf-8")

            result = import_graph(store, {"file_path": str(source_path), "graph_id": "logitrans"})

            self.assertEqual(result["graph_id"], "logitrans")
            self.assertEqual(result["node_count"], 1)
            self.assertEqual(len(store.query_nodes("logitrans")), 1)
        finally:
            store.close()
            project_dir.cleanup()

    def test_import_graph_path_traversal_rejected(self) -> None:
        project_dir, store, project_root = self._create_import_store()
        try:
            outside_dir = Path(project_root).parent
            outside_path = outside_dir / "outside-seed.json"
            outside_path.write_text("{}", encoding="utf-8")

            escaped = import_graph(store, {"file_path": str(project_root / ".." / outside_path.name)})

            self.assertEqual(escaped["code"], -32000)
            self.assertIn("Path traversal", escaped["message"])
        finally:
            if outside_path.exists():
                outside_path.unlink()
            store.close()
            project_dir.cleanup()

    def test_list_data_sources(self) -> None:
        update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "DS-1",
                "label": "ERP",
                "type": "Data Source",
                "supertype": "data",
                "details": {"owner": "ops"},
            },
        )

        result = self._expect_rows(list_data_sources(self.store, {"graph_id": self.graph_id}))

        self.assertEqual([item["id"] for item in result], ["DS-1"])
        typed = self._expect_rows(list_nodes(self.store, {"graph_id": self.graph_id, "type": "Data Source"}))
        self.assertEqual(result, typed)

    def test_registry_has_twenty_four_tools_and_reads_do_not_audit(self) -> None:
        names = sorted(TOOL_REGISTRY.keys())
        self.assertEqual(len(names), 24)
        self.assertEqual(
            names,
            [
                "add_edge",
                "assess_completeness",
                "create_graph",
                "delete_edge",
                "delete_node",
                "explore_source",
                "generate_brd",
                "get_node",
                "get_weak_edges",
                "import_graph",
                "list_data_sources",
                "list_graphs",
                "list_nodes",
                "list_secret_handles",
                "list_source_connections",
                "list_workspaces",
                "map_connections",
                "open_workspace",
                "query_source",
                "run_elicit",
                "search_graph",
                "suggest_connections",
                "update_node",
                "validate_secret_handle",
            ],
        )

        # Task 1.11 — flipped to assertFalse after registry update in Task 1.10.
        self.assertFalse(TOOL_REGISTRY["run_elicit"]["requires_ai_agent"])
        self.assertFalse(TOOL_REGISTRY["map_connections"]["requires_ai_agent"])
        self.assertFalse(TOOL_REGISTRY["generate_brd"]["requires_ai_agent"])

        before = self._audit_count()
        list_nodes(self.store, {"graph_id": self.graph_id})
        get_node(self.store, {"graph_id": self.graph_id, "node_id": "N-1"})
        search_graph(self.store, {"graph_id": self.graph_id, "query": "alpha"})
        after = self._audit_count()
        self.assertEqual(before, after)


class PaginatedListToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / ".brain_ds" / "store.db"
        self.db_path.parent.mkdir(parents=True)
        self.store = GraphStore(str(self.db_path))
        self.graph_id = "paginated-tools"
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

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def test_list_source_connections_returns_bounded_page_with_next_offset(self) -> None:
        for index in range(25):
            update_node(
                self.store,
                {
                    "graph_id": self.graph_id,
                    "node_id": f"DS-{index:02d}",
                    "label": f"Source {index:02d}",
                    "type": "Data Source",
                    "details": {"connection": {"kind": "sqlite", "path": f"data/{index}.db"}},
                },
            )

        page = list_source_connections(self.store, {"graph_id": self.graph_id, "limit": 10, "offset": 5})

        self.assertEqual(page["limit"], 10)
        self.assertEqual(page["offset"], 5)
        self.assertEqual(page["next_offset"], 15)
        self.assertEqual(len(page["connections"]), 10)
        self.assertEqual(page["connections"][0]["node_id"], "DS-05")

    def test_list_source_connections_compact_mode_omits_connection_payload(self) -> None:
        update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "DS-1",
                "label": "Source 1",
                "type": "Data Source",
                "details": {"connection": {"kind": "sqlite", "path": "data/source.db"}},
            },
        )

        page = list_source_connections(self.store, {"graph_id": self.graph_id, "compact": True})

        self.assertEqual(page["connections"], [{"graph_id": self.graph_id, "node_id": "DS-1", "label": "Source 1"}])

    def test_list_workspaces_schema_accepts_pagination_and_compact(self) -> None:
        params = validate_tool_input(
            "list_workspaces",
            {"limit": 20, "offset": 0, "compact": True},
        )

        self.assertEqual(params["limit"], 20)
        self.assertTrue(params["compact"])

    def test_list_workspaces_returns_page_metadata(self) -> None:
        page = list_workspaces(self.store, {"limit": 1, "offset": 0, "compact": True})

        self.assertIn("workspaces", page)
        self.assertEqual(page["limit"], 1)
        self.assertEqual(page["offset"], 0)
        self.assertIn("total", page)


class ExploreSourceDocumentationLevelTests(unittest.TestCase):
    """DDS-4/DDS-5: explore_source level='documentation' returns joined doc bundle."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        store_dir = Path(self.temp_dir.name) / ".brain_ds"
        store_dir.mkdir(parents=True)
        self.store = GraphStore(str(store_dir / "store.db"))
        self.graph_id = "ds-docs-graph"
        self.store.meta_repo.save_graph_meta(
            graph_id=self.graph_id,
            workspace_root=self.temp_dir.name,
            workspace_path=self.temp_dir.name,
            project="project-docs",
            org="org-docs",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at="",
        )
        # Data Source node
        self.store.upsert_node(
            self.graph_id,
            {
                "id": "ds-1",
                "label": "Warehouse DB",
                "type": "Data Source",
                "details": {
                    "what": "Main warehouse",
                    "connection": {"kind": "sqlite", "path": "data/store.db"},
                },
            },
        )
        # Child table-level node with columns card section
        self.store.upsert_node(
            self.graph_id,
            {
                "id": "tbl-orders",
                "label": "orders",
                "type": "Unknown",
                "parent_id": "ds-1",
                "card_sections": [
                    {
                        "title": "Columns / Fields",
                        "content": "| col | type |\n|---|---|\n| id | int |",
                        "icon": "table",
                        "order": 1,
                    },
                    {
                        "title": "Purpose",
                        "content": "Order tracking table.",
                        "icon": "info",
                        "order": 2,
                    },
                ],
            },
        )
        # Add an edge to create a relationship
        self.store.upsert_edge(
            self.graph_id,
            {"source": "ds-1", "target": "tbl-orders", "label": "uses", "weight": 0.9},
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def test_explore_source_documentation_level_returns_bundle(self):
        from brain_ds.mcp.tools import explore_source

        result = explore_source(
            self.store,
            {"graph_id": self.graph_id, "node_id": "ds-1", "level": "documentation"},
        )
        self.assertNotIn("code", result, f"Expected success, got error: {result}")
        self.assertEqual(result["level"], "documentation")

    def test_explore_source_documentation_level_contains_tables(self):
        from brain_ds.mcp.tools import explore_source

        result = explore_source(
            self.store,
            {"graph_id": self.graph_id, "node_id": "ds-1", "level": "documentation"},
        )
        self.assertIn("tables", result)
        self.assertEqual(len(result["tables"]), 1)

    def test_explore_source_documentation_level_table_entry_has_columns_markdown(self):
        from brain_ds.mcp.tools import explore_source

        result = explore_source(
            self.store,
            {"graph_id": self.graph_id, "node_id": "ds-1", "level": "documentation"},
        )
        orders = result["tables"][0]
        self.assertEqual(orders["node_id"], "tbl-orders")
        self.assertIn("columns_markdown", orders)
        self.assertIn("| id | int |", orders["columns_markdown"])

    def test_explore_source_documentation_level_tool_count_unchanged(self):
        """DDS-4: tool count MUST stay 24 after adding level='documentation'."""
        self.assertEqual(len(TOOL_REGISTRY), 24)

    def test_explore_source_schema_accepts_level_param(self):
        """DDS-4: explore_source schema must accept optional level string."""
        from brain_ds.mcp.security import TOOL_SCHEMAS, validate_tool_input

        result = validate_tool_input(
            "explore_source",
            {
                "graph_id": self.graph_id,
                "node_id": "ds-1",
                "level": "documentation",
            },
            TOOL_SCHEMAS["explore_source"],
        )
        self.assertEqual(result["level"], "documentation")


class DataSourceInternalHierarchyToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / ".brain_ds" / "store.db"
        self.db_path.parent.mkdir(parents=True)
        self.store = GraphStore(str(self.db_path))
        self.graph_id = "internal-hierarchy"
        self.store.meta_repo.save_graph_meta(
            graph_id=self.graph_id,
            workspace_root=self.temp_dir.name,
            workspace_path=self.temp_dir.name,
            project="project-internal",
            org="org-internal",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at="",
        )
        update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "ds-1",
                "label": "Warehouse",
                "type": "Data Source",
                "supertype": "data",
                "details": {"connection": {"kind": "sqlite", "path": "warehouse.db"}},
            },
        )
        update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "ds-2",
                "label": "Reporting",
                "type": "Data Source",
                "supertype": "data",
                "details": {"connection": {"kind": "csv", "path": "reporting.csv"}},
            },
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def test_update_node_accepts_parent_id_depth_for_internal_child_under_data_source(self) -> None:
        created = update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "schema-main",
                "label": "main",
                "type": "DataContainer",
                "parent_id": "ds-1",
                "depth": 1,
                "details": {"kind": "schema"},
            },
        )

        self.assertEqual(created["parent_id"], "ds-1")
        self.assertEqual(created["depth"], 1)
        self.assertEqual(created["details"]["kind"], "schema")

    def test_update_node_allows_internal_descendant_with_data_source_ancestor(self) -> None:
        update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "schema-main",
                "label": "main",
                "type": "DataContainer",
                "parent_id": "ds-1",
                "depth": 1,
                "details": {"kind": "schema"},
            },
        )

        field = update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "field-order-id",
                "label": "order_id",
                "type": "DataField",
                "parent_id": "schema-main",
                "depth": 2,
                "details": {"kind": "column"},
            },
        )

        self.assertEqual(field["parent_id"], "schema-main")
        self.assertEqual(field["details"]["kind"], "column")

    def test_update_node_rejects_internal_child_without_data_source_ancestor(self) -> None:
        result = update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "orphan-table",
                "label": "orders",
                "type": "DataContainer",
                "parent_id": "missing-parent",
                "depth": 1,
                "details": {"kind": "table"},
            },
        )

        self.assertEqual(result["code"], -32000)
        self.assertIn("scope_violation", result["message"])

    def test_update_node_rejects_internal_child_whose_parent_chain_cycles(self) -> None:
        self.store.upsert_node(
            self.graph_id,
            {
                "id": "cycle-a",
                "label": "cycle a",
                "type": "DataContainer",
                "parent_id": "cycle-b",
                "depth": 1,
                "details": {"kind": "schema"},
            },
        )
        self.store.upsert_node(
            self.graph_id,
            {
                "id": "cycle-b",
                "label": "cycle b",
                "type": "DataContainer",
                "parent_id": "cycle-a",
                "depth": 1,
                "details": {"kind": "table"},
            },
        )

        result = update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "cycle-field",
                "label": "field",
                "type": "DataField",
                "parent_id": "cycle-a",
                "depth": 2,
                "details": {"kind": "column"},
            },
        )

        self.assertEqual(result["code"], -32000)
        self.assertIn("scope_violation", result["message"])
        self.assertIn("cycle", result["message"])

    def test_update_node_validates_container_and_field_detail_kinds(self) -> None:
        bad_container = update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "bad-container",
                "label": "bad",
                "type": "DataContainer",
                "parent_id": "ds-1",
                "depth": 1,
                "details": {"kind": "column"},
            },
        )
        bad_field = update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "bad-field",
                "label": "bad",
                "type": "DataField",
                "parent_id": "ds-1",
                "depth": 1,
                "details": {"kind": "table"},
            },
        )

        self.assertEqual(bad_container["code"], -32602)
        self.assertIn("DataContainer details.kind", bad_container["message"])
        self.assertEqual(bad_field["code"], -32602)
        self.assertIn("DataField details.kind", bad_field["message"])

    def test_list_nodes_filters_internal_nodes_by_details_kind_and_source_id(self) -> None:
        for node_id, source_id, kind in (
            ("ds1-orders", "ds-1", "table"),
            ("ds1-customers", "ds-1", "view"),
            ("ds2-orders", "ds-2", "table"),
        ):
            update_node(
                self.store,
                {
                    "graph_id": self.graph_id,
                    "node_id": node_id,
                    "label": node_id,
                    "type": "DataContainer",
                    "parent_id": source_id,
                    "depth": 1,
                    "details": {"kind": kind},
                },
            )

        rows = list_nodes(
            self.store,
            {
                "graph_id": self.graph_id,
                "type": "DataContainer",
                "details_kind": "table",
                "source_id": "ds-1",
            },
        )

        self.assertEqual([row["id"] for row in rows], ["ds1-orders"])

    def test_explore_source_internal_returns_source_template_and_nested_subtree(self) -> None:
        update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "schema-main",
                "label": "main",
                "type": "DataContainer",
                "parent_id": "ds-1",
                "depth": 1,
                "details": {"kind": "schema"},
            },
        )
        update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "table-orders",
                "label": "orders",
                "type": "DataContainer",
                "parent_id": "schema-main",
                "depth": 2,
                "details": {"kind": "table"},
            },
        )
        update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "column-id",
                "label": "id",
                "type": "DataField",
                "parent_id": "table-orders",
                "depth": 3,
                "details": {"kind": "column"},
            },
        )

        result = explore_source(
            self.store,
            {"graph_id": self.graph_id, "node_id": "ds-1", "level": "internal"},
        )

        self.assertEqual(result["level"], "internal")
        self.assertEqual(result["source"]["node_id"], "ds-1")
        self.assertEqual(result["template"]["source_kind"], "relational-db")
        self.assertEqual(result["internal_subtree"][0]["id"], "schema-main")
        self.assertEqual(result["internal_subtree"][0]["children"][0]["id"], "table-orders")
        self.assertEqual(result["internal_subtree"][0]["children"][0]["children"][0]["id"], "column-id")

    def test_source_kind_hierarchy_templates_are_derived_into_grounding_context(self) -> None:
        from brain_ds.mcp import grounding

        templates = grounding.SOURCE_KIND_HIERARCHY_TEMPLATES
        self.assertEqual(templates["relational-db"][0]["kind"], "schema")
        self.assertIn("column", templates["relational-db"][1]["children"][0]["children"])
        self.assertIn("Data Source Hierarchy Documentation", grounding.NODE_WRITE_TEMPLATES["Data Source"]["hierarchy_template"])
        self.assertIn("relational-db", grounding.NODE_WRITE_TEMPLATES["Data Source"]["hierarchy_template"])


class SourceDocumentationBundleContractTests(unittest.TestCase):
    """DDS-7: SOURCE_DOCUMENTATION_BUNDLE_CONTRACT must be registered in grounding."""

    def test_constant_exists(self):
        from brain_ds.mcp import grounding

        self.assertTrue(hasattr(grounding, "SOURCE_DOCUMENTATION_BUNDLE_CONTRACT"))

    def test_constant_is_dict(self):
        from brain_ds.mcp import grounding

        self.assertIsInstance(grounding.SOURCE_DOCUMENTATION_BUNDLE_CONTRACT, dict)

    def test_constant_has_required_keys(self):
        from brain_ds.mcp import grounding

        contract = grounding.SOURCE_DOCUMENTATION_BUNDLE_CONTRACT
        for key in ("description", "mcp_call", "response_shape", "agent_answerability"):
            with self.subTest(key=key):
                self.assertIn(key, contract)

    def test_constant_in_elicit_context(self):
        from brain_ds.mcp import grounding

        ctx = grounding.elicit_context()
        self.assertIn("source_documentation_bundle_contract", ctx)

    def test_constant_in_map_connections_context(self):
        from brain_ds.mcp import grounding

        ctx = grounding.map_connections_context()
        self.assertIn("source_documentation_bundle_contract", ctx)


if __name__ == "__main__":
    unittest.main()
