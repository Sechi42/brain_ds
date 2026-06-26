from __future__ import annotations

import unittest

from brain_ds.retrieval.models import RetrievalCandidate
from brain_ds.retrieval.neighborhood import ClusterRoute
from brain_ds.scoring.retrieval import SignalScores


class BusinessRouterTests(unittest.TestCase):
    def test_business_entities_outrank_raw_sources_with_equal_retrieval_signals(self) -> None:
        from brain_ds.dossier.business_router import rank_business_interpretations

        interpretations = rank_business_interpretations(
            query="customer churn",
            candidates=[
                RetrievalCandidate(
                    id="ds-1",
                    label="customer_churn_table",
                    signals=SignalScores(lexical=0.9, semantic=0.8, governance=0.8, graph=0.4),
                    metadata={"type": "DataSource"},
                ),
                RetrievalCandidate(
                    id="kpi-1",
                    label="Customer Churn",
                    signals=SignalScores(lexical=0.9, semantic=0.8, governance=0.8, graph=0.4),
                    metadata={"type": "KPI"},
                ),
            ],
        )

        self.assertEqual([item.entity_ids for item in interpretations], [("kpi-1",), ("ds-1",)])
        self.assertEqual(interpretations[0].entity_type, "KPI")
        self.assertTrue(interpretations[0].is_default)
        self.assertFalse(interpretations[1].is_default)

    def test_ambiguous_query_returns_bounded_ranked_alternatives_with_evidence(self) -> None:
        from brain_ds.dossier.business_router import rank_business_interpretations

        interpretations = rank_business_interpretations(
            query="margin risk",
            candidates=[
                RetrievalCandidate(
                    id="problem-1",
                    label="Margin erosion",
                    signals=SignalScores(lexical=0.8, semantic=0.7, governance=0.7, graph=0.5),
                    metadata={"type": "Problem / Improvement Area", "evidence_ids": ["source-1"]},
                ),
                RetrievalCandidate(
                    id="dept-1",
                    label="Commercial Operations",
                    signals=SignalScores(lexical=0.78, semantic=0.68, governance=0.7, graph=0.5),
                    metadata={"type": "Department", "evidence_ids": ["source-2"]},
                ),
                RetrievalCandidate(
                    id="source-raw",
                    label="margin_export.csv",
                    signals=SignalScores(lexical=1.0, semantic=0.9, governance=0.6, graph=0.2),
                    metadata={"type": "DataSource"},
                ),
                RetrievalCandidate(
                    id="process-1",
                    label="Quarterly pricing review",
                    signals=SignalScores(lexical=0.65, semantic=0.6, governance=0.7, graph=0.4),
                    metadata={"type": "Process"},
                ),
            ],
            max_alternatives=3,
        )

        self.assertEqual(len(interpretations), 3)
        self.assertEqual(interpretations[0].entity_type, "Problem / Improvement Area")
        self.assertEqual(interpretations[0].evidence_ids, ("source-1",))
        self.assertEqual(interpretations[1].entity_type, "Department")
        self.assertTrue(all(0.0 <= item.confidence <= 1.0 for item in interpretations))
        self.assertEqual(sum(1 for item in interpretations if item.is_default), 1)

    def test_cluster_routes_can_seed_business_interpretations_for_vague_queries(self) -> None:
        from brain_ds.dossier.business_router import rank_business_interpretations

        interpretations = rank_business_interpretations(
            query="fulfillment performance",
            candidates=[],
            cluster_routes=[
                ClusterRoute(
                    id="cluster-1",
                    name="Fulfillment performance risk",
                    status="confirmed",
                    summary="On-time delivery and warehouse backlog signals",
                    anchor_ids=["kpi-1"],
                    member_ids=["kpi-1", "problem-1", "ds-1"],
                    routing_weight=1.0,
                )
            ],
        )

        self.assertEqual(len(interpretations), 1)
        self.assertEqual(interpretations[0].id, "cluster-1")
        self.assertEqual(interpretations[0].entity_ids, ("kpi-1", "problem-1"))
        self.assertEqual(interpretations[0].evidence_ids, ("ds-1",))
        self.assertTrue(interpretations[0].is_default)


if __name__ == "__main__":
    unittest.main()
