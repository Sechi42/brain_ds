"""Tests for retrieval use-case DTOs."""

from __future__ import annotations

import pytest


def test_retrieval_request_is_immutable_and_bounds_limit_and_depth() -> None:
    """Router requests clamp public bounds while remaining independent from MCP JSON."""
    from brain_ds.retrieval.models import RetrievalRequest

    request = RetrievalRequest(query="margin risk", limit=99, depth=9)

    assert request.limit == 50
    assert request.depth == 2
    with pytest.raises(AttributeError):
        request.limit = 10  # type: ignore[misc]


def test_retrieval_request_preserves_valid_small_bounds() -> None:
    """Non-default valid bounds are preserved for focused retrieval calls."""
    from brain_ds.retrieval.models import RetrievalRequest

    request = RetrievalRequest(query="margin risk", limit=3, depth=1)

    assert request.limit == 3
    assert request.depth == 1


def test_router_candidate_defaults_to_zero_scores_and_confirmed_status() -> None:
    """Abstract candidates can be built from lexical-only adapters with safe defaults."""
    from brain_ds.retrieval.models import RetrievalCandidate

    candidate = RetrievalCandidate(id="node-1", label="Gross Margin")

    assert candidate.id == "node-1"
    assert candidate.status == "confirmed"
    assert candidate.signals.lexical == 0.0
    assert candidate.neighbor_ids == ()


def test_retrieval_result_limits_anchors_and_preserves_metadata() -> None:
    """Use-case results expose bounded anchors plus route metadata for later adapters."""
    from brain_ds.retrieval.models import RetrievalResult, RouterAnchor

    result = RetrievalResult(
        anchors=tuple(RouterAnchor(id=f"n{index}", score=1.0 - index * 0.1) for index in range(7)),
        candidate_depths={"n0": 0, "n1": 1},
        dense_used=True,
    )

    assert [anchor.id for anchor in result.anchors] == ["n0", "n1", "n2", "n3", "n4"]
    assert result.candidate_depths == {"n0": 0, "n1": 1}
    assert result.dense_used is True
