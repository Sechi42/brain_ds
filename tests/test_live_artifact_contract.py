"""Golden-fixture CI guard for live artifact contract (C7 — Slice 2).

These tests are the deterministic CI substitute for a live LLM re-run.
They verify that a set of curated golden fixture files satisfy
check_elicit_compliance with zero CRITICALs, and that deliberately
broken copies produce CRITICAL findings.

No live LLM calls, no network access, no fixtures with real secrets.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from brain_ds.mcp.grounding import ARTIFACT_CONTRACT
from brain_ds.verify.elicit_compliance import check_elicit_compliance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "elicit"
"""Golden fixture directory — canonical artifacts one per phase prefix."""


def _load_payload_from_fixture(path: Path) -> dict:
    """Extract the LAST fenced JSON block from a fixture file."""
    text = path.read_text(encoding="utf-8")
    import re
    matches = list(re.finditer(r"```json\n(.*?)\n```", text, re.DOTALL))
    assert matches, f"{path.name} must have at least one fenced JSON block"
    return json.loads(matches[-1].group(1))


def _copy_fixtures_to(tmp: Path) -> list[Path]:
    """Copy all golden fixtures into tmp and return their paths."""
    copied: list[Path] = []
    for src in sorted(FIXTURES_DIR.glob("*.md")):
        dst = tmp / src.name
        shutil.copy2(src, dst)
        copied.append(dst)
    return copied


# ---------------------------------------------------------------------------
# C7-S1: golden fixtures exist (one per phase prefix)
# ---------------------------------------------------------------------------


def test_golden_fixtures_exist_for_all_phase_prefixes() -> None:
    """C7-S1: tests/fixtures/elicit/ must have at least one file per prefix."""
    assert FIXTURES_DIR.exists(), (
        f"Golden fixture directory missing: {FIXTURES_DIR}\n"
        "Run sdd-apply Slice 2 to create it."
    )
    prefixes = {"source-docs", "map", "brd", "verify"}
    present = {p.name.split("-")[0] for p in FIXTURES_DIR.glob("*.md")}
    # source-docs has a hyphen — detect by startswith
    prefix_found = {
        "source-docs": any(p.name.startswith("source-docs-") for p in FIXTURES_DIR.glob("*.md")),
        "map": any(p.name.startswith("map-") for p in FIXTURES_DIR.glob("*.md")),
        "brd": any(p.name.startswith("brd-") for p in FIXTURES_DIR.glob("*.md")),
        "verify": any(p.name.startswith("verify-") for p in FIXTURES_DIR.glob("*.md")),
    }
    missing = [k for k, v in prefix_found.items() if not v]
    assert not missing, (
        f"Golden fixture directory is missing files for prefix(es): {missing}\n"
        f"Present files: {sorted(p.name for p in FIXTURES_DIR.glob('*.md'))}"
    )


# ---------------------------------------------------------------------------
# C7-S2: check_elicit_compliance over golden fixtures → zero CRITICALs
# ---------------------------------------------------------------------------


def test_golden_fixtures_pass_compliance_with_zero_criticals(tmp_path: Path) -> None:
    """C7-S2: check_elicit_compliance over golden fixture dir → 0 CRITICALs.

    This is the primary CI guard: any format regression in the fixture files
    will cause this test to fail immediately.
    """
    assert FIXTURES_DIR.exists(), f"Golden fixture dir missing: {FIXTURES_DIR}"
    _copy_fixtures_to(tmp_path)
    findings = check_elicit_compliance(tmp_path)
    critical = [f for f in findings if f.severity == "CRITICAL"]
    assert not critical, (
        f"Golden fixtures raised {len(critical)} CRITICAL finding(s):\n"
        + "\n".join(f"  {f.file.name}: {f.message}" for f in critical)
    )


# ---------------------------------------------------------------------------
# C7-S3: each fixture's required_keys match ARTIFACT_CONTRACT
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("prefix", ["source-docs", "map", "brd", "verify"])
def test_golden_fixture_has_all_required_keys(prefix: str, tmp_path: Path) -> None:
    """C7-S3: each golden fixture's payload must include all ARTIFACT_CONTRACT required_keys."""
    assert FIXTURES_DIR.exists(), f"Golden fixture dir missing: {FIXTURES_DIR}"
    matches = list(FIXTURES_DIR.glob(f"{prefix}-*.md"))
    assert matches, f"No golden fixture file found for prefix '{prefix}-'"
    fixture = matches[0]
    payload = _load_payload_from_fixture(fixture)
    required = ARTIFACT_CONTRACT[prefix]["required_keys"]
    missing_keys = [k for k in required if k not in payload]
    assert not missing_keys, (
        f"{fixture.name} is missing required keys {missing_keys} "
        f"(expected by ARTIFACT_CONTRACT['{prefix}']['required_keys'])"
    )


# ---------------------------------------------------------------------------
# C7-S4 / C7-S5: negative cases — mutated fixtures → CRITICAL
# ---------------------------------------------------------------------------


def test_source_docs_missing_documented_nodes_is_critical(tmp_path: Path) -> None:
    """C7-S4: a source-docs fixture mutated to remove documented_nodes → CRITICAL."""
    assert FIXTURES_DIR.exists(), f"Golden fixture dir missing: {FIXTURES_DIR}"
    src = next(FIXTURES_DIR.glob("source-docs-*.md"))
    payload = _load_payload_from_fixture(src)

    # Remove documented_nodes AND completeness_gate — the verifier will raise
    # CRITICAL for missing completeness recording (no valid pre_mapping_recommendation).
    bad_payload = {k: v for k, v in payload.items() if k not in ("documented_nodes", "completeness_gate")}
    sentinel = ARTIFACT_CONTRACT["canonical_sentinel"]
    bad_file = tmp_path / src.name
    bad_file.write_text(
        f"# Source Docs (mutated — missing documented_nodes)\n\n"
        f"{sentinel}\n"
        f"```json\n{json.dumps(bad_payload, indent=2)}\n```\n",
        encoding="utf-8",
    )
    findings = check_elicit_compliance(tmp_path)
    # Expect CRITICAL: no valid completeness_gate recorded (no non-verify artifact
    # has a pre_mapping_recommendation in the allowed set).
    critical = [f for f in findings if f.severity == "CRITICAL"]
    assert critical, (
        "Mutated source-docs (missing documented_nodes + completeness_gate) must produce "
        f"CRITICAL findings, got zero. Findings: {findings}"
    )


def test_verify_fixture_with_gate_blocked_is_critical(tmp_path: Path) -> None:
    """C7-S5: a verify fixture with gate=BLOCKED → CRITICAL (archive not allowed)."""
    assert FIXTURES_DIR.exists(), f"Golden fixture dir missing: {FIXTURES_DIR}"
    src = next(FIXTURES_DIR.glob("verify-*.md"))
    payload = _load_payload_from_fixture(src)

    # Mutate: flip gate and status to BLOCKED
    bad_payload = {
        **payload,
        "gate": "BLOCKED",
        "status": "BLOCKED",
        "critical_count": 1,
        "findings": [{"severity": "CRITICAL", "artifact": "some-file.md", "message": "test mutation"}],
    }
    sentinel = ARTIFACT_CONTRACT["canonical_sentinel"]
    bad_file = tmp_path / src.name
    bad_file.write_text(
        f"# Verify Gate (mutated — BLOCKED)\n\n"
        f"{sentinel}\n"
        f"```json\n{json.dumps(bad_payload, indent=2)}\n```\n",
        encoding="utf-8",
    )
    findings = check_elicit_compliance(tmp_path)
    critical = [f for f in findings if f.severity == "CRITICAL"]
    assert critical, (
        "Verify artifact with gate=BLOCKED must produce CRITICAL finding, "
        f"got zero. Findings: {findings}"
    )


# ---------------------------------------------------------------------------
# T2-5 CONTRACT RECONCILIATION: _check_verify_payload must enforce artifact_type
# ---------------------------------------------------------------------------


def test_verify_payload_missing_artifact_type_is_critical(tmp_path: Path) -> None:
    """T2-5 RED: a verify payload missing artifact_type key must produce CRITICAL.

    ARTIFACT_CONTRACT['verify']['required_keys'] already lists artifact_type.
    _check_verify_payload must enforce it so the contract and code are consistent.
    """
    verify_file = tmp_path / "verify-acme-2026-06-14.md"
    # Payload has all 6 legacy required keys but is missing artifact_type
    payload = {
        "graph_id": "acme",
        "stage": "verify",
        "status": "PASS",
        "critical_count": 0,
        "findings": [],
        "gate": "PASS",
        # artifact_type deliberately omitted
    }
    sentinel = ARTIFACT_CONTRACT["canonical_sentinel"]
    verify_file.write_text(
        f"# Verify Gate\n\n{sentinel}\n```json\n{json.dumps(payload)}\n```\n",
        encoding="utf-8",
    )
    findings = check_elicit_compliance(tmp_path)
    critical = [f for f in findings if f.severity == "CRITICAL"]
    assert critical, (
        "verify payload missing 'artifact_type' must produce CRITICAL finding; "
        f"got zero. Findings: {findings}"
    )
    # Confirm the finding mentions artifact_type
    assert any("artifact_type" in f.message for f in critical), (
        f"Expected a CRITICAL mentioning 'artifact_type', got: {[f.message for f in critical]}"
    )


def test_verify_payload_with_artifact_type_passes(tmp_path: Path) -> None:
    """T2-5 complement GREEN: a complete verify payload (all 7 keys) → zero CRITICALs."""
    verify_file = tmp_path / "verify-acme-2026-06-14.md"
    payload = {
        "artifact_type": "verify",
        "graph_id": "acme",
        "stage": "verify",
        "status": "PASS",
        "critical_count": 0,
        "findings": [],
        "gate": "PASS",
    }
    sentinel = ARTIFACT_CONTRACT["canonical_sentinel"]
    verify_file.write_text(
        f"# Verify Gate\n\n{sentinel}\n```json\n{json.dumps(payload)}\n```\n",
        encoding="utf-8",
    )
    findings = check_elicit_compliance(tmp_path)
    critical = [f for f in findings if f.severity == "CRITICAL"]
    assert not critical, (
        f"Complete verify payload must pass with zero CRITICALs; got: {critical}"
    )
