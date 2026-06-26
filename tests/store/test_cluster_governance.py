"""Strict-TDD tests for semantic cluster governance helpers."""

from __future__ import annotations

import unittest

from brain_ds.scoring.similarity import classify_identity_reuse
from brain_ds.store.cluster_governance import choose_cluster_center
from brain_ds.store.models import NodeRow


def _node(node_id: str, label: str, node_type: str, details: dict | None = None) -> NodeRow:
    return NodeRow(
        graph_id="graph-c",
        id=node_id,
        label=label,
        type=node_type,
        supertype=None,
        details=details or {},
        card_sections=None,
        editable_fields=None,
        evidence_ids=None,
        layout_hint=None,
        parent_id=None,
        depth=0,
        created_at="",
        modified_at="",
    )


class ClusterGovernanceTests(unittest.TestCase):
    def test_kpi_anchor_wins_with_department_and_source_support(self) -> None:
        metadata = choose_cluster_center(
            [
                _node("dept-finance", "Finance", "Department"),
                _node("role-analyst", "Finance Analyst", "Role"),
                _node("source-warehouse", "Revenue Warehouse", "Data Source"),
                _node(
                    "kpi-revenue",
                    "Net Revenue",
                    "KPI",
                    {"formula": "gross - refunds", "owner": "Finance"},
                ),
            ]
        )

        self.assertEqual(metadata["primary_anchor_id"], "kpi-revenue")
        self.assertEqual(metadata["primary_anchor_type"], "KPI")
        self.assertEqual(metadata["dominant_department_id"], "dept-finance")
        self.assertEqual(metadata["supporting_anchor_ids"], ["source-warehouse", "role-analyst"])
        self.assertFalse(metadata["needs_source"])
        self.assertEqual(metadata["quality_signals"]["center_selection"], "semantic_anchor")

    def test_business_problem_anchor_wins_before_department_fallback(self) -> None:
        metadata = choose_cluster_center(
            [
                _node("dept-ops", "Operations", "Department"),
                _node("problem-delays", "Shipment Delays", "Problem / Improvement Area"),
            ]
        )

        self.assertEqual(metadata["primary_anchor_id"], "problem-delays")
        self.assertEqual(metadata["primary_anchor_type"], "Problem / Improvement Area")
        self.assertEqual(metadata["dominant_department_id"], "dept-ops")
        self.assertTrue(metadata["needs_source"])

    def test_department_fallback_marks_missing_semantic_anchor_gap(self) -> None:
        metadata = choose_cluster_center(
            [_node("dept-ops", "Operations", "Department"), _node("role-planner", "Planner", "Role")]
        )

        self.assertEqual(metadata["primary_anchor_id"], "dept-ops")
        self.assertEqual(metadata["primary_anchor_type"], "Department")
        self.assertTrue(metadata["needs_source"])
        self.assertEqual(metadata["quality_signals"]["missing_anchor_gap"], "kpi_or_business_problem")

    def test_identity_reuse_accepts_same_kpi_owner_scope(self) -> None:
        result = classify_identity_reuse(
            {"id": "kpi-1", "label": "Net Revenue", "type": "KPI", "details": {"owner": "Finance"}},
            {"label": "net revenue", "type": "KPI", "details": {"owner": "finance"}},
        )

        self.assertEqual(result["action"], "reuse")
        self.assertEqual(result["tier"], "exact_identity")
        self.assertEqual(result["target_id"], "kpi-1")

    def test_identity_reuse_prompts_for_same_label_different_source_scope(self) -> None:
        result = classify_identity_reuse(
            {
                "id": "source-1",
                "label": "Orders",
                "type": "Data Source",
                "details": {"database": "warehouse", "table": "orders"},
            },
            {
                "label": "Orders",
                "type": "Data Source",
                "details": {"database": "crm", "table": "orders"},
            },
        )

        self.assertEqual(result["action"], "ask_human")
        self.assertEqual(result["tier"], "ambiguous_identity")
        self.assertIn("same label", result["reason"])

    def test_cluster_identity_reuses_same_primary_anchor(self) -> None:
        result = classify_identity_reuse(
            {
                "id": "cluster-revenue",
                "label": "Revenue",
                "type": "Cluster",
                "metadata": {"primary_anchor_id": "kpi-revenue"},
            },
            {
                "label": "Revenue performance",
                "type": "Cluster",
                "metadata": {"primary_anchor_id": "kpi-revenue"},
            },
        )

        self.assertEqual(result["action"], "reuse")
        self.assertEqual(result["tier"], "shared_primary_anchor")


if __name__ == "__main__":
    unittest.main()
