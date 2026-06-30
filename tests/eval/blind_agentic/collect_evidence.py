from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import stat
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tests.eval.blind_agentic.prepare_subject import scan_for_contamination
from tests.eval.blind_agentic.trace_schema import (
    TRACE_VERSION,
    TraceSchemaError,
    _extract_records_from_object,
    _is_transcript_source,
    _record_chronology_key,
    parse_opencode_export,
    write_session_trace,
)


TRACE_REQUIRED_SCENARIOS = ("datasource_documentation",)
# File copies can differ by a sub-second tick across filesystems. Treat only
# graph snapshots older by more than this tolerance as stale.
SUBJECT_LOCAL_GRAPH_STALE_TOLERANCE_SECONDS = 1.0


class CollectEvidenceError(RuntimeError):
    """Raised when evidence cannot support an offline blind-agentic score."""


@dataclass(frozen=True)
class EvidenceBundle:
    scenario: str
    run_id: str
    subject_path: Path
    evidence_path: Path
    manifest_path: Path


def collect_evidence(
    *,
    scenario: str,
    run_id: str,
    subject_path: Path | str,
    evidence_path: Path | str | None = None,
    repo_root: Path | str = Path.cwd(),
    opencode_artifacts_path: Path | str | None = None,
    graph_db_path: Path | str | None = None,
) -> EvidenceBundle:
    """Collect deterministic evidence from a completed blind subject run."""

    subject = Path(subject_path)
    evidence = Path(evidence_path) if evidence_path is not None else subject.parent / "evidence"
    repo = Path(repo_root)
    opencode_artifacts = Path(opencode_artifacts_path) if opencode_artifacts_path else None
    graph_db_override = Path(graph_db_path) if graph_db_path is not None else None
    export_path = _resolve_opencode_export_path(subject)

    if not subject.is_dir():
        raise CollectEvidenceError(f"Subject workspace does not exist: {subject}")
    if scenario in TRACE_REQUIRED_SCENARIOS and export_path is None:
        raise CollectEvidenceError(
            "Missing required OpenCode export at opencode-export/session.json; "
            "stdout/stderr diagnostics are not scoring evidence"
        )

    _raise_on_contamination(subject)

    if evidence.exists():
        _remove_tree_with_retries(evidence)
    evidence.mkdir(parents=True, exist_ok=True)

    captured: dict[str, Any] = {}
    omissions: list[dict[str, str]] = []

    graph_db_source = {"kind": "subject_workspace", "path": (subject / ".brain_ds" / "store.db").as_posix()}
    graph_db = subject / ".brain_ds" / "store.db"
    if graph_db_override is not None:
        graph_db = graph_db_override
        graph_db_source = {"kind": "explicit_override", "path": graph_db_override.as_posix()}
    if not graph_db.is_file():
        hint = " Pass --graph-db-path <path-to-active-workspace/.brain_ds/store.db> if BrainDS wrote to a registered/global workspace."
        if graph_db_override is not None:
            raise CollectEvidenceError(f"Missing graph snapshot at explicit --graph-db-path: {graph_db}.{hint}")
        raise CollectEvidenceError(f"Missing graph snapshot at subject .brain_ds/store.db.{hint}")
    captured["graph_db"] = _copy_file(graph_db, evidence / "graph" / "store.db", evidence)

    setup_json = subject / ".brain_ds" / "setup.json"
    if setup_json.is_file():
        captured["setup_metadata"] = _copy_file(
            setup_json, evidence / "metadata" / "setup.json", evidence
        )
    else:
        omissions.append({"artifact": "setup_metadata", "reason": ".brain_ds/setup.json not found"})

    generated_outputs = _copy_generated_outputs(subject, evidence)
    if generated_outputs:
        captured["generated_outputs"] = generated_outputs
    else:
        omissions.append(
            {"artifact": "generated_outputs", "reason": "no generated markdown/json files found"}
        )

    captured["git_diff"] = _write_git_diff(repo, evidence / "git_diff.patch", evidence)
    captured["file_inventory"] = _write_inventory(
        subject, evidence / "file_inventory.json", evidence
    )

    trace_required = scenario in TRACE_REQUIRED_SCENARIOS
    session_transcript = _copy_optional_opencode_artifacts(
        opencode_artifacts,
        evidence,
        export_path=export_path,
    )
    session_transcript["required"] = trace_required
    session_transcript["required_for_scenarios"] = list(TRACE_REQUIRED_SCENARIOS)
    if session_transcript["status"] == "captured":
        if session_transcript.get("source") == "export":
            captured["opencode_export"] = session_transcript["files"][0]
        else:
            captured["opencode_artifacts"] = session_transcript["files"]
        try:
            trace, trace_omissions = parse_opencode_export(
                evidence / "opencode",
                scenario=scenario,
                run_id=run_id,
                pathway_id=scenario,
                model_provider="opencode",
                model=None,
            )
        except TraceSchemaError as exc:
            raise CollectEvidenceError(f"Invalid OpenCode export schema: {exc}") from exc
        trace_target = evidence / "trace" / "session_trace.json"
        trace_hash = write_session_trace(trace, trace_target)
        captured["session_trace"] = trace_target.relative_to(evidence).as_posix()
        omissions.extend(trace_omissions)
        trace_status = {
            "status": "captured" if trace.events else "empty",
            "required": trace_required,
            "required_for_scenarios": list(TRACE_REQUIRED_SCENARIOS),
            "path": captured["session_trace"],
            "sha256": trace_hash["sha256"],
            "event_count": len(trace.events),
            "omissions": trace_omissions,
        }
    else:
        trace_status = {
            "status": "missing",
            "required": trace_required,
            "required_for_scenarios": list(TRACE_REQUIRED_SCENARIOS),
        }
        if trace_required:
            omissions.append(
                {
                    "artifact": "session_trace",
                    "reason": "required session trace not found for datasource_documentation",
                }
            )

    freshness_checks = _freshness_checks(
        captured=captured,
        evidence=evidence,
        graph_db_source=graph_db_source,
        trace_status=trace_status,
    )
    minimum = _minimum_evidence_status(
        captured, trace_status=trace_status, freshness_checks=freshness_checks
    )
    if minimum["status"] == "rejected":
        raise CollectEvidenceError(minimum["reason"])
    immutable_snapshot = _freeze_evidence_snapshot(evidence, captured)

    manifest = {
        "scenario": scenario,
        "run_id": run_id,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "subject_path": subject.as_posix(),
        "evidence_path": evidence.as_posix(),
        "run_metadata": {
            **_run_metadata_for_scenario(scenario),
        },
        "captured": captured,
        "graph_db_source": graph_db_source,
        "omissions": omissions,
        "immutable_evidence_snapshot": immutable_snapshot,
        "session_transcript": session_transcript,
        "trace": trace_status,
        "freshness_checks": freshness_checks,
        "minimum_evidence": minimum,
        "anti_contamination": {"status": "passed", "findings": []},
    }
    manifest_path = evidence / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    return EvidenceBundle(
        scenario=scenario,
        run_id=run_id,
        subject_path=subject,
        evidence_path=evidence,
        manifest_path=manifest_path,
    )


def _copy_file(source: Path, target: Path, evidence: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target.relative_to(evidence).as_posix()


def _resolve_opencode_export_path(subject: Path) -> Path | None:
    default = subject.parent / "opencode-export" / "session.json"
    return default if default.is_file() else None


def _raise_on_contamination(subject: Path) -> None:
    contamination = scan_for_contamination(subject)
    if contamination:
        summary = ", ".join(f"{item['path']}:{item['term']}" for item in contamination)
        raise CollectEvidenceError(f"Subject workspace contains forbidden terms: {summary}")


def _remove_tree_with_retries(path: Path, *, attempts: int = 5, delay_seconds: float = 0.05) -> None:
    """Remove an evidence tree reliably on Windows and retry transient locks."""

    last_error: BaseException | None = None
    for attempt in range(attempts):
        try:
            shutil.rmtree(path, onerror=_make_writable_and_retry)
            return
        except (OSError, PermissionError) as exc:
            last_error = exc
            if attempt == attempts - 1:
                break
            time.sleep(delay_seconds * (2**attempt))
    if last_error is not None:
        raise last_error


def _make_writable_and_retry(function: Any, path: str, exc_info: Any) -> None:
    """Clear read-only bits during rmtree cleanup, then retry the failed operation."""

    del exc_info
    os.chmod(path, stat.S_IWRITE)
    function(path)


def _copy_generated_outputs(subject: Path, evidence: Path) -> list[str]:
    captured: list[str] = []
    candidates = [subject / "generated", subject / ".elicit"]
    for root in candidates:
        if not root.is_dir():
            continue
        for source in sorted(root.rglob("*")):
            if not source.is_file() or source.suffix.lower() not in {".md", ".json", ".txt"}:
                continue
            target = evidence / "generated" / source.relative_to(root)
            captured.append(_copy_file(source, target, evidence))
    return captured


def _materialize_datasource_output_from_transcript(subject: Path, opencode_artifacts: Path | None) -> None:
    target = subject / "generated" / "source_documentation.md"
    if target.is_file() or opencode_artifacts is None or not opencode_artifacts.exists():
        return
    final_text = _final_opencode_text(opencode_artifacts)
    if final_text is None:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(final_text.rstrip() + "\n", encoding="utf-8")


def _final_opencode_text(opencode_artifacts: Path) -> str | None:
    candidates: list[tuple[int, dict[str, Any], str]] = []
    agent_by_session = _opencode_agent_by_session(opencode_artifacts)
    record_index = 0
    for source in sorted(opencode_artifacts.rglob("*")):
        if not source.is_file() or source.suffix.lower() not in {".json", ".jsonl", ".ndjson"}:
            continue
        if not _is_transcript_source(source):
            continue
        for record in _json_records_from_source(source):
            record_index += 1
            if not isinstance(record, dict) or not _is_materializable_final_text(record, agent_by_session):
                continue
            part = record.get("part")
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if isinstance(text, str) and _looks_like_source_documentation(text):
                candidates.append((record_index, record, text))
    if not candidates:
        return None
    return max(candidates, key=lambda item: _record_chronology_key(item[1], item[0]))[2]


def _json_records_from_source(source: Path) -> list[Any]:
    try:
        if source.suffix.lower() == ".json":
            parsed = json.loads(source.read_text(encoding="utf-8"))
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                return _extract_records_from_object(parsed)
            return []
        records: list[Any] = []
        for line in source.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
        return records
    except json.JSONDecodeError:
        return []


def _is_materializable_final_text(record: dict[str, Any], agent_by_session: dict[str, str]) -> bool:
    if record.get("type") != "text":
        return False
    agent = str(record.get("agent_name") or record.get("agent") or "").strip()
    session_id = str(record.get("sessionID") or record.get("session_id") or "").strip()
    if not agent and session_id:
        agent = agent_by_session.get(session_id, "")
    return agent.casefold() in {"brainds-orchestrator", "brain-ds-orchestrator"}


def _opencode_agent_by_session(opencode_artifacts: Path) -> dict[str, str]:
    agents: dict[str, str] = {}
    for source in sorted(opencode_artifacts.rglob("*")):
        if not source.is_file() or not _is_transcript_source(source):
            continue
        if source.suffix.lower() == ".log":
            for line in source.read_text(encoding="utf-8").splitlines():
                session_id = _line_value(line, "session.id") or _line_value(line, "id")
                agent = _line_value(line, "agent")
                if session_id and agent and not _is_metadata_agent(agent):
                    agents[session_id] = agent
            continue
        if source.suffix.lower() not in {".json", ".jsonl", ".ndjson"}:
            continue
        for record in _json_records_from_source(source):
            if not isinstance(record, dict):
                continue
            session_id = str(record.get("sessionID") or record.get("session_id") or "").strip()
            agent = str(record.get("agent_name") or record.get("agent") or "").strip()
            if session_id and agent and not _is_metadata_agent(agent):
                agents[session_id] = agent
    return agents


def _is_metadata_agent(agent: str | None) -> bool:
    return (agent or "").casefold() in {"title", "unknown"}


def _line_value(line: str, key: str) -> str | None:
    match = re.search(rf"(?:^|\s){re.escape(key)}=(\"[^\"]*\"|\S+)", line)
    if not match:
        return None
    value = match.group(1)
    return value[1:-1] if value.startswith('"') and value.endswith('"') else value


def _looks_like_source_documentation(text: str) -> bool:
    normalized = text.casefold()
    if "source documentation" in normalized:
        return True
    if "datasource" not in normalized and "data source" not in normalized:
        return False
    documentation_signals = ("owner:", "freshness:", "columns:", "data gaps:")
    return sum(signal in normalized for signal in documentation_signals) >= 2


def _write_git_diff(repo: Path, target: Path, evidence: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "diff", "--no-ext-diff"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    target.write_text(result.stdout, encoding="utf-8")
    return target.relative_to(evidence).as_posix()


def _write_inventory(subject: Path, target: Path, evidence: Path) -> str:
    files = [
        path.relative_to(subject).as_posix()
        for path in sorted(subject.rglob("*"))
        if path.is_file()
    ]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(files, indent=2), encoding="utf-8")
    return target.relative_to(evidence).as_posix()


def _copy_optional_opencode_artifacts(
    opencode_artifacts_path: Path | None, evidence: Path, *, export_path: Path | None = None
) -> dict[str, Any]:
    if export_path is not None:
        return {
            "status": "captured",
            "required": False,
            "source": "export",
            "files": [_copy_file(export_path, evidence / "opencode" / "session.json", evidence)],
        }
    if opencode_artifacts_path is None or not opencode_artifacts_path.exists():
        return {"status": "missing", "required": False, "files": []}

    files: list[str] = []
    for source in sorted(opencode_artifacts_path.rglob("*")):
        if source.is_file() and _is_transcript_source(source):
            target = evidence / "opencode" / source.relative_to(opencode_artifacts_path)
            files.append(_copy_file(source, target, evidence))
    if not files:
        return {"status": "missing", "required": False, "files": []}
    return {"status": "captured", "required": False, "files": files}


def _minimum_evidence_status(
    captured: dict[str, Any], *, trace_status: dict[str, Any], freshness_checks: dict[str, Any]
) -> dict[str, str]:
    if "graph_db" not in captured:
        return {"status": "rejected", "reason": "Missing graph snapshot evidence"}
    if "generated_outputs" not in captured and "git_diff" not in captured:
        return {"status": "rejected", "reason": "Missing generated outputs or git diff evidence"}
    if trace_status.get("required") and trace_status.get("status") != "captured":
        return {"status": "degraded", "reason": "Missing required session trace evidence"}
    if trace_status.get("required") and freshness_checks.get("status") == "degraded":
        return {"status": "degraded", "reason": "Freshness checks degraded evidence eligibility"}
    return {"status": "accepted", "reason": "graph snapshot plus output/diff evidence captured"}


def _freshness_checks(
    *,
    captured: dict[str, Any],
    evidence: Path,
    graph_db_source: dict[str, str],
    trace_status: dict[str, Any],
) -> dict[str, Any]:
    subject_local = graph_db_source.get("kind") == "subject_workspace"
    generated = captured.get("generated_outputs", [])
    subject_local_graph = _subject_local_graph_check(
        evidence=evidence,
        captured=captured,
        subject_local=subject_local,
    )
    checks: dict[str, Any] = {
        "report_schema_version": "2026-06-27.pr2",
        "trace_schema_version": TRACE_VERSION,
        "subject_local_graph": subject_local_graph,
        "generated_outputs": {
            "status": "captured" if generated else "missing",
            "count": len(generated),
        },
        "trace": {
            "status": trace_status.get("status", "missing"),
            "required": bool(trace_status.get("required")),
        },
        "artifact_hashes": _artifact_hashes(evidence, captured),
    }
    failed = [
        name
        for name in ("subject_local_graph", "generated_outputs", "trace")
        if checks[name].get("status") not in {"passed", "captured"}
        and (name != "trace" or checks[name].get("required"))
    ]
    checks["status"] = "passed" if not failed else "degraded"
    checks["failing_checks"] = failed
    return checks


def _subject_local_graph_check(
    *, evidence: Path, captured: dict[str, Any], subject_local: bool
) -> dict[str, Any]:
    if not subject_local:
        return {
            "status": "failed",
            "reason": "datasource_documentation requires the graph snapshot from the subject workspace",
            "action": "Re-run the subject workspace or pass only the matching subject-local graph DB.",
        }

    graph_ref = captured.get("graph_db")
    graph_path = evidence / str(graph_ref) if graph_ref else None
    if graph_path is None or not graph_path.is_file():
        return {
            "status": "failed",
            "reason": "subject-local graph snapshot was not captured",
            "action": "Regenerate the graph in the subject workspace and collect evidence again.",
        }

    graph_mtime = graph_path.stat().st_mtime
    comparison_refs = [
        *captured.get("generated_outputs", []),
        captured.get("session_trace"),
    ]
    comparison_mtimes = [
        (evidence / str(ref)).stat().st_mtime
        for ref in comparison_refs
        if ref and (evidence / str(ref)).is_file()
    ]
    newest_related = max(comparison_mtimes, default=graph_mtime)
    if newest_related - graph_mtime > SUBJECT_LOCAL_GRAPH_STALE_TOLERANCE_SECONDS:
        return {
            "status": "stale",
            "reason": "subject-local graph is older than generated outputs or trace artifacts",
            "action": "Regenerate the graph after the latest subject outputs/trace, then collect evidence again.",
            "graph_mtime_utc": datetime.fromtimestamp(graph_mtime, UTC).isoformat(),
            "newest_output_or_trace_mtime_utc": datetime.fromtimestamp(newest_related, UTC).isoformat(),
        }

    return {
        "status": "passed",
        "reason": "graph snapshot was captured from subject workspace and is current with captured outputs",
        "graph_mtime_utc": datetime.fromtimestamp(graph_mtime, UTC).isoformat(),
    }


def _artifact_hashes(evidence: Path, captured: dict[str, Any]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    refs = [
        captured.get("graph_db"),
        *captured.get("generated_outputs", []),
        captured.get("session_trace"),
    ]
    for relative in refs:
        if not relative:
            continue
        path = evidence / str(relative)
        if path.is_file():
            hashes[str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def _run_metadata_for_scenario(scenario: str) -> dict[str, str]:
    if scenario == "datasource_documentation":
        return {
            "prompt_version": "datasource-documentation-v1",
            "fixture_version": "datasource-documentation-fixture-v1",
        }
    return {
        "prompt_version": "revops-growth-v1",
        "fixture_version": "revops-growth-fixture-v1",
    }


def _freeze_evidence_snapshot(evidence: Path, captured: dict[str, Any]) -> dict[str, Any]:
    paths = [
        captured.get("graph_db"),
        *captured.get("generated_outputs", []),
        captured.get("git_diff"),
    ]
    files = []
    for relative in sorted(str(path) for path in paths if path):
        source = evidence / relative
        if source.is_file():
            files.append(
                {
                    "path": relative,
                    "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                }
            )
    digest = hashlib.sha256()
    for item in files:
        digest.update(item["path"].encode("utf-8"))
        digest.update(item["sha256"].encode("utf-8"))
    return {
        "status": "frozen",
        "algorithm": "sha256",
        "files": files,
        "evidence_hash": digest.hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect blind agentic eval evidence.")
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--subject-path", type=Path)
    parser.add_argument("--evidence-path", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--opencode-artifacts-path", type=Path)
    parser.add_argument("--graph-db-path", type=Path)
    args = parser.parse_args()

    subject_path = args.subject_path or Path("tmp") / "blind-agentic-eval" / args.run_id / "subject"
    evidence_path = (
        args.evidence_path or Path("tmp") / "blind-agentic-eval" / args.run_id / "evidence"
    )
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
    except CollectEvidenceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(f"Evidence manifest: {bundle.manifest_path}")


if __name__ == "__main__":
    main()
