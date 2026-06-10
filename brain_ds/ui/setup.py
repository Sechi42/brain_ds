from __future__ import annotations

import difflib
import json
import os
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from brain_ds.mcp.config import generate_claude_config, generate_opencode_config
from brain_ds.store.graph_store import GraphStore


CHECKLIST_LINES = [
    "1. Rebuild/install the Windows exe",
    "2. Launch the desktop exe and pick this folder",
    "3. Restart your agent client",
    "4. Approve the brain_ds MCP server if prompted",
]


@dataclass(frozen=True)
class ConfigTarget:
    agent: str
    path: Path
    root_key: str
    server_key: str
    desired: dict


def _package_version() -> str:
    try:
        return version("brain_ds")
    except PackageNotFoundError:
        return "0.1.0"


def _normalize_path(value: str | Path) -> str:
    text = str(value)
    if os.name == "nt":
        if text.startswith("\\\\?\\UNC\\"):
            text = "\\\\" + text[8:]
        elif text.startswith("\\\\?\\"):
            text = text[4:]
        drive, tail = os.path.splitdrive(text)
        if drive:
            text = drive.upper() + tail
        text = os.path.normcase(text)
    return str(Path(text))


def paths_align(left: str | Path, right: str | Path) -> bool:
    return _normalize_path(Path(left).resolve()) == _normalize_path(Path(right).resolve())


def _load_json(path: Path, *, default_root_key: str) -> dict:
    if not path.exists():
        return {default_root_key: {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _merged_payload(existing: dict, target: ConfigTarget) -> dict:
    payload = deepcopy(existing)
    container = payload.setdefault(target.root_key, {})
    if not isinstance(container, dict):
        container = {}
        payload[target.root_key] = container
    desired_container = target.desired[target.root_key]
    container[target.server_key] = desired_container[target.server_key]
    return payload


def _render_json(payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _diff_preview(path: Path, before: str, after: str) -> str:
    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    diff = difflib.unified_diff(before_lines, after_lines, fromfile=f"{path} (current)", tofile=f"{path} (new)")
    return "".join(diff)


def _backup_path(path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return path.with_name(f"{path.name}.{stamp}.bak")


def _ensure_store(project_root: Path, *, dry_run: bool) -> None:
    store_dir = project_root / ".brain_ds"
    store_path = store_dir / "store.db"
    if store_path.exists() or dry_run:
        return
    store_dir.mkdir(parents=True, exist_ok=True)
    store = GraphStore(str(store_path))
    store.close()


def _targets_for(project_root: Path, agent: str) -> list[ConfigTarget]:
    targets: list[ConfigTarget] = []
    if agent in {"claude", "both"}:
        targets.append(
            ConfigTarget(
                agent="claude",
                path=project_root / ".mcp.json",
                root_key="mcpServers",
                server_key="brain_ds",
                desired=generate_claude_config(project_root, absolute=True),
            )
        )
    if agent in {"opencode", "both"}:
        targets.append(
            ConfigTarget(
                agent="opencode",
                path=project_root / ".opencode" / "opencode.json",
                root_key="mcp",
                server_key="brain_ds",
                desired=generate_opencode_config(project_root, absolute=True),
            )
        )
    return targets


def _confirm(project_root: Path, targets: list[ConfigTarget]) -> bool:
    print(f"Project root: {project_root}")
    print("Will update:")
    for target in targets:
        print(f"- {target.path}")
    answer = input("Continue? [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def _write_manifest(project_root: Path, agents: list[str]) -> None:
    manifest_path = project_root / ".brain_ds" / "setup.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "project_root": str(project_root),
        "agents": agents,
        "version": _package_version(),
        "created_at": datetime.now(UTC).isoformat(),
    }
    manifest_path.write_text(_render_json(manifest), encoding="utf-8")


def _display_path(project_root: Path, target_path: Path) -> str:
    return target_path.relative_to(project_root).as_posix()


def setup_main(args) -> int:
    project_root = Path(args.project_root or ".").resolve()
    targets = _targets_for(project_root, args.agent)

    if not args.force and not args.dry_run and not _confirm(project_root, targets):
        print("Setup cancelled.")
        return 1

    _ensure_store(project_root, dry_run=args.dry_run)

    print(f"Resolved project root: {project_root}")
    for target in targets:
        existing = _load_json(target.path, default_root_key=target.root_key)
        merged = _merged_payload(existing, target)
        before = _render_json(existing)
        after = _render_json(merged)
        display_path = _display_path(project_root, target.path)
        print(f"Config target ({target.agent}): {display_path}")

        if args.dry_run:
            print(f"DRY RUN: preview for {display_path}")
            print(_diff_preview(Path(display_path), before, after) or "(no changes)")
            continue

        target.path.parent.mkdir(parents=True, exist_ok=True)
        if target.path.exists():
            _backup_path(target.path).write_text(target.path.read_text(encoding="utf-8"), encoding="utf-8")
        target.path.write_text(after, encoding="utf-8")

    if not args.dry_run:
        _write_manifest(project_root, [target.agent for target in targets])

    for line in CHECKLIST_LINES:
        print(line)

    return 0
