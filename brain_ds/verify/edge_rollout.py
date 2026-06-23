"""Advisory rollout gate for the semantic edge judge.

This module turns an :class:`EdgeCalibrationReport` plus its source gold
records into a structured ``rollout_ready`` vs ``advisory_only`` verdict with
explicit named reasons. It is the Phase 5 advisory half of the rollout
contract in the ``semantic-edge-judge-calibration`` change (spec section E).

The helper is intentionally:

* **Pure** — no I/O, no MCP tool calls, no chat-completion client, no graph
  mutation. The input report and records are read-only.
* **Advisory-only** — the result never blocks ``archive``,
  ``update_node``, ``add_edge``, or any other operation. The actual gating
  is enforced by callers; the helper surfaces the structured reasons so
  those callers can decide what to do.
* **Calibration-scoped** — it evaluates calibration quality and gold-set
  provenance, not the snapshot API surface. Large-graph safety
  (MCP ``snapshot_edges`` ``400 limit_required`` and payload caps) is
  documented as a still-required, separate follow-up and surfaced as an
  advisory note, not as a hard failing gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Sequence

from brain_ds.ontology.relationship_types import RelationshipType
from brain_ds.verify.edge_calibration import (
    EdgeCalibrationReport,
    EdgeGoldRecord,
    EdgeClassMetrics,
)

RolloutStatus = Literal["rollout_ready", "advisory_only"]


class GateReason(StrEnum):
    """Named reasons surfaced by :func:`evaluate_rollout_gates`."""

    SEED_ONLY_BASELINE = "seed_only_baseline"
    GENERATED_RECORDS_PRESENT = "generated_records_present"
    INSUFFICIENT_HAND_LABELED = "insufficient_hand_labeled"
    INSUFFICIENT_EXAMPLES_PER_TYPE = "insufficient_examples_per_type"
    BELOW_PRECISION = "below_precision_threshold"
    BELOW_RECALL = "below_recall_threshold"
    ABOVE_FALSE_POSITIVE = "above_false_positive_threshold"
    ABOVE_FALSE_NEGATIVE = "above_false_negative_threshold"
    ABSTAIN_BAND_TOO_WIDE = "abstain_band_too_wide"
    MISSING_CLASS_METRICS = "missing_class_metrics"
    CONSECUTIVE_RUNS_INSUFFICIENT = "consecutive_runs_insufficient"
    HUMAN_ABSTAIN_REVIEW_INSUFFICIENT = "human_abstain_review_insufficient"
    LARGE_GRAPH_SAFETY_PENDING = "large_graph_safety_pending_followup"


def _validate_rate(field_name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{field_name} must be in [0,1]")


def _validate_non_negative_int(field_name: str, value: int) -> None:
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


@dataclass(frozen=True)
class RolloutPolicy:
    """Tunable thresholds for the rollout gate.

    Defaults mirror the spec section E gates and the calibration spec
    per-class thresholds. Override individual fields to tighten or relax
    a single dimension; the helper is read-only against the input report
    and records regardless of policy.
    """

    min_examples_per_relationship_type: int = 10
    min_hand_labeled_per_relationship_type: int = 10
    min_precision: float = 0.85
    min_recall: float = 0.70
    max_false_positive_rate: float = 0.15
    max_false_negative_rate: float = 0.30
    max_abstain_band_size: float = 0.50
    min_hand_labeled_total: int = 50
    min_consecutive_runs: int = 2
    min_human_reviewed_abstain: int = 20

    def __post_init__(self) -> None:
        _validate_non_negative_int(
            "min_examples_per_relationship_type",
            self.min_examples_per_relationship_type,
        )
        _validate_non_negative_int(
            "min_hand_labeled_per_relationship_type",
            self.min_hand_labeled_per_relationship_type,
        )
        _validate_rate("min_precision", self.min_precision)
        _validate_rate("min_recall", self.min_recall)
        _validate_rate("max_false_positive_rate", self.max_false_positive_rate)
        _validate_rate("max_false_negative_rate", self.max_false_negative_rate)
        _validate_rate("max_abstain_band_size", self.max_abstain_band_size)
        _validate_non_negative_int("min_hand_labeled_total", self.min_hand_labeled_total)
        _validate_non_negative_int("min_consecutive_runs", self.min_consecutive_runs)
        _validate_non_negative_int(
            "min_human_reviewed_abstain",
            self.min_human_reviewed_abstain,
        )


@dataclass(frozen=True)
class RolloutGateResult:
    """Structured verdict from :func:`evaluate_rollout_gates`.

    ``status`` is the rolled-up verdict. ``failing_reasons`` lists the gates
    that flipped the verdict to ``advisory_only``. ``advisory_notes`` lists
    follow-up items that the caller should track but that do not by
    themselves block rollout — e.g. large-graph safety, which lives in a
    separate Phase 5 work unit.
    """

    status: RolloutStatus
    failing_reasons: tuple[GateReason, ...]
    failing_by_class: dict[str, tuple[GateReason, ...]]
    advisory_notes: tuple[GateReason, ...]


DEFAULT_POLICY = RolloutPolicy()


def evaluate_rollout_gates(
    report: EdgeCalibrationReport,
    records: Sequence[EdgeGoldRecord],
    *,
    policy: RolloutPolicy = DEFAULT_POLICY,
    consecutive_passing_runs: int = 1,
    human_reviewed_abstain_count: int = 0,
) -> RolloutGateResult:
    """Evaluate whether the edge judge is rollout-ready.

    Parameters
    ----------
    report:
        Output of :func:`calibrate_edges` for the current gold set.
    records:
        The gold records that produced ``report``. Used to inspect
        provenance distribution; the helper does not mutate them.
    policy:
        Optional override of the rollout thresholds. Defaults match the
        spec section E gates.
    consecutive_passing_runs:
        Number of consecutive calibration runs that already met the
        per-class metrics. The spec requires two; callers that have not
        yet collected a second passing run should pass ``1``.
    human_reviewed_abstain_count:
        Number of abstain-band edges that have been human-reviewed per
        the spec's 20-edge review requirement.

    Returns
    -------
    :class:`RolloutGateResult`
        The status (``rollout_ready`` or ``advisory_only``) plus the named
        reasons. The result never mutates ``report`` or ``records``.
    """
    failing_by_class: dict[str, list[GateReason]] = {}
    global_failing: list[GateReason] = []
    provenance_counts = _safe_provenance_counts(records)
    hand_labeled_by_label = _hand_labeled_counts_by_label(records)
    metrics_by_label = dict(report.classes)

    if _is_seed_only(provenance_counts):
        global_failing.append(GateReason.SEED_ONLY_BASELINE)
    if provenance_counts.get("generated", 0) > 0:
        global_failing.append(GateReason.GENERATED_RECORDS_PRESENT)
    if provenance_counts.get("hand_labeled", 0) < policy.min_hand_labeled_total:
        global_failing.append(GateReason.INSUFFICIENT_HAND_LABELED)

    expected_labels = {relationship.value for relationship in RelationshipType}
    for label in sorted(expected_labels - metrics_by_label.keys()):
        _add_class_failure(
            failing_by_class,
            label,
            GateReason.MISSING_CLASS_METRICS,
        )

    for label in sorted(expected_labels):
        if hand_labeled_by_label.get(label, 0) < policy.min_hand_labeled_per_relationship_type:
            _add_class_failure(
                failing_by_class,
                label,
                GateReason.INSUFFICIENT_HAND_LABELED,
            )

    for label, metrics in sorted(metrics_by_label.items()):
        if metrics.examples < policy.min_examples_per_relationship_type:
            _add_class_failure(
                failing_by_class,
                label,
                GateReason.INSUFFICIENT_EXAMPLES_PER_TYPE,
            )

    _collect_metric_failures(metrics_by_label, policy, failing_by_class)

    if consecutive_passing_runs < policy.min_consecutive_runs:
        global_failing.append(GateReason.CONSECUTIVE_RUNS_INSUFFICIENT)
    if human_reviewed_abstain_count < policy.min_human_reviewed_abstain:
        global_failing.append(GateReason.HUMAN_ABSTAIN_REVIEW_INSUFFICIENT)

    advisory_notes: list[GateReason] = [GateReason.LARGE_GRAPH_SAFETY_PENDING]
    failing = _dedupe_reasons(
        [*global_failing, *[reason for reasons in failing_by_class.values() for reason in reasons]]
    )
    status: RolloutStatus = "advisory_only" if failing else "rollout_ready"
    return RolloutGateResult(
        status=status,
        failing_reasons=tuple(failing),
        failing_by_class={
            label: tuple(_dedupe_reasons(reasons))
            for label, reasons in sorted(failing_by_class.items())
        },
        advisory_notes=tuple(advisory_notes),
    )


def _safe_provenance_counts(records: Sequence[EdgeGoldRecord]) -> dict[str, int]:
    counts = {provenance: 0 for provenance in ("seed", "hand_labeled", "generated")}
    for record in records:
        counts[record.provenance] = counts.get(record.provenance, 0) + 1
    return counts


def _hand_labeled_counts_by_label(records: Sequence[EdgeGoldRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        if record.provenance == "hand_labeled":
            counts[record.label] = counts.get(record.label, 0) + 1
    return counts


def _is_seed_only(provenance_counts: dict[str, int]) -> bool:
    return (
        provenance_counts.get("seed", 0) > 0
        and provenance_counts.get("hand_labeled", 0) == 0
    )


def _collect_metric_failures(
    metrics_by_label: dict[str, EdgeClassMetrics],
    policy: RolloutPolicy,
    failing_by_class: dict[str, list[GateReason]],
) -> None:
    for label, metrics in metrics_by_label.items():
        if metrics.precision < policy.min_precision:
            _add_class_failure(failing_by_class, label, GateReason.BELOW_PRECISION)
        if metrics.recall < policy.min_recall:
            _add_class_failure(failing_by_class, label, GateReason.BELOW_RECALL)
        if metrics.false_positive_rate > policy.max_false_positive_rate:
            _add_class_failure(failing_by_class, label, GateReason.ABOVE_FALSE_POSITIVE)
        if metrics.false_negative_rate > policy.max_false_negative_rate:
            _add_class_failure(failing_by_class, label, GateReason.ABOVE_FALSE_NEGATIVE)
        if metrics.abstain_band_size > policy.max_abstain_band_size:
            _add_class_failure(failing_by_class, label, GateReason.ABSTAIN_BAND_TOO_WIDE)


def _add_class_failure(
    failing_by_class: dict[str, list[GateReason]],
    label: str,
    reason: GateReason,
) -> None:
    failing_by_class.setdefault(label, []).append(reason)


def _dedupe_reasons(reasons: Sequence[GateReason]) -> list[GateReason]:
    seen: set[GateReason] = set()
    deduped: list[GateReason] = []
    for reason in reasons:
        if reason not in seen:
            deduped.append(reason)
            seen.add(reason)
    return deduped


__all__ = [
    "DEFAULT_POLICY",
    "GateReason",
    "RolloutGateResult",
    "RolloutPolicy",
    "RolloutStatus",
    "evaluate_rollout_gates",
]
