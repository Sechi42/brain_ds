"""Confidence-ledger capture and calibration helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from brain_ds.ontology.relationship_types import RelationshipType
from brain_ds.store.models import LedgerRow
from brain_ds.verify.edge_calibration import (
    EdgeCalibrationReport,
    EdgeGoldRecord,
    GoldVerdict,
    _iter_jsonl,
    _parse_gold_line,
    calibrate_edges,
)
from brain_ds.verify.edge_rollout import DEFAULT_POLICY, RolloutPolicy

DEFAULT_THRESHOLD = 0.55
_SENSITIVE_OWNERSHIP_LABELS = {"owns", "owned-by"}
_VERDICT_BY_STATUS: dict[str, GoldVerdict] = {
    "confirmed": "valid",
    "invalidated": "invalid",
    "abstain": "abstain",
}


_SENSITIVE_NODE_TYPES = {"Role", "Person"}


def _should_flag_for_confirmation(
    *,
    label: str,
    source_type: str | None,
    target_type: str | None,
    weight: float | None,
    verifier_findings: Sequence[dict] | None = None,
    target_kind: str = "edge",
    fact_subject_type: str | None = None,
) -> str | None:
    """Return a reason when an inferred fact needs human confirmation.

    target_kind='node': evaluates node-fact sensitivity rules.
    target_kind='edge' (default): evaluates edge sensitivity rules (unchanged).
    """
    if target_kind == "node":
        if fact_subject_type in _SENSITIVE_NODE_TYPES:
            return "sensitive_node_fact"
        return None

    # Edge path (original behavior preserved exactly)
    normalized_label = label.lower()
    if normalized_label in _SENSITIVE_OWNERSHIP_LABELS and "Role" in {source_type, target_type}:
        return "sensitive_ownership_transition"
    if weight is not None and 0.0 < weight < DEFAULT_THRESHOLD:
        return "low_confidence_abstain_band"
    if any(str(finding.get("severity", "")).upper() == "CRITICAL" for finding in verifier_findings or ()):
        return "verifier_critical_finding"
    return None


def ledger_to_gold_records(rows: Iterable[LedgerRow]) -> list[EdgeGoldRecord]:
    """Convert latest verdict-bearing ledger states to calibration gold records."""
    latest_by_target: dict[str, LedgerRow] = {}
    for row in rows:
        if row.id is None:
            latest_by_target[row.target_id] = row
            continue
        current = latest_by_target.get(row.target_id)
        if current is None or current.id is None or row.id > current.id:
            latest_by_target[row.target_id] = row

    records: list[EdgeGoldRecord] = []
    for row in sorted(latest_by_target.values(), key=lambda item: item.id or 0):
        verdict = _VERDICT_BY_STATUS.get(row.status)
        if verdict is None:
            continue
        weight = row.current_confidence
        if weight is None:
            weight = row.initial_confidence if row.initial_confidence is not None else 0.0
        records.append(
            EdgeGoldRecord(
                edge_id=row.target_id,
                graph_id=row.graph_id,
                label=row.relationship_label or getattr(row, "fact_label", None) or "",
                source_type=row.source_node_type or "",
                target_type=row.target_node_type or "",
                weight=max(0.0, min(1.0, weight)),
                evidence_ids=tuple(str(item) for item in row.evidence_ids or []),
                gold_verdict=verdict,
                gold_rationale=row.gold_rationale or f"ledger:{row.status} by={row.captured_by}",
                provenance=row.provenance,  # type: ignore[arg-type]
            )
        )
    return records


def calibrate_from_ledger(
    graph_id: str,
    store,
    *,
    global_seed_path: str | Path = "tests/gold/edge_gold_set.jsonl",
    policy: RolloutPolicy = DEFAULT_POLICY,
) -> EdgeCalibrationReport:
    """Calibrate from per-graph ledger rows with sparse-label seed fallback."""
    records = ledger_to_gold_records(store.query_ledger_latest(graph_id))
    records = _merge_global_seed(records, global_seed_path, policy)
    return calibrate_edges(records)


def _merge_global_seed(
    records: list[EdgeGoldRecord],
    global_seed_path: str | Path,
    policy: RolloutPolicy,
) -> list[EdgeGoldRecord]:
    counts_by_label: dict[str, int] = {}
    for record in records:
        counts_by_label[record.label] = counts_by_label.get(record.label, 0) + 1

    expected_labels = {relationship.value for relationship in RelationshipType}
    sparse_labels = {
        label
        for label in expected_labels
        if counts_by_label.get(label, 0) < policy.min_examples_per_relationship_type
    }
    if not sparse_labels:
        return records

    seed_records = [
        _parse_gold_line(line, global_seed_path, line_number, include_generated=False)
        for line_number, line in _iter_jsonl(global_seed_path)
    ]
    return [*records, *[record for record in seed_records if record.label in sparse_labels]]
