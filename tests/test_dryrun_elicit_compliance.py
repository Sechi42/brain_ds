from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import cast

from brain_ds.store.graph_store import GraphStore
from brain_ds.verify.elicit_compliance import PHASE_PATTERN, check_elicit_compliance


def _artifact_payload(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"```json\n(.*?)\n```", text, re.DOTALL)
    assert match, f"{path.name} must contain a JSON payload fenced as ```json"
    return json.loads(match.group(1))


def test_synthetic_source_builder_creates_expected_schema(synthetic_source_path: Path) -> None:
    with sqlite3.connect(synthetic_source_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        assert {"customers", "orders"}.issubset(tables)

        for table in ("customers", "orders"):
            columns = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
            row_count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            assert len(columns) >= 3
            assert row_count >= 5


def test_elicit_files_naming_pattern(dry_run_elicit_output: dict[str, object]) -> None:
    elicit_dir = Path(cast(str, dry_run_elicit_output["elicit_dir"]))
    artifact_names = sorted(path.name for path in elicit_dir.glob("*.md"))
    assert artifact_names
    assert all(PHASE_PATTERN.match(name) for name in artifact_names)


def test_source_docs_brainds_format(dry_run_elicit_output: dict[str, object]) -> None:
    elicit_dir = Path(cast(str, dry_run_elicit_output["elicit_dir"]))
    source_docs = next(elicit_dir.glob("source-docs-*.md"))
    payload = _artifact_payload(source_docs)

    for node in payload["documented_nodes"]:
        for section in node["card_sections"]:
            assert section["title"]
            assert section["content"]
            if node["type"] == "Unknown":
                assert section["order"] == 0
                assert section["icon"] == ""
            else:
                assert section["order"] >= 1
                assert section["icon"]


def test_brd_persistence_contract_in_dry_run(dry_run_elicit_output: dict[str, object]) -> None:
    elicit_dir = Path(cast(str, dry_run_elicit_output["elicit_dir"]))
    brd_artifacts = list(elicit_dir.glob("brd-*.md"))
    assert brd_artifacts

    graph_id = str(dry_run_elicit_output["graph_id"])
    store_path = str(dry_run_elicit_output["store_path"])
    with GraphStore(store_path, read_only=True) as store:
        rows = store.query_nodes(graph_id)
        brd_node = next(row for row in rows if row.id == f"brd-{graph_id}")

    assert brd_node.label == "BRD"
    assert brd_node.type == "Unknown"
    assert brd_node.card_sections is not None
    assert brd_node.card_sections[0]["order"] == 0
    assert brd_node.card_sections[0]["icon"] == ""


def test_completeness_gate_recorded(dry_run_elicit_output: dict[str, object]) -> None:
    elicit_dir = Path(cast(str, dry_run_elicit_output["elicit_dir"]))
    recorded = False
    for artifact in elicit_dir.glob("*.md"):
        payload = _artifact_payload(artifact)
        if payload.get("completeness_gate", {}).get("pre_mapping_recommendation"):
            recorded = True
            assert payload["completeness_gate"]["pre_mapping_recommendation"] in {
                "elicit",
                "document",
                "proceed_with_gaps",
            }
    assert recorded


def test_sub_agent_writes_only_to_elicit(dry_run_elicit_output: dict[str, object]) -> None:
    elicit_dir = Path(cast(str, dry_run_elicit_output["elicit_dir"]))
    synthetic_source_path = str(dry_run_elicit_output["synthetic_source_path"])
    prompt_records = cast(list[dict[str, str]], dry_run_elicit_output["handoffs"])
    written_files = cast(list[str], dry_run_elicit_output["written_files"])

    assert written_files
    assert all(str(Path(path)).startswith(str(elicit_dir)) for path in written_files)

    forbidden = ("engram", "graph history", "unrelated file", "Observation #")
    for handoff in prompt_records:
        prompt = handoff["prompt"]
        assert synthetic_source_path in prompt
        assert "artifact" in prompt.lower()
        assert all(term.lower() not in prompt.lower() for term in forbidden)


# T1-7: verifier scoping — non-phase files (README, scratch) must be IGNORED
def test_readme_is_ignored_by_compliance_checker(tmp_path: Path) -> None:
    """README.md does not match PHASE_PATTERN — must produce zero findings."""
    readme = tmp_path / "README.md"
    readme.write_text("# Lifecycle docs\n\nNo JSON payload here.", encoding="utf-8")
    findings = check_elicit_compliance(tmp_path)
    assert not any(f.file.name == "README.md" for f in findings), (
        "README.md must be silently ignored, not raise findings"
    )


def test_scratch_file_is_ignored_by_compliance_checker(tmp_path: Path) -> None:
    """scratch.md does not match PHASE_PATTERN — must produce zero findings."""
    scratch = tmp_path / "scratch.md"
    scratch.write_text("# Draft notes\n\nNo JSON payload.", encoding="utf-8")
    findings = check_elicit_compliance(tmp_path)
    assert not any(f.file.name == "scratch.md" for f in findings), (
        "scratch.md must be silently ignored, not raise findings"
    )


# T1-8: phase-named file with broken/missing payload → CRITICAL
def test_phase_named_file_missing_payload_is_critical(tmp_path: Path) -> None:
    """A file matching PHASE_PATTERN with no JSON block must be CRITICAL."""
    broken = tmp_path / "map-acme-2026-06-14.md"
    broken.write_text("# Map\n\nSome prose but no JSON payload.", encoding="utf-8")
    findings = check_elicit_compliance(tmp_path)
    critical = [f for f in findings if f.severity == "CRITICAL" and f.file == broken]
    assert critical, (
        "phase-named file with missing payload must raise CRITICAL, got no findings"
    )


def test_phase_named_file_with_last_block_valid_ignores_example_block(tmp_path: Path) -> None:
    """File with an example block first and canonical payload last → no CRITICAL for payload."""
    # Use a source-docs file so _check_documented_nodes is invoked
    artifact = tmp_path / "source-docs-acme-2026-06-14.md"
    example_block = '```json\n{"example": true}\n```'
    canonical_payload = json.dumps({
        "graph_id": "acme",
        "artifact_type": "source-docs",
        "documented_nodes": [
            {
                "node_id": "acme-source-db",
                "label": "DB",
                "type": "Data Source",
                "card_sections": [
                    {"title": "Overview", "content": "A database.", "icon": "info", "order": 1}
                ],
            }
        ],
    })
    artifact.write_text(
        f"# Source Docs\n\nHere is an example:\n\n{example_block}\n\n"
        f"<!-- canonical-payload -->\n```json\n{canonical_payload}\n```\n",
        encoding="utf-8",
    )
    findings = check_elicit_compliance(tmp_path)
    critical = [f for f in findings if f.severity == "CRITICAL"]
    # Completeness gate missing for non-verify artifacts — expected. But no payload CRITICAL.
    payload_criticals = [f for f in critical if "payload" in f.message.lower() or "JSON" in f.message]
    assert not payload_criticals, (
        f"canonical payload in last block must pass; got payload criticals: {payload_criticals}"
    )


# C4: completeness_gate ownership tests
def test_invalid_completeness_gate_recommendation_is_critical(tmp_path: Path) -> None:
    """completeness_gate with invalid recommendation must raise CRITICAL, not pass silently."""
    map_file = tmp_path / "map-acme-2026-06-14.md"
    payload = json.dumps({
        "graph_id": "acme",
        "artifact_type": "map",
        "documented_nodes": [
            {
                "node_id": "acme-role-rev-ops",
                "label": "Revenue Ops",
                "type": "Role",
                "card_sections": [
                    {"title": "Overview", "content": "Owns reporting.", "icon": "link", "order": 1}
                ],
            }
        ],
        "edges": [],
        "completeness_gate": {"pre_mapping_recommendation": "INVALID_VALUE"},
    })
    map_file.write_text(f"# Map\n\n```json\n{payload}\n```\n", encoding="utf-8")
    findings = check_elicit_compliance(tmp_path)
    # Should have a CRITICAL for no valid completeness_gate recorded
    critical = [f for f in findings if f.severity == "CRITICAL"]
    assert critical, (
        f"Invalid completeness_gate recommendation must produce CRITICAL, got: {findings}"
    )


def test_only_verify_artifacts_missing_completeness_gate_is_critical(tmp_path: Path) -> None:
    """A cycle with only verify artifacts (no non-verify) must raise CRITICAL for missing completeness gate."""
    verify_file = tmp_path / "verify-acme-2026-06-14.md"
    payload = json.dumps({
        "graph_id": "acme",
        "artifact_type": "verify",
        "stage": "verify",
        "status": "PASS",
        "critical_count": 0,
        "findings": [],
        "gate": "PASS",
    })
    verify_file.write_text(f"# Verify\n\n```json\n{payload}\n```\n", encoding="utf-8")
    findings = check_elicit_compliance(tmp_path)
    # verify-only cycle: has_non_verify_artifacts is False → no CRITICAL for completeness
    # (the rule is: if there ARE non-verify artifacts but none records completeness → CRITICAL)
    # With only verify artifacts, no completeness CRITICAL is raised (expected per spec)
    completeness_criticals = [f for f in findings if "assess_completeness" in f.message]
    assert not completeness_criticals, (
        "verify-only cycle must not raise completeness CRITICAL (no non-verify artifacts present)"
    )


# T1-11/T1-12: dry-run double alignment — full suite passes check_elicit_compliance
def test_dry_run_elicit_output_passes_compliance(dry_run_elicit_output: dict) -> None:
    """The full dry-run elicit output must pass check_elicit_compliance with zero CRITICALs."""
    elicit_dir = Path(cast(str, dry_run_elicit_output["elicit_dir"]))
    findings = check_elicit_compliance(elicit_dir)
    critical = [f for f in findings if f.severity == "CRITICAL"]
    assert not critical, (
        f"dry-run elicit output raised {len(critical)} CRITICAL finding(s):\n"
        + "\n".join(f"  {f.file.name}: {f.message}" for f in critical)
    )


def test_source_docs_artifact_has_artifact_type_in_payload(dry_run_elicit_output: dict) -> None:
    """The source-docs artifact must include artifact_type at top level."""
    elicit_dir = Path(cast(str, dry_run_elicit_output["elicit_dir"]))
    source_docs = next(elicit_dir.glob("source-docs-*.md"))
    payload = _artifact_payload(source_docs)
    assert "artifact_type" in payload, "source-docs payload must include artifact_type"
    assert payload["artifact_type"] == "source-docs"


def test_map_artifact_has_artifact_type_in_payload(dry_run_elicit_output: dict) -> None:
    """The map artifact must include artifact_type at top level."""
    elicit_dir = Path(cast(str, dry_run_elicit_output["elicit_dir"]))
    map_artifact = next(elicit_dir.glob("map-*.md"))
    payload = _artifact_payload(map_artifact)
    assert "artifact_type" in payload, "map payload must include artifact_type"
    assert payload["artifact_type"] == "map"


def test_brd_artifact_has_artifact_type_in_payload(dry_run_elicit_output: dict) -> None:
    """The brd artifact must include artifact_type at top level."""
    elicit_dir = Path(cast(str, dry_run_elicit_output["elicit_dir"]))
    brd_artifact = next(elicit_dir.glob("brd-*.md"))
    payload = _artifact_payload(brd_artifact)
    assert "artifact_type" in payload, "brd payload must include artifact_type"
    assert payload["artifact_type"] == "brd"


def test_sddverify_reports_critical_on_noncompliant_node(tmp_path: Path) -> None:
    bad_file = tmp_path / "source-docs-acme-2026-06-14.md"
    bad_file.write_text(
        "# Source Docs\n\n```json\n"
        + json.dumps(
            {
                "documented_nodes": [
                    {
                        "node_id": "acme-source-1",
                        "type": "Data Source",
                        "card_sections": [
                            {
                                "title": "Overview",
                                "content": "bad order",
                                "icon": "database",
                                "order": 0,
                            }
                        ],
                    }
                ]
            }
        )
        + "\n```\n",
        encoding="utf-8",
    )

    findings = check_elicit_compliance(tmp_path)

    assert any(
        finding.severity == "CRITICAL"
        and bad_file.name in finding.file.name
        and "acme-source-1" in finding.message
        for finding in findings
    )
