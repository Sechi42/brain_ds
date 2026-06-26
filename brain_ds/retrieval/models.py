"""Use-case DTOs for hybrid retrieval."""

from __future__ import annotations

from dataclasses import dataclass, field

from brain_ds.scoring.retrieval import SignalScores

MAX_RETRIEVAL_LIMIT = 50
MAX_RETRIEVAL_DEPTH = 2
MAX_ROUTER_ANCHORS = 5


@dataclass(frozen=True, slots=True)
class RetrievalRequest:
    """Internal retrieval request independent from MCP request/response JSON."""

    query: str
    limit: int = 10
    depth: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "limit", max(1, min(int(self.limit), MAX_RETRIEVAL_LIMIT)))
        object.__setattr__(self, "depth", max(1, min(int(self.depth), MAX_RETRIEVAL_DEPTH)))


@dataclass(frozen=True, slots=True)
class RetrievalCandidate:
    """Abstract candidate supplied to the router by future adapters or tests."""

    id: str
    label: str
    signals: SignalScores = field(default_factory=SignalScores)
    status: str = "confirmed"
    depth: int = 0
    neighbor_ids: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "neighbor_ids", tuple(self.neighbor_ids))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True, slots=True)
class RouterAnchor:
    """Bounded anchor selected by the retrieval use case."""

    id: str
    score: float
    label: str = ""
    status: str = "confirmed"
    depth: int = 0
    signals: SignalScores = field(default_factory=SignalScores)


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    """Pure retrieval result for later MCP serialization."""

    anchors: tuple[RouterAnchor, ...] = ()
    candidate_depths: dict[str, int] = field(default_factory=dict)
    dense_used: bool = False
    module_route: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "anchors", tuple(self.anchors[:MAX_ROUTER_ANCHORS]))
        object.__setattr__(self, "candidate_depths", dict(self.candidate_depths))
        object.__setattr__(self, "module_route", dict(self.module_route))
