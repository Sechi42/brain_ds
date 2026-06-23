from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from brain_ds.ontology.relationship_types import RelationshipType
from brain_ds.verify.edge_calibration import (
    EdgeGoldRecord,
    calibrate_edges,
    load_gold_set,
    write_calibration_artifacts,
)


GOLD_DIR = Path(__file__).resolve().parent / "gold"
GOLD_SET_PATH = GOLD_DIR / "edge_gold_set.jsonl"


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


def _json_line(
    edge_id: str,
    *,
    label: str = "owns",
    weight: float = 0.5,
    verdict: str = "abstain",
    evidence_ids: object = None,
    provenance: str = "hand_labeled",
) -> str:
    payload = {
        "edge_id": edge_id,
        "graph_id": "unit",
        "label": label,
        "source_type": "Department",
        "target_type": "Solution",
        "weight": weight,
        "evidence_ids": [f"e-{edge_id}"] if evidence_ids is None else evidence_ids,
        "gold_verdict": verdict,
        "gold_rationale": f"{edge_id} rationale",
        "provenance": provenance,
    }
    return json.dumps(payload)


class EdgeCalibrationTests(unittest.TestCase):
    def test_gold_set_is_loadable_and_covers_every_relationship_type(self) -> None:
        records = load_gold_set(GOLD_SET_PATH, min_examples_per_type=5)

        labels = {record.label for record in records}
        expected = {relationship.value for relationship in RelationshipType}
        self.assertEqual(labels, expected)
        for relationship in RelationshipType:
            examples = [record for record in records if record.label == relationship.value]
            self.assertGreaterEqual(len(examples), 5, relationship.value)
            self.assertTrue(
                all(record.provenance in {"seed", "hand_labeled", "generated"} for record in examples)
            )

    def test_gold_set_loader_fails_loudly_when_relationship_type_is_underrepresented(self) -> None:
        with self.assertRaisesRegex(ValueError, "underrepresented"):
            load_gold_set(GOLD_SET_PATH, min_examples_per_type=6)

    def test_gold_set_loader_enforces_three_example_floor_even_when_lower_minimum_requested(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = Path(temp_dir) / "two-per-label.jsonl"
            lines = []
            for relationship in RelationshipType:
                lines.append(
                    _json_line(
                        f"{relationship.value}-valid",
                        label=relationship.value,
                        weight=0.8,
                        verdict="valid",
                    )
                )
                lines.append(
                    _json_line(
                        f"{relationship.value}-invalid",
                        label=relationship.value,
                        weight=0.2,
                        verdict="invalid",
                    )
                )
            fixture.write_text("\n".join(lines) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "underrepresented"):
                load_gold_set(fixture, min_examples_per_type=1)

    def test_gold_set_loader_rejects_malformed_jsonl_with_path_and_line(self) -> None:
        malformed_cases = {
            "invalid-json": "{not json}",
            "missing-required-field": json.dumps(
                {
                    "edge_id": "missing-label",
                    "graph_id": "unit",
                    "source_type": "Department",
                    "target_type": "Solution",
                    "weight": 0.5,
                    "evidence_ids": ["e-missing-label"],
                    "gold_verdict": "valid",
                    "gold_rationale": "missing label",
                    "provenance": "hand_labeled",
                }
            ),
            "wrong-evidence-type": _json_line("bad-evidence", evidence_ids="not-a-list"),
            "invalid-verdict": _json_line("bad-verdict", verdict="maybe"),
            "invalid-provenance": _json_line("bad-provenance", provenance="crawler"),
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            for name, line in malformed_cases.items():
                fixture = Path(temp_dir) / f"{name}.jsonl"
                fixture.write_text(line + "\n", encoding="utf-8")

                with self.subTest(name=name):
                    with self.assertRaisesRegex(ValueError, rf"{re.escape(str(fixture))}:1"):
                        load_gold_set(fixture, min_examples_per_type=3)

    def test_gold_set_loader_reports_unknown_relationship_label_with_path_and_line(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = Path(temp_dir) / "unknown-label.jsonl"
            fixture.write_text(
                _json_line("bad-label", label="not-a-relationship", verdict="valid") + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                rf"{re.escape(str(fixture))}:1 .*RelationshipType.*not-a-relationship",
            ):
                load_gold_set(fixture, min_examples_per_type=3)

    def test_gold_set_loader_rejects_non_finite_and_out_of_range_weights_with_path_and_line(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cases = {"nan-weight": float("nan"), "high-weight": 1.1, "low-weight": -0.1}
            for edge_id, weight in cases.items():
                fixture = Path(temp_dir) / f"{edge_id}.jsonl"
                fixture.write_text(_json_line(edge_id, weight=weight, verdict="valid") + "\n", encoding="utf-8")

                with self.subTest(edge_id=edge_id):
                    with self.assertRaisesRegex(ValueError, rf"{re.escape(str(fixture))}:1 .*weight.*\[0,1\]"):
                        load_gold_set(fixture, min_examples_per_type=3)

    def test_generated_provenance_is_excluded_from_ground_truth_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = Path(temp_dir) / "generated.jsonl"
            fixture.write_text(_json_line("generated-edge", provenance="generated") + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, r"generated.*not ground truth"):
                load_gold_set(fixture, min_examples_per_type=3)

            with self.assertRaisesRegex(ValueError, "missing RelationshipType"):
                load_gold_set(fixture, min_examples_per_type=1, include_generated=True)

    def test_calibration_derives_per_class_thresholds_and_metrics(self) -> None:
        records = load_gold_set(GOLD_SET_PATH, min_examples_per_type=5)

        report = calibrate_edges(records)

        self.assertEqual(set(report.classes), {relationship.value for relationship in RelationshipType})
        self.assertIsNone(report.global_accept_threshold)
        self.assertIsNone(report.global_reject_threshold)
        for relationship in RelationshipType:
            metrics = report.classes[relationship.value]
            self.assertLess(metrics.reject_threshold, metrics.accept_threshold)
            self.assertGreaterEqual(metrics.precision, 0.85, relationship.value)
            self.assertGreaterEqual(metrics.recall, 0.70, relationship.value)
            self.assertLessEqual(metrics.false_positive_rate, 0.15, relationship.value)
            self.assertLessEqual(metrics.false_negative_rate, 0.30, relationship.value)
            self.assertGreater(metrics.abstain_band_size, 0.0, relationship.value)
            self.assertEqual(set(metrics.confusion_matrix), {"valid", "invalid", "abstain"})

    def test_calibration_reports_abstain_confusion_for_inside_and_outside_band_records(self) -> None:
        records = [
            _record("invalid-low", weight=0.2, verdict="invalid"),
            _record("invalid-high", weight=0.4, verdict="invalid"),
            _record("abstain-inside", weight=0.5, verdict="abstain"),
            _record("valid-low", weight=0.6, verdict="valid"),
            _record("valid-high", weight=0.9, verdict="valid"),
            _record("abstain-outside", weight=0.95, verdict="abstain"),
        ]

        report = calibrate_edges(records, run_id="abstain-metrics")
        metrics = report.classes["owns"]

        self.assertEqual(metrics.confusion_matrix["abstain"]["abstain"], 1)
        self.assertEqual(metrics.confusion_matrix["abstain"]["valid"], 1)
        self.assertEqual(metrics.abstain_actual_count, 2)
        self.assertEqual(metrics.abstain_predicted_count, 1)
        self.assertEqual(metrics.abstain_recall, 0.5)
        self.assertEqual(metrics.abstain_coverage, round(1 / 6, 4))

    def test_calibration_uses_midpoint_fallback_for_overlapping_valid_and_invalid_weights(self) -> None:
        records = [
            _record("invalid-low", weight=0.2, verdict="invalid"),
            _record("invalid-overlap", weight=0.7, verdict="invalid"),
            _record("abstain-middle", weight=0.65, verdict="abstain"),
            _record("valid-overlap", weight=0.6, verdict="valid"),
            _record("valid-high", weight=0.9, verdict="valid"),
        ]

        report = calibrate_edges(records, run_id="overlap")
        metrics = report.classes["owns"]

        self.assertEqual(metrics.reject_threshold, 0.64)
        self.assertEqual(metrics.accept_threshold, 0.66)
        self.assertEqual(metrics.confusion_matrix["abstain"]["abstain"], 1)

    def test_calibration_metrics_are_persisted_with_run_id_and_log_entry(self) -> None:
        records = load_gold_set(GOLD_SET_PATH, min_examples_per_type=5)
        report = calibrate_edges(records, run_id="unit-test-run")
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "metrics"
            log_path = Path(temp_dir) / "calibration_log.md"

            written_path = write_calibration_artifacts(
                report,
                metrics_dir=output_dir,
                log_path=log_path,
            )

            metrics_path = output_dir / "unit-test-run.json"
            self.assertEqual(written_path, metrics_path)
            payload = json.loads(metrics_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["run_id"], "unit-test-run")
            self.assertEqual(set(payload["classes"]), {relationship.value for relationship in RelationshipType})
            log_text = log_path.read_text(encoding="utf-8")
            self.assertIn("unit-test-run", log_text)
            self.assertIn("per-class thresholds", log_text)

    def test_default_artifact_write_paths_are_explicitly_documented_as_tracked_baselines(self) -> None:
        docstring = write_calibration_artifacts.__doc__ or ""
        readme_text = (GOLD_DIR / "README.md").read_text(encoding="utf-8")

        self.assertIn("tracked", docstring)
        self.assertIn("tests/gold/metrics", docstring)
        self.assertIn("tests/gold/calibration_log.md", docstring)
        self.assertIn("write_calibration_artifacts", readme_text)
        self.assertIn("tracked seed baseline", readme_text)

    def test_committed_seed_log_generated_timestamp_matches_seed_metrics(self) -> None:
        seed_payload = json.loads((GOLD_DIR / "metrics" / "seed-20260623.json").read_text(encoding="utf-8"))
        log_text = (GOLD_DIR / "calibration_log.md").read_text(encoding="utf-8")
        match = re.search(r"## seed-20260623\n- Generated: (?P<generated_at>[^\n]+)", log_text)

        self.assertIsNotNone(match)
        self.assertEqual(match.group("generated_at"), seed_payload["generated_at"])

    def test_committed_seed_metrics_match_deterministic_rerun_except_timestamp(self) -> None:
        records = load_gold_set(GOLD_SET_PATH, min_examples_per_type=5)
        report = calibrate_edges(records, run_id="seed-20260623")
        with tempfile.TemporaryDirectory() as temp_dir:
            written_path = write_calibration_artifacts(
                report,
                metrics_dir=Path(temp_dir) / "metrics",
                log_path=Path(temp_dir) / "calibration_log.md",
            )
            rerun_payload = json.loads(written_path.read_text(encoding="utf-8"))
            seed_payload = json.loads((GOLD_DIR / "metrics" / "seed-20260623.json").read_text(encoding="utf-8"))

        rerun_payload.pop("generated_at")
        seed_payload.pop("generated_at")
        self.assertEqual(rerun_payload, seed_payload)

    def test_generated_metrics_written_to_temp_paths_do_not_touch_committed_gold_artifacts(self) -> None:
        records = load_gold_set(GOLD_SET_PATH, min_examples_per_type=5)
        report = calibrate_edges(records, run_id="hermetic-run")
        committed_log = GOLD_DIR / "calibration_log.md"
        committed_metrics = GOLD_DIR / "metrics" / "seed-20260623.json"
        original_log = committed_log.read_text(encoding="utf-8")
        original_seed_metrics = committed_metrics.read_text(encoding="utf-8")

        with tempfile.TemporaryDirectory() as temp_dir:
            write_calibration_artifacts(
                report,
                metrics_dir=Path(temp_dir) / "metrics",
                log_path=Path(temp_dir) / "calibration_log.md",
            )

        self.assertEqual(committed_log.read_text(encoding="utf-8"), original_log)
        self.assertEqual(committed_metrics.read_text(encoding="utf-8"), original_seed_metrics)


if __name__ == "__main__":
    unittest.main()
