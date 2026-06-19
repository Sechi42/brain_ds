from __future__ import annotations

import os
from pathlib import Path

import pytest

from brain_ds.ui.bundle_freshness import check_viewer_bundle_freshness


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _touch(path: Path, timestamp: int) -> None:
    os.utime(path, (timestamp, timestamp))


def _fresh_ui_tree(root: Path) -> Path:
    ui_root = root / "brain_ds" / "ui"
    _write(ui_root / "src" / "main.ts", 'window.brainDsUI = { bundleRevision: "rev-1" };')
    _write(ui_root / "src" / "main.css", ".viewer { color: currentColor; }")
    _write(ui_root / "assets" / "viewer.bundle.js", 'window.brainDsUI={bundleRevision:"rev-1"};')
    _write(ui_root / "assets" / "viewer.bundle.css", ".viewer{color:currentColor}")
    for path in ui_root.rglob("*"):
        if path.is_file():
            _touch(path, 1_700_000_000)
    return ui_root


def test_freshness_guard_accepts_rebuilt_bundle_with_matching_revision(tmp_path: Path) -> None:
    ui_root = _fresh_ui_tree(tmp_path)

    result = check_viewer_bundle_freshness(ui_root)

    assert result.ok is True
    assert result.messages == []


@pytest.mark.parametrize(
    "bundle_name",
    ["viewer.bundle.js", "viewer.bundle.css"],
)
def test_freshness_guard_rejects_bundle_older_than_ui_source(
    tmp_path: Path, bundle_name: str
) -> None:
    ui_root = _fresh_ui_tree(tmp_path)
    _write(ui_root / "src" / "panels" / "detail-panel.ts", "export const changed = true;")
    _touch(ui_root / "src" / "panels" / "detail-panel.ts", 1_700_000_100)
    _touch(ui_root / "assets" / bundle_name, 1_700_000_000)

    result = check_viewer_bundle_freshness(ui_root)

    assert result.ok is False
    assert any(bundle_name in message and "older than" in message for message in result.messages)


def test_freshness_guard_rejects_bundle_revision_drift(tmp_path: Path) -> None:
    ui_root = _fresh_ui_tree(tmp_path)
    _write(ui_root / "assets" / "viewer.bundle.js", 'window.brainDsUI={bundleRevision:"rev-2"};')
    _touch(ui_root / "assets" / "viewer.bundle.js", 1_700_000_100)

    result = check_viewer_bundle_freshness(ui_root)

    assert result.ok is False
    assert any("bundleRevision" in message and "rev-1" in message and "rev-2" in message for message in result.messages)


def test_freshness_guard_requires_committed_bundle_assets(tmp_path: Path) -> None:
    ui_root = _fresh_ui_tree(tmp_path)
    (ui_root / "assets" / "viewer.bundle.css").unlink()

    result = check_viewer_bundle_freshness(ui_root)

    assert result.ok is False
    assert any("viewer.bundle.css" in message and "missing" in message for message in result.messages)
