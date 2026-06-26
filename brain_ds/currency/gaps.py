"""Pure gap aggregation for temporal currency assessment."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .coverage import coverage_score
from .criticality import criticality_score
from .staleness import classify_staleness, resolve_last_seen
from .stakeholder import resolve_owner

TYPE_WEIGHTS = {
    "DATA_SOURCE": 1.0,
    "KPI": 0.9,
    "PROBLEM": 0.85,
    "PROBLEM_IMPROVEMENT_AREA": 0.85,
    "DECISION": 0.8,
    "RISK": 0.8,
    "PROJECT": 0.75,
    "SOLUTION": 0.75,
    "ORGANIZATION": 0.7,
    "DEPARTMENT": 0.65,
    "ROLE": 0.65,
    "HEURISTIC": 0.45,
    "TACIT_KNOWLEDGE": 0.45,
}


def aggregate_gaps(
    nodes: list[Any],
    adjacency: dict[str, set[str]],
    ledger_evidence: dict[str, Any],
    thresholds: dict[str, int] | None = None,
    *,
    top_n: int = 10,
    now: datetime | str | None = None,
    sparse_node_ids: set[str] | None = None,
    question_bank: dict[str, list[str]] | None = None,
    edges: list[dict[str, Any]] | None = None,
    structural_missing_types: list[str] | None = None,
    calibration_gap_labels: list[str] | None = None,
) -> dict[str, Any]:
    """Aggregate currency, structural, sparse, and calibration gaps."""
    reference = _as_datetime(now) or datetime.now(timezone.utc)
    sparse_ids = {str(node_id) for node_id in (sparse_node_ids or set())}
    nodes_by_id = {_field(node, "id"): _node_dict(node) for node in nodes}
    assessed: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []

    for node in nodes:
        node_id = _field(node, "id")
        entity_type = _field(node, "type")
        evidence = _evidence_dict(ledger_evidence.get(node_id))
        ledger_status = evidence.get("status") or evidence.get("ledger_status")
        last_seen = resolve_last_seen(
            ledger_status=ledger_status,
            ledger_confirmed_at=evidence.get("confirmed_at") or evidence.get("ledger_confirmed_at"),
            ledger_captured_at=_ledger_captured_at_for_currency(evidence, ledger_status),
            schema_baseline_last_documented_at=evidence.get(
                "schema_baseline_last_documented_at"
            ),
            modified_at=evidence.get("modified_at") or _field(node, "modified_at") or None,
            created_at=evidence.get("created_at") or _field(node, "created_at") or None,
        )
        staleness = classify_staleness(
            entity_type,
            last_seen,
            thresholds=thresholds,
            now=reference,
        )
        assessed.append(
            {
                "entity_type": entity_type,
                "staleness_class": staleness,
                "ledger_status": ledger_status,
                "confirmed_within_window": ledger_status == "confirmed" and staleness == "current",
            }
        )

        gap_kinds = []
        if staleness in {"stale", "unknown"}:
            gap_kinds.append("staleness")
        if node_id in sparse_ids:
            gap_kinds.append("sparseness")
        if not gap_kinds:
            continue

        criticality = criticality_score(
            node_id,
            adjacency,
            in_degree=_in_degree(node_id, edges or []),
            incident_weights=_incident_weights(node_id, edges or []),
            type_weight=TYPE_WEIGHTS.get(_normalize(entity_type), 0.5),
            brd_ref=bool(evidence.get("brd_ref")),
            kpi_feed=bool(evidence.get("kpi_feed")),
        )
        priority = round(_staleness_factor(staleness, last_seen, reference, entity_type, thresholds) * criticality, 6)
        stakeholder = resolve_owner(node_id, edges or [], nodes_by_id)
        questions = _questions_for(gap_kinds[0], entity_type, question_bank)
        gaps.append(
            {
                "node_id": node_id,
                "gap_kind": gap_kinds,
                "staleness_class": staleness,
                "criticality_score": criticality,
                "priority": priority,
                "suggested_questions": questions,
                "stakeholder_tags": [stakeholder],
            }
        )

    gaps.extend(_structural_gap_entries(structural_missing_types or []))
    gaps.extend(_calibration_gap_entries(calibration_gap_labels or []))

    ranked = sorted(gaps, key=lambda item: (-float(item["priority"]), str(item["node_id"])))
    capped = ranked[: max(int(top_n), 0)]
    return {
        "ranked_gaps": capped,
        "coverage": coverage_score(assessed),
        "suggested_questions": [
            {"node_id": gap["node_id"], "question": question, "stakeholder_tag": gap["stakeholder_tags"][0]}
            for gap in capped
            for question in gap["suggested_questions"]
        ],
    }


def _ledger_captured_at_for_currency(evidence: dict[str, Any], ledger_status: Any) -> Any:
    if ledger_status == "needs-confirmation":
        return None
    return evidence.get("captured_at") or evidence.get("ledger_captured_at")


def _structural_gap_entries(missing_types: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "node_id": f"missing:{entity_type}",
            "gap_kind": ["structural"],
            "staleness_class": "unknown",
            "criticality_score": 0.0,
            "priority": 0.0,
            "suggested_questions": [],
            "stakeholder_tags": ["unknown"],
        }
        for entity_type in sorted({str(item) for item in missing_types})
    ]


def _calibration_gap_entries(labels: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "node_id": f"calibration:{label}",
            "gap_kind": ["calibration"],
            "staleness_class": "unknown",
            "criticality_score": 0.0,
            "priority": 0.0,
            "suggested_questions": [],
            "stakeholder_tags": ["unknown"],
        }
        for label in sorted({str(item) for item in labels})
    ]


def _staleness_factor(
    staleness: str,
    last_seen: datetime | None,
    now: datetime,
    entity_type: str,
    thresholds: dict[str, int] | None,
) -> float:
    if staleness == "unknown" or last_seen is None:
        return 1.0
    window = (thresholds or {}).get(entity_type) or (thresholds or {}).get(_normalize(entity_type)) or 60
    age_days = max((now - last_seen).total_seconds() / 86_400, 0.0)
    return max(1.0, age_days / window)


def _questions_for(
    gap_kind: str,
    entity_type: str,
    question_bank: dict[str, list[str]] | None,
) -> list[str]:
    if not question_bank:
        return []
    return list(question_bank.get(entity_type) or question_bank.get(entity_type.replace("_", " ").title()) or [])


def _node_dict(node: Any) -> dict[str, Any]:
    if isinstance(node, dict):
        return node
    return {"id": _field(node, "id"), "label": _field(node, "label"), "type": _field(node, "type")}


def _field(item: Any, name: str) -> str:
    if isinstance(item, dict):
        return str(item.get(name) or "")
    return str(getattr(item, name, "") or "")


def _evidence_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    return {
        "status": getattr(value, "status", None),
        "captured_at": getattr(value, "captured_at", None),
        "confirmed_at": getattr(value, "confirmed_at", None),
    }


def _incident_weights(node_id: str, edges: list[dict[str, Any]]) -> list[float]:
    weights = []
    for edge in edges:
        if node_id in {str(edge.get("source", "")), str(edge.get("target", ""))}:
            weights.append(float(edge.get("weight") or 0.0))
    return weights


def _in_degree(node_id: str, edges: list[dict[str, Any]]) -> int:
    return sum(1 for edge in edges if str(edge.get("target", "")) == node_id)


def _normalize(value: str) -> str:
    return str(value or "").strip().upper().replace(" ", "_").replace("/", "_")


def _as_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
