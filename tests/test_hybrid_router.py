"""Tests for the hybrid retrieval router use case core."""

from __future__ import annotations


def test_lexical_only_fallback_is_deterministic_and_stable() -> None:
    """Missing semantic scores still produces repeatable lexical/governance ordering."""
    from brain_ds.retrieval.hybrid_router import HybridRetrievalRouter
    from brain_ds.retrieval.models import RetrievalCandidate, RetrievalRequest
    from brain_ds.scoring.retrieval import SignalScores

    candidates = [
        RetrievalCandidate(id="b", label="Beta", signals=SignalScores(lexical=0.7, governance=1.0)),
        RetrievalCandidate(id="a", label="Alpha", signals=SignalScores(lexical=0.7, governance=1.0)),
        RetrievalCandidate(id="c", label="Cluster", signals=SignalScores(lexical=0.9, governance=0.65), status="proposed"),
    ]
    router = HybridRetrievalRouter(candidates=candidates)

    first = router.retrieve(RetrievalRequest(query="margin", limit=3, depth=1))
    second = router.retrieve(RetrievalRequest(query="margin", limit=3, depth=1))

    assert [anchor.id for anchor in first.anchors] == ["a", "b", "c"]
    assert [anchor.id for anchor in second.anchors] == ["a", "b", "c"]
    assert first.dense_used is False


def test_full_signal_fusion_can_promote_stronger_evidence() -> None:
    """Semantic and graph signals participate when supplied to the use case."""
    from brain_ds.retrieval.hybrid_router import HybridRetrievalRouter
    from brain_ds.retrieval.models import RetrievalCandidate, RetrievalRequest
    from brain_ds.scoring.retrieval import SignalScores

    router = HybridRetrievalRouter(
        candidates=[
            RetrievalCandidate(id="lexical", label="Lexical", signals=SignalScores(lexical=0.9, governance=1.0)),
            RetrievalCandidate(
                id="hybrid",
                label="Hybrid",
                signals=SignalScores(lexical=0.7, semantic=1.0, governance=1.0, graph=1.0),
            ),
        ]
    )

    result = router.retrieve(RetrievalRequest(query="cash flow", limit=2, depth=1))

    assert [anchor.id for anchor in result.anchors] == ["hybrid", "lexical"]
    assert result.dense_used is True


def test_bounded_expansion_respects_depth_and_result_limit() -> None:
    """Expansion includes neighbors only up to the request depth and bounded result size."""
    from brain_ds.retrieval.hybrid_router import HybridRetrievalRouter
    from brain_ds.retrieval.models import RetrievalCandidate, RetrievalRequest
    from brain_ds.scoring.retrieval import SignalScores

    router = HybridRetrievalRouter(
        candidates=[
            RetrievalCandidate(
                id="root",
                label="Root",
                signals=SignalScores(lexical=1.0, governance=1.0),
                neighbor_ids=("first",),
            ),
            RetrievalCandidate(id="first", label="First", neighbor_ids=("second",)),
            RetrievalCandidate(id="second", label="Second"),
        ]
    )

    depth_one = router.retrieve(RetrievalRequest(query="root", limit=5, depth=1))
    depth_two_limited = router.retrieve(RetrievalRequest(query="root", limit=2, depth=2))

    assert depth_one.candidate_depths == {"root": 0, "first": 1}
    assert depth_two_limited.candidate_depths == {"root": 0, "first": 1}


def test_archived_and_rejected_candidates_do_not_dominate_router_results() -> None:
    """Inactive candidates are dampened before anchor selection."""
    from brain_ds.retrieval.hybrid_router import HybridRetrievalRouter
    from brain_ds.retrieval.models import RetrievalCandidate, RetrievalRequest
    from brain_ds.scoring.retrieval import SignalScores

    router = HybridRetrievalRouter(
        candidates=[
            RetrievalCandidate(id="archived", label="Archived", signals=SignalScores(lexical=1.0, governance=1.0), status="archived"),
            RetrievalCandidate(id="rejected", label="Rejected", signals=SignalScores(lexical=1.0, governance=1.0), status="rejected"),
            RetrievalCandidate(id="confirmed", label="Confirmed", signals=SignalScores(lexical=0.4, governance=1.0)),
        ]
    )

    result = router.retrieve(RetrievalRequest(query="risk", limit=3, depth=1))

    assert [anchor.id for anchor in result.anchors] == ["confirmed", "archived", "rejected"]
