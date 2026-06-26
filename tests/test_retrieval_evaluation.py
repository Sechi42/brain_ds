"""Tests for the offline retrieval evaluation harness."""

from __future__ import annotations

from pathlib import Path


def test_evaluation_reports_quality_latency_and_determinism() -> None:
    """A standard run emits comparable quality, latency, and stability metrics."""
    from brain_ds.retrieval.evaluation import EvaluationHarness, load_query_set
    from brain_ds.retrieval.hybrid_router import HybridRetrievalRouter
    from brain_ds.retrieval.models import RetrievalCandidate
    from brain_ds.scoring.retrieval import SignalScores

    queries = load_query_set(Path("tests/fixtures/retrieval_queries.json"))
    router = HybridRetrievalRouter(
        candidates=[
            RetrievalCandidate(
                id="confirmed-risk",
                label="Confirmed risk register",
                signals=SignalScores(lexical=1.0, semantic=0.9, governance=1.0, graph=0.7),
                neighbor_ids=("mitigation-plan",),
            ),
            RetrievalCandidate(
                id="mitigation-plan",
                label="Mitigation plan",
                signals=SignalScores(lexical=0.75, semantic=0.8, governance=1.0, graph=0.8),
            ),
            RetrievalCandidate(
                id="proposed-risk-cluster",
                label="Proposed risk cluster",
                signals=SignalScores(lexical=1.0, semantic=1.0, governance=0.55, graph=0.5),
                status="proposed",
            ),
        ]
    )

    report = EvaluationHarness(router=router).evaluate(queries, k=2, repeats=2)

    assert report.metrics["recall@2"] == 1.0
    assert report.metrics["precision@2"] == 1.0
    assert 0.9 <= report.metrics["ndcg@2"] <= 1.0
    assert report.metrics["p50_latency_ms"] >= 0.0
    assert report.metrics["p95_latency_ms"] >= report.metrics["p50_latency_ms"]
    assert report.deterministic is True
    assert report.query_count == 1


def test_ablation_report_compares_signal_families_without_mutating_router() -> None:
    """The harness can remove each signal family and report deterministic deltas."""
    from brain_ds.retrieval.evaluation import EvaluationHarness, LabeledQuery
    from brain_ds.retrieval.hybrid_router import HybridRetrievalRouter
    from brain_ds.retrieval.models import RetrievalCandidate
    from brain_ds.scoring.retrieval import SignalScores

    router = HybridRetrievalRouter(
        candidates=[
            RetrievalCandidate(
                id="confirmed-control",
                label="Confirmed control",
                signals=SignalScores(lexical=0.2, semantic=1.0, governance=0.8, graph=0.4),
            ),
            RetrievalCandidate(
                id="lexical-distractor",
                label="Lexical distractor",
                signals=SignalScores(lexical=1.0, semantic=0.0, governance=0.6, graph=0.3),
            ),
        ]
    )
    harness = EvaluationHarness(router=router)
    queries = [LabeledQuery(query="control", relevant_ids=("confirmed-control",))]

    comparison = harness.evaluate_ablations(queries, k=1, repeats=2)

    assert set(comparison) == {"baseline", "without_lexical", "without_semantic", "without_governance", "without_graph"}
    assert comparison["baseline"].metrics["recall@1"] == 1.0
    assert comparison["without_semantic"].metrics["recall@1"] == 0.0
    assert router.candidates[0].signals.semantic == 1.0


def test_evaluation_scope_rejects_viewer_bulk_write_and_unrelated_architecture_requests() -> None:
    """Scope review excludes non-retrieval-evaluation changes from this capability."""
    from brain_ds.retrieval.evaluation import is_evaluation_scope_allowed

    assert is_evaluation_scope_allowed("Add recall@5 and nDCG metrics to the retrieval eval harness") is True
    assert is_evaluation_scope_allowed("Change graph viewer behavior for highlighted routes") is False
    assert is_evaluation_scope_allowed("Add bulk writes to persist evaluation results") is False
    assert is_evaluation_scope_allowed("Rewrite unrelated architecture around workspaces") is False
