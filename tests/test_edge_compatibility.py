from __future__ import annotations

import unittest

from brain_ds.ontology.edge_compatibility import classify_edge_compatibility


class EdgeCompatibilityTests(unittest.TestCase):
    def test_risk_owns_department_is_invalid(self) -> None:
        verdict = classify_edge_compatibility("Risk", "Department", "owns")

        self.assertEqual(verdict.status, "invalid")
        self.assertEqual(verdict.source_supertype, "risk")
        self.assertEqual(verdict.target_supertype, "actor")
        self.assertEqual(verdict.relationship, "owns")
        self.assertIn("risk.owns.actor", verdict.matrix_key)

    def test_unknown_relationship_label_is_suspect_not_crashing(self) -> None:
        verdict = classify_edge_compatibility("KPI", "Data Source", "legacy-link")

        self.assertEqual(verdict.status, "suspect")
        self.assertEqual(verdict.reason, "unknown_relationship_type")
        self.assertEqual(verdict.relationship, "legacy-link")
        self.assertEqual(verdict.source_supertype, "metric")
        self.assertEqual(verdict.target_supertype, "data")


if __name__ == "__main__":
    unittest.main()
