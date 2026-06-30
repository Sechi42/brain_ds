from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sqlite3
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


DEFAULT_FORBIDDEN_TERMS = (
    "eval",
    "rubric",
    "gold",
    "answer key",
    "expected output",
    "benchmark",
    "hidden test",
)

DEFAULT_INFRASTRUCTURE_EXCLUDE_DIRS = (
    ".atl",
    ".git",
    ".opencode",
    ".pytest_cache",
    "__pycache__",
)


class PrepareSubjectError(RuntimeError):
    """Raised when a blind subject workspace would violate run constraints."""


@dataclass(frozen=True)
class PreparedSubjectWorkspace:
    scenario: str
    run_id: str
    subject_path: Path
    files: tuple[Path, ...]


def prepare_subject(
    *,
    scenario: str,
    run_id: str,
    output_root: Path | str = Path("tmp") / "blind-agentic-eval",
    repo_root: Path | str | None = None,
) -> PreparedSubjectWorkspace:
    """Materialize a subject-only workspace for a blind agentic run."""

    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[3]
    template_root = root / "tests" / "fixtures" / "blind_agentic" / scenario
    if not template_root.is_dir():
        raise PrepareSubjectError(f"Unknown blind subject scenario: {scenario}")

    subject_path = Path(output_root) / run_id / "subject"
    if subject_path.exists():
        _remove_tree_with_retries(subject_path)
    subject_path.mkdir(parents=True)

    _copy_allowlisted_subject_files(template_root, subject_path)
    sqlite_name = "datasource.sqlite" if scenario == "datasource_documentation" else "revops.sqlite"
    _build_sqlite_from_csv_sources(subject_path / "sources", sqlite_name=sqlite_name)
    if scenario == "datasource_documentation":
        _write_datasource_protocol_metadata(subject_path)

    findings = scan_for_contamination(subject_path)
    if findings:
        summary = ", ".join(f"{finding['path']}:{finding['term']}" for finding in findings)
        raise PrepareSubjectError(f"Subject workspace contains forbidden terms: {summary}")

    files = tuple(
        sorted(
            (path for path in subject_path.rglob("*") if path.is_file()), key=lambda p: p.as_posix()
        )
    )
    return PreparedSubjectWorkspace(
        scenario=scenario, run_id=run_id, subject_path=subject_path, files=files
    )


def validate_non_goal_request(options: dict[str, Any]) -> None:
    """Reject execution paths outside the non-goals for the blind harness."""

    violations = {
        "requires_local_model": "local model execution is not supported",
        "requires_openai_api_key": "OpenAI API keys are not required or supported",
        "requires_opencode_go_api_key": "opencode-go API keys are not required or supported",
        "requires_live_llm_ci_gate": "live-LLM CI gates are not supported",
        "requires_ci_live_llm_gate": "live-LLM CI gates are not supported",
        "requires_pyagent_replatforming": "PyAgent replatforming is not part of this harness",
    }
    for key, message in violations.items():
        if options.get(key):
            raise PrepareSubjectError(message)


def scan_for_contamination(
    root: Path | str,
    forbidden_terms: tuple[str, ...] = DEFAULT_FORBIDDEN_TERMS,
    excluded_dirs: tuple[str, ...] = DEFAULT_INFRASTRUCTURE_EXCLUDE_DIRS,
) -> list[dict[str, str]]:
    """Return subject-visible files containing evaluator leakage terms."""

    base = Path(root)
    findings: list[dict[str, str]] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file() or path.suffix.lower() in {".sqlite", ".db"}:
            continue
        if any(part in excluded_dirs for part in path.relative_to(base).parts[:-1]):
            continue
        text = path.read_text(encoding="utf-8").lower()
        for term in forbidden_terms:
            if term.lower() in text:
                findings.append({"path": path.relative_to(base).as_posix(), "term": term})
    return findings


def _copy_allowlisted_subject_files(template_root: Path, subject_path: Path) -> None:
    allowed_roots = {"sources"}
    allowed_files = {"README.md", "PROMPT.md", "seed_graph.json"}
    for path in sorted(template_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(template_root)
        if relative.parts[0] in allowed_roots or relative.as_posix() in allowed_files:
            target = subject_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def _write_datasource_protocol_metadata(subject_path: Path) -> None:
    brain_ds_root = subject_path / ".brain_ds"
    brain_ds_root.mkdir(parents=True, exist_ok=True)
    setup = {
        "blind_agentic_protocol": {
            "version": "blind-agent-flow-v1",
            "required_orchestrator": "brain-ds-orchestrator",
            "prompt_path": "PROMPT.md",
            "expected_outputs": ["generated/source_documentation.md"],
            "graph_db": ".brain_ds/store.db",
            "opencode_export": "opencode-export/session.json",
            "wrapper_diagnostics": [
                "diagnostics/opencode-run.stdout.jsonl",
                "diagnostics/opencode-run.stderr.txt",
                "diagnostics/opencode-export.stderr.txt",
            ],
            "required_evidence": [
                "opencode_export",
                "normalized_trace_events",
                "verifiable_text_exchange",
                "subagent_identity_plus_action_or_tool_call",
                "subject_local_graph",
                "workspace_open_before_graph_write",
            ],
        }
    }
    (brain_ds_root / "setup.json").write_text(
        json.dumps(setup, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _remove_tree_with_retries(path: Path, *, attempts: int = 5, delay_seconds: float = 0.05) -> None:
    """Remove a tree reliably on Windows without swallowing persistent failures."""

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


def _build_sqlite_from_csv_sources(sources_root: Path, *, sqlite_name: str = "revops.sqlite") -> None:
    db_path = sources_root / sqlite_name
    if db_path.exists():
        db_path.unlink()
    csv_paths = sorted(path for path in sources_root.glob("*.csv") if path.is_file())
    conn = sqlite3.connect(db_path)
    try:
        for csv_path in csv_paths:
            table = _sqlite_identifier(csv_path.stem)
            with csv_path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                columns = list(reader.fieldnames or [])
                if not columns:
                    continue
                quoted_column_names = [_sqlite_identifier(column) for column in columns]
                quoted_columns = ", ".join(f"{column} TEXT" for column in quoted_column_names)
                conn.execute(f"CREATE TABLE {table} ({quoted_columns})")
                placeholders = ", ".join("?" for _ in columns)
                quoted_names = ", ".join(quoted_column_names)
                for row in reader:
                    conn.execute(
                            f"INSERT INTO {table} ({quoted_names}) VALUES ({placeholders})",
                            [row[column] for column in columns],
                        )
        conn.commit()
    finally:
        conn.close()


def _sqlite_identifier(name: str) -> str:
    """Return a safely quoted SQLite identifier or reject names SQLite cannot store."""

    if not name or not name.strip():
        raise PrepareSubjectError("SQLite identifiers must not be empty")
    if "\x00" in name:
        raise PrepareSubjectError("SQLite identifiers must not contain NUL bytes")
    return f'"{name.replace(chr(34), chr(34) + chr(34))}"'


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare a blind agentic eval subject workspace.")
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("tmp") / "blind-agentic-eval",
        help="Root where the run folder will be created.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root containing tests/fixtures/blind_agentic.",
    )
    args = parser.parse_args(argv)

    try:
        workspace = prepare_subject(
            scenario=args.scenario,
            run_id=args.run_id,
            output_root=args.output_root,
            repo_root=args.repo_root,
        )
    except PrepareSubjectError as exc:
        parser.exit(2, f"error: {exc}\n")

    print(f"Subject workspace: {workspace.subject_path.as_posix()}")
    print(f"Files prepared: {len(workspace.files)}")
    print(f"OpenCode folder: {workspace.subject_path.as_posix()}")
    print("Next: cd into the subject workspace, run opencode, and paste PROMPT.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
