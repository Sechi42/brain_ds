from __future__ import annotations

import json
import unittest

from brain_ds.dossier.business_models import BusinessDossier, BusinessInterpretation, BusinessUncertainty, PendingQuestionProposal


class BusinessDossierSerializationTests(unittest.TestCase):
    def test_serialized_business_dossier_shape_includes_uncertainty_and_llm_summary(self) -> None:
        from brain_ds.dossier.business_serialization import serialize_business_dossier

        payload = serialize_business_dossier(
            BusinessDossier(
                query="why are deliveries late?",
                selected_interpretation_id="kpi-1",
                interpretations=[BusinessInterpretation(id="kpi-1", label="On-time Delivery", entity_type="KPI", entity_ids=("kpi-1",), evidence_ids=("ds-1",), is_default=True)],
                dossier={"kpis": [{"id": "kpi-1", "label": "On-time Delivery", "entity_type": "KPI", "details": "Delivery performance"}], "problems": [], "departments": [], "processes": [], "actors": []},
                evidence_sources=[{"id": "ds-1", "label": "warehouse_db", "entity_type": "DataSource", "details": "Shipment events"}],
                uncertainty=BusinessUncertainty(currency=[{"description": "Shipment evidence is stale"}]),
                pending_question_proposals=[PendingQuestionProposal(target_node_id="kpi-1", gap_kind="ownership", entity_type="KPI", question_text="Who owns On-time Delivery?")],
            )
        )

        self.assertEqual(list(payload), ["query", "selected_interpretation_id", "interpretations", "dossier", "evidence_sources", "uncertainty", "pending_question_proposals", "pending_questions_created", "serialized_for_llm"])
        self.assertEqual(payload["interpretations"][0]["evidence_ids"], ["ds-1"])
        self.assertEqual(payload["uncertainty"]["currency"][0]["description"], "Shipment evidence is stale")
        self.assertEqual(payload["pending_question_proposals"][0]["question_text"], "Who owns On-time Delivery?")
        self.assertIn("On-time Delivery", payload["serialized_for_llm"])
        self.assertIn("Uncertainty", payload["serialized_for_llm"])

    def test_oversized_business_dossier_truncates_deterministically_under_cap(self) -> None:
        from brain_ds.dossier.business_serialization import _MAX_PAYLOAD_BYTES, serialize_business_dossier

        long_text = "x" * 6000
        dossier = BusinessDossier(
            query="large graph",
            selected_interpretation_id="kpi-1",
            interpretations=[BusinessInterpretation(id="kpi-1", label="Large KPI", entity_type="KPI", entity_ids=("kpi-1",), is_default=True)],
            dossier={
                "kpis": [{"id": f"kpi-{index}", "label": f"KPI {index}", "entity_type": "KPI", "details": long_text} for index in range(80)],
                "problems": [{"id": f"problem-{index}", "label": f"Problem {index}", "entity_type": "Problem / Improvement Area", "details": long_text} for index in range(80)],
                "departments": [],
                "processes": [],
                "actors": [],
            },
            evidence_sources=[{"id": f"ds-{index}", "label": f"Source {index}", "entity_type": "DataSource", "details": long_text} for index in range(80)],
        )

        payload = serialize_business_dossier(dossier)
        encoded = len(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8"))

        self.assertLessEqual(encoded, _MAX_PAYLOAD_BYTES)
        self.assertTrue(payload["uncertainty"]["truncated"])
        self.assertIn("Dropped", payload["uncertainty"]["truncation_reason"])
        self.assertLess(len(payload["evidence_sources"]), 80)


if __name__ == "__main__":
    unittest.main()
