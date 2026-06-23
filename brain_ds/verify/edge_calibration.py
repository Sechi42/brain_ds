"""Calibration helpers for statistical edge uncertainty, not ontology compatibility.

The calibration verdicts (`valid`, `invalid`, `abstain`) are gold-label outcomes for
weight-threshold calibration. They are intentionally separate from the ontology
compatibility classifier's `suspect` verdict, which means "structurally unusual but
allowed for review." A `suspect` edge is not automatically an `abstain` edge; the
two dimensions are reported independently until Phase 5 advisory rollout bridges them.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable, Literal

from brain_ds.ontology.relationship_types import RelationshipType

GoldVerdict = Literal["valid", "invalid", "abstain"]
Provenance = Literal["seed", "hand_labeled", "generated"]
CONFUSION_LABELS: tuple[GoldVerdict, ...] = ("valid", "invalid", "abstain")


@dataclass(frozen=True)
class EdgeGoldRecord:
    edge_id: str
    graph_id: str
    label: str
    source_type: str
    target_type: str
    weight: float
    evidence_ids: tuple[str, ...]
    gold_verdict: GoldVerdict
    gold_rationale: str
    provenance: Provenance


@dataclass(frozen=True)
class EdgeClassMetrics:
    label: str
    examples: int
    accept_threshold: float
    reject_threshold: float
    precision: float
    recall: float
    false_positive_rate: float
    false_negative_rate: float
    abstain_band_size: float
    confusion_matrix: dict[str, dict[str, int]]
    abstain_actual_count: int
    abstain_predicted_count: int
    abstain_recall: float
    abstain_coverage: float


@dataclass(frozen=True)
class EdgeCalibrationReport:
    run_id: str
    generated_at: str
    classes: dict[str, EdgeClassMetrics]
    provenance_counts: dict[str, int]
    global_accept_threshold: None = None
    global_reject_threshold: None = None


def load_gold_set(
    path: str | Path,
    *,
    min_examples_per_type: int = 3,
    include_generated: bool = False,
) -> list[EdgeGoldRecord]:
    records = [
        _parse_gold_line(line, path, line_number, include_generated=include_generated)
        for line_number, line in _iter_jsonl(path)
    ]
    expected_labels = {relationship.value for relationship in RelationshipType}
    labels = {record.label for record in records}
    missing = sorted(expected_labels - labels)
    if missing:
        raise ValueError(f"gold set missing RelationshipType examples: {', '.join(missing)}")

    required_examples = max(min_examples_per_type, 3)
    underrepresented = sorted(
        label
        for label in expected_labels
        if sum(1 for record in records if record.label == label) < required_examples
    )
    if underrepresented:
        raise ValueError(
            "gold set underrepresented RelationshipType examples: "
            + ", ".join(underrepresented)
        )
    return records


def calibrate_edges(
    records: Iterable[EdgeGoldRecord], *, run_id: str | None = None
) -> EdgeCalibrationReport:
    grouped: dict[str, list[EdgeGoldRecord]] = {}
    provenance_counts = {provenance: 0 for provenance in ("seed", "hand_labeled", "generated")}
    for record in records:
        grouped.setdefault(record.label, []).append(record)
        provenance_counts[record.provenance] += 1

    classes = {
        label: _calibrate_class(label, sorted(class_records, key=lambda record: record.weight))
        for label, class_records in sorted(grouped.items())
    }
    return EdgeCalibrationReport(
        run_id=run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        generated_at=datetime.now(UTC).isoformat(),
        classes=classes,
        provenance_counts=provenance_counts,
    )


def write_calibration_artifacts(
    report: EdgeCalibrationReport,
    *,
    metrics_dir: str | Path = "tests/gold/metrics",
    log_path: str | Path = "tests/gold/calibration_log.md",
) -> Path:
    """Write metrics JSON and append a calibration-log entry.

    The defaults intentionally write to tracked seed-baseline locations:
    `tests/gold/metrics` and `tests/gold/calibration_log.md`. Use explicit
    `metrics_dir` and `log_path` scratch paths for ad-hoc/local reruns that should
    not update committed gold artifacts.
    """
    metrics_directory = Path(metrics_dir)
    metrics_directory.mkdir(parents=True, exist_ok=True)
    metrics_path = metrics_directory / f"{report.run_id}.json"
    metrics_path.write_text(
        json.dumps(_report_to_json(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    log_file = Path(log_path)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(
            f"\n## {report.run_id}\n"
            f"- Generated: {report.generated_at}\n"
            f"- Result: per-class thresholds for {len(report.classes)} RelationshipTypes.\n"
            f"- Metrics: `{metrics_path.as_posix()}`\n"
        )
    return metrics_path


def _iter_jsonl(path: str | Path) -> Iterable[tuple[int, str]]:
    gold_path = Path(path)
    if not gold_path.exists():
        raise FileNotFoundError(gold_path)
    for line_number, raw_line in enumerate(gold_path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if line:
            yield line_number, line


def _parse_gold_line(
    line: str,
    path: str | Path,
    line_number: int,
    *,
    include_generated: bool,
) -> EdgeGoldRecord:
    location = f"{path}:{line_number}"
    try:
        raw = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{location} invalid JSON: {exc.msg}") from exc

    required_fields = {
        "edge_id",
        "graph_id",
        "label",
        "source_type",
        "target_type",
        "weight",
        "evidence_ids",
        "gold_verdict",
        "gold_rationale",
        "provenance",
    }
    missing_fields = sorted(required_fields - raw.keys())
    if missing_fields:
        raise ValueError(f"{location} missing required field(s): {', '.join(missing_fields)}")

    label = str(raw["label"])
    try:
        RelationshipType.from_string(label)
    except ValueError as exc:
        raise ValueError(f"{location} invalid RelationshipType label: {label}") from exc
    verdict = str(raw["gold_verdict"])
    if verdict not in {"valid", "invalid", "abstain"}:
        raise ValueError(f"{location} invalid gold_verdict: {verdict}")
    provenance = str(raw["provenance"])
    if provenance not in {"seed", "hand_labeled", "generated"}:
        raise ValueError(f"{location} invalid provenance: {provenance}")
    if provenance == "generated" and not include_generated:
        raise ValueError(f"{location} generated provenance is not ground truth by default")
    evidence_ids = raw["evidence_ids"]
    if not isinstance(evidence_ids, list) or not all(isinstance(item, str) for item in evidence_ids):
        raise ValueError(f"{location} evidence_ids must be a list of strings")
    weight = float(raw["weight"])
    if not math.isfinite(weight) or not 0.0 <= weight <= 1.0:
        raise ValueError(f"{location} weight must be finite and in [0,1]: {raw['weight']}")
    return EdgeGoldRecord(
        edge_id=str(raw["edge_id"]),
        graph_id=str(raw["graph_id"]),
        label=label,
        source_type=str(raw["source_type"]),
        target_type=str(raw["target_type"]),
        weight=weight,
        evidence_ids=tuple(evidence_ids),
        gold_verdict=verdict,  # type: ignore[arg-type]
        gold_rationale=str(raw["gold_rationale"]),
        provenance=provenance,  # type: ignore[arg-type]
    )


def _calibrate_class(label: str, records: list[EdgeGoldRecord]) -> EdgeClassMetrics:
    valid_weights = [record.weight for record in records if record.gold_verdict == "valid"]
    invalid_weights = [record.weight for record in records if record.gold_verdict == "invalid"]
    if not valid_weights or not invalid_weights:
        raise ValueError(f"gold set for {label!r} must include valid and invalid examples")

    reject_threshold = max(invalid_weights)
    accept_threshold = min(valid_weights)
    if reject_threshold >= accept_threshold:
        midpoint = (reject_threshold + accept_threshold) / 2
        reject_threshold = midpoint - 0.01
        accept_threshold = midpoint + 0.01

    predictions = [_predict(record.weight, reject_threshold, accept_threshold) for record in records]
    confusion_matrix = _confusion_matrix(records, predictions)
    actual_valid = sum(1 for record in records if record.gold_verdict == "valid")
    actual_invalid = sum(1 for record in records if record.gold_verdict == "invalid")
    actual_abstain = sum(1 for record in records if record.gold_verdict == "abstain")
    predicted_abstain = sum(1 for prediction in predictions if prediction == "abstain")
    true_valid = sum(
        1
        for record, prediction in zip(records, predictions, strict=True)
        if record.gold_verdict == "valid" and prediction == "valid"
    )
    false_valid = sum(
        1
        for record, prediction in zip(records, predictions, strict=True)
        if record.gold_verdict != "valid" and prediction == "valid"
    )
    false_invalid = sum(
        1
        for record, prediction in zip(records, predictions, strict=True)
        if record.gold_verdict == "valid" and prediction == "invalid"
    )
    precision = true_valid / max(true_valid + false_valid, 1)
    recall = true_valid / max(actual_valid, 1)
    false_positive_rate = false_valid / max(actual_invalid, 1)
    false_negative_rate = false_invalid / max(actual_valid, 1)
    abstain_recall = confusion_matrix["abstain"]["abstain"] / max(actual_abstain, 1)
    abstain_coverage = predicted_abstain / max(len(records), 1)
    return EdgeClassMetrics(
        label=label,
        examples=len(records),
        accept_threshold=round(accept_threshold, 4),
        reject_threshold=round(reject_threshold, 4),
        precision=round(precision, 4),
        recall=round(recall, 4),
        false_positive_rate=round(false_positive_rate, 4),
        false_negative_rate=round(false_negative_rate, 4),
        abstain_band_size=round(max(accept_threshold - reject_threshold, 0.0), 4),
        confusion_matrix=confusion_matrix,
        abstain_actual_count=actual_abstain,
        abstain_predicted_count=predicted_abstain,
        abstain_recall=round(abstain_recall, 4),
        abstain_coverage=round(abstain_coverage, 4),
    )


def _predict(weight: float, reject_threshold: float, accept_threshold: float) -> GoldVerdict:
    if weight >= accept_threshold:
        return "valid"
    if weight <= reject_threshold:
        return "invalid"
    return "abstain"


def _confusion_matrix(
    records: list[EdgeGoldRecord], predictions: list[GoldVerdict]
) -> dict[str, dict[str, int]]:
    matrix = {actual: {predicted: 0 for predicted in CONFUSION_LABELS} for actual in CONFUSION_LABELS}
    for record, prediction in zip(records, predictions, strict=True):
        matrix[record.gold_verdict][prediction] += 1
    return matrix


def _report_to_json(report: EdgeCalibrationReport) -> dict[str, object]:
    payload = asdict(report)
    payload["classes"] = {
        label: asdict(metrics) for label, metrics in sorted(report.classes.items())
    }
    return payload
