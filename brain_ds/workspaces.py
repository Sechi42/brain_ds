"""Global workspace registry — Obsidian-style vault list.

Every initialized project folder (via `brain_ds setup`, the desktop vault
picker, or an MCP server launched over an existing store) is recorded here so
any client can discover all workspaces globally while each workspace keeps its
own isolated `.brain_ds/store.db`.

The registry lives outside any single project: `~/.brain_ds/workspaces.json`
(override the parent directory with the BRAIN_DS_HOME environment variable).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REGISTRY_VERSION = 1


def registry_home() -> Path:
    override = os.environ.get("BRAIN_DS_HOME")
    if override:
        return Path(override)
    return Path.home() / ".brain_ds"


def registry_path() -> Path:
    return registry_home() / "workspaces.json"


def normalize_root(path: str | Path) -> str:
    resolved = Path(path).resolve()
    text = str(resolved)
    if os.name == "nt":
        text = os.path.normcase(text)
    return text


def project_root_from_store_path(store_path: str | Path) -> Path:
    path = Path(store_path)
    if path.parent.name == ".brain_ds":
        return path.parent.parent
    return path.parent


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _empty_registry() -> dict[str, Any]:
    return {"version": _REGISTRY_VERSION, "workspaces": []}


def _load_registry() -> dict[str, Any]:
    path = registry_path()
    if not path.exists():
        return _empty_registry()
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return _empty_registry()
    if not isinstance(payload, dict) or not isinstance(payload.get("workspaces"), list):
        return _empty_registry()
    return payload


def _save_registry(payload: dict[str, Any]) -> None:
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def register_workspace(root: str | Path, *, name: str | None = None) -> dict[str, Any]:
    """Upsert a workspace by canonical path; bumps last_opened_at on re-register."""
    resolved = Path(root).resolve()
    key = normalize_root(resolved)
    payload = _load_registry()
    now = _now()

    for entry in payload["workspaces"]:
        if normalize_root(entry.get("path", "")) == key:
            entry["last_opened_at"] = now
            if name:
                entry["name"] = name
            _save_registry(payload)
            return dict(entry)

    entry = {
        "path": str(resolved),
        "name": name or resolved.name,
        "registered_at": now,
        "last_opened_at": now,
    }
    payload["workspaces"].append(entry)
    _save_registry(payload)
    return dict(entry)


def list_workspaces() -> list[dict[str, Any]]:
    """All registered workspaces with a live `store_exists` flag (no pruning)."""
    entries: list[dict[str, Any]] = []
    for entry in _load_registry()["workspaces"]:
        raw_path = str(entry.get("path", ""))
        store_exists = bool(raw_path) and (Path(raw_path) / ".brain_ds" / "store.db").exists()
        entries.append({**entry, "store_exists": store_exists})
    return entries


def find_workspace(root: str | Path) -> dict[str, Any] | None:
    key = normalize_root(root)
    for entry in _load_registry()["workspaces"]:
        if normalize_root(entry.get("path", "")) == key:
            return dict(entry)
    return None
