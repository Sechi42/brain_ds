from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from brain_ds.connectors.secrets.binding_store import SecretBindingRecord, SecretBindingStore
from brain_ds.connectors.secrets.catalog import SecretCatalog, SecretEntry
from brain_ds.mcp.security import ValidationError
from brain_ds.store.graph_store import GraphStore


class SourceConnectionError(Exception):
    def __init__(self, error_code: str, message: str, *, retryable: bool = True, status_code: int = 422) -> None:
        self.error_code = error_code
        self.retryable = retryable
        self.status_code = status_code
        super().__init__(message)

    def to_public(self) -> dict[str, Any]:
        return {"error_code": self.error_code, "message": str(self), "retryable": self.retryable}


_SOURCE_KIND_BY_PROVIDER = {"google-sheets-json": {"google-sheets", "google_sheets", "sheets"}}


def connection_error(error_code: str, message: str, *, retryable: bool = True, status_code: int = 422) -> dict[str, Any]:
    return {"error_code": error_code, "message": message, "retryable": retryable, "status": "error", "status_code": status_code}


def secret_ref_for(graph_id: str, handle: str) -> str:
    return "sec_" + sha256(f"{graph_id}:{handle}".encode("utf-8")).hexdigest()[:16]


def _source_item(row: Any, provider_kind: str, validation_status: str) -> dict[str, Any]:
    return {
        "graph_id": row.graph_id,
        "node_id": row.id,
        "label": row.label,
        "provider_kind": provider_kind,
        "validation_status": validation_status,
    }


def _safe_source(row: Any) -> dict[str, Any]:
    return {"graph_id": row.graph_id, "node_id": row.id, "label": row.label}


def _matching_sources(store: GraphStore, graph_id: str, provider_kind: str) -> list[Any]:
    rows = store.query_nodes(graph_id, type="Data Source")
    result = []
    for row in rows:
        if _source_matches_provider(row, provider_kind):
            result.append(row)
    return result


def _source_matches_provider(row: Any, provider_kind: str) -> bool:
    allowed = _SOURCE_KIND_BY_PROVIDER.get(provider_kind, {provider_kind})
    details = row.details or {}
    source_kind = str(details.get("source_kind") or details.get("kind") or "").lower()
    connection = details.get("connection") if isinstance(details.get("connection"), dict) else {}
    connection_kind = str(connection.get("kind") or "").lower() if isinstance(connection, dict) else ""
    binding = details.get("secret_binding") if isinstance(details.get("secret_binding"), dict) else {}
    binding_kind = str(binding.get("provider_kind") or "").lower() if isinstance(binding, dict) else ""
    return source_kind in allowed or connection_kind == provider_kind or binding_kind == provider_kind


def _source_by_id(store: GraphStore, graph_id: str, source_node_id: str) -> Any:
    for row in store.query_nodes(graph_id, type="Data Source"):
        if row.id == source_node_id:
            return row
    raise SourceConnectionError("not_allowlisted", "Data Source is not available for this graph.", status_code=404)


def _entry_for_ref(catalog: SecretCatalog, graph_id: str, secret_ref: str) -> SecretEntry:
    for entry in catalog.list_handles():
        if secret_ref_for(graph_id, entry.handle) == secret_ref:
            return entry
    raise SourceConnectionError("not_allowlisted", "Secret is not available for this graph.", status_code=404)


def _provider_inputs(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SourceConnectionError("invalid_provider_input", "provider_inputs must be an object.", retryable=False)
    spreadsheet_ref = value.get("spreadsheet_ref")
    if not isinstance(spreadsheet_ref, str) or not spreadsheet_ref.strip():
        raise SourceConnectionError("invalid_provider_input", "provider_inputs.spreadsheet_ref is required.", retryable=False)
    return {"spreadsheet_ref": spreadsheet_ref.strip()}


def _project_binding(store: GraphStore, graph_id: str, source_node_id: str, projection: dict[str, Any] | None) -> None:
    row = _source_by_id(store, graph_id, source_node_id)
    details = dict(row.details or {})
    details.pop("connection", None)
    if projection is None:
        details.pop("secret_binding", None)
    else:
        details["secret_binding"] = projection
    store.upsert_node(graph_id, {"id": source_node_id, "details": details})


def list_candidate_secrets(store: GraphStore, graph_id: str, workspace_root: str | Path, source_node_id: str) -> dict[str, Any]:
    source = _source_by_id(store, graph_id, source_node_id)
    catalog = SecretCatalog(workspace_root)
    catalog.load()
    records = SecretBindingStore(workspace_root)
    existing = records.get(graph_id, source_node_id)
    secrets = []
    for entry in catalog.list_handles():
        if entry.kind not in _SOURCE_KIND_BY_PROVIDER:
            continue
        if source not in _matching_sources(store, graph_id, entry.kind):
            continue
        secrets.append(
            {
                "secret_ref": secret_ref_for(graph_id, entry.handle),
                "provider_kind": entry.kind,
                "label": entry.kind,
                "validation_status": existing.validation_status if existing and existing.internal_secret_id == entry.handle else "unbound",
                "required_provider_inputs": ["spreadsheet_ref"],
            }
        )
    return {"status": "ok", "source": _safe_source(source), "secrets": secrets}


def list_candidate_sources(store: GraphStore, graph_id: str, workspace_root: str | Path, secret_ref: str) -> dict[str, Any]:
    catalog = SecretCatalog(workspace_root)
    catalog.load()
    entry = _entry_for_ref(catalog, graph_id, secret_ref)
    records = SecretBindingStore(workspace_root)
    sources = []
    for row in _matching_sources(store, graph_id, entry.kind):
        existing = records.get(graph_id, row.id)
        status = existing.validation_status if existing and existing.internal_secret_id == entry.handle else "unbound"
        sources.append(_source_item(row, entry.kind, status))
    return {"status": "ok", "secret_ref": secret_ref, "provider_kind": entry.kind, "sources": sources}


def bind_source_connection(store: GraphStore, graph_id: str, workspace_root: str | Path, source_node_id: str, secret_ref: str, provider_inputs: Any) -> dict[str, Any]:
    source = _source_by_id(store, graph_id, source_node_id)
    catalog = SecretCatalog(workspace_root)
    catalog.load()
    entry = _entry_for_ref(catalog, graph_id, secret_ref)
    if not _source_matches_provider(source, entry.kind):
        raise SourceConnectionError("not_allowlisted", "Secret is not compatible with this Data Source for this graph.", status_code=404)
    inputs = _provider_inputs(provider_inputs)
    record = SecretBindingRecord(
        graph_id=graph_id,
        source_node_id=source_node_id,
        secret_ref_alias=secret_ref,
        internal_secret_id=entry.handle,
        provider_kind=entry.kind,
        provider_inputs=inputs,
    )
    records = SecretBindingStore(workspace_root)
    records.upsert(record)
    projection = record.to_projection()
    _project_binding(store, graph_id, source_node_id, projection)
    return {"status": "ok", "binding": projection}


def source_connection_status(store: GraphStore, graph_id: str, workspace_root: str | Path, source_node_id: str) -> dict[str, Any]:
    _source_by_id(store, graph_id, source_node_id)
    record = SecretBindingStore(workspace_root).get(graph_id, source_node_id)
    if record is None:
        return {
            "status": "ok",
            "binding": {
                "validation_status": "unbound",
                "documentation_status": "not_started",
                "writeback_status": "idle",
                "requires_binding": True,
            },
        }
    return {"status": "ok", "binding": record.to_projection()}


def validate_source_connection(store: GraphStore, graph_id: str, workspace_root: str | Path, source_node_id: str) -> dict[str, Any]:
    records = SecretBindingStore(workspace_root)
    record = records.get(graph_id, source_node_id)
    if record is None:
        raise SourceConnectionError("missing_private_mapping", "No private binding exists for this Data Source.", status_code=409)
    catalog = SecretCatalog(workspace_root)
    catalog.load()
    entry = catalog.get(record.internal_secret_id)
    if entry is None:
        raise SourceConnectionError("revalidation_required", "The bound secret is no longer available; choose a new binding.", status_code=409)
    from brain_ds.connectors.secrets.providers import get_provider_adapter
    from brain_ds.connectors.secrets.providers.google_sheets import RAW_VALUE_METADATA_KEY

    adapter = get_provider_adapter(entry.kind)
    metadata = dict(entry.metadata)
    raw_value = catalog.get_raw(entry.handle)
    if entry.kind == "google-sheets-json" and raw_value:
        metadata[RAW_VALUE_METADATA_KEY] = raw_value
    try:
        probe_result = adapter.probe(entry.handle, metadata)
    except Exception as exc:
        failed = replace(
            record,
            validation_status="invalid",
            validation={"validated_at": _now(), "error_code": "validation_failed"},
        )
        records.upsert(failed)
        _project_binding(store, graph_id, source_node_id, failed.to_projection())
        raise SourceConnectionError("validation_failed", "Connection validation failed. Check sharing and credentials, then retry.") from exc
    provider_mapping: dict[str, Any] = {}
    if entry.kind in {"google-sheets-json", "aws-google-sheets"}:
        if isinstance(probe_result, dict) and probe_result.get("spreadsheet_id"):
            provider_mapping["spreadsheet_id"] = str(probe_result["spreadsheet_id"])
        elif metadata.get("spreadsheet_id"):
            provider_mapping["spreadsheet_id"] = str(metadata["spreadsheet_id"])
        if metadata.get("sheet_range"):
            provider_mapping["sheet_range"] = str(metadata["sheet_range"])
    valid = replace(
        record,
        provider_mapping=provider_mapping,
        validation_status="valid",
        validation={"validated_at": _now(), "error_code": None},
    )
    records.upsert(valid)
    projection = valid.to_projection()
    _project_binding(store, graph_id, source_node_id, projection)
    return {"status": "ok", "binding": projection}


def unbind_source_connection(store: GraphStore, graph_id: str, workspace_root: str | Path, source_node_id: str) -> dict[str, Any]:
    _source_by_id(store, graph_id, source_node_id)
    SecretBindingStore(workspace_root).delete(graph_id, source_node_id)
    _project_binding(store, graph_id, source_node_id, None)
    return {
        "status": "ok",
        "binding": {
            "validation_status": "unbound",
            "documentation_status": "not_started",
            "writeback_status": "idle",
            "requires_binding": True,
        },
    }


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def as_validation_error(exc: SourceConnectionError) -> ValidationError:
    return ValidationError(code=-32000, message=exc.to_public()["message"])
