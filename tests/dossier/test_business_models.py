from __future__ import annotations

import dataclasses
import unittest


class BusinessDossierModelTests(unittest.TestCase):
    def test_business_dossier_dtos_are_frozen_slotted_and_bounded(self) -> None:
        from brain_ds.dossier.business_models import (
            BusinessDossier,
            BusinessDossierRequest,
            BusinessInterpretation,
            BusinessUncertainty,
            PendingQuestionProposal,
        )

        for dto in (
            BusinessDossierRequest,
            BusinessInterpretation,
            BusinessDossier,
            BusinessUncertainty,
            PendingQuestionProposal,
        ):
            with self.subTest(dto=dto.__name__):
                self.assertTrue(dataclasses.is_dataclass(dto))
                self.assertTrue(dto.__dataclass_params__.frozen)
                self.assertIn("__slots__", dto.__dict__)

        request = BusinessDossierRequest(
            graph_id="graph-1",
            query="  why is fulfillment late?  ",
            limit=500,
            max_alternatives=99,
        )

        self.assertEqual(request.query, "why is fulfillment late?")
        self.assertEqual(request.limit, 50)
        self.assertEqual(request.max_alternatives, 3)
        self.assertFalse(request.create_pending_questions)

    def test_business_interpretation_contract_preserves_evidence_and_confidence_bounds(self) -> None:
        from brain_ds.dossier.business_models import BusinessInterpretation

        interpretation = BusinessInterpretation(
            id="late-shipments",
            label="Late shipment performance",
            entity_type="KPI",
            entity_ids=["kpi-1", "dept-1"],
            evidence_ids=["ds-1"],
            confidence=1.8,
            rationale="KPI and department evidence both mention late shipments.",
            is_default=True,
        )

        self.assertEqual(interpretation.entity_ids, ("kpi-1", "dept-1"))
        self.assertEqual(interpretation.evidence_ids, ("ds-1",))
        self.assertEqual(interpretation.confidence, 1.0)
        self.assertTrue(interpretation.is_default)


if __name__ == "__main__":
    unittest.main()
