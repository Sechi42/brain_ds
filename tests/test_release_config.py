"""
PR5 — Release automation config/manifest validation.
Satisfies: T5.1 (S6-B, S6-C), T5.6 (S6-A), T5.8 (S6-D).
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent


def _load_workflow(name: str) -> dict:
    wf_path = REPO_ROOT / ".github" / "workflows" / name
    assert wf_path.exists(), f".github/workflows/{name} not found"
    wf = yaml.safe_load(wf_path.read_text(encoding="utf-8"))
    assert isinstance(wf, dict), f"{name} must parse to a YAML mapping"
    return wf


def _on_push(workflow: dict) -> dict:
    on = workflow.get("on") or workflow.get(True)  # YAML parses bare 'on' as boolean True
    return on.get("push", {}) if isinstance(on, dict) else {}


def _release_please_tag_pattern() -> str:
    config_path = REPO_ROOT / ".release-please-config.json"
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    package_name = cfg["packages"]["."].get("package-name")
    assert package_name, "release-please root package must define package-name"
    return f"{package_name}-v*.*.*"


# ---------------------------------------------------------------------------
# T5.1 — manifest + config structural assertions (S6-B, S6-C)
# ---------------------------------------------------------------------------


def test_release_please_manifest_exists_and_has_root_version():
    """Manifest must exist and seed '.' at 0.1.0 (S6-B)."""
    manifest_path = REPO_ROOT / ".release-please-manifest.json"
    assert manifest_path.exists(), ".release-please-manifest.json not found at repo root"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "." in data, "Manifest must have a root component keyed as '.'"
    assert data["."] == "0.1.0", f"Expected root version 0.1.0, got {data['.']!r}"


def test_release_please_config_exists_and_release_type_python():
    """Config must exist and use release-type: python for root package (R6.2)."""
    config_path = REPO_ROOT / ".release-please-config.json"
    assert config_path.exists(), ".release-please-config.json not found at repo root"
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    assert "packages" in cfg, "Config must have a 'packages' key"
    assert "." in cfg["packages"], "Config packages must contain root component '.'"
    root = cfg["packages"]["."]
    assert root.get("release-type") == "python", (
        f"release-type must be 'python', got {root.get('release-type')!r}"
    )


def test_release_please_config_extra_files_cover_tauri_and_cargo():
    """extra-files must reference src-tauri/tauri.conf.json and src-tauri/Cargo.toml (S6-C, R6.7)."""
    config_path = REPO_ROOT / ".release-please-config.json"
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    root = cfg["packages"]["."]
    extra_files = root.get("extra-files", [])
    assert extra_files, "extra-files must be non-empty"

    paths_in_extra = [
        (ef["path"] if isinstance(ef, dict) else ef) for ef in extra_files
    ]
    assert any("tauri.conf.json" in p for p in paths_in_extra), (
        "extra-files must include src-tauri/tauri.conf.json"
    )
    assert any("Cargo.toml" in p for p in paths_in_extra), (
        "extra-files must include src-tauri/Cargo.toml"
    )


def test_manifest_version_matches_pyproject():
    """Manifest root version must match pyproject.toml [project] version (S6-B)."""
    manifest_path = REPO_ROOT / ".release-please-manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_version = data["."]

    pyproject_path = REPO_ROOT / "pyproject.toml"
    assert pyproject_path.exists(), "pyproject.toml not found"
    # Parse the version line from [project] section without a full TOML parser.
    pyproject_text = pyproject_path.read_text(encoding="utf-8")
    pyproject_version: str | None = None
    in_project = False
    for line in pyproject_text.splitlines():
        stripped = line.strip()
        if stripped == "[project]":
            in_project = True
            continue
        if in_project and stripped.startswith("[") and stripped != "[project]":
            in_project = False
        if in_project and stripped.startswith("version"):
            pyproject_version = stripped.split("=", 1)[1].strip().strip('"').strip("'")
            break

    assert pyproject_version is not None, "Could not parse version from pyproject.toml [project]"
    assert manifest_version == pyproject_version, (
        f"Manifest version {manifest_version!r} != pyproject.toml version {pyproject_version!r}"
    )


# ---------------------------------------------------------------------------
# T5.6 — release-please.yml structural assertions (S6-A)
# ---------------------------------------------------------------------------


def test_release_please_workflow_exists_and_is_valid_yaml():
    """Workflow must exist and parse as valid YAML (S6-A)."""
    wf_path = REPO_ROOT / ".github" / "workflows" / "release-please.yml"
    assert wf_path.exists(), ".github/workflows/release-please.yml not found"
    with wf_path.open(encoding="utf-8") as fh:
        wf = yaml.safe_load(fh)
    assert isinstance(wf, dict), "release-please.yml must parse to a YAML mapping"


def test_release_please_workflow_triggers_on_main():
    """Workflow on.push.branches must contain 'main' (R6.1)."""
    wf_path = REPO_ROOT / ".github" / "workflows" / "release-please.yml"
    wf = yaml.safe_load(wf_path.read_text(encoding="utf-8"))
    on = wf.get("on") or wf.get(True)  # YAML parses bare 'on' as boolean True
    push = on.get("push", {}) if isinstance(on, dict) else {}
    branches = push.get("branches", [])
    assert "main" in branches, f"on.push.branches must contain 'main', got {branches!r}"


def test_release_please_workflow_uses_release_please_action():
    """Workflow must have a step using google-github-actions/release-please-action (R6.1)."""
    wf_path = REPO_ROOT / ".github" / "workflows" / "release-please.yml"
    wf = yaml.safe_load(wf_path.read_text(encoding="utf-8"))
    steps = []
    for job in (wf.get("jobs") or {}).values():
        steps.extend(job.get("steps") or [])
    uses_values = [s.get("uses", "") for s in steps if isinstance(s, dict)]
    assert any(
        "release-please-action" in u for u in uses_values
    ), f"No step uses release-please-action. Found: {uses_values}"


def test_release_please_workflow_has_write_permissions():
    """Workflow must grant contents: write and pull-requests: write (A5)."""
    wf_path = REPO_ROOT / ".github" / "workflows" / "release-please.yml"
    wf = yaml.safe_load(wf_path.read_text(encoding="utf-8"))
    perms = wf.get("permissions", {})
    assert perms.get("contents") == "write", (
        f"permissions.contents must be 'write', got {perms.get('contents')!r}"
    )
    assert perms.get("pull-requests") == "write", (
        f"permissions.pull-requests must be 'write', got {perms.get('pull-requests')!r}"
    )


# ---------------------------------------------------------------------------
# T5.8 — build-windows-exe.yml trigger assertions (S6-D)
# ---------------------------------------------------------------------------


def test_build_windows_workflow_triggers_on_release_please_tags():
    """build-windows-exe.yml on.push.tags must match release-please package tags."""
    wf = _load_workflow("build-windows-exe.yml")
    push = _on_push(wf)
    tags = push.get("tags", [])
    assert tags, "on.push.tags must be present in build-windows-exe.yml"
    assert _release_please_tag_pattern() in tags, (
        "Windows app-generation workflow tags must match release-please's "
        f"package tag pattern; expected {_release_please_tag_pattern()!r}, got {tags!r}"
    )


def test_build_macos_workflow_triggers_on_release_please_tags():
    """build-macos-exe.yml on.push.tags must match release-please package tags."""
    wf = _load_workflow("build-macos-exe.yml")
    push = _on_push(wf)
    tags = push.get("tags", [])
    assert tags, "on.push.tags must be present in build-macos-exe.yml"
    assert _release_please_tag_pattern() in tags, (
        "macOS app-generation workflow tags must match release-please's "
        f"package tag pattern; expected {_release_please_tag_pattern()!r}, got {tags!r}"
    )


def test_build_windows_workflow_preserves_main_draft_builds():
    """build-windows-exe.yml should keep push-to-main draft builds fresh."""
    wf = _load_workflow("build-windows-exe.yml")
    push = _on_push(wf)
    branches = push.get("branches", [])
    assert "main" in branches, f"on.push.branches must contain 'main', got {branches!r}"


def test_build_macos_workflow_preserves_main_draft_builds():
    """build-macos-exe.yml should keep push-to-main draft builds fresh."""
    wf = _load_workflow("build-macos-exe.yml")
    push = _on_push(wf)
    branches = push.get("branches", [])
    assert "main" in branches, f"on.push.branches must contain 'main', got {branches!r}"
