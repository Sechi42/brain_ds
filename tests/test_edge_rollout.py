"""Tests for the edge judge rollout gate helper.

The rollout gate is a pure, read-only advisor that turns a calibration report
and its source gold records into a ``rollout_ready`` vs ``advisory_only``
verdict with a structured set of reasons. It must never mutate the graph, the
calibration report, or the gold records.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Iterable

from brain_ds.ontology.relationship_types import RelationshipType
from brain_ds.verify.edge_calibration import (
    EdgeCalibrationReport,
    EdgeClassMetrics,
    EdgeGoldRecord,
    calibrate_edges,
    load_gold_set,
)
from brain_ds.verify.edge_rollout import (
    DEFAULT_POLICY,
    GateReason,
    RolloutGateResult,
    RolloutPolicy,
    evaluate_rollout_gates,
)

GOLD_DIR = Path(__file__).resolve().parent / "gold"
GOLD_SET_PATH = GOLD_DIR / "edge_gold_set.jsonl"
ROLLOUT_DOC_PATH = (
    Path(__file__).resolve().parent.parent / "docs" / "edge-judge-rollout.md"
)


def _record(
    edge_id: str,
    *,
    label: str = "owns",
    weight: float = 0.5,
    verdict: str = "abstain",
    provenance: str = "hand_labeled",
) -> EdgeGoldRecord:
    return EdgeGoldRecord(
        edge_id=edge_id,
        graph_id="unit",
        label=label,
        source_type="Department",
        target_type="Solution",
        weight=weight,
        evidence_ids=(f"e-{edge_id}",),
        gold_verdict=verdict,  # type: ignore[arg-type]
        gold_rationale=f"{edge_id} rationale",
        provenance=provenance,  # type: ignore[arg-type]
    )


def _metrics(
    label: str,
    *,
    examples: int = 12,
    precision: float = 0.95,
    recall: float = 0.9,
    false_positive_rate: float = 0.05,
    false_negative_rate: float = 0.1,
    abstain_band_size: float = 0.2,
) -> EdgeClassMetrics:
    confusion = {
        verdict: {predicted: 0 for predicted in ("valid", "invalid", "abstain")}
        for verdict in ("valid", "invalid", "abstain")
    }
    confusion["valid"]["valid"] = max(examples - 2, 0)
    confusion["abstain"]["abstain"] = 1
    confusion["invalid"]["invalid"] = 1
    return EdgeClassMetrics(
        label=label,
        examples=examples,
        accept_threshold=0.7,
        reject_threshold=0.5,
        precision=precision,
        recall=recall,
        false_positive_rate=false_positive_rate,
        false_negative_rate=false_negative_rate,
        abstain_band_size=abstain_band_size,
        confusion_matrix=confusion,
        abstain_actual_count=1,
        abstain_predicted_count=1,
        abstain_recall=1.0,
        abstain_coverage=0.1,
    )


def _perfect_report(
    records: Iterable[EdgeGoldRecord],
    *,
    per_class_metrics: dict[str, EdgeClassMetrics] | None = None,
) -> EdgeCalibrationReport:
    records_list = list(records)
    classes: dict[str, EdgeClassMetrics] = {}
    if per_class_metrics is not None:
        classes = dict(per_class_metrics)
    else:
        for relationship in RelationshipType:
            classes[relationship.value] = _metrics(relationship.value, examples=12)
    provenance_counts = {provenance: 0 for provenance in ("seed", "hand_labeled", "generated")}
    for record in records_list:
        provenance_counts[record.provenance] += 1
    return EdgeCalibrationReport(
        run_id="unit-ready",
        generated_at="2026-06-23T00:00:00+00:00",
        classes=classes,
        provenance_counts=provenance_counts,
    )


def _hand_labeled_records(per_type: int = 12) -> list[EdgeGoldRecord]:
    records: list[EdgeGoldRecord] = []
    for relationship in RelationshipType:
        for index in range(per_type):
            label = relationship.value
            weight = 0.2 if index < 2 else 0.8
            verdict = "invalid" if index < 2 else "valid"
            records.append(
                _record(
                    f"{label}-hl-{index}",
                    label=label,
                    weight=weight,
                    verdict=verdict,
                    provenance="hand_labeled",
                )
            )
    return records


class DefaultPolicyTests(unittest.TestCase):
    def test_default_policy_matches_spec_thresholds(self) -> None:
        self.assertEqual(DEFAULT_POLICY.min_examples_per_relationship_type, 10)
        self.assertEqual(DEFAULT_POLICY.min_hand_labeled_per_relationship_type, 10)
        self.assertEqual(DEFAULT_POLICY.min_precision, 0.85)
        self.assertEqual(DEFAULT_POLICY.min_recall, 0.70)
        self.assertEqual(DEFAULT_POLICY.max_false_positive_rate, 0.15)
        self.assertEqual(DEFAULT_POLICY.max_false_negative_rate, 0.30)
        self.assertEqual(DEFAULT_POLICY.max_abstain_band_size, 0.50)
        self.assertEqual(DEFAULT_POLICY.min_consecutive_runs, 2)
        self.assertEqual(DEFAULT_POLICY.min_human_reviewed_abstain, 20)
        self.assertGreater(DEFAULT_POLICY.min_hand_labeled_total, 0)


class EvaluateRolloutGatesTests(unittest.TestCase):
    def test_rollout_ready_when_all_gates_pass(self) -> None:
        records = _hand_labeled_records(per_type=12)
        report = _perfect_report(records)

        result = evaluate_rollout_gates(
            report,
            records,
            consecutive_passing_runs=2,
            human_reviewed_abstain_count=20,
        )

        self.assertEqual(result.status, "rollout_ready")
        self.assertEqual(result.failing_reasons, ())
        self.assertIn(
            GateReason.LARGE_GRAPH_SAFETY_PENDING,
            result.advisory_notes,
        )

    def test_seed_only_baseline_returns_advisory_only_with_seed_only_reason(self) -> None:
        records = load_gold_set(GOLD_SET_PATH, min_examples_per_type=5)
        report = calibrate_edges(records, run_id="seed-only")

        result = evaluate_rollout_gates(
            report,
            records,
            consecutive_passing_runs=2,
            human_reviewed_abstain_count=20,
        )

        self.assertEqual(result.status, "advisory_only")
        self.assertIn(GateReason.SEED_ONLY_BASELINE, result.failing_reasons)
        self.assertIn(GateReason.INSUFFICIENT_EXAMPLES_PER_TYPE, result.failing_reasons)
        self.assertIn(GateReason.INSUFFICIENT_HAND_LABELED, result.failing_reasons)
        self.assertIn(
            GateReason.LARGE_GRAPH_SAFETY_PENDING,
            result.advisory_notes,
        )

    def test_missing_relationship_type_metrics_returns_advisory_only_by_label(self) -> None:
        records = _hand_labeled_records(per_type=12)
        classes = {
            relationship.value: _metrics(relationship.value, examples=12)
            for relationship in RelationshipType
            if relationship is not RelationshipType.MEASURED_BY
        }
        report = _perfect_report(records, per_class_metrics=classes)

        result = evaluate_rollout_gates(
            report,
            records,
            consecutive_passing_runs=2,
            human_reviewed_abstain_count=20,
        )

        self.assertEqual(result.status, "advisory_only")
        self.assertIn(GateReason.MISSING_CLASS_METRICS, result.failing_reasons)
        self.assertEqual(
            result.failing_by_class[RelationshipType.MEASURED_BY.value],
            (GateReason.MISSING_CLASS_METRICS,),
        )

    def test_empty_class_metrics_reports_every_missing_relationship_type(self) -> None:
        records = _hand_labeled_records(per_type=12)
        report = _perfect_report(records, per_class_metrics={})

        result = evaluate_rollout_gates(
            report,
            records,
            consecutive_passing_runs=2,
            human_reviewed_abstain_count=20,
        )

        self.assertEqual(result.status, "advisory_only")
        self.assertEqual(
            set(result.failing_by_class),
            {relationship.value for relationship in RelationshipType},
        )
        for relationship in RelationshipType:
            self.assertEqual(
                result.failing_by_class[relationship.value],
                (GateReason.MISSING_CLASS_METRICS,),
            )

    def test_single_label_report_reports_remaining_relationship_types_missing(self) -> None:
        records = _hand_labeled_records(per_type=12)
        report = _perfect_report(
            records,
            per_class_metrics={RelationshipType.OWNS.value: _metrics("owns", examples=12)},
        )

        result = evaluate_rollout_gates(
            report,
            records,
            consecutive_passing_runs=2,
            human_reviewed_abstain_count=20,
        )

        self.assertEqual(result.status, "advisory_only")
        self.assertNotIn(RelationshipType.OWNS.value, result.failing_by_class)
        self.assertIn(RelationshipType.USES.value, result.failing_by_class)
        self.assertEqual(
            result.failing_by_class[RelationshipType.USES.value],
            (GateReason.MISSING_CLASS_METRICS,),
        )

    def test_generated_records_present_returns_advisory_only(self) -> None:
        records = [
            _record("seed-1", provenance="hand_labeled"),
            _record("generated-1", provenance="generated"),
        ]
        report = _perfect_report(records, per_class_metrics={"owns": _metrics("owns", examples=12)})

        result = evaluate_rollout_gates(
            report,
            records,
            consecutive_passing_runs=2,
            human_reviewed_abstain_count=20,
        )

        self.assertEqual(result.status, "advisory_only")
        self.assertIn(GateReason.GENERATED_RECORDS_PRESENT, result.failing_reasons)

    def test_insufficient_hand_labeled_returns_advisory_only(self) -> None:
        records = [
            _record(f"seed-{index}", provenance="seed", label="owns")
            for index in range(12)
        ] + [
            _record(f"hl-{index}", provenance="hand_labeled", label="owns")
            for index in range(2)
        ]
        report = _perfect_report(records, per_class_metrics={"owns": _metrics("owns", examples=14)})

        result = evaluate_rollout_gates(
            report,
            records,
            consecutive_passing_runs=2,
            human_reviewed_abstain_count=20,
        )

        self.assertEqual(result.status, "advisory_only")
        self.assertIn(GateReason.INSUFFICIENT_HAND_LABELED, result.failing_reasons)
        self.assertNotIn(GateReason.SEED_ONLY_BASELINE, result.failing_reasons)

    def test_per_class_hand_labeled_floor_identifies_underrepresented_label(self) -> None:
        records = [
            _record(f"owns-hl-{index}", provenance="hand_labeled", label="owns")
            for index in range(10)
        ] + [
            _record(f"uses-seed-{index}", provenance="seed", label="uses")
            for index in range(12)
        ]
        report = _perfect_report(
            records,
            per_class_metrics={
                "owns": _metrics("owns", examples=10),
                "uses": _metrics("uses", examples=12),
            },
        )
        policy = RolloutPolicy(
            min_examples_per_relationship_type=10,
            min_hand_labeled_per_relationship_type=10,
            min_hand_labeled_total=10,
            min_consecutive_runs=2,
            min_human_reviewed_abstain=20,
        )

        result = evaluate_rollout_gates(
            report,
            records,
            policy=policy,
            consecutive_passing_runs=2,
            human_reviewed_abstain_count=20,
        )

        self.assertEqual(result.status, "advisory_only")
        self.assertIn(GateReason.INSUFFICIENT_HAND_LABELED, result.failing_reasons)
        self.assertEqual(
            result.failing_by_class["uses"],
            (GateReason.INSUFFICIENT_HAND_LABELED,),
        )

    def test_multiple_labels_failing_same_reason_are_recoverable_by_class(self) -> None:
        records = _hand_labeled_records(per_type=12)
        report = _perfect_report(records)
        report.classes["owns"] = _metrics("owns", examples=12, precision=0.50)
        report.classes["uses"] = _metrics("uses", examples=12, precision=0.40)

        result = evaluate_rollout_gates(
            report,
            records,
            consecutive_passing_runs=2,
            human_reviewed_abstain_count=20,
        )

        self.assertEqual(result.failing_reasons.count(GateReason.BELOW_PRECISION), 1)
        self.assertIn(GateReason.BELOW_PRECISION, result.failing_by_class["owns"])
        self.assertIn(GateReason.BELOW_PRECISION, result.failing_by_class["uses"])

    def test_insufficient_examples_per_relationship_type_returns_advisory_only(self) -> None:
        records = _hand_labeled_records(per_type=12)
        report = _perfect_report(records)
        for label in report.classes:
            if label == "owns":
                continue
            report.classes[label] = _metrics(label, examples=4)

        result = evaluate_rollout_gates(
            report,
            records,
            consecutive_passing_runs=2,
            human_reviewed_abstain_count=20,
        )

        self.assertEqual(result.status, "advisory_only")
        self.assertIn(
            GateReason.INSUFFICIENT_EXAMPLES_PER_TYPE, result.failing_reasons
        )

    def test_below_precision_threshold_returns_advisory_only(self) -> None:
        records = _hand_labeled_records(per_type=12)
        report = _perfect_report(records)
        report.classes["owns"] = _metrics("owns", examples=12, precision=0.50)

        result = evaluate_rollout_gates(
            report,
            records,
            consecutive_passing_runs=2,
            human_reviewed_abstain_count=20,
        )

        self.assertEqual(result.status, "advisory_only")
        self.assertIn(GateReason.BELOW_PRECISION, result.failing_reasons)

    def test_below_recall_threshold_returns_advisory_only(self) -> None:
        records = _hand_labeled_records(per_type=12)
        report = _perfect_report(records)
        report.classes["owns"] = _metrics("owns", examples=12, recall=0.40)

        result = evaluate_rollout_gates(
            report,
            records,
            consecutive_passing_runs=2,
            human_reviewed_abstain_count=20,
        )

        self.assertEqual(result.status, "advisory_only")
        self.assertIn(GateReason.BELOW_RECALL, result.failing_reasons)

    def test_above_false_positive_threshold_returns_advisory_only(self) -> None:
        records = _hand_labeled_records(per_type=12)
        report = _perfect_report(records)
        report.classes["owns"] = _metrics("owns", examples=12, false_positive_rate=0.50)

        result = evaluate_rollout_gates(
            report,
            records,
            consecutive_passing_runs=2,
            human_reviewed_abstain_count=20,
        )

        self.assertEqual(result.status, "advisory_only")
        self.assertIn(GateReason.ABOVE_FALSE_POSITIVE, result.failing_reasons)

    def test_above_false_negative_threshold_returns_advisory_only(self) -> None:
        records = _hand_labeled_records(per_type=12)
        report = _perfect_report(records)
        report.classes["owns"] = _metrics("owns", examples=12, false_negative_rate=0.60)

        result = evaluate_rollout_gates(
            report,
            records,
            consecutive_passing_runs=2,
            human_reviewed_abstain_count=20,
        )

        self.assertEqual(result.status, "advisory_only")
        self.assertIn(GateReason.ABOVE_FALSE_NEGATIVE, result.failing_reasons)

    def test_abstain_band_too_wide_returns_advisory_only(self) -> None:
        records = _hand_labeled_records(per_type=12)
        report = _perfect_report(records)
        report.classes["owns"] = _metrics("owns", examples=12, abstain_band_size=0.9)

        result = evaluate_rollout_gates(
            report,
            records,
            consecutive_passing_runs=2,
            human_reviewed_abstain_count=20,
        )

        self.assertEqual(result.status, "advisory_only")
        self.assertIn(GateReason.ABSTAIN_BAND_TOO_WIDE, result.failing_reasons)

    def test_consecutive_runs_below_minimum_returns_advisory_only(self) -> None:
        records = _hand_labeled_records(per_type=12)
        report = _perfect_report(records)

        result = evaluate_rollout_gates(
            report,
            records,
            consecutive_passing_runs=1,
            human_reviewed_abstain_count=20,
        )

        self.assertEqual(result.status, "advisory_only")
        self.assertIn(
            GateReason.CONSECUTIVE_RUNS_INSUFFICIENT, result.failing_reasons
        )

    def test_human_review_below_minimum_returns_advisory_only(self) -> None:
        records = _hand_labeled_records(per_type=12)
        report = _perfect_report(records)

        result = evaluate_rollout_gates(
            report,
            records,
            consecutive_passing_runs=2,
            human_reviewed_abstain_count=5,
        )

        self.assertEqual(result.status, "advisory_only")
        self.assertIn(
            GateReason.HUMAN_ABSTAIN_REVIEW_INSUFFICIENT, result.failing_reasons
        )

    def test_multiple_failing_reasons_are_reported_together(self) -> None:
        records = [
            _record(f"seed-{index}", provenance="seed", label="owns")
            for index in range(12)
        ]
        report = _perfect_report(records, per_class_metrics={"owns": _metrics("owns", examples=12)})

        result = evaluate_rollout_gates(
            report,
            records,
            consecutive_passing_runs=1,
            human_reviewed_abstain_count=0,
        )

        self.assertEqual(result.status, "advisory_only")
        self.assertIn(GateReason.SEED_ONLY_BASELINE, result.failing_reasons)
        self.assertIn(GateReason.INSUFFICIENT_HAND_LABELED, result.failing_reasons)
        self.assertIn(
            GateReason.CONSECUTIVE_RUNS_INSUFFICIENT, result.failing_reasons
        )
        self.assertIn(
            GateReason.HUMAN_ABSTAIN_REVIEW_INSUFFICIENT, result.failing_reasons
        )

    def test_large_graph_safety_surfaced_as_advisory_note_not_failing(self) -> None:
        records = _hand_labeled_records(per_type=12)
        report = _perfect_report(records)

        result = evaluate_rollout_gates(
            report,
            records,
            consecutive_passing_runs=2,
            human_reviewed_abstain_count=20,
        )

        self.assertEqual(result.status, "rollout_ready")
        self.assertIn(
            GateReason.LARGE_GRAPH_SAFETY_PENDING,
            result.advisory_notes,
        )
        self.assertNotIn(
            GateReason.LARGE_GRAPH_SAFETY_PENDING,
            result.failing_reasons,
        )

    def test_evaluate_rollout_gates_does_not_mutate_report_or_records(self) -> None:
        records = _hand_labeled_records(per_type=12)
        report = _perfect_report(records)
        snapshot_report_classes = {
            label: dict(metrics.confusion_matrix)
            for label, metrics in report.classes.items()
        }
        snapshot_records = [record.edge_id for record in records]

        evaluate_rollout_gates(
            report,
            records,
            consecutive_passing_runs=2,
            human_reviewed_abstain_count=20,
        )

        for label, metrics in report.classes.items():
            self.assertEqual(metrics.confusion_matrix, snapshot_report_classes[label])
        self.assertEqual([record.edge_id for record in records], snapshot_records)

    def test_custom_policy_overrides_default_thresholds(self) -> None:
        records = _hand_labeled_records(per_type=12)
        report = _perfect_report(records)
        relaxed = RolloutPolicy(
            min_examples_per_relationship_type=5,
            min_hand_labeled_per_relationship_type=5,
            min_precision=0.5,
            min_recall=0.5,
            max_false_positive_rate=0.5,
            max_false_negative_rate=0.5,
            min_consecutive_runs=1,
            min_human_reviewed_abstain=0,
            max_abstain_band_size=1.0,
            min_hand_labeled_total=1,
        )

        result = evaluate_rollout_gates(
            report,
            records,
            policy=relaxed,
            consecutive_passing_runs=1,
            human_reviewed_abstain_count=0,
        )

        self.assertEqual(result.status, "rollout_ready")
        self.assertEqual(result.failing_reasons, ())

    def test_real_calibration_report_from_hand_labeled_records_keeps_rollout_advisory(self) -> None:
        records = _hand_labeled_records(per_type=12)
        report = calibrate_edges(records, run_id="hand-labeled-real-report")

        result = evaluate_rollout_gates(
            report,
            records,
            consecutive_passing_runs=2,
            human_reviewed_abstain_count=20,
        )

        self.assertEqual(result.status, "advisory_only")
        self.assertIn(GateReason.ABSTAIN_BAND_TOO_WIDE, result.failing_reasons)
        self.assertEqual(
            set(result.failing_by_class),
            {relationship.value for relationship in RelationshipType},
        )
        for relationship in RelationshipType:
            self.assertEqual(
                result.failing_by_class[relationship.value],
                (GateReason.ABSTAIN_BAND_TOO_WIDE,),
            )


class RolloutDocTests(unittest.TestCase):
    def test_rollout_doc_exists_and_covers_gates(self) -> None:
        self.assertTrue(
            ROLLOUT_DOC_PATH.is_file(),
            f"spec section E gate 5 requires {ROLLOUT_DOC_PATH}",
        )
        text = ROLLOUT_DOC_PATH.read_text(encoding="utf-8")
        for reason in GateReason:
            if reason is GateReason.LARGE_GRAPH_SAFETY_PENDING:
                continue
            self.assertIn(
                reason.name,
                text,
                f"rollout doc must document gate reason {reason.name}",
            )


class RolloutGateResultShapeTests(unittest.TestCase):
    def test_result_is_immutable_dataclass(self) -> None:
        result = RolloutGateResult(
            status="advisory_only",
            failing_reasons=(GateReason.SEED_ONLY_BASELINE,),
            failing_by_class={},
            advisory_notes=(GateReason.LARGE_GRAPH_SAFETY_PENDING,),
        )
        with self.assertRaises(Exception):
            result.status = "rollout_ready"  # type: ignore[misc]

    def test_evaluate_rollout_gates_is_pure_and_does_not_import_mcp(self) -> None:
        import brain_ds.verify.edge_rollout as module

        self.assertFalse(hasattr(module, "add_edge"))
        self.assertFalse(hasattr(module, "delete_edge"))
        self.assertFalse(hasattr(module, "update_node"))


class AdvisoryContractTests(unittest.TestCase):
    """Task 5.1 RED → GREEN: pre-calibration findings must never block archive/mutate.

    The edge judge is advisory-only by spec (section E).  These tests bind that
    contract explicitly: a ``RolloutGateResult`` with ``status="advisory_only"``
    MUST NOT carry any ``CRITICAL`` severity, and calling code MUST be able to
    proceed with archive/mutate operations regardless of gate status.
    """

    def test_advisory_only_result_never_has_critical_severity(self) -> None:
        """Pre-calibration ``advisory_only`` status carries no CRITICAL severity code.

        The valid severities for edge findings are SUGGESTION and WARNING.
        The gate result itself only surfaces structured GateReasons — none of
        which are CRITICAL.  This test makes the contract explicit so that any
        future change that adds a CRITICAL-equivalent enum value or field fails
        loudly here.
        """
        records = load_gold_set(GOLD_SET_PATH, min_examples_per_type=5)
        report = calibrate_edges(records, run_id="advisory-contract")

        result = evaluate_rollout_gates(
            report,
            records,
            consecutive_passing_runs=1,
            human_reviewed_abstain_count=0,
        )

        self.assertEqual(result.status, "advisory_only")
        # No field on RolloutGateResult is named or typed "CRITICAL".
        # Verify the result fields only carry GateReason enums (advisory severity).
        for reason in result.failing_reasons:
            self.assertIsInstance(reason, GateReason)
        for reason in result.advisory_notes:
            self.assertIsInstance(reason, GateReason)
        # No GateReason value contains the word "critical" (case-insensitive).
        all_reason_values = [r.value for r in result.failing_reasons] + [
            r.value for r in result.advisory_notes
        ]
        for value in all_reason_values:
            self.assertNotIn("critical", value.lower(), f"Found critical-severity reason: {value}")

    def test_pre_calibration_findings_do_not_block_operations(self) -> None:
        """``advisory_only`` means callers can proceed; nothing is raised or blocked.

        This test verifies the advisory-first rollout contract: archive, update_node,
        add_edge, etc. are not prevented by a failing gate result.  The gate returns
        a verdict — the caller decides what to do.  The helper itself MUST NOT raise
        an exception, call any MCP tool, or block any operation.
        """
        records = load_gold_set(GOLD_SET_PATH, min_examples_per_type=5)
        report = calibrate_edges(records, run_id="no-block-contract")

        # This should complete without raising even under worst-case advisory state.
        result = evaluate_rollout_gates(
            report,
            records,
            consecutive_passing_runs=0,
            human_reviewed_abstain_count=0,
        )

        # Gate says advisory_only — the function returned normally, nothing blocked.
        self.assertEqual(result.status, "advisory_only")
        # The caller can freely read the result and proceed with any operation.
        # (No archive/mutate call needed here — the point is no exception was raised.)
        self.assertIsInstance(result.failing_reasons, tuple)
        self.assertIsInstance(result.advisory_notes, tuple)

    def test_gate_result_carries_no_mcp_mutation_side_effect(self) -> None:
        """The rollout gate helper imports NO MCP mutation tools.

        Confirmed by inspecting the module namespace: add_edge, delete_edge,
        update_node, delete_node must be absent from edge_rollout.
        """
        import brain_ds.verify.edge_rollout as module

        mutation_names = ["add_edge", "delete_edge", "update_node", "delete_node", "archive"]
        for name in mutation_names:
            self.assertFalse(
                hasattr(module, name),
                f"edge_rollout must not import MCP mutation tool '{name}'",
            )

    def test_warning_severity_findings_are_the_maximum_allowed(self) -> None:
        """Edge findings severity ceiling is WARNING, not CRITICAL.

        Deterministic flags in a snapshot use SUGGESTION.  Compatibility matrix
        issues use WARNING.  No finding from the edge judge pipeline should ever
        be CRITICAL until all rollout gates pass.  This test pins the allowed
        set for the rollout gate phase.
        """
        from brain_ds.verify.edge_snapshot import build_edge_snapshot
        from brain_ds.store.models import EdgeRow

        def _edge(eid: str, label: str, weight: float | None, evidence_ids: list[str] | None = None) -> EdgeRow:
            return EdgeRow(
                graph_id="g",
                edge_id=eid,
                source="s",
                target="t",
                label=label,
                weight=weight,
                reasons=[],
                evidence_ids=evidence_ids,
                created_at="now",
            )

        snapshot = build_edge_snapshot(
            graph_id="g",
            edges=[
                _edge("no-ev", "rel", 0.5, []),
                _edge("bad-w", "rel", 1.5, ["e1"]),
            ],
            mode="sample",
            limit=10,
        )
        allowed_severities = {"SUGGESTION", "WARNING"}
        for edge in snapshot["edges"]:
            for flag in edge["deterministic_flags"]:
                self.assertIn(
                    flag["severity"],
                    allowed_severities,
                    f"Severity {flag['severity']!r} on edge {edge['edge_id']!r} "
                    f"exceeds advisory ceiling",
                )


if __name__ == "__main__":
    unittest.main()
