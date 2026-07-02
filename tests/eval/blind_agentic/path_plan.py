import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from subprocess import PIPE, run as _subprocess_run
from typing import Any


PLAN_VERSION = "2026-06-30.pr1"
INTERPRETATION_STATUSES = ("pass", "warn", "fail", "not_applicable")
INTERPRETATION_LANES = (
    "artifact_quality",
    "flow_tool_delegation_quality",
    "model_capability_context",
)
_SDD_CHANGE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_SCENARIO_PATH_ALIASES = {"graph_qa": "graph-qa"}


class PathPlanError(ValueError): ...


@dataclass(frozen=True)
class EvaluationLineage:
    commit_sha: str
    sdd_change: str
    worktree_dirty: bool
    git_diff_hash: str | None
    untracked_files_present: bool
    captured_at_utc: str
    untracked_files: tuple[str, ...] = ()


@dataclass(frozen=True)
class ComparabilityState:
    status: str
    reason: str | None
    key: dict[str, Any] | None

    def __post_init__(self) -> None:
        if self.status not in {"comparable", "non_comparable"}:
            raise PathPlanError(f"Unsupported comparability status: {self.status}")
        if self.status == "comparable" and self.key is None:
            raise PathPlanError("Comparable runs require a comparability key")
        if self.status == "non_comparable" and not self.reason:
            raise PathPlanError("Non-comparable runs require a reason")


@dataclass(frozen=True)
class NormalizedPathSelection:
    path_id: str
    scenario: str
    plan_entry: "PathMatrixEntry"


@dataclass(frozen=True)
class PathMatrixEntry:
    path_id: str
    path_plan_version: str
    label: str
    scenario: str
    agents_or_tools: tuple[str, ...]
    required_evidence: tuple[str, ...]
    expected_artifacts: tuple[str, ...]
    scorer: str
    rubric_version: str
    output_contract: str
    status: str
    execute_in_first_slice: bool

    def __post_init__(self) -> None:
        if self.path_plan_version != PLAN_VERSION:
            raise PathPlanError("Path entry version must match PLAN_VERSION")
        if self.status not in {"required", "candidate", "supported"}:
            raise PathPlanError(f"Unsupported path status: {self.status}")
        required = (
            self.path_id,
            self.label,
            self.scenario,
            self.scorer,
            self.rubric_version,
            self.output_contract,
        )
        if not all(required):
            raise PathPlanError("Path entry missing required fields")
        if not self.required_evidence or not self.expected_artifacts:
            raise PathPlanError("Path entry must declare evidence and artifacts")


@dataclass(frozen=True)
class EvaluationPlan:
    sdd_change: str
    path_plan_version: str
    entries: tuple[PathMatrixEntry, ...]

    def __post_init__(self) -> None:
        validate_sdd_change(self.sdd_change)
        if self.path_plan_version != PLAN_VERSION:
            raise PathPlanError("Unsupported path_plan_version")
        required = [entry.path_id for entry in self.entries if entry.status == "required"]
        if required != ["doc-map", "graph-qa"]:
            raise PathPlanError("Default plan requires doc-map and graph-qa first")
        if len({entry.path_id for entry in self.entries}) != len(self.entries):
            raise PathPlanError("Path IDs must be unique")
        for entry in self.entries:
            if entry.status == "candidate" and entry.execute_in_first_slice:
                raise PathPlanError("Candidate paths must remain planned-only in PR1")

    def required_entries(self) -> list[PathMatrixEntry]:
        return [entry for entry in self.entries if entry.status == "required"]

    def path_by_id(self, path_id: str) -> PathMatrixEntry:
        for entry in self.entries:
            if entry.path_id == path_id:
                return entry
        raise PathPlanError(f"Unknown path_id: {path_id}")

    def path_for_scenario(self, scenario: str) -> PathMatrixEntry:
        path_id = _SCENARIO_PATH_ALIASES.get(scenario)
        if path_id is not None:
            return self.path_by_id(path_id)
        for entry in self.entries:
            if entry.scenario == scenario:
                return entry
        raise PathPlanError(f"Unknown scenario for path selection: {scenario}")


def ensure_single_path_selection(value: str | list[str] | tuple[str, ...]) -> str:
    if isinstance(value, (list, tuple)):
        if len(value) != 1:
            raise PathPlanError("Select exactly one path; multiple paths are not allowed")
        value = value[0]
    if not isinstance(value, str) or not value.strip():
        raise PathPlanError("Select exactly one path before execution")
    selected = value.strip()
    lowered = selected.lower()
    if "," in selected or " vs " in lowered or " and " in lowered:
        raise PathPlanError("Select exactly one path; comparative inputs are not allowed")
    return selected


def normalize_requested_path(value: str | list[str] | tuple[str, ...], *, sdd_change: str) -> NormalizedPathSelection:
    selected = ensure_single_path_selection(value)
    plan = build_default_plan(sdd_change=sdd_change)
    try:
        entry = plan.path_by_id(selected)
    except PathPlanError:
        try:
            entry = plan.path_for_scenario(selected)
        except PathPlanError as exc:
            raise PathPlanError(f"Unknown path_id or scenario: {selected}") from exc
    return NormalizedPathSelection(path_id=entry.path_id, scenario=entry.scenario, plan_entry=entry)


def validate_sdd_change(value: str | None) -> str:
    if value is None or not _SDD_CHANGE_RE.fullmatch(value):
        raise PathPlanError("sdd_change is required and must be a lowercase slug")
    return value


def build_lineage(
    *,
    commit_sha: str,
    sdd_change: str,
    status_porcelain: str,
    git_diff: str | None,
    captured_at_utc: str,
) -> EvaluationLineage:
    if not commit_sha:
        raise PathPlanError("commit_sha is required")
    validate_sdd_change(sdd_change)
    lines = [line for line in status_porcelain.splitlines() if line.strip()]
    untracked_files = tuple(line[3:].strip() for line in lines if line.startswith("?? "))
    untracked = bool(untracked_files)
    tracked_dirty = any(not line.startswith("??") for line in lines)
    if tracked_dirty and git_diff is None:
        raise PathPlanError("git_diff is required for dirty tracked changes")
    diff_hash = (
        hashlib.sha256(git_diff.encode("utf-8")).hexdigest() if tracked_dirty and git_diff else None
    )
    return EvaluationLineage(
        commit_sha=commit_sha,
        sdd_change=sdd_change,
        worktree_dirty=bool(lines),
        git_diff_hash=diff_hash,
        untracked_files_present=untracked,
        captured_at_utc=captured_at_utc,
        untracked_files=untracked_files,
    )


def discover_git_lineage(repo_root: Path | str, *, sdd_change: str) -> EvaluationLineage:
    root = Path(repo_root)
    commit = _git(root, "rev-parse", "HEAD")
    return build_lineage(
        commit_sha=commit.strip(),
        sdd_change=sdd_change,
        status_porcelain=_git(root, "status", "--porcelain"),
        git_diff=_combined_tracked_diff(root),
        captured_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )


def _combined_tracked_diff(root: Path) -> str:
    unstaged = _git(root, "diff")
    staged = _git(root, "diff", "--cached")
    return f"-- unstaged diff --\n{unstaged}\n-- staged diff --\n{staged}"


def build_comparability_state(
    *,
    lineage: EvaluationLineage,
    selected_path: PathMatrixEntry,
    prompt_version: str,
    trace_schema_version: str,
    report_schema_version: str,
) -> ComparabilityState:
    ignored_untracked = [path for path in lineage.untracked_files if _is_safe_untracked_path(path)]
    blocking_untracked = [path for path in lineage.untracked_files if path not in ignored_untracked]
    if lineage.git_diff_hash is not None:
        return ComparabilityState("non_comparable", "tracked_source_drift", None)
    if lineage.untracked_files_present and not lineage.untracked_files:
        return ComparabilityState("non_comparable", "untracked_files_not_captured", None)
    if lineage.untracked_files_present and blocking_untracked:
        return ComparabilityState("non_comparable", "untracked_files_not_captured", None)
    key = build_comparability_key(
        lineage=lineage,
        selected_path=selected_path,
        prompt_version=prompt_version,
        trace_schema_version=trace_schema_version,
        report_schema_version=report_schema_version,
    )
    if ignored_untracked:
        key["ignored_untracked_files"] = ignored_untracked
    return ComparabilityState(
        status="comparable",
        reason=None,
        key=key,
    )


def _is_safe_untracked_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    return normalized.startswith("tmp/blind-agentic-eval/") or normalized.startswith("node_modules/")


def build_comparability_key(
    *,
    lineage: EvaluationLineage,
    selected_path: PathMatrixEntry,
    prompt_version: str,
    trace_schema_version: str,
    report_schema_version: str,
) -> dict[str, Any]:
    return {
        "commit_sha": lineage.commit_sha,
        "worktree_dirty": lineage.worktree_dirty,
        "git_diff_hash": lineage.git_diff_hash,
        "untracked_files_present": lineage.untracked_files_present,
        "sdd_change": lineage.sdd_change,
        "path_id": selected_path.path_id,
        "path_plan_version": selected_path.path_plan_version,
        "scenario": selected_path.scenario,
        "prompt_version": prompt_version,
        "rubric_version": selected_path.rubric_version,
        "trace_schema_version": trace_schema_version,
        "report_schema_version": report_schema_version,
    }


def build_interpretation_lane(
    *, lane: str, status: str, evidence_refs: list[str]
) -> dict[str, Any]:
    if lane not in INTERPRETATION_LANES or status not in INTERPRETATION_STATUSES:
        raise PathPlanError("Invalid interpretation lane or status")
    if not evidence_refs:
        raise PathPlanError("interpretation evidence_refs are required")
    return {"lane": lane, "status": status, "evidence_refs": evidence_refs}


def build_default_plan(*, sdd_change: str) -> EvaluationPlan:
    return EvaluationPlan(
        sdd_change=sdd_change,
        path_plan_version=PLAN_VERSION,
        entries=(
            _entry(
                "doc-map",
                "Source documentation to graph mapping",
                "datasource_documentation",
                ("brainds-source-explorer", "brainds-graph-mapper", "brainds-connection-mapper"),
                required=True,
            ),
            _entry(
                "graph-qa",
                "Graph Q&A dossier answer",
                "revops_growth",
                ("brainds-query-consultant",),
                required=True,
            ),
            _entry(
                "kpi-lineage",
                "KPI dossier lineage",
                "kpi_lineage",
                ("brainds-kpi-composer",),
                supported=True,
            ),
            _entry(
                "currency-elicitation",
                "Currency elicitation",
                "currency_elicitation",
                ("brainds-currency-elicitor",),
                supported=True,
            ),
        ),
    )


def _entry(
    path_id: str,
    label: str,
    scenario: str,
    agents: tuple[str, ...],
    *,
    required: bool = False,
    supported: bool = False,
) -> PathMatrixEntry:
    status = "required" if required else "supported" if supported else "candidate"
    return PathMatrixEntry(
        path_id=path_id,
        path_plan_version=PLAN_VERSION,
        label=label,
        scenario=scenario,
        agents_or_tools=agents,
        required_evidence=("manifest.json", "session_trace.json", "graph/store.db"),
        expected_artifacts=("report.json", "report.md"),
        scorer="deterministic-local-evidence",
        rubric_version="agentic-eval-rubric.v1",
        output_contract="blind-agentic-report.v1",
        status=status,
        execute_in_first_slice=required or supported,
    )


def _git(root: Path, *args: str) -> str:
    completed = _subprocess_run(
        ["git", *args],
        cwd=root,
        check=True,
        text=True,
        stdout=PIPE,
        stderr=PIPE,
    )
    return completed.stdout
