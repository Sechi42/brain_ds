from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from collections.abc import Sequence
from pathlib import Path

from tests.eval.blind_agentic.collect_evidence import CollectEvidenceError, collect_evidence
from tests.eval.blind_agentic.score_report import ScoreReportError, score_evidence


class CollectAndScoreError(RuntimeError):
    """Raised when collect-and-score wrapper inputs cannot produce valid outputs."""


def build_model_comparison(
    *, scenario: str, model_runs: Sequence[tuple[str, dict[str, Any]]]
) -> dict[str, Any]:
    """Build a same-pathway model matrix from existing score reports."""

    if len(model_runs) < 2:
        raise CollectAndScoreError("Model comparison requires at least two --model-run inputs")

    first_label, first_report = model_runs[0]
    expected_scenario = _report_scenario(first_label, first_report)
    expected_pathway = _report_pathway(first_label, first_report)
    expected_schema = _report_schema(first_label, first_report)
    expected_metadata = _report_comparable_metadata(first_label, first_report)
    if expected_scenario != scenario:
        raise CollectAndScoreError(
            f"Model run {first_label!r} scenario {expected_scenario!r} does not match {scenario!r}"
        )

    rows: list[dict[str, Any]] = []
    for label, report in model_runs:
        report_scenario = _report_scenario(label, report)
        pathway = _report_pathway(label, report)
        schema = _report_schema(label, report)
        metadata = _report_comparable_metadata(label, report)
        if report_scenario != expected_scenario:
            raise CollectAndScoreError("Model comparison requires the same scenario for every run")
        if pathway != expected_pathway:
            raise CollectAndScoreError("Model comparison requires the same pathway for every run")
        if schema != expected_schema:
            raise CollectAndScoreError("Model comparison requires the same report schema for every run")
        if metadata != expected_metadata:
            raise CollectAndScoreError(
                "Model comparison requires matching prompt, fixture, and rubric metadata"
            )
        rows.append(
            {
                "label": label,
                "run_id": report.get("run_id"),
                "model": report.get("trace_summary", {}).get("model") or label,
                "overall_score_0_5": report.get("overall_score_0_5"),
                "deterministic_status": report.get("deterministic", {}).get("status"),
                "blocking_failures": report.get("blocking_failures", []),
                "freshness_status": report.get("freshness", {}).get("status"),
            }
        )

    return {
        "comparison_status": "comparable",
        "scenario": expected_scenario,
        "pathway_id": expected_pathway,
        "report_schema_version": expected_schema,
        "comparable_rerun_metadata": expected_metadata,
        "runs": rows,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Collect blind agentic eval evidence and score it in one command."
    )
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--subject-path", type=Path)
    parser.add_argument("--evidence-path", type=Path)
    parser.add_argument("--report-out", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--opencode-artifacts-path", type=Path)
    parser.add_argument("--graph-db-path", type=Path)
    parser.add_argument("--graph-id")
    parser.add_argument("--judge-response", type=Path)
    parser.add_argument("--judge-packet-out", type=Path)
    parser.add_argument("--verifier-a-model")
    parser.add_argument("--verifier-b-audit", type=Path)
    parser.add_argument("--model-run", action="append", default=[])
    parser.add_argument("--comparison-out", type=Path)
    args = parser.parse_args(argv)

    run_root = Path("tmp") / "blind-agentic-eval" / args.run_id
    subject_path = args.subject_path or run_root / "subject"
    evidence_path = args.evidence_path or subject_path.parent / "evidence"
    report_out = args.report_out or subject_path.parent / "report.json"

    if args.model_run:
        try:
            comparison = build_model_comparison(
                scenario=args.scenario,
                model_runs=[_load_model_run(value) for value in args.model_run],
            )
        except CollectAndScoreError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        comparison_out = args.comparison_out or run_root / "model_matrix.json"
        comparison_out.parent.mkdir(parents=True, exist_ok=True)
        comparison_out.write_text(
            json.dumps(comparison, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"Model comparison: {comparison_out} ({len(comparison['runs'])} runs)")
        return 0

    try:
        bundle = collect_evidence(
            scenario=args.scenario,
            run_id=args.run_id,
            subject_path=subject_path,
            evidence_path=evidence_path,
            repo_root=args.repo_root,
            opencode_artifacts_path=args.opencode_artifacts_path,
            graph_db_path=args.graph_db_path,
        )
        report = score_evidence(
            scenario=args.scenario,
            evidence_path=bundle.evidence_path,
            out_path=report_out,
            repo_root=args.repo_root,
            graph_id=args.graph_id,
            judge_response_path=args.judge_response,
            judge_packet_out=args.judge_packet_out,
        )
        if args.verifier_a_model or args.verifier_b_audit is not None:
            report = _add_double_verifier_audit(
                report=report,
                verifier_a_model=args.verifier_a_model,
                verifier_b_audit_path=args.verifier_b_audit,
            )
            report_out.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        if report.get("scenario") == "datasource_documentation" and report.get("blocking_failures"):
            codes = ", ".join(str(item.get("code")) for item in report["blocking_failures"])
            print(f"error: invalid datasource run ({codes})", file=sys.stderr)
            return 2
    except (CollectEvidenceError, ScoreReportError, CollectAndScoreError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"Evidence manifest: {bundle.manifest_path}")
    print(f"Score report: {report_out} ({report['overall_score_0_5']} / 5)")
    if report.get("double_verifier"):
        print(f"Double-verifier audit: {report['double_verifier']['audit_status']}")
    return 0


def _load_model_run(value: str) -> tuple[str, dict[str, Any]]:
    if "=" not in value:
        raise CollectAndScoreError("--model-run must use label=path syntax")
    label, path_text = value.split("=", 1)
    if not label.strip():
        raise CollectAndScoreError("--model-run label cannot be empty")
    path = Path(path_text)
    if not path.is_file():
        raise CollectAndScoreError(f"--model-run report does not exist: {path}")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CollectAndScoreError(f"--model-run report is not valid JSON: {path}") from exc
    if not isinstance(report, dict):
        raise CollectAndScoreError(f"--model-run report must be a JSON object: {path}")
    return label.strip(), report


def _report_scenario(label: str, report: dict[str, Any]) -> str:
    scenario = report.get("scenario")
    if not isinstance(scenario, str) or not scenario:
        raise CollectAndScoreError(f"Model run {label!r} is missing scenario")
    return scenario


def _report_pathway(label: str, report: dict[str, Any]) -> str:
    pathway = report.get("trace_summary", {}).get("pathway_id") or report.get("scenario")
    if not isinstance(pathway, str) or not pathway:
        raise CollectAndScoreError(f"Model run {label!r} is missing pathway_id")
    return pathway


def _report_schema(label: str, report: dict[str, Any]) -> str:
    schema = report.get("freshness", {}).get("report_schema_version")
    if not isinstance(schema, str) or not schema:
        raise CollectAndScoreError(f"Model run {label!r} is missing freshness.report_schema_version")
    return schema


def _report_comparable_metadata(label: str, report: dict[str, Any]) -> dict[str, Any]:
    metadata = report.get("comparable_rerun_metadata")
    if not isinstance(metadata, dict):
        raise CollectAndScoreError(f"Model run {label!r} is missing comparable_rerun_metadata")
    return {
        "prompt_version": metadata.get("prompt_version"),
        "fixture_version": metadata.get("fixture_version"),
        "rubric_version": metadata.get("rubric_version"),
    }


def _add_double_verifier_audit(
    *,
    report: dict[str, Any],
    verifier_a_model: str | None,
    verifier_b_audit_path: Path | None,
) -> dict[str, Any]:
    audit = _load_verifier_b_audit(verifier_b_audit_path) if verifier_b_audit_path else {}
    challenges = _string_list(audit.get("challenges", []), field="challenges")
    confirmations = _string_list(audit.get("confirmations", []), field="confirmations")
    refinements = _string_list(audit.get("refinements", []), field="refinements")
    status = "challenged" if challenges else "refined" if refinements else "confirmed"
    updated = dict(report)
    updated["double_verifier"] = {
        "verifier_a_model": verifier_a_model
        or report.get("trace_summary", {}).get("model")
        or "unspecified",
        "verifier_b_model": audit.get("verifier_b_model", "unspecified"),
        "audit_status": status,
        "confirmations": confirmations,
        "challenges": challenges,
        "refinements": refinements,
    }
    return updated


def _load_verifier_b_audit(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    if not path.is_file():
        raise CollectAndScoreError(f"Verifier-B audit does not exist: {path}")
    try:
        audit = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CollectAndScoreError(f"Verifier-B audit is not valid JSON: {path}") from exc
    if not isinstance(audit, dict):
        raise CollectAndScoreError("Verifier-B audit must be a JSON object")
    return audit


def _string_list(value: Any, *, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CollectAndScoreError(f"Verifier-B audit field {field!r} must be a list of strings")
    return value


if __name__ == "__main__":
    sys.exit(main())
