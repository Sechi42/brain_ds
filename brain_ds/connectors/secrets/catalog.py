"""Workspace-scoped secret catalog: manifest + isolated raw-value store."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import importlib.resources as resources


class SecretManifestError(Exception):
    """Raised when the workspace secret manifest is invalid or corrupted."""


@dataclass
class SecretEntry:
    """A single secret handle as persisted in the public manifest.

    Never stores the raw credential value.
    """

    handle: str
    kind: str
    metadata: dict[str, Any]
    created_at: str | None = None


class SecretCatalog:
    """Load, persist, and validate a workspace's secret manifest.

    The manifest (``.brain_ds/secrets.json``) stores handles, kinds, and
    redacted metadata. Raw values live in ``.brain_ds/secrets.values.json``
    with ``0o600`` permissions. A schema violation on load fails closed with
    ``SecretManifestError``.
    """

    _SCHEMA_PACKAGE = "brain_ds.connectors.secrets"
    _SCHEMA_FILE = "schema.json"
    _VALUES_MODE = 0o600

    def __init__(self, workspace_root: str | Path) -> None:
        self.root = Path(workspace_root)
        self.brain_ds_dir = self.root / ".brain_ds"
        self.manifest_path = self.brain_ds_dir / "secrets.json"
        self.values_path = self.brain_ds_dir / "secrets.values.json"
        self._schema: dict[str, Any] | None = None
        self._entries: list[SecretEntry] = []
        self._values: dict[str, str] = {}

    @property
    def schema(self) -> dict[str, Any]:
        if self._schema is None:
            schema_text = resources.files(self._SCHEMA_PACKAGE).joinpath(self._SCHEMA_FILE).read_text(encoding="utf-8")
            self._schema = json.loads(schema_text)
        return self._schema

    def load(self) -> None:
        """Load manifest and values from disk; raise SecretManifestError on invalid data."""
        if not self.manifest_path.exists():
            self._entries = []
            self._values = {}
            return

        try:
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SecretManifestError(f"invalid JSON in {self.manifest_path}: {exc}") from exc

        if not isinstance(manifest, dict):
            raise SecretManifestError("manifest root must be an object")
        if manifest.get("schema_version") != self.schema["schema_version"]:
            raise SecretManifestError(
                f"unsupported schema_version: {manifest.get('schema_version')}"
            )

        raw_entries = manifest.get("entries", [])
        if not isinstance(raw_entries, list):
            raise SecretManifestError("manifest entries must be an array")

        required = set(self.schema["entry_required_fields"])
        valid_kinds = set(self.schema["provider_kinds"])
        entries: list[SecretEntry] = []
        for index, raw in enumerate(raw_entries):
            if not isinstance(raw, dict):
                raise SecretManifestError(f"entry[{index}] is not an object")
            missing = required - set(raw)
            if missing:
                raise SecretManifestError(
                    f"entry[{index}] missing required fields: {sorted(missing)}"
                )
            kind = raw["kind"]
            if kind not in valid_kinds:
                raise SecretManifestError(
                    f"entry[{index}] has unknown kind: {kind}"
                )
            entries.append(
                SecretEntry(
                    handle=raw["handle"],
                    kind=kind,
                    metadata=raw["metadata"],
                    created_at=raw["created_at"],
                )
            )

        self._entries = entries
        self._values = self._load_values()

    def _load_values(self) -> dict[str, str]:
        if not self.values_path.exists():
            return {}
        try:
            payload = json.loads(self.values_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SecretManifestError(f"invalid JSON in {self.values_path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise SecretManifestError("values file root must be an object")
        return payload.get("values", {})

    def save(self) -> None:
        """Persist the manifest and raw-value store to disk."""
        self.brain_ds_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "schema_version": self.schema["schema_version"],
            "entries": [asdict(entry) for entry in self._entries],
        }
        self.manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._write_values()

    def _write_values(self) -> None:
        values_payload = {
            "schema_version": self.schema["schema_version"],
            "values": self._values,
        }
        self.values_path.write_text(
            json.dumps(values_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        try:
            os.chmod(self.values_path, self._VALUES_MODE)
        except OSError:
            # Windows does not support Unix permission bits; the file still exists.
            pass

    def list_handles(self) -> list[SecretEntry]:
        """Return all manifest entries (handles and metadata, no raw values)."""
        return list(self._entries)

    def get(self, handle: str) -> SecretEntry | None:
        """Return the entry for a handle, or None if not present."""
        for entry in self._entries:
            if entry.handle == handle:
                return entry
        return None

    def get_raw(self, handle: str) -> str | None:
        """Return the raw credential value for a handle, or None."""
        return self._values.get(handle)

    def add(self, entry: SecretEntry, raw_value: str | None = None) -> None:
        """Add or update an entry and optionally store its raw value."""
        if not entry.created_at:
            entry.created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        self._entries = [e for e in self._entries if e.handle != entry.handle]
        self._entries.append(entry)

        if raw_value is not None:
            self._values[entry.handle] = raw_value

        self.save()

    def remove(self, handle: str) -> None:
        """Remove an entry and its raw value from the catalog."""
        self._entries = [e for e in self._entries if e.handle != handle]
        self._values.pop(handle, None)
        self.save()

    def validate_all(self) -> list[str]:
        """Validate every entry against the per-kind schema; return error strings."""
        errors: list[str] = []
        valid_kinds = self.schema["provider_kinds"]
        for entry in self._entries:
            kind_schema = valid_kinds.get(entry.kind)
            if kind_schema is None:
                errors.append(f"{entry.handle}: unknown kind {entry.kind}")
                continue
            metadata = entry.metadata
            if not isinstance(metadata, dict):
                errors.append(f"{entry.handle}: metadata must be an object")
                continue
            for field in kind_schema.get("required", []):
                if field not in metadata:
                    errors.append(f"{entry.handle}: missing required field '{field}'")
            for field, expected_type in kind_schema.get("types", {}).items():
                if field in metadata and not self._matches_type(metadata[field], expected_type):
                    errors.append(
                        f"{entry.handle}: field '{field}' must be of type {expected_type}"
                    )
        return errors

    @staticmethod
    def _matches_type(value: Any, expected_type: str) -> bool:
        if expected_type == "string":
            return isinstance(value, str)
        if expected_type == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if expected_type == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if expected_type == "boolean":
            return isinstance(value, bool)
        return True
