"""Hybrid retrieval router core use case."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from brain_ds.retrieval.models import RetrievalCandidate, RetrievalRequest, RetrievalResult, RouterAnchor
from brain_ds.scoring.retrieval import RetrievalScoreWeights, ScoreInput, rank_candidates


@dataclass(slots=True)
class HybridRetrievalRouter:
    """Pure use case that ranks abstract candidates and expands bounded neighbors."""

    candidates: list[RetrievalCandidate] = field(default_factory=list)
    weights: RetrievalScoreWeights = field(default_factory=RetrievalScoreWeights)

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        """Return deterministic anchors and bounded candidate depths for a request."""
        candidates_by_id = {candidate.id: candidate for candidate in self.candidates}
        ranked = rank_candidates(
            [
                ScoreInput(
                    id=candidate.id,
                    signals=candidate.signals,
                    status=candidate.status,
                    depth=candidate.depth,
                )
                for candidate in self.candidates
            ],
            weights=self.weights,
        )
        ranked = [candidate for candidate in ranked if candidate.score > 0.0]
        anchors = tuple(
            RouterAnchor(
                id=candidate.id,
                score=candidate.score,
                label=candidates_by_id[candidate.id].label,
                status=candidate.status,
                depth=candidate.depth,
                signals=candidate.signals,
            )
            for candidate in ranked[: request.limit]
        )
        candidate_depths = _expand_depths(
            anchor_ids=[anchor.id for anchor in anchors],
            candidates_by_id=candidates_by_id,
            depth=request.depth,
            limit=request.limit,
        )
        return RetrievalResult(
            anchors=anchors,
            candidate_depths=candidate_depths,
            dense_used=any(candidate.signals.semantic > 0.0 for candidate in self.candidates),
            module_route={
                "mode": "hybrid" if any(candidate.signals.semantic > 0.0 for candidate in self.candidates) else "fallback",
                "anchor_ids": [anchor.id for anchor in anchors],
            },
        )


def _expand_depths(
    *,
    anchor_ids: list[str],
    candidates_by_id: dict[str, RetrievalCandidate],
    depth: int,
    limit: int,
) -> dict[str, int]:
    depth_by_id: dict[str, int] = {}
    queue: deque[tuple[str, int]] = deque()
    for anchor_id in anchor_ids:
        if len(depth_by_id) >= limit:
            break
        if anchor_id not in candidates_by_id or anchor_id in depth_by_id:
            continue
        depth_by_id[anchor_id] = 0
        queue.append((anchor_id, 0))

    while queue and len(depth_by_id) < limit:
        current_id, current_depth = queue.popleft()
        if current_depth >= depth:
            continue
        current = candidates_by_id[current_id]
        for neighbor_id in sorted(current.neighbor_ids):
            if len(depth_by_id) >= limit:
                break
            if neighbor_id not in candidates_by_id or neighbor_id in depth_by_id:
                continue
            next_depth = current_depth + 1
            depth_by_id[neighbor_id] = next_depth
            queue.append((neighbor_id, next_depth))
    return depth_by_id
