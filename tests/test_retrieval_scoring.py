"""Tests for pure hybrid retrieval scoring helpers."""

from __future__ import annotations


def test_signal_scores_clamp_inputs_to_unit_interval() -> None:
    """Signal values are normalized before fusion so adapters cannot dominate."""
    from brain_ds.scoring.retrieval import SignalScores

    scores = SignalScores(lexical=1.4, semantic=-0.2, governance=0.75, graph=2.0).normalized()

    assert scores.lexical == 1.0
    assert scores.semantic == 0.0
    assert scores.governance == 0.75
    assert scores.graph == 1.0


def test_confirmed_candidate_ranks_above_matching_proposed_candidate_by_default() -> None:
    """Governance gates keep proposed recall hints below confirmed evidence by default."""
    from brain_ds.scoring.retrieval import RetrievalScoreWeights, ScoreInput, SignalScores, rank_candidates

    ranked = rank_candidates(
        [
            ScoreInput("proposed", SignalScores(lexical=0.9, semantic=0.7, governance=0.65, graph=0.8), status="proposed"),
            ScoreInput("confirmed", SignalScores(lexical=0.72, semantic=0.5, governance=1.0, graph=0.45), status="confirmed"),
        ],
        weights=RetrievalScoreWeights(),
    )

    assert [candidate.id for candidate in ranked] == ["confirmed", "proposed"]
    assert ranked[0].governance_tier < ranked[1].governance_tier


def test_strong_evidence_can_justify_proposed_candidate_over_confirmed() -> None:
    """A proposed candidate may outrank confirmed evidence only with materially stronger signals."""
    from brain_ds.scoring.retrieval import RetrievalScoreWeights, ScoreInput, SignalScores, rank_candidates

    ranked = rank_candidates(
        [
            ScoreInput("confirmed", SignalScores(lexical=0.25, semantic=0.0, governance=1.0, graph=0.1), status="confirmed"),
            ScoreInput("proposed", SignalScores(lexical=1.0, semantic=1.0, governance=0.75, graph=1.0), status="proposed"),
        ],
        weights=RetrievalScoreWeights(),
    )

    assert [candidate.id for candidate in ranked] == ["proposed", "confirmed"]


def test_archived_and_rejected_candidates_are_dampened_below_active_routes() -> None:
    """Inactive governance states cannot dominate active candidates with comparable evidence."""
    from brain_ds.scoring.retrieval import RetrievalScoreWeights, ScoreInput, SignalScores, rank_candidates

    ranked = rank_candidates(
        [
            ScoreInput("archived", SignalScores(lexical=1.0, semantic=1.0, governance=1.0, graph=1.0), status="archived"),
            ScoreInput("rejected", SignalScores(lexical=1.0, semantic=1.0, governance=1.0, graph=1.0), status="rejected"),
            ScoreInput("confirmed", SignalScores(lexical=0.45, semantic=0.0, governance=1.0, graph=0.2), status="confirmed"),
        ],
        weights=RetrievalScoreWeights(),
    )

    assert [candidate.id for candidate in ranked] == ["confirmed", "archived", "rejected"]


def test_stable_tie_breaks_use_tier_depth_and_id() -> None:
    """Equal scores return deterministic ordering across repeated runs."""
    from brain_ds.scoring.retrieval import RetrievalScoreWeights, ScoreInput, SignalScores, rank_candidates

    candidates = [
        ScoreInput("z-depth", SignalScores(lexical=0.5, governance=1.0), status="confirmed", depth=1),
        ScoreInput("a-root", SignalScores(lexical=0.5, governance=1.0), status="confirmed", depth=0),
        ScoreInput("b-root", SignalScores(lexical=0.5, governance=1.0), status="confirmed", depth=0),
    ]

    first = rank_candidates(candidates, weights=RetrievalScoreWeights())
    second = rank_candidates(list(reversed(candidates)), weights=RetrievalScoreWeights())

    assert [candidate.id for candidate in first] == ["a-root", "b-root", "z-depth"]
    assert [candidate.id for candidate in second] == ["a-root", "b-root", "z-depth"]
