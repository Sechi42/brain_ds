"""Pure scoring models for hybrid graph retrieval."""

from __future__ import annotations

from dataclasses import dataclass


_STATUS_TIERS = {
    "confirmed": 0,
    "inferred": 1,
    "incomplete": 2,
    "needs-source": 2,
    "needs-confirmation": 2,
    "proposed": 3,
    "abstain": 4,
    "archived": 8,
    "rejected": 9,
}
_STATUS_MULTIPLIERS = {
    "confirmed": 1.0,
    "inferred": 0.92,
    "incomplete": 0.82,
    "needs-source": 0.82,
    "needs-confirmation": 0.78,
    "proposed": 0.72,
    "abstain": 0.45,
    "archived": 0.08,
    "rejected": 0.04,
}


@dataclass(frozen=True, slots=True)
class SignalScores:
    """Normalized signal family scores used by retrieval ranking."""

    lexical: float = 0.0
    semantic: float = 0.0
    governance: float = 0.0
    graph: float = 0.0

    def normalized(self) -> "SignalScores":
        """Return a copy with every signal clamped to the inclusive ``0..1`` range."""
        return SignalScores(
            lexical=_unit(self.lexical),
            semantic=_unit(self.semantic),
            governance=_unit(self.governance),
            graph=_unit(self.graph),
        )


@dataclass(frozen=True, slots=True)
class RetrievalScoreWeights:
    """Fixed deterministic fusion weights for the first hybrid router slice."""

    lexical: float = 0.35
    semantic: float = 0.25
    governance: float = 0.25
    graph: float = 0.15


@dataclass(frozen=True, slots=True)
class ScoreInput:
    """Candidate input for pure score fusion."""

    id: str
    signals: SignalScores
    status: str = "confirmed"
    depth: int = 0


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    """Candidate after pure signal fusion and deterministic tie-break metadata."""

    id: str
    score: float
    signals: SignalScores
    governance_tier: int
    depth: int
    status: str


def rank_candidates(
    candidates: list[ScoreInput],
    *,
    weights: RetrievalScoreWeights | None = None,
) -> list[RankedCandidate]:
    """Fuse candidate signals and return stable, trust-aware ranking."""
    active_weights = weights or RetrievalScoreWeights()
    ranked = [_rank_candidate(candidate, active_weights) for candidate in candidates]
    return sorted(
        ranked,
        key=lambda candidate: (
            -candidate.score,
            candidate.governance_tier,
            candidate.depth,
            candidate.id,
        ),
    )


def _rank_candidate(candidate: ScoreInput, weights: RetrievalScoreWeights) -> RankedCandidate:
    signals = candidate.signals.normalized()
    raw_score = (
        signals.lexical * weights.lexical
        + signals.semantic * weights.semantic
        + signals.governance * weights.governance
        + signals.graph * weights.graph
    )
    multiplier = _STATUS_MULTIPLIERS.get(candidate.status, 0.7)
    return RankedCandidate(
        id=candidate.id,
        score=round(_unit(raw_score * multiplier), 6),
        signals=signals,
        governance_tier=_STATUS_TIERS.get(candidate.status, 5),
        depth=max(0, int(candidate.depth)),
        status=candidate.status,
    )


def _unit(value: float) -> float:
    return max(0.0, min(float(value), 1.0))
