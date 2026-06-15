"""Workspace-scoped secret catalog: manifest + isolated raw-value store."""
from __future__ import annotations

import json
import os
import sys
import tempfile
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


def _is_windows() -> bool:
    return sys.platform == "win32"


def _atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Write ``text`` to ``path`` atomically using a temp file + os.replace.

    On platforms where ``os.replace`` is atomic (POSIX, modern Windows), the
    destination file is either fully replaced or untouched on failure.
    Older Windows releases (pre-Vista) may not be fully atomic; the documented
    supported platforms are the same as the rest of the project (Windows
    10+/macOS/Linux) so this is safe for the workspace secret surface.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Use a sibling temp file so os.replace is an atomic rename on the same fs.
    fd, tmp_path = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as handle:
            handle.write(text)
            handle.flush()
            try:
                os.fdatasync(handle.fileno())
            except (AttributeError, OSError):
                # os.fdatasync is Unix-only; fall back to fsync on platforms that have it.
                try:
                    os.fsync(handle.fileno())
                except OSError:
                    pass
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


class SecretCatalog:
    """Load, persist, and validate a workspace's secret manifest.

    The manifest (``.brain_ds/secrets.json``) stores handles, kinds, and
    redacted metadata. Raw values live in ``.brain_ds/secrets.values.json``.
    A schema violation on load fails closed with ``SecretManifestError``.

    Permission guarantee: on POSIX systems the values file is chmod-ed to
    ``0o600`` (owner read/write only). On Windows the project relies on the
    user's NTFS ACL: the file is created with the default inherited ACL and
    the project does not attempt to lock it down further. Operators who need
    a tighter ACL on Windows should apply it via the host OS (icacls / PowerShell
    Set-Acl); the catalog does not provide a portable cross-OS guarantee.
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
        """Persist the manifest and raw-value store to disk atomically.

        Each file is written via a sibling temp file + ``os.replace`` so a
        crash mid-write leaves the existing file intact. Manifest and values
        are written in a single ``save()`` call; if the second write fails the
        first is already durable and the operator can re-run ``save()`` (the
        catalog reloads state from disk on the next call).
        """
        self.brain_ds_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "schema_version": self.schema["schema_version"],
            "entries": [asdict(entry) for entry in self._entries],
        }
        _atomic_write_text(
            self.manifest_path,
            json.dumps(manifest, indent=2, ensure_ascii=False),
        )
        self._write_values()

    def _write_values(self) -> None:
        values_payload = {
            "schema_version": self.schema["schema_version"],
            "values": self._values,
        }
        _atomic_write_text(
            self.values_path,
            json.dumps(values_payload, indent=2, ensure_ascii=False),
        )
        self._apply_values_permissions()

    def _apply_values_permissions(self) -> None:
        """Best-effort permission tightening. See class docstring for cross-OS contract."""
        if _is_windows():
            # Windows does not support Unix mode bits; the file inherits the
            # user's default ACL. The catalog deliberately does not call
            # win32security.SetSecurityInfo here to stay portable; operators
            # who need a tighter ACL must apply it via the host OS.
            return
        try:
            os.chmod(self.values_path, self._VALUES_MODE)
        except OSError:
            # POSIX chmod failed (e.g. mounted fs without mode support); the
            # file is still created and readable by the owner.
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
        """Add or update an entry and optionally store its raw value.

        Validates the entry kind and metadata against the schema before
        persisting. Raises ``SecretManifestError`` on an unknown kind or a
        missing required field, so callers do not need to pre-validate to
        keep the manifest consistent. A non-string or empty ``raw_value``
        is rejected because the values file is meant to carry credential
        strings only.
        """
        if not entry.created_at:
            entry.created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        self._validate_new_entry(entry, raw_value)
        self._entries = [e for e in self._entries if e.handle != entry.handle]
        self._entries.append(entry)

        if raw_value is not None:
            self._values[entry.handle] = raw_value

        self.save()

    def _validate_new_entry(self, entry: SecretEntry, raw_value: str | None) -> None:
        """Reject unknown kinds, missing required fields, and bad raw_value.

        Keeps the manifest fail-closed: callers that bypass the API
        validation (CLI, MCP write path, etc.) still cannot persist an
        invalid entry. The errors here are intentionally specific so the
        upstream 422 response can name the bad field.
        """
        valid_kinds = self.schema["provider_kinds"]
        if entry.kind not in valid_kinds:
            raise SecretManifestError(f"unknown kind: {entry.kind!r}")
        if not isinstance(entry.metadata, dict):
            raise SecretManifestError("metadata must be an object")
        if raw_value is not None and (not isinstance(raw_value, str) or not raw_value):
            raise SecretManifestError("raw_value must be a non-empty string when provided")
        kind_schema = valid_kinds[entry.kind]
        for field in kind_schema.get("required", []):
            if field not in entry.metadata:
                raise SecretManifestError(
                    f"missing required field {field!r} for kind {entry.kind!r}"
                )
        for field, expected_type in kind_schema.get("types", {}).items():
            if field in entry.metadata and not self._matches_type(
                entry.metadata[field], expected_type
            ):
                raise SecretManifestError(
                    f"field {field!r} must be of type {expected_type} for kind {entry.kind!r}"
                )

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

