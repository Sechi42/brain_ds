import unittest

from brain_ds.ontology import Edge, RelationshipType
from brain_ds.scoring.engine import ScoringEngine
from brain_ds.scoring.factors import (
    directionality,
    evidence_count,
    explicit_reference,
    process_cooccurrence,
    relationship_base,
    token_overlap,
)
from brain_ds.scoring.models import ScoringContext


class TestScoringFactors(unittest.TestCase):
    def test_token_overlap_detects_shared_terms(self):
        score, reason = token_overlap("Fleet Planning", "Planning Workflow")
        self.assertGreater(score, 0.0)
        self.assertIn("Token overlap", reason)

    def test_relationship_base_uses_enum_mapping(self):
        score, reason = relationship_base(RelationshipType.DEPENDS_ON)
        self.assertGreater(score, 0.0)
        self.assertIn("depends-on", reason)

    def test_directionality_rewards_asymmetric_edges(self):
        score, reason = directionality(("A", "B"), [{"source": "A", "target": "B"}])
        self.assertEqual(score, 0.80)
        self.assertIn("Asymmetric", reason)

    def test_evidence_count_normalizes(self):
        score, _ = evidence_count([{}, {}, {}])
        self.assertEqual(score, 0.6)

    def test_process_cooccurrence_detects_shared_where(self):
        score, reason = process_cooccurrence(
            ("Fleet", "Dispatch"),
            [{"where": "Fleet and Dispatch review same queue daily"}],
        )
        self.assertEqual(score, 1.0)
        self.assertIn("co-occur", reason)

    def test_explicit_reference_detects_named_link(self):
        score, reason = explicit_reference(
            ("Fleet", "Dispatch"),
            [{"explicit_refs": ["dispatch"]}],
        )
        self.assertEqual(score, 1.0)
        self.assertIn("Explicit reference", reason)


class TestScoringEngine(unittest.TestCase):
    def test_engine_full_evidence_produces_reasons_and_evidence_ids(self):
        ctx = ScoringContext(
            edge_source="Fleet Planning",
            edge_target="Planning Workflow",
            relation_type="depends-on",
            evidence_items=[
                {
                    "id": "obs-1",
                    "where": "Fleet Planning and Planning Workflow share process",
                    "explicit_refs": ["planning workflow"],
                    "text": "Fleet Planning depends on Planning Workflow",
                },
                {
                    "id": "obs-2",
                    "source": "Fleet Planning",
                    "target": "Planning Workflow",
                },
            ],
        )
        result = ScoringEngine().score(ctx)
        self.assertGreater(result.weight, 0.0)
        self.assertLessEqual(result.weight, 1.0)
        self.assertGreaterEqual(len(result.reasons), 3)
        self.assertEqual(result.evidence_ids, ["obs-1", "obs-2"])

    def test_engine_clamps_weight_to_one(self):
        engine = ScoringEngine(
            factor_weights={
                "token_overlap": 1.0,
                "relationship_base": 1.0,
                "directionality": 1.0,
                "evidence_count": 1.0,
                "process_cooccurrence": 1.0,
                "explicit_reference": 1.0,
            }
        )
        ctx = ScoringContext(
            edge_source="A B",
            edge_target="A B",
            relation_type="creates-risk",
            evidence_items=[
                {
                    "id": "obs-1",
                    "where": "A B",
                    "explicit_refs": ["a b"],
                    "text": "A B",
                }
            ],
        )
        result = engine.score(ctx)
        self.assertEqual(result.weight, 1.0)

    def test_engine_handles_missing_evidence(self):
        ctx = ScoringContext(
            edge_source="Ops",
            edge_target="Risk",
            relation_type="creates-risk",
            evidence_items=[],
        )
        result = ScoringEngine().score(ctx)
        self.assertGreaterEqual(result.weight, 0.0)
        self.assertLessEqual(result.weight, 1.0)
        self.assertEqual(result.evidence_ids, [])


class TestEdgeBackwardCompatibility(unittest.TestCase):
    def test_edge_defaults_are_none(self):
        edge = Edge(source="a", target="b", label="depends-on")
        self.assertIsNone(edge.weight)
        self.assertIsNone(edge.reasons)
        self.assertIsNone(edge.evidence_ids)


if __name__ == "__main__":
    unittest.main()
