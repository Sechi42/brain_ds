from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from brain_ds.pipeline import PIPELINE_ARTIFACT_TYPES, assert_pipeline_artifact_trail_shape


PHASE_PATTERN = re.compile(
    r"^(elicit|recon|plan|source-exploration|source-docs|consolidation|dry-run|map|brd|setup|intake|verify|archive)-[a-z0-9_-]+-\d{4}-\d{2}-\d{2}\.md$"
)
PAYLOAD_PATTERN = re.compile(r"```json\n(.*?)\n```", re.DOTALL)
ALLOWED_RECOMMENDATIONS = {"elicit", "document", "proceed_with_gaps"}


@dataclass(frozen=True)
class Finding:
    severity: str
    message: str
    file: Path


def _critical(message: str, file: Path) -> Finding:
    return Finding(severity="CRITICAL", message=message, file=file)


def _load_payload(path: Path) -> tuple[dict | None, Finding | None]:
    text = path.read_text(encoding="utf-8")
    # Select the LAST fenced JSON block (positional selection — earlier example
    # blocks are ignored; the canonical payload must be the last one in the file).
    matches = list(PAYLOAD_PATTERN.finditer(text))
    if not matches:
        return None, _critical(f"{path.name} is missing a fenced JSON payload", path)
    match = matches[-1]
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        return None, _critical(f"{path.name} contains invalid JSON payload: {exc}", path)
    if not isinstance(payload, dict):
        return None, _critical(f"{path.name} payload must be a JSON object", path)
    return payload, None


def _check_documented_nodes(path: Path, payload: dict) -> list[Finding]:
    findings: list[Finding] = []
    for node in payload.get("documented_nodes", []):
        node_id = node.get("node_id", "<unknown-node>")
        sections = node.get("card_sections") or []
        if not sections:
            findings.append(_critical(f"{node_id} in {path.name} has no card_sections", path))
            continue
        for index, section in enumerate(sections):
            title = str(section.get("title", ""))
            content = str(section.get("content", ""))
            icon = str(section.get("icon", ""))
            order = section.get("order")
            is_brd = str(node.get("type")) == "Unknown" and str(node_id).startswith("brd-")
            if not title:
                findings.append(_critical(f"{node_id} in {path.name} has empty title at section {index}", path))
            if not content:
                findings.append(_critical(f"{node_id} in {path.name} has empty content at section {index}", path))
            if is_brd:
                if order != 0 or icon != "":
                    findings.append(
                        _critical(
                            f"{node_id} in {path.name} violates BRD carve-out (expected order 0 and empty icon)",
                            path,
                        )
                    )
            else:
                if not isinstance(order, int) or order < 1:
                    findings.append(_critical(f"{node_id} in {path.name} has invalid order {order!r}", path))
                if not icon:
                    findings.append(_critical(f"{node_id} in {path.name} has empty icon at section {index}", path))
    return findings


def _check_brd_payload(path: Path, payload: dict) -> list[Finding]:
    findings: list[Finding] = []
    graph_id = payload.get("graph_id")
    brd_node = payload.get("brd_node") or {}
    expected_node_id = f"brd-{graph_id}"
    sections = brd_node.get("card_sections") or []

    if brd_node.get("node_id") != expected_node_id:
        findings.append(_critical(f"{path.name} expected BRD node_id {expected_node_id}", path))
    if brd_node.get("label") != "BRD":
        findings.append(_critical(f"{path.name} BRD node label must be 'BRD'", path))
    if brd_node.get("type") != "Unknown":
        findings.append(_critical(f"{path.name} BRD node type must be 'Unknown'", path))
    if not sections:
        findings.append(_critical(f"{path.name} BRD node has no card_sections", path))
        return findings

    first = sections[0]
    if first.get("order") != 0 or first.get("icon") != "":
        findings.append(_critical(f"{path.name} BRD card_sections[0] must keep order 0 and icon ''", path))
    if first.get("title") != "Contenido":
        findings.append(_critical(f"{path.name} BRD card_sections[0] must keep title 'Contenido'", path))
    if "[[" not in str(payload.get("markdown", "")):
        findings.append(_critical(f"{path.name} BRD markdown must include wikilinks", path))
    return findings


def _check_verify_payload(path: Path, payload: dict) -> list[Finding]:
    """Validate a verify-stage artifact envelope.

    A clean verify artifact (gate == "PASS" and no findings) means archive is allowed.
    A blocked artifact (gate == "BLOCKED" or non-empty findings) raises CRITICAL.
    """
    findings: list[Finding] = []
    required_keys = ("artifact_type", "graph_id", "stage", "status", "critical_count", "findings", "gate")
    for key in required_keys:
        if key not in payload:
            findings.append(_critical(f"{path.name} verify payload is missing required key '{key}'", path))

    if findings:
        return findings

    gate = payload.get("gate")
    payload_findings = payload.get("findings", [])
    if gate == "BLOCKED" or payload_findings:
        findings.append(
            _critical(
                f"{path.name} verify gate is BLOCKED — archive is not allowed until all findings are resolved",
                path,
            )
        )
    return findings


def check_elicit_compliance(elicit_dir: Path) -> list[Finding]:
    findings: list[Finding] = []
    # Additive two-pass glob: flat level + one subdir level, deduplicated and sorted.
    # PHASE_PATTERN.match(path.name) provides subdir scoping for free at both levels.
    artifact_paths = sorted(
        set(elicit_dir.glob("*.md")) | set(elicit_dir.glob("*/*.md")),
        key=lambda p: str(p),
    )
    artifact_paths = [p for p in artifact_paths if p.is_file()]
    completeness_recorded = False
    has_non_verify_artifacts = False

    for path in artifact_paths:
        if not PHASE_PATTERN.match(path.name):
            # Non-phase files (README, scratch, notes) are silently ignored.
            # Only phase-named files are subject to the payload contract.
            continue

        payload, error = _load_payload(path)
        if error is not None:
            findings.append(error)
            continue
        assert payload is not None

        artifact_type = str(payload.get("artifact_type", ""))
        if artifact_type in PIPELINE_ARTIFACT_TYPES:
            try:
                assert_pipeline_artifact_trail_shape([path])
            except AssertionError as exc:
                findings.append(_critical(f"{path.name} fails pipeline deliverable shape: {exc}", path))
                continue

        if path.name.startswith("verify-"):
            findings.extend(_check_verify_payload(path, payload))
            # verify artifacts do not carry completeness_gate — skip completeness check for them
            continue

        has_non_verify_artifacts = True
        recommendation = payload.get("completeness_gate", {}).get("pre_mapping_recommendation")
        if recommendation in ALLOWED_RECOMMENDATIONS:
            completeness_recorded = True

        if path.name.startswith(("source-docs-", "map-")):
            findings.extend(_check_documented_nodes(path, payload))
        if path.name.startswith("brd-"):
            findings.extend(_check_brd_payload(path, payload))

    if has_non_verify_artifacts and not completeness_recorded:
        findings.append(
            _critical(
                "No assess_completeness recommendation was recorded in the dry-run artifacts",
                elicit_dir,
            )
        )
    return findings
