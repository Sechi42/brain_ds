"""Offline retrieval evaluation harness."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from time import perf_counter

from brain_ds.retrieval.hybrid_router import HybridRetrievalRouter
from brain_ds.retrieval.models import RetrievalCandidate, RetrievalRequest
from brain_ds.scoring.retrieval import SignalScores


SIGNAL_FAMILIES = ("lexical", "semantic", "governance", "graph")
_OUT_OF_SCOPE_TERMS = (
    "viewer",
    "ui",
    "bulk write",
    "bulk mutation",
    "persist evaluation",
    "unrelated architecture",
    "workspace rewrite",
)


@dataclass(frozen=True, slots=True)
class LabeledQuery:
    """Offline evaluation query with known relevant result identifiers."""

    query: str
    relevant_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "relevant_ids", tuple(self.relevant_ids))


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    """Comparable offline evaluation output for one router configuration."""

    metrics: dict[str, float]
    deterministic: bool
    query_count: int
    ablation: str = "baseline"

    def __post_init__(self) -> None:
        object.__setattr__(self, "metrics", dict(self.metrics))


@dataclass(slots=True)
class EvaluationHarness:
    """Run deterministic, read-only retrieval evaluations over labeled queries."""

    router: HybridRetrievalRouter

    def evaluate(self, queries: list[LabeledQuery], *, k: int = 5, repeats: int = 2) -> EvaluationReport:
        """Evaluate quality, latency, and repeated-run determinism."""
        bounded_k = max(1, int(k))
        bounded_repeats = max(1, int(repeats))
        recalls: list[float] = []
        precisions: list[float] = []
        ndcgs: list[float] = []
        latencies_ms: list[float] = []
        deterministic = True

        for labeled_query in queries:
            repeated_rankings: list[tuple[str, ...]] = []
            for _ in range(bounded_repeats):
                started = perf_counter()
                result = self.router.retrieve(
                    RetrievalRequest(query=labeled_query.query, limit=bounded_k, depth=2)
                )
                latencies_ms.append((perf_counter() - started) * 1000.0)
                repeated_rankings.append(tuple(anchor.id for anchor in result.anchors[:bounded_k]))

            first_ranking = repeated_rankings[0]
            deterministic = deterministic and all(ranking == first_ranking for ranking in repeated_rankings)
            relevant = set(labeled_query.relevant_ids)
            hits = [node_id for node_id in first_ranking if node_id in relevant]
            recalls.append(len(hits) / len(relevant) if relevant else 1.0)
            precisions.append(len(hits) / bounded_k)
            ndcgs.append(_ndcg(first_ranking, relevant, bounded_k))

        metrics = {
            f"recall@{bounded_k}": _mean(recalls),
            f"precision@{bounded_k}": _mean(precisions),
            f"ndcg@{bounded_k}": _mean(ndcgs),
            "p50_latency_ms": round(median(latencies_ms), 6) if latencies_ms else 0.0,
            "p95_latency_ms": round(_percentile(latencies_ms, 0.95), 6) if latencies_ms else 0.0,
        }
        return EvaluationReport(metrics=metrics, deterministic=deterministic, query_count=len(queries))

    def evaluate_ablations(
        self,
        queries: list[LabeledQuery],
        *,
        k: int = 5,
        repeats: int = 2,
    ) -> dict[str, EvaluationReport]:
        """Compare the baseline against lexical, semantic, governance, and graph ablations."""
        reports = {"baseline": self.evaluate(queries, k=k, repeats=repeats)}
        for signal in SIGNAL_FAMILIES:
            ablated_router = HybridRetrievalRouter(
                candidates=[_candidate_without_signal(candidate, signal) for candidate in self.router.candidates],
                weights=self.router.weights,
            )
            report = EvaluationHarness(router=ablated_router).evaluate(queries, k=k, repeats=repeats)
            reports[f"without_{signal}"] = EvaluationReport(
                metrics=report.metrics,
                deterministic=report.deterministic,
                query_count=report.query_count,
                ablation=f"without_{signal}",
            )
        return reports


def load_query_set(path: Path) -> list[LabeledQuery]:
    """Load labeled queries from a small offline JSON fixture."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        LabeledQuery(query=str(item["query"]), relevant_ids=tuple(item.get("relevant_ids", ())))
        for item in payload["queries"]
    ]


def is_evaluation_scope_allowed(change_request: str) -> bool:
    """Return whether a request belongs to retrieval evaluation harness scope."""
    normalized = change_request.lower()
    return not any(term in normalized for term in _OUT_OF_SCOPE_TERMS)


def _candidate_without_signal(candidate: RetrievalCandidate, signal: str) -> RetrievalCandidate:
    signals = candidate.signals.normalized()
    ablated = SignalScores(
        lexical=0.0 if signal == "lexical" else signals.lexical,
        semantic=0.0 if signal == "semantic" else signals.semantic,
        governance=0.0 if signal == "governance" else signals.governance,
        graph=0.0 if signal == "graph" else signals.graph,
    )
    return RetrievalCandidate(
        id=candidate.id,
        label=candidate.label,
        signals=ablated,
        status=candidate.status,
        depth=candidate.depth,
        neighbor_ids=candidate.neighbor_ids,
        metadata=candidate.metadata,
    )


def _ndcg(ranking: tuple[str, ...], relevant: set[str], k: int) -> float:
    if not relevant:
        return 1.0
    dcg = sum(1.0 / math.log2(index + 2) for index, node_id in enumerate(ranking[:k]) if node_id in relevant)
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(index + 2) for index in range(ideal_hits))
    return round(dcg / idcg, 6) if idcg else 0.0


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 6) if values else 0.0


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, math.ceil(len(ordered) * percentile) - 1)
    return ordered[index]
