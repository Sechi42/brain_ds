from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from brain_ds.mcp.tools import suggest_connections
from brain_ds.scoring import similarity
from brain_ds.store.graph_store import GraphStore


class SuggestConnectionsToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "store.db"
        self.store = GraphStore(str(self.db_path))
        self.graph_id = "graph-suggest"
        self.store.meta_repo.save_graph_meta(
            graph_id=self.graph_id,
            workspace_root=self.temp_dir.name,
            workspace_path=self.temp_dir.name,
            project="project-suggest",
            org="org-suggest",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at="",
        )
        # Every fixture node carries a non-empty "where": the sparse gate marks
        # where-less nodes as review-needed, which is covered separately below.
        self._add_node("kpi-ventas", "Ventas Mensuales", "KPI", "metric", {"where": "Dashboard comercial", "learned": "Data Source: CRM Salesforce ventas"})
        self._add_node("ds-crm", "CRM Salesforce", "Data Source", "data", {"where": "Salesforce cloud", "what": "CRM Salesforce con tabla ventas"})
        self._add_node("role-analista", "Analista Ventas", "Role", "actor", {"where": "Equipo comercial ventas"})
        self._add_node("risk-legal", "Riesgo Regulatorio", "Risk", "risk", {"where": "Legal", "what": "Cambios normativos"})
        # KPI already accountable to the Role — must be excluded from suggestions.
        self.store.upsert_edge(self.graph_id, {"source": "role-analista", "target": "kpi-ventas", "label": "accountable"})

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def _add_node(self, node_id: str, label: str, type_: str, supertype: str, details: dict) -> None:
        self.store.upsert_node(
            self.graph_id,
            {
                "id": node_id,
                "label": label,
                "type": type_,
                "supertype": supertype,
                "parent_id": "ROOT",
                "details": details,
            },
        )

    def test_suggests_data_source_with_measured_by_direction(self) -> None:
        result = suggest_connections(self.store, {"graph_id": self.graph_id, "node_id": "kpi-ventas"})

        self.assertNotIn("code", result)
        ids = [item["node_id"] for item in result["suggestions"]]
        self.assertIn("ds-crm", ids)
        top = next(item for item in result["suggestions"] if item["node_id"] == "ds-crm")
        self.assertEqual(top["suggested_edge"], {"source": "kpi-ventas", "target": "ds-crm", "label": "measured-by"})
        self.assertGreaterEqual(top["score"], 0.45)

    def test_excludes_already_connected_and_self(self) -> None:
        result = suggest_connections(self.store, {"graph_id": self.graph_id, "node_id": "kpi-ventas"})

        ids = [item["node_id"] for item in result["suggestions"]]
        self.assertNotIn("kpi-ventas", ids)
        self.assertNotIn("role-analista", ids)
        self.assertIn("role-analista", result["already_connected"])

    def test_threshold_filters_weak_candidates(self) -> None:
        result = suggest_connections(
            self.store,
            {"graph_id": self.graph_id, "node_id": "kpi-ventas", "threshold": 0.5},
        )

        ids = [item["node_id"] for item in result["suggestions"]]
        # Risk has no type rule with KPI and no token overlap — must be filtered.
        self.assertNotIn("risk-legal", ids)

    def test_limit_caps_results_and_reports_effective_threshold(self) -> None:
        for index in range(15):
            self._add_node(f"ds-extra-{index}", f"Fuente ventas {index}", "Data Source", "data", {"where": "Almacén ventas", "what": "ventas"})

        result = suggest_connections(
            self.store,
            {"graph_id": self.graph_id, "node_id": "kpi-ventas", "limit": 5},
        )

        self.assertEqual(result["returned"], 5)
        self.assertGreater(result["candidates_above_threshold"], 5)
        self.assertGreaterEqual(result["effective_threshold"], result["threshold"])

    def test_missing_node_returns_validation_error(self) -> None:
        result = suggest_connections(self.store, {"graph_id": self.graph_id, "node_id": "nope"})

        self.assertEqual(result["code"], -32000)
        self.assertIn("not found", result["message"])

    def test_missing_graph_returns_validation_error(self) -> None:
        result = suggest_connections(self.store, {"graph_id": "ghost", "node_id": "kpi-ventas"})

        self.assertEqual(result["code"], -32000)

    def test_sparse_node_candidates_are_blocked_as_review_needed(self) -> None:
        self._add_node(
            "ds-sparse",
            "Fuente ventas mensuales dashboard comercial",
            "Data Source",
            "data",
            {"where": "", "learned": "Underspecified: faltan tablas"},
        )

        result = suggest_connections(self.store, {"graph_id": self.graph_id, "node_id": "kpi-ventas"})

        sparse = next((item for item in result["suggestions"] if item["node_id"] == "ds-sparse"), None)
        if sparse is not None:
            self.assertEqual(sparse["suggested_edge"]["label"], "review-needed")
            self.assertIn("sparse", sparse["reason"])


class SimilarityAlgorithmTests(unittest.TestCase):
    def test_type_pair_suggestions_use_canonical_relationship_labels(self) -> None:
        from brain_ds.ontology.relationship_types import RelationshipType

        valid_labels = {item.value for item in RelationshipType}
        for source_type, target_type, label in similarity.TYPE_PAIR_SUGGESTIONS.values():
            self.assertIn(label, valid_labels, f"{source_type}->{target_type} uses unknown label {label}")

    def test_type_pair_keys_match_their_rule_types(self) -> None:
        for pair, (source_type, target_type, _label) in similarity.TYPE_PAIR_SUGGESTIONS.items():
            self.assertEqual(pair, frozenset({source_type, target_type}))


if __name__ == "__main__":
    unittest.main()
