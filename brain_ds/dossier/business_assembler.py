"""Pure business-first dossier assembly."""

from __future__ import annotations

from typing import Any

from brain_ds.dossier.business_models import (
    BusinessDossier,
    BusinessInterpretation,
    BusinessUncertainty,
    PendingQuestionProposal,
)
from brain_ds.dossier.models import DossierGapInputs, DossierGraphView
from brain_ds.retrieval.neighborhood import expand_neighborhood

_SECTION_TYPES = {
    "kpis": {"KPI"},
    "problems": {"ProblemImprovementArea", "Problem/ImprovementArea", "Problem / Improvement Area", "Risk"},
    "departments": {"Department", "Organization"},
    "processes": {"Process", "Heuristic", "Project", "Decision"},
    "actors": {"Role"},
}
_BUSINESS_TYPES = set().union(*_SECTION_TYPES.values())
_SOURCE_TYPES = {"DataSource", "Data Source", "DataContainer", "DataField"}


def assemble_business_dossier(
    view: DossierGraphView,
    gaps: DossierGapInputs,
    *,
    query: str,
    interpretations: list[BusinessInterpretation],
    depth: int = 2,
) -> BusinessDossier:
    """Project ranked interpretations into a bounded business-first dossier."""
    selected = _selected_interpretation(interpretations)
    reachable_ids = _reachable_ids(view, selected, depth)
    sections = {section: [] for section in _SECTION_TYPES}
    evidence_sources: list[dict[str, Any]] = []

    for node_id in sorted(reachable_ids, key=lambda value: (_source_sort_key(view.nodes_by_id.get(value)), value)):
        node = view.nodes_by_id.get(node_id)
        node_type = _type(node)
        if node_type in _SOURCE_TYPES:
            evidence_sources.append(_node_dict(node))
            continue
        for section, type_names in _SECTION_TYPES.items():
            if node_type in type_names:
                sections[section].append(_node_dict(node))
                break

    business_count = sum(len(items) for items in sections.values())
    uncertainty = BusinessUncertainty(
        source_heavy=bool(evidence_sources) and business_count == 0,
        business_light=business_count == 0,
        completeness=_dedupe_dicts(gaps.completeness),
        currency=_dedupe_dicts(gaps.currency),
        weak_edges=_dedupe_dicts(gaps.weak_edges),
    )
    return BusinessDossier(
        query=query,
        selected_interpretation_id=selected.id if selected else "",
        interpretations=interpretations,
        dossier=sections,
        evidence_sources=evidence_sources,
        uncertainty=uncertainty,
        pending_question_proposals=_pending_question_proposals(view, gaps),
    )


def _selected_interpretation(interpretations: list[BusinessInterpretation]) -> BusinessInterpretation | None:
    if not interpretations:
        return None
    return next((item for item in interpretations if item.is_default), interpretations[0])


def _reachable_ids(view: DossierGraphView, selected: BusinessInterpretation | None, depth: int) -> set[str]:
    if selected is None:
        return set()
    anchors = [*selected.entity_ids, *selected.evidence_ids]
    reachable = set(expand_neighborhood(anchors, view.adjacency, depth=depth))
    reachable.update(anchors)
    for evidence_id in selected.evidence_ids:
        for child in view.children_by_parent.get(evidence_id, []):
            reachable.add(child.id)
    return {node_id for node_id in reachable if node_id in view.nodes_by_id}


def _pending_question_proposals(view: DossierGraphView, gaps: DossierGapInputs) -> list[PendingQuestionProposal]:
    proposals: list[PendingQuestionProposal] = []
    for gap in [*gaps.unconfirmed_lineage, *gaps.weak_edges]:
        target_node_id = str(gap.get("to_node") or gap.get("target_node_id") or "")
        if not target_node_id:
            continue
        source_id = str(gap.get("from_node") or "")
        source = view.nodes_by_id.get(source_id)
        target = view.nodes_by_id.get(target_node_id)
        relationship = str(gap.get("relationship") or gap.get("gap_kind") or "business-link")
        proposals.append(
            PendingQuestionProposal(
                target_node_id=target_node_id,
                gap_kind=relationship,
                entity_type=_type(target) or str(gap.get("entity_type") or "Unknown"),
                question_text=_question_text(source, target, relationship),
                stakeholder_owner=str(gap.get("stakeholder_owner") or ""),
                evidence_ids=(str(gap.get("candidate_id")),) if gap.get("candidate_id") else (),
            )
        )
    return _dedupe_proposals(proposals)


def _question_text(source: Any, target: Any, relationship: str) -> str:
    source_label = getattr(source, "label", "this business item")
    target_label = getattr(target, "label", "the target item")
    return f"Can you confirm whether {source_label} has a {relationship} relationship with {target_label}?"


def _node_dict(node: Any) -> dict[str, Any]:
    return {"id": node.id, "label": node.label, "entity_type": _type(node), "details": _description(node)}


def _description(node: Any) -> str:
    details = getattr(node, "details", None) or {}
    if isinstance(details, dict):
        value = details.get("description") or details.get("summary") or details.get("meaning")
        if value is not None:
            return str(value)
    return ""


def _type(node: Any) -> str | None:
    value = getattr(node, "type", None) if node is not None else None
    return str(value) if value is not None else None


def _source_sort_key(node: Any) -> int:
    order = {"DataSource": 0, "Data Source": 0, "DataContainer": 1, "DataField": 2}
    return order.get(_type(node) or "", 3)


def _dedupe_dicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        key = repr(sorted(item.items()))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _dedupe_proposals(items: list[PendingQuestionProposal]) -> list[PendingQuestionProposal]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[PendingQuestionProposal] = []
    for item in items:
        key = (item.target_node_id, item.gap_kind, item.question_text)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique
