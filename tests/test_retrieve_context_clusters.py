"""Cluster-routed retrieval tests for modular Graph RAG routing."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from brain_ds.mcp.tools import retrieve_context
from brain_ds.store.graph_store import GraphStore


def _make_store() -> tuple[tempfile.TemporaryDirectory[str], GraphStore, str]:
    temp_dir = tempfile.TemporaryDirectory()
    db_path = Path(temp_dir.name) / ".brain_ds" / "store.db"
    db_path.parent.mkdir(parents=True)
    store = GraphStore(str(db_path))
    graph_id = "g-cluster-route"
    store.meta_repo.save_graph_meta(
        graph_id=graph_id,
        workspace_root=temp_dir.name,
        workspace_path=temp_dir.name,
        project="p-cluster-route",
        org="o-cluster-route",
        schema_version="2.0.0",
        contract_version="1.0.0",
        node_count=0,
        edge_count=0,
        imported_from=None,
        generated_at="",
    )
    return temp_dir, store, graph_id


def _seed_portfolio_graph(store: GraphStore, graph_id: str) -> None:
    for node in [
        {"id": "KPI_MARGIN", "label": "Gross Margin", "type": "KPI", "supertype": "Metric"},
        {"id": "SRC_MARGIN", "label": "Margin Warehouse", "type": "Data Source", "supertype": "Data"},
        {"id": "KPI_PIPE", "label": "Sales Pipeline", "type": "KPI", "supertype": "Metric"},
        {"id": "SRC_CRM", "label": "CRM Opportunities", "type": "Data Source", "supertype": "Data"},
        {"id": "NOISE", "label": "Office Seating", "type": "Task", "supertype": "Work"},
    ]:
        store.upsert_node(graph_id, node)
    store.upsert_edge(graph_id, {"source": "KPI_MARGIN", "target": "SRC_MARGIN", "label": "measured_by", "weight": 0.9})
    store.upsert_edge(graph_id, {"source": "KPI_PIPE", "target": "SRC_CRM", "label": "measured_by", "weight": 0.8})
    store.cluster_repo.save_clusters(
        graph_id,
        [
            {
                "id": "CL_FIN",
                "name": "Finance Profitability",
                "description": "Portfolio profitability module for gross margin analysis.",
                "metadata": {
                    "status": "confirmed",
                    "primary_anchor_id": "KPI_MARGIN",
                    "primary_anchor_type": "KPI",
                    "summary": "Global portfolio profitability, margin, revenue, and finance performance.",
                    "quality_signals": {"confidence": 0.96},
                },
            },
            {
                "id": "CL_SALES",
                "name": "Sales Growth",
                "description": "Pipeline module proposed by CRM exploration.",
                "metadata": {
                    "status": "proposed",
                    "primary_anchor_id": "KPI_PIPE",
                    "primary_anchor_type": "KPI",
                    "summary": "Global portfolio sales growth and pipeline coverage.",
                    "quality_signals": {"confidence": 0.72},
                },
            },
            {
                "id": "CL_ARCHIVED",
                "name": "Archived Portfolio Route",
                "description": "Retired global portfolio route that should not steer retrieval.",
                "metadata": {
                    "status": "archived",
                    "primary_anchor_id": "NOISE",
                    "primary_anchor_type": "Task",
                    "summary": "Retired obsolete global portfolio route.",
                    "quality_signals": {"confidence": 1.0},
                },
            },
            {
                "id": "CL_REJECTED",
                "name": "Rejected Portfolio Route",
                "description": "Rejected global portfolio route that should not steer retrieval.",
                "metadata": {
                    "status": "rejected",
                    "primary_anchor_id": "NOISE",
                    "primary_anchor_type": "Task",
                    "summary": "Rejected obsolete global portfolio route.",
                    "quality_signals": {"confidence": 1.0},
                },
            },
        ],
    )
    store.cluster_repo.save_members(
        graph_id,
        [
            {"cluster_id": "CL_FIN", "node_id": "KPI_MARGIN", "weight": 1.0},
            {"cluster_id": "CL_FIN", "node_id": "SRC_MARGIN", "weight": 0.8},
            {"cluster_id": "CL_SALES", "node_id": "KPI_PIPE", "weight": 1.0},
            {"cluster_id": "CL_SALES", "node_id": "SRC_CRM", "weight": 0.8},
            {"cluster_id": "CL_ARCHIVED", "node_id": "NOISE", "weight": 1.0},
            {"cluster_id": "CL_REJECTED", "node_id": "NOISE", "weight": 1.0},
        ],
    )


class ClusterRoutedRetrieveContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir, self.store, self.graph_id = _make_store()

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def test_global_query_routes_through_confirmed_and_proposed_cluster_summaries(self) -> None:
        _seed_portfolio_graph(self.store, self.graph_id)

        result = retrieve_context(self.store, {"graph_id": self.graph_id, "query": "global portfolio", "limit": 8})

        self.assertNotIn("code", result)
        route = result["module_route"]
        self.assertEqual(route["mode"], "cluster")
        self.assertEqual([cluster["id"] for cluster in route["clusters"]], ["CL_FIN", "CL_SALES"])
        self.assertEqual(route["clusters"][0]["status"], "confirmed")
        self.assertEqual(route["clusters"][0]["routing_weight"], 1.0)
        self.assertEqual(route["clusters"][1]["status"], "proposed")
        self.assertLess(route["clusters"][1]["routing_weight"], route["clusters"][0]["routing_weight"])
        self.assertIn("MODULE ROUTE:", result["serialized_for_llm"])
        self.assertIn("[CONFIRMED CLUSTER] Finance Profitability", result["serialized_for_llm"])
        self.assertIn("[PROPOSED CLUSTER] Sales Growth", result["serialized_for_llm"])

    def test_local_kpi_query_starts_from_cluster_anchor_and_expands_members(self) -> None:
        _seed_portfolio_graph(self.store, self.graph_id)

        result = retrieve_context(self.store, {"graph_id": self.graph_id, "query": "gross margin", "limit": 4})

        self.assertNotIn("code", result)
        self.assertEqual([anchor["id"] for anchor in result["anchors"]], ["KPI_MARGIN"])
        node_ids = {node["id"] for node in result["subgraph"]["nodes"]}
        self.assertIn("KPI_MARGIN", node_ids)
        self.assertIn("SRC_MARGIN", node_ids)
        self.assertNotIn("NOISE", node_ids)
        self.assertEqual(result["module_route"]["clusters"][0]["id"], "CL_FIN")

    def test_retrieve_context_preserves_bfs_fallback_when_no_cluster_matches(self) -> None:
        _seed_portfolio_graph(self.store, self.graph_id)

        result = retrieve_context(self.store, {"graph_id": self.graph_id, "query": "office seating", "limit": 4})

        self.assertNotIn("code", result)
        self.assertEqual(result["module_route"], {"mode": "bfs", "clusters": []})
        self.assertEqual([anchor["id"] for anchor in result["anchors"]], ["NOISE"])
        self.assertNotIn("MODULE ROUTE:", result["serialized_for_llm"])

    def test_archived_and_rejected_cluster_routes_do_not_cross_route_boundary(self) -> None:
        _seed_portfolio_graph(self.store, self.graph_id)

        result = retrieve_context(self.store, {"graph_id": self.graph_id, "query": "obsolete global portfolio", "limit": 4})

        self.assertNotIn("code", result)
        route = result["module_route"]
        routed_ids = [cluster["id"] for cluster in route["clusters"]]
        self.assertEqual(route["mode"], "cluster")
        self.assertEqual(routed_ids, ["CL_FIN", "CL_SALES"])
        self.assertNotIn("CL_ARCHIVED", routed_ids)
        self.assertNotIn("CL_REJECTED", routed_ids)
        self.assertNotEqual([anchor["id"] for anchor in result["anchors"]], ["NOISE"])
        self.assertNotIn("ARCHIVED CLUSTER", result["serialized_for_llm"])
        self.assertNotIn("REJECTED CLUSTER", result["serialized_for_llm"])

    def test_cluster_route_failure_falls_back_to_bfs_retrieval(self) -> None:
        _seed_portfolio_graph(self.store, self.graph_id)

        with patch.object(self.store, "query_clusters", side_effect=RuntimeError("cluster table unavailable")):
            result = retrieve_context(self.store, {"graph_id": self.graph_id, "query": "office seating", "limit": 4})

        self.assertNotIn("code", result)
        self.assertEqual(result["module_route"], {"mode": "bfs", "clusters": []})
        self.assertEqual([anchor["id"] for anchor in result["anchors"]], ["NOISE"])

    def test_cluster_route_members_are_bounded_before_ledger_lookup_and_metadata(self) -> None:
        _seed_portfolio_graph(self.store, self.graph_id)
        extra_members = []
        for index in range(20):
            node_id = f"FIN_MEMBER_{index:02d}"
            self.store.upsert_node(
                self.graph_id,
                {"id": node_id, "label": f"Finance member {index:02d}", "type": "Metric", "supertype": "Metric"},
            )
            self.store.upsert_edge(
                self.graph_id,
                {"source": "KPI_MARGIN", "target": node_id, "label": "explains", "weight": 0.7},
            )
            extra_members.append({"cluster_id": "CL_FIN", "node_id": node_id, "weight": 0.4})
        self.store.cluster_repo.save_members(self.graph_id, extra_members)

        with patch.object(
            self.store,
            "query_ledger_latest_for_targets",
            wraps=self.store.query_ledger_latest_for_targets,
        ) as ledger_lookup:
            result = retrieve_context(self.store, {"graph_id": self.graph_id, "query": "gross margin", "limit": 4})

        self.assertNotIn("code", result)
        ledger_edge_ids = ledger_lookup.call_args.args[1]
        self.assertLessEqual(len(ledger_edge_ids), 4)
        self.assertLessEqual(len(result["module_route"]["clusters"][0]["member_ids"]), 4)
        self.assertLessEqual(len(result["subgraph"]["nodes"]), 4)


if __name__ == "__main__":
    unittest.main()
