from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from brain_ds.store.graph_store import GraphStore
from tests.eval.blind_agentic.path_plan import PathPlanError, build_interpretation_lane, validate_sdd_change
from tests.eval.blind_agentic.prepare_subject import resolve_repo_root
from tests.eval.blind_agentic.trace_schema import REPORT_SCHEMA_VERSION


class ScoreReportError(RuntimeError):
    """Raised when a blind-agentic evidence bundle cannot be scored."""


@dataclass(frozen=True)
class GraphSnapshot:
    graph_id: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    pending_questions: list[dict[str, Any]]


class GraphSnapshotReader:
    """Read captured graph evidence from the SQLite store snapshot."""

    def __init__(self, db_path: Path | str, *, graph_id: str | None = None) -> None:
        self.db_path = Path(db_path)
        self.graph_id = graph_id

    @classmethod
    def from_manifest(cls, manifest_path: Path | str) -> "GraphSnapshotReader":
        manifest_file = Path(manifest_path)
        manifest = _load_json(manifest_file)
        captured = manifest.get("captured", {})
        graph_db = captured.get("graph_db")
        if not isinstance(graph_db, str) or not graph_db:
            raise ScoreReportError("Evidence manifest is missing captured.graph_db")
        graph_id = captured.get("graph_id")
        if graph_id is not None and not isinstance(graph_id, str):
            raise ScoreReportError("Evidence manifest captured.graph_id must be a string")
        return cls(manifest_file.parent / graph_db, graph_id=graph_id)

    def read(self) -> GraphSnapshot:
        if not self.db_path.is_file():
            raise ScoreReportError(f"Missing captured graph DB: {self.db_path}")
        store = GraphStore(str(self.db_path), read_only=True)
        try:
            graph_id = self.graph_id or self._single_graph_id(store)
            return GraphSnapshot(
                graph_id=graph_id,
                nodes=[_node_row_to_dict(row) for row in store.query_nodes(graph_id)],
                edges=[_edge_row_to_dict(row) for row in store.query_edges(graph_id)],
                pending_questions=[
                    _pending_question_row_to_dict(row)
                    for row in store.list_pending_questions(graph_id, status="pending")
                ],
            )
        finally:
            try:
                store.close()
            except Exception:
                store.conn.close()

    def _single_graph_id(self, store: GraphStore) -> str:
        graphs = store.list_graphs()
        if len(graphs) != 1:
            raise ScoreReportError(
                "Captured graph DB must contain exactly one graph or manifest captured.graph_id"
            )
        return graphs[0].id


_GOLD_V2_REQUIRED_KEYS = {
    "version",
    "scenario",
    "rubric",
    "canonical_nodes",
    "expected_edges",
    "optional_edges",
    "forbidden_edges",
    "pending_question_themes",
}
_GENERATED_EXCERPT_MAX_LINES = 20
_GENERATED_EXCERPT_MAX_CHARS = 1200
_LINEAGE_REQUIRED_FIELDS = (
    "commit_sha",
    "sdd_change",
    "worktree_dirty",
    "git_diff_hash",
    "untracked_files_present",
    "captured_at_utc",
)
_COMPARABILITY_KEY_REQUIRED_FIELDS = (
    "commit_sha",
    "worktree_dirty",
    "git_diff_hash",
    "untracked_files_present",
    "sdd_change",
    "path_id",
    "path_plan_version",
    "scenario",
    "prompt_version",
    "rubric_version",
    "trace_schema_version",
    "report_schema_version",
)


def load_gold_v2(path: Path | str) -> dict[str, Any]:
    """Load and validate the evaluator-only gold v2 contract."""

    gold = _load_json(Path(path))
    missing = sorted(_GOLD_V2_REQUIRED_KEYS - gold.keys())
    if missing:
        raise ScoreReportError(
            f"Invalid gold v2 contract; missing required keys: {', '.join(missing)}"
        )
    if gold["version"] != 2:
        raise ScoreReportError("Invalid gold v2 contract; version must be 2")
    if not isinstance(gold["rubric"], dict) or not gold["rubric"].get("version"):
        raise ScoreReportError("Invalid gold v2 contract; rubric.version is required")
    if not isinstance(gold["canonical_nodes"], list) or not gold["canonical_nodes"]:
        raise ScoreReportError("Invalid gold v2 contract; canonical_nodes must be non-empty")
    _validate_canonical_nodes(gold["canonical_nodes"])
    for key in ("expected_edges", "optional_edges", "forbidden_edges", "pending_question_themes"):
        if not isinstance(gold[key], list):
            raise ScoreReportError(f"Invalid gold v2 contract; {key} must be a list")
    return gold


def normalize_gold_alias(value: str) -> str:
    """Normalize gold-owned aliases for deterministic graph matching."""

    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    punctuation_as_space = re.sub(r"[^\w\s]", " ", without_accents.replace("_", " "))
    return " ".join(punctuation_as_space.split())


class GoldAliasResolver:
    """Resolve generated labels to canonical IDs using gold-only, type-scoped aliases."""

    def __init__(self, canonical_nodes: list[dict[str, Any]]) -> None:
        self._aliases: dict[tuple[str, str], str] = {}
        for node in canonical_nodes:
            canonical_id = _required_string(node, "id", "canonical_nodes")
            node_type = _required_string(node, "type", "canonical_nodes")
            labels = [canonical_id, _required_string(node, "label", "canonical_nodes")]
            labels.extend(str(alias) for alias in node.get("aliases", []))
            for label in labels:
                self._aliases[(node_type, normalize_gold_alias(label))] = canonical_id

    def resolve(self, entity_type: str, value: str) -> str | None:
        return self._aliases.get((entity_type, normalize_gold_alias(value)))


def edge_labels_are_compatible(label: str, compatible_labels: list[str], *, direction: str) -> bool:
    """Compare edge labels after stable normalization while preserving direction semantics."""

    normalized = _normalize_edge_label(label)
    compatible = {_normalize_edge_label(candidate) for candidate in compatible_labels}
    if normalized in compatible:
        return True
    if direction == "target_to_source" and normalized == "measured_from":
        return "measures" in compatible
    return False


def score_evidence(
    *,
    scenario: str,
    evidence_path: Path | str,
    out_path: Path | str,
    repo_root: Path | str | None = None,
    graph_id: str | None = None,
    judge_response_path: Path | str | None = None,
    judge_packet_out: Path | str | None = None,
) -> dict[str, Any]:
    """Score a collected blind-agentic evidence bundle and write JSON/Markdown reports."""

    repo = resolve_repo_root(repo_root)
    evidence = Path(evidence_path)
    output = Path(out_path)
    gold_root = repo / "tests" / "gold" / "blind_agentic" / scenario
    gold_v2 = load_gold_v2(gold_root / "gold_v2.json")
    manifest = _load_json(evidence / "manifest.json")

    if manifest.get("scenario") != scenario:
        raise ScoreReportError(f"Evidence scenario does not match requested scenario: {scenario}")
    output_contract = _output_contract(manifest)

    generated_text = _read_generated_text(evidence, manifest)
    if graph_id is not None:
        manifest.setdefault("captured", {})["graph_id"] = graph_id
    graph_snapshot = _read_graph_snapshot(evidence / "manifest.json", graph_id=graph_id)
    trace_summary = _trace_summary(evidence, manifest)
    orchestrator_gate = _orchestrator_gate(trace_summary)
    freshness = _freshness_report(manifest)
    datasource_contract = None
    pathway_compliance = None
    tool_quality = None
    conversation_axes = None
    if scenario == "datasource_documentation":
        datasource_contract = _datasource_scoring_contract(
            gold=gold_v2,
            graph=graph_snapshot,
            manifest=manifest,
            generated_text=generated_text,
            evidence=evidence,
        )
        trace_summary = datasource_contract["trace_summary"]
        orchestrator_gate = datasource_contract["orchestrator_gate"]
        freshness = datasource_contract["freshness"]
        axes = datasource_contract["axes"]
        pathway_compliance = datasource_contract["pathway_compliance"]
        tool_quality = datasource_contract["tool_quality"]
        conversation_axes = datasource_contract["conversation_axes"]
    else:
        axes = _score_graph_axes(
            gold=gold_v2,
            graph=graph_snapshot,
            manifest=manifest,
            generated_text=generated_text,
        )
    overall = (
        datasource_contract["overall_score_0_5"]
        if datasource_contract is not None
        else round(sum(axis["score_0_5"] * axis["weight"] for axis in axes.values()), 2)
    )
    blocking_failures = (
        datasource_contract["blocking_failures"] if datasource_contract is not None else []
    )
    status = (
        datasource_contract["status"]
        if datasource_contract is not None
        else _datasource_status(overall, blocking_failures, freshness)
    )

    deterministic = {
        "overall_score_0_5": overall,
        "status": status,
        "axes": axes,
    }
    if scenario == "datasource_documentation":
        deterministic["orchestrator_gate"] = orchestrator_gate
        deterministic["conversation_axes"] = conversation_axes

    report = {
        "run_id": manifest["run_id"],
        "scenario": scenario,
        "rubric_version": gold_v2["rubric"]["version"],
        "evidence_hash": _evidence_hash(evidence, manifest),
        "deterministic": deterministic,
        "advisory_judge": None,
        "disagreements": [],
        "judge_packet": None,
        "anti_contamination": manifest.get(
            "anti_contamination", {"status": "unknown", "findings": []}
        ),
        "blocking_failures": blocking_failures,
        "trace_summary": trace_summary,
        "freshness": freshness,
        **output_contract,
        "interpretation": _interpretation_lanes(
            deterministic=deterministic,
            freshness=freshness,
            selected_path=output_contract["selected_path"],
        ),
        "comparable_rerun_metadata": _comparable_metadata(manifest, gold_v2["rubric"]),
        # Compatibility keys for callers not yet moved to the v2 deterministic lane.
        "overall_score_0_5": overall,
        "axes": axes,
        "evidence_manifest": "manifest.json",
    }
    if pathway_compliance is not None:
        report["pathway_compliance"] = pathway_compliance
    if tool_quality is not None:
        report["tool_quality"] = tool_quality

    if judge_response_path is not None:
        advisory = ingest_judge_response(
            judge_response_path, expected_evidence_hash=report["evidence_hash"]
        )
        report["advisory_judge"] = advisory
        report["disagreements"] = advisory["disagreements"]

    if judge_packet_out is not None:
        packet = _build_judge_packet(
            report=report,
            gold=gold_v2,
            graph=graph_snapshot,
            evidence=evidence,
            manifest=manifest,
        )
        packet_path = Path(judge_packet_out)
        packet_path.parent.mkdir(parents=True, exist_ok=True)
        packet_path.write_text(
            json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        report["judge_packet"] = {
            "path": packet_path.as_posix(),
            "evidence_hash": packet["evidence_hash"],
        }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output.with_suffix(".md").write_text(_render_markdown(report), encoding="utf-8")
    return report


def generate_judge_packet(
    *,
    scenario: str,
    evidence_path: Path | str,
    repo_root: Path | str | None = None,
    graph_id: str | None = None,
) -> dict[str, Any]:
    """Build an evaluator-only packet for an optional manual advisory judge."""

    repo = resolve_repo_root(repo_root)
    evidence = Path(evidence_path)
    gold_root = repo / "tests" / "gold" / "blind_agentic" / scenario
    gold_v2 = load_gold_v2(gold_root / "gold_v2.json")
    manifest = _load_json(evidence / "manifest.json")
    if graph_id is not None:
        manifest.setdefault("captured", {})["graph_id"] = graph_id
    if manifest.get("scenario") != scenario:
        raise ScoreReportError(f"Evidence scenario does not match requested scenario: {scenario}")
    generated_text = _read_generated_text(evidence, manifest)
    graph_snapshot = _read_graph_snapshot(evidence / "manifest.json", graph_id=graph_id)
    trace_summary: dict[str, Any] | None = None
    pathway_compliance: dict[str, Any] | None = None
    tool_quality: dict[str, Any] | None = None
    conversation_axes: dict[str, dict[str, Any]] | None = None
    blocking_failures: list[dict[str, Any]] = []
    if scenario == "datasource_documentation":
        datasource_contract = _datasource_scoring_contract(
            gold=gold_v2,
            graph=graph_snapshot,
            manifest=manifest,
            generated_text=generated_text,
            evidence=evidence,
        )
        axes = datasource_contract["axes"]
        trace_summary = datasource_contract["trace_summary"]
        pathway_compliance = datasource_contract["pathway_compliance"]
        tool_quality = datasource_contract["tool_quality"]
        conversation_axes = datasource_contract["conversation_axes"]
        blocking_failures = datasource_contract["blocking_failures"]
        overall = datasource_contract["overall_score_0_5"]
        status = datasource_contract["status"]
    else:
        axes = _score_graph_axes(
            gold=gold_v2,
            graph=graph_snapshot,
            manifest=manifest,
            generated_text=generated_text,
        )
        overall = round(sum(axis["score_0_5"] * axis["weight"] for axis in axes.values()), 2)
        status = _score_status(overall)
    report = {
        "run_id": manifest["run_id"],
        "scenario": scenario,
        "rubric_version": gold_v2["rubric"]["version"],
        "evidence_hash": _evidence_hash(evidence, manifest),
        "deterministic": {
            "overall_score_0_5": overall,
            "status": status,
            "axes": axes,
        },
    }
    if conversation_axes is not None:
        report["deterministic"]["conversation_axes"] = conversation_axes
    if trace_summary is not None:
        report["trace_summary"] = trace_summary
    if pathway_compliance is not None:
        report["pathway_compliance"] = pathway_compliance
    if tool_quality is not None:
        report["tool_quality"] = tool_quality
    if blocking_failures:
        report["blocking_failures"] = blocking_failures
    return _build_judge_packet(
        report=report,
        gold=gold_v2,
        graph=graph_snapshot,
        evidence=evidence,
        manifest=manifest,
    )


def ingest_judge_response(
    response_path: Path | str, *, expected_evidence_hash: str
) -> dict[str, Any]:
    """Validate and normalize a manual advisory judge response."""

    response = _load_json(Path(response_path))
    actual_hash = response.get("evidence_hash")
    if actual_hash != expected_evidence_hash:
        raise ScoreReportError(
            "Advisory judge response evidence hash does not match packet evidence hash"
        )
    verdict = _required_response_string(response, "verdict")
    return {
        "status": "non_blocking",
        "judge_model": _required_response_string(response, "judge_model"),
        "evidence_hash": actual_hash,
        "verdict": verdict,
        "axis_findings": _optional_response_list(response, "axis_findings"),
        "disagreements": _optional_response_list(response, "disagreements"),
        "rationale": _required_response_string(response, "rationale"),
    }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file() and not path.is_absolute() and path.parts[:1] == ("tests",):
        path = resolve_repo_root() / path
    if not path.is_file():
        raise ScoreReportError(f"Missing required scorer input: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _node_row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "label": row.label,
        "type": row.type,
        "details": row.details or {},
    }


def _edge_row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "source": row.source,
        "target": row.target,
        "label": row.label,
        "weight": row.weight,
    }


def _pending_question_row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "target_node_id": row.target_node_id,
        "gap_kind": row.gap_kind,
        "entity_type": row.entity_type,
        "question_text": row.question_text,
        "stakeholder_owner": row.stakeholder_owner,
        "status": row.status,
    }


def _read_graph_snapshot(manifest_path: Path, *, graph_id: str | None = None) -> GraphSnapshot:
    reader = GraphSnapshotReader.from_manifest(manifest_path)
    if graph_id is not None:
        reader = GraphSnapshotReader(reader.db_path, graph_id=graph_id)
    try:
        return reader.read()
    except ScoreReportError:
        raise
    except Exception as exc:
        raise ScoreReportError(f"Unable to read captured graph DB: {reader.db_path}") from exc


def _build_judge_packet(
    *,
    report: dict[str, Any],
    gold: dict[str, Any],
    graph: GraphSnapshot | None,
    evidence: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    generated_refs = list(manifest.get("captured", {}).get("generated_outputs", []))
    axes = report["deterministic"].get("axes", {})
    missing_generated_refs = _missing_generated_refs(evidence, generated_refs)
    has_conversation_contract = "pathway_compliance" in report or "tool_quality" in report
    packet = {
        "packet_version": 2 if has_conversation_contract else 1,
        "evidence_hash": report["evidence_hash"],
        "rubric_version": report["rubric_version"],
        "deterministic_summary": dict(report["deterministic"]),
        "graph_summary": _graph_summary(graph),
        "pending_questions": [] if graph is None else graph.pending_questions,
        "generated_excerpt_refs": generated_refs,
        "generated_excerpts": _generated_excerpts(evidence, generated_refs),
        "missing_items": _actionable_missing_items(
            axes, missing_generated_refs=missing_generated_refs
        ),
        "questions": _judge_questions(gold),
        "instructions": [
            "This is an optional evaluator-only advisory review packet.",
            "Do not blend advisory findings into the deterministic score.",
            "Return evidence_hash unchanged in the response JSON.",
        ],
        "evidence_manifest": (evidence / "manifest.json").as_posix(),
    }
    if has_conversation_contract:
        packet["trace_summary"] = report.get("trace_summary", {})
        packet["conversation_axes"] = report.get("deterministic", {}).get("conversation_axes", {})
        packet["pathway_compliance"] = report.get("pathway_compliance", {})
        packet["tool_quality"] = report.get("tool_quality", {})
    return packet


def _graph_summary(graph: GraphSnapshot | None) -> dict[str, Any]:
    if graph is None:
        return {"graph_id": None, "nodes": [], "edges": []}
    return {
        "graph_id": graph.graph_id,
        "nodes": [
            {"id": node["id"], "label": node["label"], "type": node["type"]} for node in graph.nodes
        ],
        "edges": [
            {"source": edge["source"], "target": edge["target"], "label": edge["label"]}
            for edge in graph.edges
        ],
    }


def _generated_excerpts(evidence: Path, generated_refs: list[str]) -> list[dict[str, str]]:
    excerpts: list[dict[str, str]] = []
    for relative in generated_refs:
        path = evidence / relative
        if not path.is_file() or path.suffix.lower() not in {".md", ".json", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8")
        excerpt = "\n".join(
            line.rstrip() for line in text.strip().splitlines()[:_GENERATED_EXCERPT_MAX_LINES]
        )
        excerpts.append({"path": relative, "excerpt": excerpt[:_GENERATED_EXCERPT_MAX_CHARS]})
    return excerpts


def _missing_generated_refs(evidence: Path, generated_refs: list[str]) -> list[str]:
    return [relative for relative in generated_refs if not (evidence / relative).is_file()]


def _actionable_missing_items(
    axes: dict[str, dict[str, Any]], *, missing_generated_refs: list[str] | None = None
) -> dict[str, list[str]]:
    lineage = axes.get("lineage", {})
    entity_source = axes.get("entity_source", {})
    evidence_quality = axes.get("evidence_quality", {})
    artifact_hygiene = axes.get("artifact_hygiene", {})
    return {
        "canonical_nodes": list(entity_source.get("missing_expected", [])),
        "lineage_edges": list(lineage.get("missing_expected", [])),
        "artifact_classes": [
            *list(evidence_quality.get("missing_expected", [])),
            *list(artifact_hygiene.get("missing_expected", [])),
        ],
        "generated_files": list(missing_generated_refs or []),
    }


def _judge_questions(gold: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "id": "lineage_quality",
            "prompt": "Does the generated graph support the expected KPI/source lineage without forbidden facts?",
        },
        {
            "id": "pending_question_quality",
            "prompt": "Are pending questions useful, specific, and aligned to the expected themes?",
        },
        {
            "id": "business_usefulness",
            "prompt": "Is the diagnosis actionable for the Revenue Operations scenario?",
        },
        {
            "id": "rubric_version",
            "prompt": f"Apply rubric version {gold['rubric']['version']} and report any disagreement separately.",
        },
    ]


def _required_response_string(response: dict[str, Any], key: str) -> str:
    value = response.get(key)
    if not isinstance(value, str) or not value:
        raise ScoreReportError(f"Invalid advisory judge response; {key} must be a non-empty string")
    return value


def _optional_response_list(response: dict[str, Any], key: str) -> list[Any]:
    value = response.get(key, [])
    if not isinstance(value, list):
        raise ScoreReportError(f"Invalid advisory judge response; {key} must be a list")
    return value


def _score_graph_axes(
    *,
    gold: dict[str, Any],
    graph: GraphSnapshot,
    manifest: dict[str, Any],
    generated_text: str,
) -> dict[str, dict[str, Any]]:
    weights = gold["rubric"]["axes"]
    resolver = GoldAliasResolver(gold["canonical_nodes"])
    canonical_by_graph_id = _canonical_by_graph_node_id(graph.nodes, resolver)
    axes = {
        "lineage": _graph_lineage_axis(
            weight=weights["lineage"]["weight"],
            gold=gold,
            graph=graph,
            canonical_by_graph_id=canonical_by_graph_id,
        ),
        "entity_source": _graph_entity_axis(
            weight=weights["entity_source"]["weight"],
            gold=gold,
            canonical_by_graph_id=canonical_by_graph_id,
        ),
        "pending_questions": _pending_questions_axis(
            weight=weights["pending_questions"]["weight"],
            gold=gold,
            graph=graph,
        ),
        "business_usefulness": _business_axis(
            weight=weights["business_usefulness"]["weight"],
            generated_text=generated_text,
        ),
        "evidence_quality": _evidence_axis(
            weight=weights["evidence_quality"]["weight"],
            manifest=manifest,
        ),
        "artifact_hygiene": _artifact_axis(
            weight=weights["artifact_hygiene"]["weight"],
            manifest=manifest,
        ),
        "anti_contamination": _anti_contamination_axis(
            weight=weights["anti_contamination"]["weight"],
            manifest=manifest,
        ),
    }
    for axis in axes.values():
        axis["weighted_score"] = round(axis["score_0_5"] * axis["weight"], 2)
    return axes


def _score_datasource_axes(
    *,
    gold: dict[str, Any],
    graph: GraphSnapshot,
    manifest: dict[str, Any],
    generated_text: str,
    orchestrator_gate: dict[str, Any],
    freshness: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    weights = gold["rubric"]["axes"]
    resolver = GoldAliasResolver(gold["canonical_nodes"])
    canonical_by_graph_id = _canonical_by_graph_node_id(graph.nodes, resolver)
    graph_axis = _graph_lineage_axis(
        weight=weights["graph_mapping"]["weight"],
        gold=gold,
        graph=graph,
        canonical_by_graph_id=canonical_by_graph_id,
    )
    axes = {
        "orchestrator_entry": _datasource_orchestrator_axis(
            weight=weights["orchestrator_entry"]["weight"], gate=orchestrator_gate
        ),
        "source_documentation": _datasource_generated_axis(
            weight=weights["source_documentation"]["weight"],
            manifest=manifest,
            generated_text=generated_text,
        ),
        "ownership_and_freshness": _datasource_freshness_axis(
            weight=weights["ownership_and_freshness"]["weight"], freshness=freshness
        ),
        "graph_mapping": graph_axis,
        "artifact_hygiene": _artifact_axis(
            weight=weights["artifact_hygiene"]["weight"], manifest=manifest
        ),
        "anti_contamination": _anti_contamination_axis(
            weight=weights["anti_contamination"]["weight"], manifest=manifest
        ),
    }
    for axis in axes.values():
        axis["weighted_score"] = round(axis["score_0_5"] * axis["weight"], 2)
    return axes


def _datasource_scoring_contract(
    *,
    gold: dict[str, Any],
    graph: GraphSnapshot,
    manifest: dict[str, Any],
    generated_text: str,
    evidence: Path,
) -> dict[str, Any]:
    trace_summary = _trace_summary(evidence, manifest)
    freshness = _freshness_report(manifest)
    orchestrator_gate = _orchestrator_gate(trace_summary)
    axes = _score_datasource_axes(
        gold=gold,
        graph=graph,
        manifest=manifest,
        generated_text=generated_text,
        orchestrator_gate=orchestrator_gate,
        freshness=freshness,
    )
    trace_events = _trace_events(evidence, manifest)
    pathway_compliance = _pathway_compliance(gold, trace_events)
    tool_quality = _tool_quality(trace_events)
    conversation_axes = _conversation_axes(pathway_compliance, tool_quality)
    overall = round(sum(axis["score_0_5"] * axis["weight"] for axis in axes.values()), 2)
    blocking_failures = _datasource_blocking_failures(
        orchestrator_gate, trace_summary, manifest=manifest, freshness=freshness
    )
    return {
        "axes": axes,
        "overall_score_0_5": overall,
        "status": _datasource_status(overall, blocking_failures, freshness),
        "trace_summary": trace_summary,
        "freshness": freshness,
        "orchestrator_gate": orchestrator_gate,
        "blocking_failures": blocking_failures,
        "pathway_compliance": pathway_compliance,
        "tool_quality": tool_quality,
        "conversation_axes": conversation_axes,
    }


def _score_status(overall: float) -> str:
    if overall >= 4:
        return "pass"
    if overall >= 3:
        return "review"
    return "fail"


def _datasource_blocking_failures(
    orchestrator_gate: dict[str, Any],
    trace_summary: dict[str, Any],
    *,
    manifest: dict[str, Any],
    freshness: dict[str, Any],
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    if orchestrator_gate.get("status") == "blocked":
        failures.append(
            {
                "code": orchestrator_gate.get("code", "orchestrator_bypass"),
                "message": orchestrator_gate.get("reason", "Datasource orchestrator gate failed"),
                "first_brainds_agent": trace_summary.get("first_brainds_agent"),
            }
        )
    text_exchange = trace_summary.get("text_exchange", {})
    if text_exchange.get("status") != "verified":
        failures.append(
            {
                "code": "missing_text_exchange",
                "message": text_exchange.get(
                    "reason", "Missing verifiable user/orchestrator text exchange"
                ),
                "first_brainds_agent": trace_summary.get("first_brainds_agent"),
            }
        )
    subagent_action = trace_summary.get("subagent_action", {})
    if subagent_action.get("status") != "verified":
        failures.append(
            {
                "code": "missing_subagent_action",
                "message": subagent_action.get(
                    "reason", "Missing subagent identity with attributable action or tool call"
                ),
                "first_brainds_agent": trace_summary.get("first_brainds_agent"),
            }
        )
    required_generated = manifest.get("required_generated_file", {})
    required_generated_status = (
        required_generated.get("status") if isinstance(required_generated, dict) else None
    )
    if required_generated_status is not None and required_generated_status not in {
        "captured",
        "not_required",
    }:
        failures.append(
            {
                "code": "missing_generated_source_documentation",
                "message": required_generated.get(
                    "reason",
                    "Missing required generated/source_documentation.md proof artifact",
                ),
                "path": required_generated.get("path", "generated/source_documentation.md"),
            }
        )
    workspace_open_gate = manifest.get("workspace_open_gate", {})
    if isinstance(workspace_open_gate, dict) and workspace_open_gate.get("status") == "missing":
        failures.append(
            {
                "code": "missing_workspace_open",
                "message": workspace_open_gate.get(
                    "reason", "Missing brain_ds_open_workspace before graph writes"
                ),
            }
        )
    elif isinstance(workspace_open_gate, dict) and workspace_open_gate.get("status") == "failed":
        code = "workspace_open_failed"
        if workspace_open_gate.get("open_status") in {None, "completed", "success", "ok"}:
            code = "write_before_workspace_open"
        failures.append(
            {
                "code": code,
                "message": workspace_open_gate.get(
                    "reason", "Graph write occurred before brain_ds_open_workspace"
                ),
                "open_event_ref": workspace_open_gate.get("open_event_ref"),
                "first_graph_write_ref": workspace_open_gate.get("first_graph_write_ref"),
            }
        )
    elif (
        isinstance(workspace_open_gate, dict)
        and workspace_open_gate.get("status") == "wrong_subject"
    ):
        failures.append(
            {
                "code": "wrong_workspace_open",
                "message": workspace_open_gate.get(
                    "reason",
                    "brain_ds_open_workspace opened a workspace outside the subject under review",
                ),
                "opened_path": workspace_open_gate.get("opened_path"),
                "expected_subject_path": workspace_open_gate.get("expected_subject_path"),
            }
        )
    subject_local_graph = freshness.get("subject_local_graph", {})
    if isinstance(subject_local_graph, dict) and subject_local_graph.get("status") == "stale":
        failures.append(
            {
                "code": "stale_graph_proof",
                "message": subject_local_graph.get(
                    "reason", "Subject-local graph proof is stale or unrelated"
                ),
            }
        )
    elif isinstance(subject_local_graph, dict) and subject_local_graph.get("status") == "failed":
        failures.append(
            {
                "code": "non_subject_local_graph_proof",
                "message": subject_local_graph.get(
                    "reason", "Datasource documentation requires subject-local graph proof"
                ),
            }
        )
    return failures


def _datasource_status(
    overall: float, blocking_failures: list[dict[str, Any]], freshness: dict[str, Any]
) -> str:
    if blocking_failures:
        return "fail"
    status = _score_status(overall)
    if freshness.get("status") == "degraded" and status == "pass":
        return "review"
    return status


def _datasource_orchestrator_axis(*, weight: float, gate: dict[str, Any]) -> dict[str, Any]:
    return {
        "score_0_5": 5 if gate["status"] == "passed" else 0,
        "weight": weight,
        "rationale": gate["reason"],
        "evidence_refs": ["trace/session_trace.json"],
        "missing_expected": [] if gate["status"] == "passed" else ["brainds-orchestrator first"],
    }


def _datasource_generated_axis(
    *, weight: float, manifest: dict[str, Any], generated_text: str
) -> dict[str, Any]:
    concepts = {
        "owner": ("owner", "ownership", "accountable"),
        "freshness": ("freshness", "fresh", "updated", "cadence"),
        "data_gap_or_quality_caveat": (
            "data gaps",
            "data gap",
            "gap",
            "caveat",
            "caveats",
            "data quality",
            "quality caveat",
        ),
    }
    missing_terms = [
        concept
        for concept, vocabulary in concepts.items()
        if not any(term in generated_text for term in vocabulary)
    ]
    missing_artifacts = (
        [] if manifest.get("captured", {}).get("generated_outputs") else ["generated_outputs"]
    )
    missing = [*missing_artifacts, *missing_terms]
    return {
        "score_0_5": 5 if not missing else max(0, 5 - len(missing)),
        "weight": weight,
        "rationale": "Datasource documentation output includes required source metadata signals.",
        "evidence_refs": manifest.get("captured", {}).get("generated_outputs", []),
        "missing_expected": missing,
    }


def _datasource_freshness_axis(*, weight: float, freshness: dict[str, Any]) -> dict[str, Any]:
    failing = list(freshness.get("failing_checks", []))
    return {
        "score_0_5": 5 if freshness.get("status") == "passed" else max(0, 5 - len(failing)),
        "weight": weight,
        "rationale": "Freshness checks validate subject-local graph, generated outputs, trace, and schema versions.",
        "evidence_refs": ["manifest.json"],
        "missing_expected": failing,
    }


def _trace_summary(evidence: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    events = _trace_events(evidence, manifest)
    first_brainds = None
    first_root_brainds = None
    roles: list[str] = []
    undelegated_subagent_contacts: list[dict[str, str | None]] = []
    wrong_or_fallback_agent: str | None = None
    for event in events:
        role = event.get("role")
        if isinstance(role, str):
            roles.append(role)
        agent = event.get("agent_name")
        if first_brainds is None and isinstance(agent, str) and _is_brainds_agent(agent):
            first_brainds = agent
        if (
            wrong_or_fallback_agent is None
            and isinstance(agent, str)
            and _is_wrong_or_fallback_agent(agent, role)
        ):
            wrong_or_fallback_agent = agent
        delegated_by = event.get("delegated_by")
        is_orchestrator_delegated = _is_orchestrator_agent(
            delegated_by if isinstance(delegated_by, str) else None
        )
        if (
            first_root_brainds is None
            and isinstance(agent, str)
            and _is_brainds_agent(agent)
            and not (role == "subagent" and is_orchestrator_delegated)
        ):
            first_root_brainds = agent
        if (
            role == "subagent"
            and isinstance(agent, str)
            and _is_brainds_agent(agent)
            and not is_orchestrator_delegated
        ):
            undelegated_subagent_contacts.append(
                {
                    "agent_name": agent,
                    "delegated_by": delegated_by if isinstance(delegated_by, str) else None,
                }
            )
    return {
        "trace_present": bool(events),
        "event_count": len(events),
        "roles": roles,
        "first_brainds_agent": first_brainds,
        "first_root_brainds_agent": first_root_brainds,
        "wrong_or_fallback_agent": wrong_or_fallback_agent,
        "undelegated_subagent_contacts": undelegated_subagent_contacts,
        "text_exchange": _text_exchange_summary(events),
        "subagent_action": _subagent_action_summary(events),
    }


def _trace_events(evidence: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    trace_ref = manifest.get("captured", {}).get("session_trace") or manifest.get("trace", {}).get(
        "path"
    )
    events: list[dict[str, Any]] = []
    if isinstance(trace_ref, str) and (evidence / trace_ref).is_file():
        payload = _load_json(evidence / trace_ref)
        raw_events = payload.get("events", [])
        if isinstance(raw_events, list):
            events = [event for event in raw_events if isinstance(event, dict)]
    return events


def _pathway_compliance(gold: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = [str(item["id"]) for item in gold.get("pathway_milestones", [])]
    observed, inferred = _observed_milestones(events)
    completed: list[str] = []
    for expected, actual in zip(ordered, observed, strict=False):
        if expected != actual:
            break
        completed.append(expected)
    observed_set = set(observed)
    missing = [milestone for milestone in ordered if milestone not in observed_set]
    out_of_order = _out_of_order_milestones(ordered, observed)
    off_path_event_count = sum(
        1
        for event in events
        if event.get("role") not in {"user", "system"} and not event.get("pathway_milestone")
    )
    return {
        "ordered_milestones": ordered,
        "observed_milestones": observed,
        "inferred_milestones": inferred,
        "completed_milestones": completed,
        "missing_milestones": missing,
        "out_of_order_milestones": out_of_order,
        "off_path_event_count": off_path_event_count,
        "progression_ratio": round(len(completed) / len(ordered), 2) if ordered else 0,
    }


def _observed_milestones(events: list[dict[str, Any]]) -> tuple[list[str], list[dict[str, str]]]:
    observed: list[str] = []
    seen: set[str] = set()
    inferred: list[dict[str, str]] = []
    for event in events:
        milestone = event.get("pathway_milestone")
        explicit = isinstance(milestone, str) and bool(milestone)
        if not explicit:
            milestone = _infer_milestone(event)
        if isinstance(milestone, str) and milestone and milestone not in seen:
            observed.append(milestone)
            seen.add(milestone)
            if not explicit:
                inferred.append({"milestone": milestone, "evidence_ref": _event_evidence_ref(event)})
    return observed, inferred


def _infer_milestone(event: dict[str, Any]) -> str | None:
    role = str(event.get("role") or "").casefold()
    action = str(event.get("action") or "").casefold()
    agent = str(event.get("agent_name") or "").casefold()
    tool = str(event.get("tool_name") or "").casefold()
    target = str(event.get("target") or "").casefold()
    if role == "orchestrator" and _is_orchestrator_agent(agent):
        return "orchestrator_entry"
    if "source-explorer" in agent or tool in {"brain_ds_explore_source", "brain_ds.explore_source"}:
        return "explore_source"
    if "source_documentation" in target or tool in {"write", "edit"}:
        return "document_source"
    if tool.startswith("brain_ds_") and any(
        term in tool for term in ("add_edge", "update_node", "create_graph", "insert_pending_question")
    ):
        return "map_to_graph"
    if "graph-mapper" in agent or (action == "delegated_task_result" and "graph" in target):
        return "map_to_graph"
    return None


def _event_evidence_ref(event: dict[str, Any]) -> str:
    source = str(event.get("source_path") or "session_trace.json")
    label = str(event.get("tool_name") or event.get("agent_name") or event.get("action") or "event")
    return f"trace:{label}:{source}"


def _out_of_order_milestones(ordered: list[str], observed: list[str]) -> list[str]:
    ordinal = {milestone: index for index, milestone in enumerate(ordered)}
    highest_seen = -1
    out_of_order: list[str] = []
    for milestone in observed:
        index = ordinal.get(milestone)
        if index is None:
            continue
        if index < highest_seen:
            out_of_order.append(milestone)
        else:
            highest_seen = index
    return out_of_order


def _tool_quality(events: list[dict[str, Any]]) -> dict[str, Any]:
    calls = [
        event
        for event in events
        if event.get("role") == "tool" and event.get("action") == "tool_call"
    ]
    responses = [
        event
        for event in events
        if event.get("role") == "tool" and event.get("action") == "tool_response"
    ]
    same_event_responses = [event for event in calls if _tool_call_has_same_event_response(event)]
    all_responses = [*responses, *same_event_responses]
    irrelevant = [
        str(event.get("tool_name")) for event in calls if not _tool_call_is_relevant(event)
    ]
    unusable = [event for event in all_responses if _tool_response_is_unusable(event)]
    successful = [event for event in all_responses if _tool_response_is_successful(event)]
    confusion = len(irrelevant) + len(unusable)
    payload = {
        "tool_call_count": len(calls),
        "tool_response_count": len(all_responses),
        "successful_response_count": len(successful),
        "relevant_tool_call_count": len(calls) - len(irrelevant),
        "irrelevant_tool_calls": irrelevant,
        "unusable_output_count": len(unusable),
        "confusion_count": confusion,
    }
    bash_commands = [str(event.get("tool_command")) for event in calls if event.get("tool_command")]
    if bash_commands:
        payload["bash_commands"] = bash_commands
    return payload


def _tool_call_has_same_event_response(event: dict[str, Any]) -> bool:
    status = str(event.get("tool_status") or "").casefold()
    return status in {"completed", "success", "ok"} and bool(event.get("tool_output_present"))


def _tool_call_is_relevant(event: dict[str, Any]) -> bool:
    tool_name = str(event.get("tool_name") or "").casefold()
    return bool(event.get("pathway_milestone")) or "brain_ds" in tool_name or "brainds" in tool_name


def _tool_response_is_successful(event: dict[str, Any]) -> bool:
    if _tool_call_has_same_event_response(event):
        return True
    marker = _tool_response_marker(event)
    return "success" in marker and not _tool_response_is_unusable(event)


def _tool_response_is_unusable(event: dict[str, Any]) -> bool:
    status = str(event.get("tool_status") or "").casefold()
    if status in {"error", "failed", "failure"}:
        return True
    marker = _tool_response_marker(event)
    return any(term in marker for term in ("error", "failed", "failure", "unusable", "empty"))


def _tool_response_marker(event: dict[str, Any]) -> str:
    return " ".join(
        str(event.get(key) or "") for key in ("content_ref", "target", "tool_name")
    ).casefold()


def _conversation_axes(
    pathway_compliance: dict[str, Any], tool_quality: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    off_path_penalty = min(2, int(pathway_compliance["off_path_event_count"]))
    pathway_score = max(
        0,
        round(
            5 * float(pathway_compliance["progression_ratio"])
            - len(pathway_compliance["out_of_order_milestones"])
            - off_path_penalty
        ),
    )
    call_count = int(tool_quality["tool_call_count"])
    success_ratio = int(tool_quality["successful_response_count"]) / call_count if call_count else 0
    tool_score = min(5, max(0, round(5 * success_ratio - int(tool_quality["confusion_count"]))))
    return {
        "pathway_progression": {
            "score_0_5": pathway_score,
            "rationale": "Ordered datasource milestones advance without off-path loops.",
            "evidence_refs": ["trace/session_trace.json"],
        },
        "tool_quality": {
            "score_0_5": tool_score,
            "rationale": "Tool calls are relevant and responses are successful and usable.",
            "evidence_refs": ["trace/session_trace.json"],
        },
    }


def _orchestrator_gate(trace_summary: dict[str, Any]) -> dict[str, Any]:
    first = trace_summary.get("first_root_brainds_agent") or trace_summary.get(
        "first_brainds_agent"
    )
    fallback = trace_summary.get("wrong_or_fallback_agent")
    if isinstance(fallback, str):
        return {
            "status": "blocked",
            "code": "wrong_agent",
            "reason": f"Wrong or fallback OpenCode agent '{fallback}' was used instead of brain-ds-orchestrator",
        }
    undelegated = trace_summary.get("undelegated_subagent_contacts") or []
    if undelegated:
        agents = ", ".join(
            str(item.get("agent_name")) for item in undelegated if isinstance(item, dict)
        )
        return {
            "status": "blocked",
            "reason": f"BrainDS subagent contact was not delegated by brainds-orchestrator: {agents}",
            "undelegated_subagent_contacts": undelegated,
        }
    if _is_orchestrator_agent(first if isinstance(first, str) else None):
        return {
            "status": "passed",
            "reason": "First BrainDS agent contacted was brain-ds-orchestrator",
        }
    if first is None:
        return {"status": "blocked", "reason": "No BrainDS agent trace event was captured"}
    return {
        "status": "blocked",
        "reason": f"First BrainDS agent was {first}, not brainds-orchestrator",
    }


def _text_exchange_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    user_events = [
        event for event in events if event.get("role") == "user" and event.get("content_ref")
    ]
    assistant_events = [
        event
        for event in events
        if event.get("role") == "orchestrator"
        and _is_orchestrator_agent(str(event.get("agent_name") or ""))
        and event.get("content_ref")
    ]
    if user_events and assistant_events:
        return {
            "status": "verified",
            "user_text_refs": [str(event["content_ref"]) for event in user_events],
            "orchestrator_text_refs": [str(event["content_ref"]) for event in assistant_events],
        }
    return {
        "status": "missing",
        "reason": "Requires at least one user text event and one brain-ds-orchestrator text event",
        "user_text_count": len(user_events),
        "orchestrator_text_count": len(assistant_events),
    }


def _subagent_action_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    subagent_names = [
        str(event.get("agent_name"))
        for event in events
        if event.get("role") == "subagent" and _is_brainds_agent(str(event.get("agent_name") or ""))
    ]
    action_events = [
        event
        for event in events
        if event.get("role") == "subagent"
        and _is_brainds_agent(str(event.get("agent_name") or ""))
        and _is_subagent_produced_evidence(event)
    ]
    subagent_set = set(subagent_names)
    tool_events = [
        event
        for event in events
        if event.get("role") == "tool"
        and event.get("action") == "tool_call"
        and (
            str(event.get("agent_name") or "") in subagent_set
            or str(event.get("delegated_by") or "") in subagent_set
        )
    ]
    task_delegation_events = [
        event
        for event in events
        if event.get("role") == "tool"
        and event.get("action") in {"tool_call", "delegated_task_result"}
        and str(event.get("tool_name") or "") == "task"
        and _is_brainds_agent(str(event.get("target") or ""))
    ]
    subagent_names.extend(str(event.get("target")) for event in task_delegation_events)
    task_result_events = [
        event for event in task_delegation_events if event.get("action") == "delegated_task_result"
    ]
    all_tool_events = [
        event
        for event in events
        if event.get("role") == "tool" and event.get("action") == "tool_call"
    ]
    if subagent_names and (action_events or tool_events or task_result_events):
        return {
            "status": "verified",
            "subagents": sorted(set(subagent_names)),
            "action_count": len(action_events),
            "tool_call_count": len(tool_events),
            "task_result_count": len(task_result_events),
        }
    return {
        "status": "missing",
        "reason": "Requires a BrainDS subagent identity plus an attributable action or tool call",
        "subagents": sorted(set(subagent_names)),
        "action_count": len(action_events),
        "tool_call_count": len(all_tool_events),
    }


def _is_orchestrator_agent(agent: str | None) -> bool:
    return (agent or "").casefold() in {"brainds-orchestrator", "brain-ds-orchestrator"}


def _is_brainds_agent(agent: str | None) -> bool:
    normalized = (agent or "").casefold()
    return normalized.startswith("brainds-") or normalized.startswith("brain-ds-")


def _is_metadata_agent(agent: str | None) -> bool:
    return (agent or "").casefold() in {"title"}


def _is_wrong_or_fallback_agent(agent: str, role: Any) -> bool:
    normalized = agent.casefold()
    if normalized == "build":
        return True
    if _is_brainds_agent(agent) or _is_metadata_agent(agent):
        return False
    return role in {"orchestrator", "verifier", "subagent"}


def _is_subagent_work_action(action: Any) -> bool:
    normalized = str(action or "message").casefold()
    return normalized not in {"message", "session_created", "agent_stream"}


def _is_subagent_produced_evidence(event: dict[str, Any]) -> bool:
    action = str(event.get("action") or "message").casefold()
    if action in {"session_created", "agent_stream"}:
        return False
    return (
        bool(event.get("content_ref")) or action == "reasoning" or _is_subagent_work_action(action)
    )


def _freshness_report(manifest: dict[str, Any]) -> dict[str, Any]:
    checks = manifest.get("freshness_checks")
    if not isinstance(checks, dict):
        return {
            "status": "unknown",
            "report_schema_version": REPORT_SCHEMA_VERSION,
            "failing_checks": ["freshness_checks"],
        }
    failing = list(checks.get("failing_checks", []))
    if not failing:
        for name in ("subject_local_graph", "generated_outputs", "trace"):
            value = checks.get(name, {})
            if isinstance(value, dict) and value.get("status") in {"failed", "missing", "stale"}:
                failing.append(name)
    return {**checks, "report_schema_version": REPORT_SCHEMA_VERSION, "failing_checks": failing}


def _output_contract(manifest: dict[str, Any]) -> dict[str, Any]:
    lineage = _required_dict(manifest, "lineage")
    selected_path = _required_dict(manifest, "selected_path")
    comparability = _required_dict(manifest, "comparability")
    _validate_lineage(lineage)
    path_plan_version = manifest.get("path_plan_version")
    if not isinstance(path_plan_version, str) or not path_plan_version:
        raise ScoreReportError("Evidence manifest is missing path_plan_version")
    for field in (
        "path_id",
        "path_plan_version",
        "label",
        "scenario",
        "agents_or_tools",
        "required_evidence",
        "expected_artifacts",
        "scorer",
        "rubric_version",
        "output_contract",
        "status",
        "execute_in_first_slice",
    ):
        if field not in selected_path:
            raise ScoreReportError(f"Evidence manifest selected_path is missing {field}")
    if selected_path.get("path_plan_version") != path_plan_version:
        raise ScoreReportError("Evidence manifest selected_path path_plan_version mismatch")
    if comparability.get("status") not in {"comparable", "non_comparable"}:
        raise ScoreReportError("Evidence manifest comparability status is invalid")
    _validate_comparability(comparability, selected_path, lineage, path_plan_version)
    return {
        "lineage": lineage,
        "path_plan_version": path_plan_version,
        "selected_path": _normalize_path_entry(selected_path),
        "comparability": comparability,
    }


def _required_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ScoreReportError(f"Evidence manifest is missing {key}")
    return value


def _validate_lineage(lineage: dict[str, Any]) -> None:
    for field in _LINEAGE_REQUIRED_FIELDS:
        if field not in lineage:
            raise ScoreReportError(f"Evidence manifest lineage is missing {field}")
    if not isinstance(lineage.get("commit_sha"), str) or not lineage["commit_sha"]:
        raise ScoreReportError("Evidence manifest lineage.commit_sha is required")
    if not isinstance(lineage.get("captured_at_utc"), str) or not lineage["captured_at_utc"]:
        raise ScoreReportError("Evidence manifest lineage.captured_at_utc is required")
    if not isinstance(lineage.get("worktree_dirty"), bool) or not isinstance(
        lineage.get("untracked_files_present"), bool
    ):
        raise ScoreReportError("Evidence manifest lineage dirty flags must be booleans")
    diff_hash = lineage.get("git_diff_hash")
    if diff_hash is not None and (not isinstance(diff_hash, str) or not diff_hash):
        raise ScoreReportError("Evidence manifest lineage.git_diff_hash must be null or a string")
    try:
        validate_sdd_change(lineage.get("sdd_change"))
    except PathPlanError as exc:
        raise ScoreReportError(f"Evidence manifest lineage.{exc}") from exc


def _validate_comparability(
    comparability: dict[str, Any],
    selected_path: dict[str, Any],
    lineage: dict[str, Any],
    path_plan_version: str,
) -> None:
    if comparability.get("status") == "non_comparable":
        if not comparability.get("reason"):
            raise ScoreReportError("Evidence manifest non-comparable comparability requires reason")
        return
    key = comparability.get("key")
    if not isinstance(key, dict):
        raise ScoreReportError("Evidence manifest comparable comparability requires key")
    for field in _COMPARABILITY_KEY_REQUIRED_FIELDS:
        if field not in key:
            raise ScoreReportError(f"Evidence manifest comparability.key is missing {field}")
    try:
        validate_sdd_change(key.get("sdd_change"))
    except PathPlanError as exc:
        raise ScoreReportError(f"Evidence manifest comparability.key.{exc}") from exc
    for field in ("commit_sha", "worktree_dirty", "git_diff_hash", "untracked_files_present", "sdd_change"):
        if key.get(field) != lineage.get(field):
            raise ScoreReportError(f"Evidence manifest comparability.key {field} does not match lineage")
    if key.get("path_id") != selected_path.get("path_id"):
        raise ScoreReportError("Evidence manifest comparability.key path_id does not match selected_path")
    if key.get("path_plan_version") != path_plan_version:
        raise ScoreReportError("Evidence manifest comparability.key path_plan_version mismatch")
    if key.get("scenario") != selected_path.get("scenario"):
        raise ScoreReportError("Evidence manifest comparability.key scenario does not match selected_path")


def _normalize_path_entry(entry: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(entry)
    for field in ("agents_or_tools", "required_evidence", "expected_artifacts"):
        value = normalized.get(field)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ScoreReportError(
                f"Evidence manifest selected_path.{field} must be a list of strings"
            )
        normalized[field] = list(value)
    return normalized


def _interpretation_lanes(
    *, deterministic: dict[str, Any], freshness: dict[str, Any], selected_path: dict[str, Any]
) -> list[dict[str, Any]]:
    status = str(deterministic.get("status", "fail"))
    artifact_status = "pass" if status == "pass" else "warn" if status == "review" else "fail"
    flow_status = (
        "not_applicable"
        if selected_path.get("scenario") != "datasource_documentation"
        else artifact_status
    )
    model_status = "not_applicable"
    if freshness.get("status") == "degraded" and artifact_status == "pass":
        artifact_status = "warn"
    return [
        build_interpretation_lane(
            lane="artifact_quality",
            status=artifact_status,
            evidence_refs=["manifest.json", *selected_path.get("expected_artifacts", [])],
        ),
        build_interpretation_lane(
            lane="flow_tool_delegation_quality",
            status=flow_status,
            evidence_refs=["trace/session_trace.json", "manifest.json"],
        ),
        build_interpretation_lane(
            lane="model_capability_context",
            status=model_status,
            evidence_refs=["manifest.json"],
        ),
    ]


def _canonical_by_graph_node_id(
    nodes: list[dict[str, Any]], resolver: GoldAliasResolver
) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for node in nodes:
        canonical = resolver.resolve(str(node["type"]), str(node["label"]))
        if canonical is None:
            canonical = resolver.resolve(str(node["type"]), str(node["id"]))
        if canonical is None:
            for value in _flatten_details_values(node.get("details", {})):
                canonical = resolver.resolve(str(node["type"]), value)
                if canonical is not None:
                    break
        if canonical is not None:
            resolved[str(node["id"])] = canonical
    return resolved


def _flatten_details_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        values: list[str] = []
        for item in value.values():
            values.extend(_flatten_details_values(item))
        return values
    if isinstance(value, list):
        values = []
        for item in value:
            values.extend(_flatten_details_values(item))
        return values
    return []


def _graph_lineage_axis(
    *,
    weight: float,
    gold: dict[str, Any],
    graph: GraphSnapshot,
    canonical_by_graph_id: dict[str, str],
) -> dict[str, Any]:
    matched: list[str] = []
    missing: list[str] = []
    for expected in gold["expected_edges"]:
        key = f"{expected['source']}->{expected['target']}"
        if _edge_expectation_matches(expected, graph.edges, canonical_by_graph_id):
            matched.append(key)
        else:
            missing.append(key)
    forbidden_matches = [
        f"{edge['source']}->{edge['target']}"
        for edge in gold["forbidden_edges"]
        if _edge_expectation_matches(edge, graph.edges, canonical_by_graph_id)
    ]
    matched_optional: list[str] = []
    missing_optional: list[str] = []
    for optional in gold["optional_edges"]:
        key = f"{optional['source']}->{optional['target']}"
        if _edge_expectation_matches(optional, graph.edges, canonical_by_graph_id):
            matched_optional.append(key)
        else:
            missing_optional.append(key)
    expected_count = len(gold["expected_edges"])
    base = 5 * len(matched) / expected_count if expected_count else 0
    penalty = len(forbidden_matches)
    score = max(0, round(base - penalty))
    return {
        "score_0_5": score,
        "weight": weight,
        "rationale": "Gold v2 expected graph edges were matched through gold-owned aliases and compatible labels.",
        "evidence_refs": ["graph/store.db", "gold_v2.json"],
        "missing_expected": missing,
        "matched_expected": matched,
        "missing_optional": missing_optional,
        "matched_optional": matched_optional,
        "forbidden_matches": forbidden_matches,
    }


def _edge_expectation_matches(
    expected: dict[str, Any],
    graph_edges: list[dict[str, Any]],
    canonical_by_graph_id: dict[str, str],
) -> bool:
    for edge in graph_edges:
        source = canonical_by_graph_id.get(str(edge["source"]))
        target = canonical_by_graph_id.get(str(edge["target"]))
        if source != expected["source"] or target != expected["target"]:
            continue
        if edge_labels_are_compatible(
            str(edge["label"]),
            list(expected["compatible_labels"]),
            direction=str(expected.get("direction", "source_to_target")),
        ):
            return True
    return False


def _graph_entity_axis(
    *, weight: float, gold: dict[str, Any], canonical_by_graph_id: dict[str, str]
) -> dict[str, Any]:
    expected = [node["id"] for node in gold["canonical_nodes"]]
    present = set(canonical_by_graph_id.values())
    missing = [canonical_id for canonical_id in expected if canonical_id not in present]
    score = round(5 * (len(expected) - len(missing)) / len(expected)) if expected else 0
    return {
        "score_0_5": score,
        "weight": weight,
        "rationale": "Gold v2 canonical entities/sources were resolved from graph nodes using type-scoped aliases.",
        "evidence_refs": ["graph/store.db", "gold_v2.json"],
        "missing_expected": missing,
    }


def _pending_questions_axis(
    *, weight: float, gold: dict[str, Any], graph: GraphSnapshot
) -> dict[str, Any]:
    matched: list[str] = []
    missing: list[str] = []
    question_text = "\n".join(
        " ".join(
            str(part or "")
            for part in (
                question.get("question_text"),
                question.get("gap_kind"),
                question.get("entity_type"),
            )
        )
        for question in graph.pending_questions
    )
    normalized_text = normalize_gold_alias(question_text)
    for theme in gold["pending_question_themes"]:
        hits = sum(
            1 for term in theme["expected_terms"] if normalize_gold_alias(term) in normalized_text
        )
        if hits >= int(theme.get("min_hits", 1)):
            matched.append(theme["id"])
        else:
            missing.append(theme["id"])
    expected_count = len(gold["pending_question_themes"])
    score = round(5 * len(matched) / expected_count) if expected_count else 0
    return {
        "score_0_5": score,
        "weight": weight,
        "rationale": "Pending graph questions were scored by expected gold v2 themes, not exact wording.",
        "evidence_refs": ["graph/store.db", "gold_v2.json"],
        "missing_expected": missing,
        "matched_expected": matched,
    }


def _evidence_hash(evidence: Path, manifest: dict[str, Any]) -> str:
    snapshot = manifest.get("immutable_evidence_snapshot", {})
    snapshot_hash = snapshot.get("evidence_hash")
    if snapshot.get("status") == "frozen" and isinstance(snapshot_hash, str) and snapshot_hash:
        return snapshot_hash
    digest = hashlib.sha256()
    for relative in [
        "manifest.json",
        manifest.get("captured", {}).get("graph_db"),
        *manifest.get("captured", {}).get("generated_outputs", []),
    ]:
        if not relative:
            continue
        path = evidence / str(relative)
        if path.is_file():
            digest.update(str(relative).encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _required_string(node: dict[str, Any], key: str, section: str) -> str:
    value = node.get(key)
    if not isinstance(value, str) or not value:
        raise ScoreReportError(
            f"Invalid gold v2 contract; {section}.{key} must be a non-empty string"
        )
    return value


def _validate_canonical_nodes(canonical_nodes: list[dict[str, Any]]) -> None:
    for node in canonical_nodes:
        _required_string(node, "id", "canonical_nodes")
        _required_string(node, "type", "canonical_nodes")
        _required_string(node, "label", "canonical_nodes")
        if not isinstance(node.get("aliases", []), list):
            raise ScoreReportError(
                "Invalid gold v2 contract; canonical_nodes.aliases must be a list"
            )


def _normalize_edge_label(label: str) -> str:
    return normalize_gold_alias(label).replace(" ", "_")


def _read_generated_text(evidence: Path, manifest: dict[str, Any]) -> str:
    chunks: list[str] = []
    for relative in manifest.get("captured", {}).get("generated_outputs", []):
        path = evidence / relative
        if path.is_file() and path.suffix.lower() in {".md", ".json", ".txt"}:
            chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks).lower()


def _evidence_axis(*, weight: float, manifest: dict[str, Any]) -> dict[str, Any]:
    captured = manifest.get("captured", {})
    expected = ["graph_db", "generated_outputs", "git_diff"]
    missing = [name for name in expected if name not in captured]
    minimum_ok = manifest.get("minimum_evidence", {}).get("status") == "accepted"
    score = 5 if not missing and minimum_ok else max(0, 3 - len(missing))
    return {
        "score_0_5": score,
        "weight": weight,
        "rationale": "Evidence bundle includes graph, generated outputs, and git diff when available.",
        "evidence_refs": ["manifest.json"],
        "missing_expected": missing,
    }


def _business_axis(*, weight: float, generated_text: str) -> dict[str, Any]:
    expected = ["next actions", "assumptions", "data gaps", "source ownership", "kpi definitions"]
    missing = [term for term in expected if term not in generated_text]
    score = round(5 * (len(expected) - len(missing)) / len(expected))
    return {
        "score_0_5": score,
        "weight": weight,
        "rationale": "Business diagnosis was checked for actionable guidance and explicit assumptions/gaps.",
        "evidence_refs": ["generated_outputs"],
        "missing_expected": missing,
    }


def _artifact_axis(*, weight: float, manifest: dict[str, Any]) -> dict[str, Any]:
    omissions = manifest.get("omissions", [])
    missing = [item.get("artifact", "unknown") for item in omissions]
    score = 5 if not missing else max(0, 5 - len(missing))
    return {
        "score_0_5": score,
        "weight": weight,
        "rationale": "Captured artifact set was checked for omissions that affect repeatable review.",
        "evidence_refs": ["manifest.json"],
        "missing_expected": missing,
    }


def _anti_contamination_axis(*, weight: float, manifest: dict[str, Any]) -> dict[str, Any]:
    anti = manifest.get("anti_contamination", {})
    findings = anti.get("findings", [])
    score = 5 if anti.get("status") == "passed" and not findings else 0
    return {
        "score_0_5": score,
        "weight": weight,
        "rationale": "Subject-visible contamination findings must be absent for a valid blind score.",
        "evidence_refs": ["manifest.json"],
        "missing_expected": findings,
    }


def _comparable_metadata(manifest: dict[str, Any], rubric: dict[str, Any]) -> dict[str, Any]:
    metadata = manifest.get("run_metadata", {})
    model = metadata.get("model") or metadata.get("wrapper_model") or "unknown"
    return {
        "prompt_version": metadata.get("prompt_version", "unknown"),
        "fixture_version": metadata.get("fixture_version", "unknown"),
        "rubric_version": rubric.get("version", "unknown"),
        "run_timestamp_utc": manifest.get("created_at_utc", "unknown"),
        "model_provider": metadata.get("model_provider", "unknown"),
        "model": model,
        "manual_deviations": metadata.get("manual_deviations", []),
    }


def _render_markdown(report: dict[str, Any]) -> str:
    deterministic = report.get("deterministic", {})
    axes = deterministic.get("axes", report["axes"])
    lines = [
        f"# Blind Agentic Eval Report: {report['run_id']}",
        "",
        f"Scenario: `{report['scenario']}`",
        f"Deterministic score: **{deterministic.get('overall_score_0_5', report['overall_score_0_5'])} / 5**",
        f"Deterministic status: `{deterministic.get('status', 'unknown')}`",
        f"Evidence hash: `{report['evidence_hash']}`",
        "",
        "## Deterministic Lane (authoritative)",
        "",
        "| Axis | Score | Weight | Weighted | Missing expected | Optional evidence |",
        "|------|-------|--------|----------|------------------|-------------------|",
    ]
    for name, axis in axes.items():
        missing = ", ".join(str(item) for item in axis["missing_expected"]) or "None"
        optional = ", ".join(str(item) for item in axis.get("matched_optional", [])) or "None"
        lines.append(
            f"| {name} | {axis['score_0_5']} | {axis['weight']} | "
            f"{axis['weighted_score']} | {missing} | {optional} |"
        )
    if report.get("pathway_compliance"):
        pathway = report["pathway_compliance"]
        lines.extend(
            [
                "",
                "## Pathway Compliance",
                "",
                f"- Completed milestones: `{', '.join(pathway['completed_milestones']) or 'none'}`",
                f"- Missing milestones: `{', '.join(pathway['missing_milestones']) or 'none'}`",
                f"- Out-of-order milestones: `{', '.join(pathway['out_of_order_milestones']) or 'none'}`",
                f"- Off-path events: `{pathway['off_path_event_count']}`",
            ]
        )
    if report.get("tool_quality"):
        tool_quality = report["tool_quality"]
        lines.extend(
            [
                "",
                "## Tool Quality",
                "",
                f"- Tool calls: `{tool_quality['tool_call_count']}`",
                f"- Tool responses: `{tool_quality['tool_response_count']}`",
                f"- Successful responses: `{tool_quality['successful_response_count']}`",
                f"- Irrelevant calls: `{', '.join(tool_quality['irrelevant_tool_calls']) or 'none'}`",
                f"- Unusable outputs: `{tool_quality['unusable_output_count']}`",
                f"- Confusion count: `{tool_quality['confusion_count']}`",
            ]
        )
    advisory = report.get("advisory_judge")
    lines.extend(["", "## Advisory Judge (non-blocking)", ""])
    if advisory is None:
        lines.append("Manual judge verdict: `absent`")
    else:
        lines.extend(
            [
                f"Manual judge verdict: `{advisory['verdict']}`",
                f"Judge model: `{advisory['judge_model']}`",
                f"Rationale: {advisory['rationale']}",
            ]
        )
    disagreements = report.get("disagreements", [])
    lines.extend(["", "## Disagreement Notes", ""])
    if not disagreements:
        lines.append("None.")
    else:
        for item in disagreements:
            if isinstance(item, dict):
                axis = item.get("axis", "unknown")
                deterministic_note = item.get("deterministic", "not provided")
                advisory_note = item.get("advisory", "not provided")
                lines.append(
                    f"- `{axis}`: deterministic `{deterministic_note}` vs advisory `{advisory_note}`"
                )
            else:
                lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Comparable Rerun Metadata",
            "",
            f"- Prompt version: `{report['comparable_rerun_metadata']['prompt_version']}`",
            f"- Fixture version: `{report['comparable_rerun_metadata']['fixture_version']}`",
            f"- Rubric version: `{report['comparable_rerun_metadata']['rubric_version']}`",
            f"- Model provider: `{report['comparable_rerun_metadata']['model_provider']}`",
            f"- Model: `{report['comparable_rerun_metadata']['model']}`",
            "",
            "## Anti-contamination",
            "",
            f"Status: `{report['anti_contamination']['status']}`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Score blind agentic eval evidence offline.")
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--graph-id")
    parser.add_argument("--judge-response", type=Path)
    parser.add_argument("--judge-packet-out", type=Path)
    args = parser.parse_args()

    report = score_evidence(
        scenario=args.scenario,
        evidence_path=args.evidence,
        out_path=args.out,
        repo_root=args.repo_root,
        graph_id=args.graph_id,
        judge_response_path=args.judge_response,
        judge_packet_out=args.judge_packet_out,
    )
    print(f"Score report: {args.out} ({report['overall_score_0_5']} / 5)")


if __name__ == "__main__":
    main()
