from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


PROTECTED_NODE_FIELDS: frozenset[str] = frozenset(
    {
        "validation_status",
        "secret_ref",
        "secret_binding",
        "connection",
        "exposure",
        "provider_inputs",
        "validation",
        "secret_ref_alias",
        "internal_secret_id",
        "provider_secret_id",
        "secret_handle",
        "spreadsheet_id",
        "spreadsheet_ref",
        "provider_mapping",
        "connector",
        "descriptor",
    }
)


@dataclass
class SecretBindingRecord:
    graph_id: str
    source_node_id: str
    secret_ref_alias: str
    internal_secret_id: str
    provider_kind: str
    provider_inputs: dict[str, Any] = field(default_factory=dict)
    provider_mapping: dict[str, Any] = field(default_factory=dict)
    validation_status: str = "unvalidated"
    documentation_status: str = "not_started"
    writeback_status: str = "idle"
    validation: dict[str, Any] = field(default_factory=dict)

    def to_projection(self) -> dict[str, Any]:
        return {
            "secret_ref": self.secret_ref_alias,
            "provider_kind": self.provider_kind,
            "validation_status": self.validation_status,
            "documentation_status": self.documentation_status,
            "writeback_status": self.writeback_status,
            "provider_inputs": dict(self.provider_inputs),
            "exposure": {"graph_id": self.graph_id, "allowed": True},
            "validation": dict(self.validation),
        }


class SecretBindingStore:
    def __init__(self, workspace_root: str | Path) -> None:
        self.root = Path(workspace_root)
        self.path = self.root / ".brain_ds" / "secret_bindings.json"
        self._records: dict[tuple[str, str], SecretBindingRecord] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self._records = {}
            return
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        records = payload.get("bindings", []) if isinstance(payload, dict) else []
        self._records = {}
        for raw in records:
            if isinstance(raw, dict):
                record = SecretBindingRecord(**raw)
                self._records[(record.graph_id, record.source_node_id)] = record

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        payload = {
            "schema_version": "1.0.0",
            "bindings": [asdict(record) for record in self._records.values()],
        }
        tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(self.path)

    def upsert(self, record: SecretBindingRecord) -> None:
        self._records[(record.graph_id, record.source_node_id)] = record
        self.save()

    def get(self, graph_id: str, source_node_id: str) -> SecretBindingRecord | None:
        return self._records.get((graph_id, source_node_id))

    def delete(self, graph_id: str, source_node_id: str) -> None:
        self._records.pop((graph_id, source_node_id), None)
        self.save()


def sanitize_node_mutation(changes: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in changes.items():
        if key in PROTECTED_NODE_FIELDS:
            continue
        if key == "details" and isinstance(value, dict):
            sanitized[key] = _strip_protected_fields(value)
            continue
        sanitized[key] = value
    return sanitized


def _strip_protected_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_protected_fields(item)
            for key, item in value.items()
            if key not in PROTECTED_NODE_FIELDS
        }
    if isinstance(value, list):
        return [_strip_protected_fields(item) for item in value]
    return value
