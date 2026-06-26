"""Pure business interpretation ranking for query-first dossiers."""

from __future__ import annotations

from typing import Any

from brain_ds.dossier.business_models import BusinessInterpretation, MAX_BUSINESS_ALTERNATIVES
from brain_ds.retrieval.models import RetrievalCandidate
from brain_ds.retrieval.neighborhood import ClusterRoute
from brain_ds.scoring.retrieval import ScoreInput, rank_candidates

_BUSINESS_TYPE_BOOSTS = {
    "KPI": 0.25,
    "Problem / Improvement Area": 0.24,
    "ProblemImprovementArea": 0.24,
    "Department": 0.22,
    "Process": 0.18,
    "Heuristic": 0.18,
    "Project": 0.18,
    "Decision": 0.18,
    "Organization": 0.16,
    "Role": 0.16,
}
_SOURCE_TYPES = {"DataSource", "Data Source", "DataContainer", "DataField"}


def rank_business_interpretations(
    *,
    query: str,
    candidates: list[RetrievalCandidate],
    cluster_routes: list[ClusterRoute] | None = None,
    max_alternatives: int = MAX_BUSINESS_ALTERNATIVES,
) -> list[BusinessInterpretation]:
    """Rank retrieval and cluster candidates into bounded business interpretations."""
    limit = max(1, min(int(max_alternatives), MAX_BUSINESS_ALTERNATIVES))
    ranked_candidates = _rank_retrieval_candidates(candidates)
    interpretations = [*_cluster_interpretations(cluster_routes or []), *ranked_candidates]
    interpretations.sort(key=lambda item: (-item.confidence, item.entity_type in _SOURCE_TYPES, item.label, item.id))

    bounded = interpretations[:limit]
    return [
        BusinessInterpretation(
            id=item.id,
            label=item.label,
            entity_type=item.entity_type,
            entity_ids=item.entity_ids,
            evidence_ids=item.evidence_ids,
            confidence=item.confidence,
            rationale=item.rationale or f"Ranked interpretation for query '{query}'.",
            is_default=index == 0,
        )
        for index, item in enumerate(bounded)
    ]


def _rank_retrieval_candidates(candidates: list[RetrievalCandidate]) -> list[BusinessInterpretation]:
    ranked_by_id = {
        item.id: item
        for item in rank_candidates(
            [ScoreInput(id=candidate.id, signals=candidate.signals, status=candidate.status, depth=candidate.depth) for candidate in candidates]
        )
    }
    interpretations: list[BusinessInterpretation] = []
    for candidate in candidates:
        ranked = ranked_by_id[candidate.id]
        entity_type = _entity_type(candidate.metadata)
        confidence = min(1.0, ranked.score + _BUSINESS_TYPE_BOOSTS.get(entity_type, 0.0))
        interpretations.append(
            BusinessInterpretation(
                id=candidate.id,
                label=candidate.label,
                entity_type=entity_type,
                entity_ids=(candidate.id,),
                evidence_ids=_evidence_ids(candidate),
                confidence=confidence,
                rationale=f"{entity_type} candidate ranked from retrieval signals.",
            )
        )
    return interpretations


def _cluster_interpretations(routes: list[ClusterRoute]) -> list[BusinessInterpretation]:
    interpretations: list[BusinessInterpretation] = []
    for route in routes:
        evidence_ids = tuple(node_id for node_id in route.member_ids if _looks_like_source_id(node_id))
        entity_ids = tuple(node_id for node_id in route.member_ids if node_id not in evidence_ids)
        confidence = min(1.0, 0.62 + (route.routing_weight * 0.25))
        interpretations.append(
            BusinessInterpretation(
                id=route.id,
                label=route.name,
                entity_type="Cluster",
                entity_ids=entity_ids or tuple(route.anchor_ids),
                evidence_ids=evidence_ids,
                confidence=confidence,
                rationale=route.summary or "Selected semantic cluster route.",
            )
        )
    return interpretations


def _entity_type(metadata: dict[str, Any]) -> str:
    value = metadata.get("type") or metadata.get("entity_type") or "Unknown"
    return str(value)


def _evidence_ids(candidate: RetrievalCandidate) -> tuple[str, ...]:
    evidence = candidate.metadata.get("evidence_ids")
    if isinstance(evidence, list | tuple):
        return tuple(str(item) for item in evidence)
    if _entity_type(candidate.metadata) in _SOURCE_TYPES:
        return (candidate.id,)
    return ()


def _looks_like_source_id(node_id: str) -> bool:
    lowered = node_id.lower()
    return lowered.startswith(("ds", "dc", "df", "source", "container", "field"))
