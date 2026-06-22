import unittest
import logging
import json
from pathlib import Path, PurePosixPath

from brain_ds.ontology import Graph
from brain_ds.ui.render_context import WorkspaceContext, build_render_context
from brain_ds.ui.workspace_storage_contract import (
    HISTORY_MAX_ENTRIES,
    TabModel,
    load_tabs_payload,
    parse_history_payload,
)


def _sample_graph_payload() -> dict:
    return {
        "org": "Acme",
        "generated_at": "2026-03-01T08:00:00Z",
        "nodes": [
            {"id": "a", "label": "A", "type": "Department", "evidence_ids": ["ev-1", "ev-2"]},
            {"id": "b", "label": "B", "type": "Role", "evidence_ids": ["ev-1"]},
            {"id": "x", "label": "X", "type": "Role"},
        ],
        "edges": [
            {"source": "a", "target": "b", "label": "uses", "weight": 0.123456789},
        ],
        "evidence": [
            {"id": "ev-1", "type": "observation", "source": "engram", "content": "First", "timestamp": "2026-01-01T10:00:00Z"},
            {"id": "ev-2", "type": "observation", "source": "engram", "content": "Second", "timestamp": "2026-05-14T12:30:00Z"},
        ],
    }


class TestRenderContextContract(unittest.TestCase):
    def test_contract_version_is_one_zero_zero(self):
        context = build_render_context(Graph.from_v1(_sample_graph_payload()))
        self.assertIn("contract_version", context)
        self.assertEqual(context["contract_version"], "1.0.0")

    def test_meta_workspace_present_and_well_formed(self):
        graph = Graph.from_v1(_sample_graph_payload())
        workspace = WorkspaceContext.from_root_and_graph(
            Path("/workspace"),
            Path("/workspace/acme-corp/billing/v2-graph.json"),
        )
        context = build_render_context(graph, workspace=workspace)
        meta_workspace = context["meta"]["workspace"]

        self.assertTrue(meta_workspace["root"].endswith("workspace"))
        self.assertEqual(meta_workspace["displayPath"], "acme-corp/billing/v2-graph.json")
        self.assertEqual(meta_workspace["project"], "acme-corp")
        self.assertEqual(meta_workspace["graph"], "v2-graph")

    def test_meta_workspace_depth_zero_fallback(self):
        graph = Graph.from_v1(_sample_graph_payload())
        workspace = WorkspaceContext.from_root_and_graph(Path("/workspace"), Path("/workspace/my-graph.json"))
        context = build_render_context(graph, workspace=workspace)

        self.assertEqual(context["meta"]["workspace"]["displayPath"], "my-graph.json")
        self.assertEqual(context["meta"]["workspace"]["project"], "workspace")

    def test_meta_workspace_depth_one_project_only(self):
        graph = Graph.from_v1(_sample_graph_payload())
        workspace = WorkspaceContext.from_root_and_graph(
            Path("/ws"),
            Path("/ws/acme-corp/billing/2026/v3-graph.json"),
        )
        context = build_render_context(graph, workspace=workspace)

        self.assertEqual(context["meta"]["workspace"]["project"], "acme-corp")

    def test_meta_workspace_display_path_uses_posix_slashes(self):
        graph = Graph.from_v1(_sample_graph_payload())
        workspace = WorkspaceContext.from_root_and_graph(
            Path("C:/workspace"),
            Path("C:/workspace/acme-corp/billing/v2-graph.json"),
        )
        context = build_render_context(graph, workspace=workspace)

        display_path = context["meta"]["workspace"]["displayPath"]
        self.assertNotIn("\\", display_path)
        self.assertEqual(str(PurePosixPath(display_path)), display_path)

    def test_meta_graph_id_populated(self):
        graph = Graph.from_v1(_sample_graph_payload())
        workspace = WorkspaceContext.from_root_and_graph(
            Path("/workspace"),
            Path("/workspace/acme-corp/billing/v2-graph.json"),
        )

        context = build_render_context(graph, workspace=workspace, graph_id="g1")

        self.assertEqual(context["meta"]["graph_id"], "g1")

    def test_every_node_has_score(self):
        context = build_render_context(Graph.from_v1(_sample_graph_payload()))
        for node in context["nodes"]:
            self.assertIn("score", node)

    def test_node_score_is_max_of_incident_edge_scores(self):
        context = build_render_context(Graph.from_v1(_sample_graph_payload()))
        by_id = {node["id"]: node for node in context["nodes"]}
        self.assertEqual(by_id["a"]["score"], 0.123456789)

    def test_node_score_with_single_incident_edge_matches_that_edge(self):
        context = build_render_context(Graph.from_v1(_sample_graph_payload()))
        by_id = {node["id"]: node for node in context["nodes"]}
        self.assertEqual(by_id["b"]["score"], 0.123456789)

    def test_isolated_node_score_is_zero(self):
        context = build_render_context(Graph.from_v1(_sample_graph_payload()))
        by_id = {node["id"]: node for node in context["nodes"]}
        self.assertEqual(by_id["x"]["score"], 0.0)

    def test_node_score_full_float_precision(self):
        context = build_render_context(Graph.from_v1(_sample_graph_payload()))
        by_id = {node["id"]: node for node in context["nodes"]}
        self.assertEqual(by_id["a"]["score"], 0.123456789)

    def test_node_score_never_undefined(self):
        context = build_render_context(Graph.from_v1(_sample_graph_payload()))
        for node in context["nodes"]:
            self.assertIsInstance(node["score"], float)

    def test_every_node_has_updated_at(self):
        context = build_render_context(Graph.from_v1(_sample_graph_payload()))
        for node in context["nodes"]:
            self.assertIn("updated_at", node)

    def test_node_updated_at_is_max_incident_evidence_timestamp(self):
        context = build_render_context(Graph.from_v1(_sample_graph_payload()))
        by_id = {node["id"]: node for node in context["nodes"]}
        self.assertEqual(by_id["a"]["updated_at"], "2026-05-14T12:30:00Z")

    def test_isolated_node_updated_at_falls_back_to_meta_generated_at(self):
        context = build_render_context(Graph.from_v1(_sample_graph_payload()))
        by_id = {node["id"]: node for node in context["nodes"]}
        self.assertEqual(by_id["x"]["updated_at"], context["meta"]["generated_at"])

    def test_updated_at_format_matches_locked_pattern(self):
        context = build_render_context(Graph.from_v1(_sample_graph_payload()))
        for node in context["nodes"]:
            self.assertRegex(node["updated_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_every_node_has_neighbor_count(self):
        context = build_render_context(Graph.from_v1(_sample_graph_payload()))
        for node in context["nodes"]:
            self.assertIn("neighbor_count", node)
            self.assertIsInstance(node["neighbor_count"], int)

    def test_neighbor_count_isolated_is_zero(self):
        context = build_render_context(Graph.from_v1(_sample_graph_payload()))
        by_id = {node["id"]: node for node in context["nodes"]}
        self.assertEqual(by_id["x"]["neighbor_count"], 0)

    def test_neighbor_count_matches_adjacency(self):
        context = build_render_context(Graph.from_v1(_sample_graph_payload()))
        by_id = {node["id"]: node for node in context["nodes"]}
        self.assertEqual(by_id["a"]["neighbor_count"], len(context["adjacency"]["a"]))
        self.assertEqual(by_id["b"]["neighbor_count"], len(context["adjacency"]["b"]))

    def test_data_source_detail_node_exposes_connection_for_explorable_badge(self):
        graph = Graph.from_v1(
            {
                "org": "Acme",
                "generated_at": "2026-03-01T08:00:00Z",
                "nodes": [
                    {
                        "id": "source-1",
                        "label": "Warehouse",
                        "type": "Data Source",
                        "details": {
                            "connection": {
                                "kind": "aws-postgres",
                                "secret_handle": "warehouse/prod",
                                "database": "orders",
                            }
                        },
                    }
                ],
                "edges": [],
                "evidence": [],
            }
        )

        context = build_render_context(graph)

        detail_node = context["detail_index"]["source-1"]["node"]
        self.assertEqual(detail_node["connection"]["kind"], "aws-postgres")
        self.assertEqual(detail_node["connection"]["secret_handle"], "warehouse/prod")

    def test_history_payload_is_bounded_and_trims_overflow(self):
        history = [f"acme/graph-{idx}.json" for idx in range(HISTORY_MAX_ENTRIES + 5)]
        raw = json.dumps(history)

        parsed = parse_history_payload(raw)

        self.assertEqual(len(parsed), HISTORY_MAX_ENTRIES)
        self.assertEqual(parsed[0], "acme/graph-0.json")
        self.assertEqual(parsed[-1], f"acme/graph-{HISTORY_MAX_ENTRIES - 1}.json")

    def test_tabs_payload_malformed_json_recovers_to_default_and_logs(self):
        logger = logging.getLogger("tests.workspace_storage_contract")

        with self.assertLogs(logger, level="ERROR") as logs:
            tabs, should_reset = load_tabs_payload("{not-json", logger=logger)

        self.assertEqual(tabs, [])
        self.assertTrue(should_reset)
        self.assertIn("resetting to []", "\n".join(logs.output))

    def test_tabs_payload_wrong_type_recovers_to_default_and_logs(self):
        logger = logging.getLogger("tests.workspace_storage_contract")

        with self.assertLogs(logger, level="ERROR") as logs:
            tabs, should_reset = load_tabs_payload('{"id":"x"}', logger=logger)

        self.assertEqual(tabs, [])
        self.assertTrue(should_reset)
        self.assertIn("Invalid tabs payload shape", "\n".join(logs.output))

    def test_tabs_payload_valid_array_parses_without_reset(self):
        raw = json.dumps(
            [
                {
                    "id": "tab-1",
                    "label": "graph",
                    "graphPath": "acme/graph.json",
                    "active": True,
                    "closeable": False,
                    "openedAt": "2026-05-20T12:00:00Z",
                }
            ]
        )

        tabs, should_reset = load_tabs_payload(raw)

        self.assertEqual(len(tabs), 1)
        self.assertIsInstance(tabs[0], TabModel)
        self.assertFalse(should_reset)


def _datasource_graph_payload() -> dict:
    """Graph with one Data Source and two child table-level nodes."""
    return {
        "org": "Acme",
        "generated_at": "2026-06-01T00:00:00Z",
        "nodes": [
            {
                "id": "ds-1",
                "label": "Warehouse DB",
                "type": "Data Source",
                "parent_id": None,
                "details": {"connection": {"kind": "aws-postgres", "secret_handle": "wh/prod", "database": "wh"}},
            },
            {
                "id": "tbl-orders",
                "label": "orders",
                "type": "Unknown",
                "parent_id": "ds-1",
                "card_sections": [
                    {"title": "Columns / Fields", "content": "| col | type |\n|---|---|\n| id | int |", "icon": "table", "order": 1},
                    {"title": "Purpose", "content": "Order tracking.", "icon": "info", "order": 2},
                ],
            },
            {
                "id": "tbl-customers",
                "label": "customers",
                "type": "Unknown",
                "parent_id": "ds-1",
                "card_sections": [
                    {"title": "Columns / Fields", "content": "| col | type |\n|---|---|\n| cid | int |", "icon": "table", "order": 1},
                ],
            },
        ],
        "edges": [
            {"source": "ds-1", "target": "tbl-orders", "label": "uses"},
            {"source": "ds-1", "target": "tbl-customers", "label": "uses"},
        ],
        "evidence": [],
    }


class TestDocumentationDigestContract(unittest.TestCase):
    """DDS-1/DDS-2: Data Source detail index must expose documentation_digest."""

    def _context(self):
        return build_render_context(Graph.from_v1(_datasource_graph_payload()))

    def test_data_source_detail_has_documentation_digest_key(self):
        ctx = self._context()
        detail = ctx["detail_index"]["ds-1"]
        self.assertIn("documentation_digest", detail)

    def test_documentation_digest_contains_tables_list(self):
        ctx = self._context()
        digest = ctx["detail_index"]["ds-1"]["documentation_digest"]
        self.assertIn("tables", digest)

    def test_documentation_digest_tables_count(self):
        ctx = self._context()
        digest = ctx["detail_index"]["ds-1"]["documentation_digest"]
        self.assertEqual(len(digest["tables"]), 2)

    def test_documentation_digest_table_entry_has_required_keys(self):
        ctx = self._context()
        digest = ctx["detail_index"]["ds-1"]["documentation_digest"]
        for entry in digest["tables"]:
            with self.subTest(table=entry.get("node_id")):
                self.assertIn("node_id", entry)
                self.assertIn("label", entry)
                self.assertIn("sections", entry)

    def test_documentation_digest_columns_section_present(self):
        """Each table entry must expose a columns_markdown key from its card_sections."""
        ctx = self._context()
        digest = ctx["detail_index"]["ds-1"]["documentation_digest"]
        orders = next(t for t in digest["tables"] if t["node_id"] == "tbl-orders")
        self.assertIn("columns_markdown", orders)
        self.assertIn("| id | int |", orders["columns_markdown"])

    def test_documentation_digest_non_datasource_node_has_no_digest(self):
        """Table-level nodes themselves must NOT get a documentation_digest key."""
        ctx = self._context()
        detail = ctx["detail_index"]["tbl-orders"]
        self.assertNotIn("documentation_digest", detail)

    def test_documentation_digest_empty_for_datasource_with_no_children(self):
        """A Data Source with no child table nodes gets an empty tables list."""
        payload = {
            "org": "Acme",
            "generated_at": "2026-06-01T00:00:00Z",
            "nodes": [{"id": "ds-only", "label": "Empty DS", "type": "Data Source"}],
            "edges": [],
            "evidence": [],
        }
        ctx = build_render_context(Graph.from_v1(payload))
        digest = ctx["detail_index"]["ds-only"]["documentation_digest"]
        self.assertEqual(digest["tables"], [])


class TestDataSourceInternalSubtreeContract(unittest.TestCase):
    def test_data_source_detail_exposes_existing_internal_subtree(self):
        payload = {
            "org": "Acme",
            "generated_at": "2026-06-01T00:00:00Z",
            "nodes": [
                {"id": "ds-1", "label": "Warehouse DB", "type": "Data Source"},
                {
                    "id": "schema-sales",
                    "label": "sales",
                    "type": "DataContainer",
                    "parent_id": "ds-1",
                    "depth": 1,
                    "details": {"kind": "schema"},
                },
                {
                    "id": "table-orders",
                    "label": "orders",
                    "type": "DataContainer",
                    "parent_id": "schema-sales",
                    "depth": 2,
                    "details": {"kind": "table"},
                },
                {
                    "id": "field-order-id",
                    "label": "order_id",
                    "type": "DataField",
                    "parent_id": "table-orders",
                    "depth": 3,
                    "details": {"kind": "column", "data_type": "integer"},
                },
            ],
            "edges": [],
            "evidence": [],
        }

        ctx = build_render_context(Graph.from_v1(payload))
        subtree = ctx["detail_index"]["ds-1"]["internal_subtree"]

        self.assertEqual(subtree[0]["id"], "schema-sales")
        self.assertEqual(subtree[0]["details"]["kind"], "schema")
        table = subtree[0]["children"][0]
        self.assertEqual(table["id"], "table-orders")
        self.assertEqual(table["details"]["kind"], "table")
        self.assertEqual(table["children"][0]["id"], "field-order-id")
        self.assertEqual(table["children"][0]["details"]["kind"], "column")

    def test_legacy_documentation_digest_remains_unchanged_when_subtree_is_added(self):
        graph = Graph.from_v1(_datasource_graph_payload())

        ctx = build_render_context(graph)
        detail = ctx["detail_index"]["ds-1"]

        self.assertEqual(len(detail["documentation_digest"]["tables"]), 2)
        self.assertEqual(detail["documentation_digest"]["tables"][0]["node_id"], "tbl-customers")
        self.assertEqual(detail["documentation_digest"]["tables"][1]["node_id"], "tbl-orders")
        self.assertIn("internal_subtree", detail)

    def test_lazy_derivation_from_legacy_digest_is_idempotent_and_deterministic(self):
        graph = Graph.from_v1(_datasource_graph_payload())

        first = build_render_context(graph)["detail_index"]["ds-1"]["internal_subtree"]
        second = build_render_context(graph)["detail_index"]["ds-1"]["internal_subtree"]

        self.assertEqual(second, first)
        self.assertEqual([item["id"] for item in first], ["ds-1-table-customers", "ds-1-table-orders"])
        orders = next(item for item in first if item["id"] == "ds-1-table-orders")
        self.assertEqual(orders["details"]["kind"], "table")
        self.assertEqual([child["id"] for child in orders["children"]], ["ds-1-table-orders-column-id"])
        self.assertEqual(orders["children"][0]["details"]["kind"], "column")

    def test_non_data_source_parent_id_is_ignored_for_digest_and_internal_subtree(self):
        payload = {
            "org": "Acme",
            "generated_at": "2026-06-01T00:00:00Z",
            "nodes": [
                {"id": "dept-1", "label": "Ops", "type": "Department"},
                {
                    "id": "role-1",
                    "label": "Analyst",
                    "type": "Role",
                    "parent_id": "dept-1",
                    "depth": 1,
                    "card_sections": [{"title": "Columns / Fields", "content": "| col | type |", "order": 1}],
                },
            ],
            "edges": [],
            "evidence": [],
        }

        ctx = build_render_context(Graph.from_v1(payload))

        self.assertNotIn("documentation_digest", ctx["detail_index"]["dept-1"])
        self.assertNotIn("internal_subtree", ctx["detail_index"]["dept-1"])
