from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
import logging
import unicodedata
from pathlib import Path
from typing import Any

import brain_ds.mcp.completeness as completeness
import brain_ds.mcp.grounding as grounding
import brain_ds.scoring.similarity as similarity
import brain_ds.workspaces as workspace_registry
from brain_ds.connectors import CsvConnector, PostgresConnector, SQLiteConnector
from brain_ds.connectors.google_sheets_connector import GoogleSheetsConnector
from brain_ds.connectors.change_detection import (
    build_change_detection,
    scope_baseline_for_table,
    should_emit_change_detection,
)
from brain_ds.connectors.secrets import SecretCatalog, SecretManifestError
from brain_ds.connectors.secrets.redaction import redact_secrets
from brain_ds.mcp.security import (
    TOOL_SCHEMAS,
    SecurityError,
    ValidationError,
    error_boundary,
    is_workspace_admin,
    validate_card_sections,
    validate_path_within_root,
    validate_tool_input,
)
from brain_ds.scoring.embedder import get_default_model, node_text
from brain_ds.ontology.entity_types import EntityType
from brain_ds.store.errors import CorruptVectorError, GraphAlreadyExistsError, GraphNotFoundError, StoreError
from brain_ds.store.graph_store import GraphStore
from brain_ds.verify.edge_snapshot import (
    build_edge_snapshot,
    decode_cursor,
    enforce_large_graph_guard,
    enforce_payload_size_guard,
    normalize_limit,
    validate_neighborhood,
)
from brain_ds.verify.ledger_calibration import _should_flag_for_confirmation


logger = logging.getLogger(__name__)


def _node_to_dict(node: Any) -> dict[str, Any]:
    return asdict(node)


def _edge_to_dict(edge: Any) -> dict[str, Any]:
    return asdict(edge)


def _details_text(details: dict[str, Any]) -> str:
    return " ".join(str(value).lower() for value in details.values())


def _normalize_optional_filter(value: Any) -> Any:
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


_INTERNAL_NODE_TYPES = {EntityType.DATA_CONTAINER.value, EntityType.DATA_FIELD.value}
_CONTAINER_KINDS = {"schema", "table", "view", "workbook", "spreadsheet", "worksheet", "range", "endpoint", "stream", "file"}
_FIELD_KINDS = {"column", "field"}


def _is_internal_type(node_type: str | None) -> bool:
    return node_type in _INTERNAL_NODE_TYPES


def _row_type(row: Any) -> str | None:
    if isinstance(row, dict):
        return row.get("type")
    return getattr(row, "type", None)


def _row_parent_id(row: Any) -> str | None:
    if isinstance(row, dict):
        return row.get("parent_id")
    return getattr(row, "parent_id", None)


def _node_descends_from_source(rows_by_id: dict[str, Any], *, node_id: str, source_id: str) -> bool:
    current_id: str | None = node_id
    visited: set[str] = set()
    while current_id:
        if current_id in visited:
            return False
        visited.add(current_id)
        if current_id == source_id:
            return True
        row = rows_by_id.get(current_id)
        if row is None:
            return False
        current_id = _row_parent_id(row)
    return False


def _validate_internal_kind(node_type: str, details: Any) -> str:
    if not isinstance(details, dict):
        raise ValidationError(code=-32602, message=f"{node_type} details.kind is required")
    kind = details.get("kind")
    if not isinstance(kind, str) or not kind.strip():
        raise ValidationError(code=-32602, message=f"{node_type} details.kind is required")
    kind = kind.strip()
    if node_type == EntityType.DATA_CONTAINER.value and kind not in _CONTAINER_KINDS:
        allowed = ", ".join(sorted(_CONTAINER_KINDS))
        raise ValidationError(code=-32602, message=f"DataContainer details.kind must be one of: {allowed}")
    if node_type == EntityType.DATA_FIELD.value and kind not in _FIELD_KINDS:
        allowed = ", ".join(sorted(_FIELD_KINDS))
        raise ValidationError(code=-32602, message=f"DataField details.kind must be one of: {allowed}")
    return kind


def _assert_data_source_ancestor(rows_by_id: dict[str, Any], parent_id: str) -> None:
    current_id: str | None = parent_id
    visited: set[str] = set()
    while current_id:
        if current_id in visited:
            raise ValidationError(code=-32000, message="scope_violation: parent chain cycle before Data Source ancestor")
        visited.add(current_id)
        parent = rows_by_id.get(current_id)
        if parent is None:
            raise ValidationError(code=-32000, message="scope_violation: internal nodes require a Data Source ancestor")
        if _row_type(parent) == EntityType.DATA_SOURCE.value:
            return
        current_id = _row_parent_id(parent)
    raise ValidationError(code=-32000, message="scope_violation: internal nodes require a Data Source ancestor")


def _validate_internal_node_payload(
    *,
    rows: list[Any],
    node_id: str,
    payload: dict[str, Any],
) -> None:
    rows_by_id = {row.id: row for row in rows}
    existing = rows_by_id.get(node_id)
    node_type = payload.get("type") or (existing.type if existing is not None else None)
    if not _is_internal_type(node_type):
        return

    details = payload.get("details") if "details" in payload else (existing.details if existing is not None else None)
    _validate_internal_kind(str(node_type), details)

    parent_id = payload.get("parent_id") if "parent_id" in payload else (existing.parent_id if existing is not None else None)
    if not isinstance(parent_id, str) or not parent_id.strip():
        raise ValidationError(code=-32000, message="scope_violation: internal nodes require parent_id under a Data Source")

    depth = payload.get("depth") if "depth" in payload else (existing.depth if existing is not None else None)
    if not isinstance(depth, int) or depth < 1:
        raise ValidationError(code=-32602, message="Internal node depth must be an integer >= 1")

    rows_by_id[node_id] = {"type": node_type, "parent_id": parent_id}
    _assert_data_source_ancestor(rows_by_id, parent_id)


def _source_kind_from_node(node: dict[str, Any]) -> str:
    details = node.get("details") or {}
    if isinstance(details.get("source_kind"), str):
        return details["source_kind"]
    connection = details.get("connection")
    if isinstance(connection, dict):
        return str(connection.get("kind") or "")
    return ""


def _build_internal_subtree(rows: list[Any], source_id: str) -> list[dict[str, Any]]:
    rows_by_id = {row.id: row for row in rows}
    internal_rows = [
        row
        for row in rows
        if _is_internal_type(row.type) and _node_descends_from_source(rows_by_id, node_id=row.id, source_id=source_id)
    ]
    children_by_parent: dict[str | None, list[Any]] = {}
    for row in internal_rows:
        children_by_parent.setdefault(row.parent_id, []).append(row)
    for children in children_by_parent.values():
        children.sort(key=lambda row: (row.depth, row.label.lower(), row.id))

    def _build(row: Any) -> dict[str, Any]:
        item = _node_to_dict(row)
        item["children"] = [_build(child) for child in children_by_parent.get(row.id, [])]
        return item

    return [_build(row) for row in children_by_parent.get(source_id, [])]


def _receipt_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


_DEFAULT_LIST_LIMIT = 50
_MAX_LIST_LIMIT = 200


def _pagination_params(params: dict[str, Any]) -> tuple[int, int, bool]:
    limit = int(params.get("limit") or _DEFAULT_LIST_LIMIT)
    offset = int(params.get("offset") or 0)
    return min(max(limit, 1), _MAX_LIST_LIMIT), max(offset, 0), bool(params.get("compact", False))


def _page(items: list[dict[str, Any]], *, limit: int, offset: int) -> tuple[list[dict[str, Any]], int | None]:
    page = items[offset: offset + limit]
    next_offset = offset + limit if offset + limit < len(items) else None
    return page, next_offset


def _project_root_from_store_path(store_path: str) -> Path:
    path = Path(store_path)
    if path.parent.name == ".brain_ds":
        return path.parent.parent
    return path.parent


def _enqueue_tool_receipt(
    store: GraphStore,
    *,
    graph_id: str,
    tool: str,
    status: str,
    target_id: str | None,
    params_summary: str,
) -> None:
    store.enqueue_event(
        "tool.invoked",
        graph_id,
        {
            "timestamp": _receipt_now(),
            "tool": tool,
            "params_summary": params_summary,
            "status": status,
            "graph_id": graph_id,
            "target_id": target_id,
        },
    )


@error_boundary
def list_graphs(store: GraphStore, params: dict[str, Any]) -> list[dict[str, Any]] | dict[str, Any]:
    validate_tool_input("list_graphs", params, TOOL_SCHEMAS["list_graphs"])
    rows = store.list_graphs()
    return [asdict(row) for row in rows]


def _load_secret_catalog(store: GraphStore) -> SecretCatalog:
    """Load the workspace secret catalog, failing closed on schema violations."""
    project_root = _project_root_from_store_path(store.path)
    catalog = SecretCatalog(project_root)
    try:
        catalog.load()
    except SecretManifestError as exc:
        raise ValidationError(code=-32000, message=f"Secret manifest error: {exc}") from exc
    return catalog


@error_boundary
def list_secret_handles(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    """List workspace secret handles and redacted metadata (admin only)."""
    validated = validate_tool_input("list_secret_handles", params, TOOL_SCHEMAS["list_secret_handles"])
    try:
        is_workspace_admin(params)
    except SecurityError:
        store.log_audit("list_secret_handles", params, "error")
        raise
    catalog = _load_secret_catalog(store)
    limit, offset, compact = _pagination_params(validated)

    handles = []
    for entry in catalog.list_handles():
        item = {
                "handle": entry.handle,
                "kind": entry.kind,
                "created_at": entry.created_at,
            }
        if not compact:
            item["metadata"] = redact_secrets(entry.metadata)
        handles.append(item)

    store.log_audit("list_secret_handles", params, "ok")
    page, next_offset = _page(handles, limit=limit, offset=offset)
    return {"handles": page, "total": len(handles), "limit": limit, "offset": offset, "next_offset": next_offset}


@error_boundary
def validate_secret_handle(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    """Validate a single secret handle. Dry-run by default; probe is opt-in."""
    validated = validate_tool_input(
        "validate_secret_handle", params, TOOL_SCHEMAS["validate_secret_handle"]
    )
    try:
        is_workspace_admin(params)
    except SecurityError:
        store.log_audit("validate_secret_handle", validated, "error")
        raise
    catalog = _load_secret_catalog(store)

    handle = validated["handle"]
    entry = catalog.get(handle)
    if entry is None:
        store.log_audit("validate_secret_handle", validated, "error")
        return {
            "valid": False,
            "status": "not_found",
            "reason": "Secret handle is not registered in this workspace.",
        }

    try:
        from brain_ds.connectors.secrets.providers import get_provider_adapter

        adapter = get_provider_adapter(entry.kind)
        adapter.validate(entry.metadata)
        if validated.get("probe"):
            adapter.probe(entry.handle, entry.metadata)
    except ValidationError as exc:
        store.log_audit("validate_secret_handle", validated, "error")
        return {"valid": False, "status": "invalid", "reason": str(exc)}

    reason = "Secret handle is valid and reachable" if validated.get("probe") else "Secret handle is valid (dry-run)"
    store.log_audit("validate_secret_handle", validated, "ok")
    return {"valid": True, "status": "ok", "reason": reason}


@error_boundary
def create_graph(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    validated = validate_tool_input("create_graph", params, TOOL_SCHEMAS["create_graph"])
    try:
        graph_id = store.create_graph(
            validated["graph_id"],
            name=validated.get("name"),
            project=validated.get("project", ""),
            workspace_root="",
            workspace_path="",
        )
        result = asdict(next(meta for meta in store.list_graphs() if meta.id == graph_id))
        store.log_audit("create_graph", validated, "ok")
        store.enqueue_event("graph.created", graph_id, result)
        return result
    except GraphAlreadyExistsError as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc
    except StoreError as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc


@error_boundary
def import_graph(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    validated = validate_tool_input("import_graph", params, TOOL_SCHEMAS["import_graph"])
    try:
        source_path = validate_path_within_root(
            validated["file_path"],
            _project_root_from_store_path(store.path),
        )
        payload = json.loads(source_path.read_text(encoding="utf-8"))
        graph_id = store.import_json(payload, graph_id=validated.get("graph_id"))
        result = {
            "graph_id": graph_id,
            "node_count": len(payload.get("nodes", [])),
            "edge_count": len(payload.get("edges", [])),
        }
        store.log_audit("import_graph", validated, "ok")
        store.enqueue_event("graph.imported", graph_id, result)
        return result
    except (SecurityError, FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc
    except StoreError as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc


@error_boundary
def list_nodes(store: GraphStore, params: dict[str, Any]) -> list[dict[str, Any]] | dict[str, Any]:
    validated = validate_tool_input("list_nodes", params, TOOL_SCHEMAS["list_nodes"])
    try:
        rows = store.query_nodes(
            validated["graph_id"],
            type=_normalize_optional_filter(validated.get("type")),
            supertype=_normalize_optional_filter(validated.get("supertype")),
            parent_id=_normalize_optional_filter(validated.get("parent_id")),
        )
        details_kind = _normalize_optional_filter(validated.get("details_kind"))
        if details_kind is not None:
            rows = [row for row in rows if (row.details or {}).get("kind") == details_kind]
        source_id = _normalize_optional_filter(validated.get("source_id"))
        if source_id is not None:
            all_rows = store.query_nodes(validated["graph_id"])
            rows_by_id = {row.id: row for row in all_rows}
            rows = [row for row in rows if _node_descends_from_source(rows_by_id, node_id=row.id, source_id=source_id)]
    except GraphNotFoundError as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc
    return [_node_to_dict(row) for row in rows]


@error_boundary
def get_node(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    validated = validate_tool_input("get_node", params, TOOL_SCHEMAS["get_node"])
    graph_id = validated["graph_id"]
    node_id = validated["node_id"]
    try:
        rows = store.query_nodes(graph_id)
    except GraphNotFoundError as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc

    for row in rows:
        if row.id == node_id:
            return _node_to_dict(row)

    raise ValidationError(code=-32000, message=f"Node '{node_id}' not found in graph '{graph_id}'")


def _normalize_query(text: str) -> str:
    """Normalize text for accent-insensitive comparison."""
    nfd = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")


def _search_graph_lexical_rows(store: GraphStore, graph_id: str, raw_query: str, rows: list[Any]) -> list[dict[str, Any]]:
    """Return the current lexical search result exactly as before."""
    fts_ids = store.search_nodes_fts(graph_id, raw_query)

    if fts_ids is not None and len(fts_ids) > 0:
        id_set = set(fts_ids)
        return [_node_to_dict(row) for row in rows if row.id in id_set]

    query = _normalize_query(raw_query)

    def _match(row: Any) -> bool:
        return (
            query in _normalize_query(row.label)
            or query in _normalize_query(row.type)
            or query in _normalize_query(_details_text(row.details))
        )

    return [_node_to_dict(row) for row in rows if _match(row)]


def _fuse_search_rows(
    rows: list[Any],
    lexical_rows: list[dict[str, Any]],
    dense_hits: list[Any],
) -> list[dict[str, Any]]:
    """Fuse lexical and dense ranks with RRF, deduping by node id."""
    rows_by_id = {row.id: row for row in rows}
    lexical_ids: list[str] = []
    for item in lexical_rows:
        node_id = item.get("id")
        if isinstance(node_id, str) and node_id in rows_by_id:
            lexical_ids.append(node_id)

    dense_ids: list[str] = []
    for hit in dense_hits:
        node_id = getattr(hit, "target_id", None)
        if isinstance(node_id, str) and node_id in rows_by_id:
            dense_ids.append(node_id)

    if not lexical_ids and not dense_ids:
        return lexical_rows

    lexical_rank = {node_id: rank + 1 for rank, node_id in enumerate(lexical_ids)}
    dense_rank = {node_id: rank + 1 for rank, node_id in enumerate(dense_ids)}
    lexical_sentinel = len(lexical_ids) + 1

    candidates: list[tuple[float, str]] = []
    seen: set[str] = set()
    for node_id in lexical_ids + dense_ids:
        if node_id in seen:
            continue
        seen.add(node_id)
        rrf = 1.0 / (60 + lexical_rank.get(node_id, lexical_sentinel))
        dense_rank_value = dense_rank.get(node_id)
        if dense_rank_value is not None:
            rrf += 1.0 / (60 + dense_rank_value)
        candidates.append((rrf, node_id))

    candidates.sort(key=lambda item: (-item[0], item[1]))
    return [_node_to_dict(rows_by_id[node_id]) for _, node_id in candidates]


@error_boundary
def search_graph(store: GraphStore, params: dict[str, Any]) -> list[dict[str, Any]] | dict[str, Any]:
    validated = validate_tool_input("search_graph", params, TOOL_SCHEMAS["search_graph"])
    graph_id = validated["graph_id"]
    raw_query = validated["query"].strip()

    try:
        rows = store.query_nodes(graph_id)
    except GraphNotFoundError as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc

    lexical_rows = _search_graph_lexical_rows(store, graph_id, raw_query, rows)

    model = get_default_model()
    if model is None:
        return lexical_rows

    try:
        limit = similarity.DEFAULT_LIMIT
        query_vector = model.embed(raw_query)
        dense_hits = store.nearest_to_vector(
            graph_id,
            query_vector,
            k=max(limit * 3, 30),
        )
    except Exception:
        return lexical_rows

    if not dense_hits:
        return lexical_rows

    return _fuse_search_rows(rows, lexical_rows, dense_hits)


@error_boundary
def list_data_sources(store: GraphStore, params: dict[str, Any]) -> list[dict[str, Any]] | dict[str, Any]:
    validated = validate_tool_input("list_data_sources", params, TOOL_SCHEMAS["list_data_sources"])
    try:
        rows = store.query_nodes(validated["graph_id"], type="Data Source")
    except GraphNotFoundError as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc
    return [_node_to_dict(row) for row in rows]


@error_boundary
def update_node(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    validated = validate_tool_input("update_node", params, TOOL_SCHEMAS["update_node"])
    if "card_sections" in validated:
        validated["card_sections"] = validate_card_sections(validated["card_sections"])
    graph_id = validated["graph_id"]
    node_id = validated["node_id"]

    try:
        is_create = False
        try:
            get_node.__wrapped__(store, {"graph_id": graph_id, "node_id": node_id})
        except ValidationError as exc:
            if "not found in graph" in exc.message:
                is_create = True
            else:
                raise

        payload = {"id": node_id}
        for field in ("label", "type", "details", "card_sections", "supertype", "parent_id", "depth"):
            if field in validated:
                payload[field] = validated[field]

        rows = store.query_nodes(graph_id)
        _validate_internal_node_payload(rows=rows, node_id=node_id, payload=payload)

        store.upsert_node(graph_id, payload)
        result = get_node.__wrapped__(store, {"graph_id": graph_id, "node_id": node_id})

        # Embedding producer hook: fire-and-forget, never fail the write.
        try:
            _model = get_default_model()
            if _model is not None:
                # Re-fetch all nodes and locate this one for the canonical NodeRow.
                for _node_row in store.query_nodes(graph_id):
                    if _node_row.id == node_id:
                        _vec = _model.embed(node_text(_node_row))
                        store.upsert_embedding(graph_id, "node", node_id, _model.name, _vec)
                        break
        except Exception:
            import logging as _logging
            _logging.getLogger(__name__).debug(
                "Embedding producer hook failed for node %s; skipping.", node_id, exc_info=True
            )

        store.log_audit("update_node", validated, "ok")
        store.enqueue_event(
            "node.created" if is_create else "node.updated",
            graph_id,
            result,
        )
        changed_fields = [
            field
            for field in ("label", "type", "details", "card_sections", "supertype", "parent_id", "depth")
            if field in validated
        ]
        _enqueue_tool_receipt(
            store,
            graph_id=graph_id,
            tool="update_node",
            status="ok",
            target_id=node_id,
            params_summary=f"node={node_id} fields={','.join(changed_fields) or 'none'}",
        )
        return result
    except ValidationError:
        raise
    except StoreError as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc


@error_boundary
def add_edge(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    validated = validate_tool_input("add_edge", params, TOOL_SCHEMAS["add_edge"])
    graph_id = validated["graph_id"]

    try:
        try:
            source_node = get_node.__wrapped__(store, {"graph_id": graph_id, "node_id": validated["source"]})
        except ValidationError as exc:
            if exc.message.startswith("Graph '"):
                raise
            raise ValidationError(code=-32000, message=f"Source node '{validated['source']}' not found")

        try:
            target_node = get_node.__wrapped__(store, {"graph_id": graph_id, "node_id": validated["target"]})
        except ValidationError as exc:
            if exc.message.startswith("Graph '"):
                raise
            raise ValidationError(code=-32000, message=f"Target node '{validated['target']}' not found")

        existing_edges = store.query_edges(
            graph_id,
            source=validated["source"],
            target=validated["target"],
        )

        edge_input = {
            "source": validated["source"],
            "target": validated["target"],
            "label": validated["label"],
        }
        if "weight" in validated:
            edge_input["weight"] = validated["weight"]
        # "confidence" is the agent-facing alias (suggest_connections score is
        # the natural seed); it lands in the same weight column.
        elif "confidence" in validated:
            edge_input["weight"] = validated["confidence"]
        if "reasons" in validated:
            edge_input["reasons"] = validated["reasons"]
        if "evidence" in validated:
            edge_input["evidence_ids"] = [str(item) for item in validated["evidence"]]

        store.upsert_edge(graph_id, edge_input)
        edge = store.query_edges(graph_id, source=validated["source"], target=validated["target"])[-1]
        try:
            flagged_reason = _should_flag_for_confirmation(
                label=edge.label,
                source_type=source_node.get("type"),
                target_type=target_node.get("type"),
                weight=edge.weight,
                target_kind="edge",
            )
            store.append_ledger(
                graph_id,
                target_id=edge.edge_id,
                target_type="edge",
                status="needs-confirmation" if flagged_reason else "inferred",
                initial_confidence=edge.weight,
                current_confidence=edge.weight,
                relationship_label=edge.label,
                source_node_id=edge.source,
                target_node_id=edge.target,
                source_node_type=source_node.get("type"),
                target_node_type=target_node.get("type"),
                evidence_ids=edge.evidence_ids or [],
                captured_by="import" if edge.weight is None else "mapper",
                captured_at=datetime.now(timezone.utc).isoformat(),
                flagged_reason=flagged_reason,
                provenance="seed",
            )
        except Exception:
            logger.warning(
                "confidence_ledger side-write failed for %s; edge persisted",
                edge.edge_id,
                exc_info=True,
            )
        store.log_audit("add_edge", validated, "ok")
        result = _edge_to_dict(edge)
        store.enqueue_event(
            "edge.created" if len(existing_edges) == 0 else "edge.updated",
            graph_id,
            result,
        )
        _enqueue_tool_receipt(
            store,
            graph_id=graph_id,
            tool="add_edge",
            status="ok",
            target_id=f"{validated['source']}->{validated['target']}",
            params_summary=f"edge={validated['source']}->{validated['target']} label={validated['label']}",
        )
        return result
    except ValidationError as exc:
        _enqueue_tool_receipt(
            store,
            graph_id=validated.get("graph_id", ""),
            tool="add_edge",
            status="error",
            target_id=f"{validated.get('source', '?')}->{validated.get('target', '?')}",
            params_summary=f"edge={validated.get('source', '?')}->{validated.get('target', '?')} error={exc.message}",
        )
        _safe_log_error(store, "add_edge", validated)
        raise exc
    except StoreError as exc:
        _safe_log_error(store, "add_edge", validated)
        raise ValidationError(code=-32000, message=str(exc)) from exc


@error_boundary
def delete_node(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    validated = validate_tool_input("delete_node", params, TOOL_SCHEMAS["delete_node"])
    graph_id = validated["graph_id"]
    node_id = validated["node_id"]

    try:
        deleted = store.delete_node(graph_id, node_id)
        if deleted == 0:
            raise ValidationError(code=-32000, message=f"Node '{node_id}' not found in graph '{graph_id}'")

        result = {"graph_id": graph_id, "node_id": node_id, "deleted": deleted}
        store.log_audit("delete_node", validated, "ok")
        store.enqueue_event(
            "node.deleted",
            graph_id,
            {"id": node_id, "graph_id": graph_id},
        )
        _enqueue_tool_receipt(
            store,
            graph_id=graph_id,
            tool="delete_node",
            status="ok",
            target_id=node_id,
            params_summary=f"node={node_id}",
        )
        return result
    except ValidationError as exc:
        _enqueue_tool_receipt(
            store,
            graph_id=graph_id,
            tool="delete_node",
            status="error",
            target_id=node_id,
            params_summary=f"node={node_id} error={exc.message}",
        )
        _safe_log_error(store, "delete_node", validated)
        raise exc
    except StoreError as exc:
        _safe_log_error(store, "delete_node", validated)
        raise ValidationError(code=-32000, message=str(exc)) from exc


@error_boundary
def delete_edge(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    validated = validate_tool_input("delete_edge", params, TOOL_SCHEMAS["delete_edge"])
    graph_id = validated["graph_id"]
    source = validated["source"]
    target = validated["target"]

    try:
        deleted = store.delete_edge(graph_id, source, target)
        if deleted == 0:
            raise ValidationError(code=-32000, message=f"Edge '{source}->{target}' not found in graph '{graph_id}'")

        result = {"graph_id": graph_id, "source": source, "target": target, "deleted": deleted}
        store.log_audit("delete_edge", validated, "ok")
        store.enqueue_event(
            "edge.deleted",
            graph_id,
            {"id": f"{source}->{target}", "graph_id": graph_id, "source": source, "target": target},
        )
        _enqueue_tool_receipt(
            store,
            graph_id=graph_id,
            tool="delete_edge",
            status="ok",
            target_id=f"{source}->{target}",
            params_summary=f"edge={source}->{target}",
        )
        return result
    except ValidationError as exc:
        _enqueue_tool_receipt(
            store,
            graph_id=graph_id,
            tool="delete_edge",
            status="error",
            target_id=f"{source}->{target}",
            params_summary=f"edge={source}->{target} error={exc.message}",
        )
        _safe_log_error(store, "delete_edge", validated)
        raise exc
    except StoreError as exc:
        _safe_log_error(store, "delete_edge", validated)
        raise ValidationError(code=-32000, message=str(exc)) from exc


@error_boundary
def suggest_connections(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    validated = validate_tool_input("suggest_connections", params, TOOL_SCHEMAS["suggest_connections"])
    graph_id = validated["graph_id"]
    node_id = validated["node_id"]
    limit = validated.get("limit", similarity.DEFAULT_LIMIT)

    try:
        nodes = store.query_nodes(graph_id)
        edges = store.query_edges(graph_id)
        evidence_rows = store.search_evidence(graph_id)
    except GraphNotFoundError as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc

    evidence_items = [{"id": row.id, "text": row.content} for row in evidence_rows]

    # Build dense ranks via nearest_embeddings. CorruptVectorError (focus has no
    # embedding) => fall back to lexical-only (dense_ranks=None).
    dense_ranks: dict[str, int] | None = None
    dense_scores: dict[str, float] | None = None
    k = max(int(limit) * 3, 30)
    try:
        hits = store.nearest_embeddings(graph_id, node_id, k=k)
        dense_ranks = {hit.target_id: rank + 1 for rank, hit in enumerate(hits)}
        dense_scores = {hit.target_id: hit.score for hit in hits}
    except CorruptVectorError:
        dense_ranks = None
        dense_scores = None

    try:
        calibration_report = grounding.get_calibration_report()
        return similarity.suggest_connections_for_node(
            nodes,
            edges,
            node_id,
            threshold=validated.get("threshold", similarity.DEFAULT_THRESHOLD),
            limit=limit,
            minimum_shared_tokens=validated.get(
                "minimum_shared_tokens", similarity.DEFAULT_MIN_SHARED_TOKENS
            ),
            evidence_items=evidence_items,
            dense_ranks=dense_ranks,
            dense_scores=dense_scores,
            calibration_report=calibration_report,
        )
    except KeyError as exc:
        raise ValidationError(code=-32000, message=f"Node '{node_id}' not found in graph '{graph_id}'") from exc


@error_boundary
def get_weak_edges(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    validated = validate_tool_input("get_weak_edges", params, TOOL_SCHEMAS["get_weak_edges"])
    graph_id = validated["graph_id"]
    max_confidence = float(validated.get("max_confidence", 0.4))
    try:
        edges = store.query_edges(graph_id)
    except GraphNotFoundError as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc

    weak = [
        {
            "edge_id": edge.edge_id,
            "source": edge.source,
            "target": edge.target,
            "label": edge.label,
            "confidence": edge.weight,
            "reasons": edge.reasons or [],
            "evidence_ids": edge.evidence_ids or [],
        }
        for edge in edges
        if edge.weight is None or float(edge.weight) < max_confidence
    ]
    weak.sort(key=lambda item: (item["confidence"] is not None, item["confidence"] or 0.0))
    return {
        "graph_id": graph_id,
        "max_confidence": max_confidence,
        "total_edges": len(edges),
        "weak_edges": weak,
    }


@error_boundary
def assess_completeness(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    validated = validate_tool_input("assess_completeness", params, TOOL_SCHEMAS["assess_completeness"])
    graph_id = validated["graph_id"]
    try:
        nodes = store.query_nodes(graph_id)
    except GraphNotFoundError as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc
    result = completeness.assess_graph_completeness(nodes)
    return {"graph_id": graph_id, **result}


@error_boundary
def list_workspaces(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    validated = validate_tool_input("list_workspaces", params, TOOL_SCHEMAS["list_workspaces"])
    limit, offset, compact = _pagination_params(validated)
    active_root = _project_root_from_store_path(store.path).resolve()
    active_key = workspace_registry.normalize_root(active_root)

    entries: list[dict[str, Any]] = []
    active_registered = False
    for entry in workspace_registry.list_workspaces():
        is_active = workspace_registry.normalize_root(entry["path"]) == active_key
        active_registered = active_registered or is_active
        item = {"path": entry["path"], "name": entry.get("name", ""), "active": is_active}
        if not compact:
            item = {**entry, "active": is_active}
        entries.append(item)
    page, next_offset = _page(entries, limit=limit, offset=offset)

    return {
        "active_project_root": str(active_root),
        "active_registered": active_registered,
        "workspaces": page,
        "total": len(entries),
        "limit": limit,
        "offset": offset,
        "next_offset": next_offset,
    }


def _normalize_edge_labels(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise ValidationError(code=-32602, message="label must be a string or array of strings")


def _cursor_tuple(raw_cursor: Any) -> tuple[str, str] | None:
    if raw_cursor is None:
        return None
    decoded = decode_cursor(str(raw_cursor))
    return str(decoded["last_label"]), str(decoded["last_edge_id"])


@error_boundary
def snapshot_edges(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    validated = validate_tool_input("snapshot_edges", params, TOOL_SCHEMAS["snapshot_edges"])
    graph_id = validated["graph_id"]
    raw_mode = validated.get("mode")
    mode = str(raw_mode or "sample")
    if mode not in {"sample", "evidence_ranked", "anomaly", "suspicious", "calibration"}:
        raise ValidationError(code=-32602, message="mode must be sample, evidence_ranked, anomaly, suspicious, or calibration")
    if mode == "anomaly":
        mode = "suspicious"
    try:
        limit = normalize_limit(validated.get("limit"))
        validate_neighborhood(validated.get("neighborhood"))
        labels = _normalize_edge_labels(validated.get("label"))
        cursor = _cursor_tuple(validated.get("cursor"))

        # Large-graph guard: detect whether the caller supplied any narrowing signal.
        # An explicit limit, explicit mode, or any filter bypasses the guard.
        has_explicit_limit = validated.get("limit") is not None
        has_explicit_mode = raw_mode is not None
        has_filter = any([
            validated.get("source") is not None,
            validated.get("target") is not None,
            bool(labels),
            validated.get("min_weight") is not None,
            validated.get("max_weight") is not None,
            validated.get("has_evidence") is not None,
            validated.get("neighborhood") is not None,
        ])
        if not has_explicit_limit and not has_explicit_mode and not has_filter:
            total_edge_count = store.get_graph_edge_count(graph_id)
            enforce_large_graph_guard(
                total_edge_count,
                has_explicit_limit=has_explicit_limit,
                has_explicit_mode=has_explicit_mode,
                has_filter=has_filter,
            )

        edges = store.query_edges(
            graph_id,
            source=validated.get("source"),
            target=validated.get("target"),
            labels=labels,
            min_weight=validated.get("min_weight"),
            max_weight=validated.get("max_weight"),
            has_evidence=validated.get("has_evidence"),
            order_by="label_edge_id",
            limit=limit + 1,
            cursor=cursor,
        )
        snapshot = build_edge_snapshot(
            graph_id=graph_id,
            edges=edges,
            mode=mode,
            limit=limit,
            neighborhood=validated.get("neighborhood"),
        )
        enforce_payload_size_guard(snapshot)
        return snapshot
    except GraphNotFoundError as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc
    except ValueError as exc:
        raise ValidationError(code=-32602, message=str(exc)) from exc


@error_boundary
def open_workspace(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    # The store swap lives in the MCP server session (brain_ds/mcp/server.py);
    # this handler only exists so the registry stays the single tool catalog.
    validate_tool_input("open_workspace", params, TOOL_SCHEMAS["open_workspace"])
    raise ValidationError(
        code=-32000,
        message="open_workspace is only available through the MCP server session",
    )


@error_boundary
def run_elicit(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    validate_tool_input("run_elicit", params, TOOL_SCHEMAS["run_elicit"])
    payload = grounding.elicit_context()
    workspace = grounding.build_workspace_context(store)
    payload["workspace"] = workspace
    grounding.apply_documentation_language(payload, workspace)
    return payload


@error_boundary
def map_connections(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    validate_tool_input("map_connections", params, TOOL_SCHEMAS["map_connections"])
    payload = grounding.map_connections_context()
    workspace = grounding.build_workspace_context(store)
    payload["workspace"] = workspace
    grounding.apply_documentation_language(payload, workspace)
    return payload


@error_boundary
def generate_brd(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    validate_tool_input("generate_brd", params, TOOL_SCHEMAS["generate_brd"])
    payload = grounding.generate_brd_context()
    workspace = grounding.build_workspace_context(store)
    payload["workspace"] = workspace
    grounding.apply_documentation_language(payload, workspace)
    return payload


def _get_node_connection(store: GraphStore, graph_id: str, node_id: str) -> dict[str, Any]:
    """Retrieve the 'connection' dict from a Data Source node's details."""
    try:
        node = get_node.__wrapped__(store, {"graph_id": graph_id, "node_id": node_id})
    except ValidationError as exc:
        raise exc

    details = node.get("details") or {}
    connection = details.get("connection")
    if not connection or not isinstance(connection, dict):
        raise ValidationError(
            code=-32000,
            message=(
                f"Node '{node_id}' has no 'connection' descriptor in details. "
                "Supported descriptors: "
                "{{kind: 'sqlite'|'csv'|'tsv', path: '...'}} for file-based sources, "
                "{{kind: 'aws-postgres', secret_handle: '...', database: '...'}} "
                "for AWS RDS Postgres sources, "
                "or {{kind: 'aws-google-sheets', secret_handle: '...', "
                "spreadsheet_id: '...', sheet_range: '...'}} "
                "for Google Sheets sources."
            ),
        )
    return connection


def _get_node_change_detection_state(
    store: GraphStore, graph_id: str, node_id: str
) -> tuple[dict[str, Any] | None, bool]:
    """Return (baseline, has_prior_doc) for a Data Source node.

    None-safe per E-REQ-11: a missing schema_baseline key never raises. The
    baseline lives in the node's details dict; prior documentation is inferred
    from the presence of card_sections.
    """
    try:
        node = get_node.__wrapped__(store, {"graph_id": graph_id, "node_id": node_id})
    except ValidationError:
        return None, False

    details = node.get("details") or {}
    baseline = details.get("schema_baseline")
    if not isinstance(baseline, dict):
        baseline = None
    card_sections = node.get("card_sections")
    has_prior_doc = bool(card_sections)
    return baseline, has_prior_doc


def _resolve_connector(connection: dict[str, Any], project_root: Path):
    """Resolve and validate a connector from a connection descriptor.

    File-based kinds (sqlite, csv, tsv): require a 'path' field validated
    within project_root.

    Secret-based kinds (aws-postgres): require a 'secret_handle' field that
    references a registered entry in the workspace SecretCatalog. The adapter
    is called to resolve the handle to typed connection params; no credentials
    are written to any log or response.
    """
    kind = connection.get("kind", "").lower()

    # ------------------------------------------------------------------
    # Secret-based kinds — dispatch through adapter + SecretCatalog
    # ------------------------------------------------------------------
    if kind == "aws-postgres":
        secret_handle = connection.get("secret_handle")
        if not secret_handle:
            raise ValidationError(
                code=-32000,
                message=(
                    "aws-postgres connection descriptor missing 'secret_handle'. "
                    "Set details.connection.secret_handle to the registered secret handle name."
                ),
            )

        # Load the SecretCatalog from the workspace root
        catalog = SecretCatalog(project_root)
        try:
            catalog.load()
        except SecretManifestError as exc:
            raise ValidationError(
                code=-32000,
                message=f"Failed to load secret catalog: {exc}",
            ) from exc

        entry = catalog.get(secret_handle)
        if entry is None:
            raise ValidationError(
                code=-32000,
                message=(
                    f"Secret handle {secret_handle!r} not found in the workspace secret catalog. "
                    "Register it first via the Secrets panel or validate_secret_handle."
                ),
            )

        from brain_ds.connectors.secrets.providers.aws_postgres import AwsPostgresAdapter

        adapter = AwsPostgresAdapter()
        try:
            params = adapter.resolve(secret_handle, entry.metadata)
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError(
                code=-32000,
                message=f"Failed to resolve aws-postgres secret '{secret_handle}': {exc}",
            ) from exc

        return PostgresConnector(params)

    # ------------------------------------------------------------------
    # aws-google-sheets — dispatch through AwsGoogleSheetsAdapter
    # ------------------------------------------------------------------
    if kind == "aws-google-sheets":
        secret_handle = connection.get("secret_handle")
        if not secret_handle:
            raise ValidationError(
                code=-32000,
                message=(
                    "aws-google-sheets connection descriptor missing 'secret_handle'. "
                    "Set details.connection.secret_handle to the registered secret handle name."
                ),
            )

        # Load the SecretCatalog from the workspace root
        catalog = SecretCatalog(project_root)
        try:
            catalog.load()
        except SecretManifestError as exc:
            raise ValidationError(
                code=-32000,
                message=f"Failed to load secret catalog: {exc}",
            ) from exc

        entry = catalog.get(secret_handle)
        if entry is None:
            raise ValidationError(
                code=-32000,
                message=(
                    f"Secret handle {secret_handle!r} not found in the workspace secret catalog. "
                    "Register it first via the Secrets panel or validate_secret_handle."
                ),
            )

        from brain_ds.connectors.secrets.providers.aws_google_sheets import (
            AwsGoogleSheetsAdapter,
        )

        adapter = AwsGoogleSheetsAdapter()
        try:
            params = adapter.resolve(secret_handle, entry.metadata)
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError(
                code=-32000,
                message=f"Failed to resolve aws-google-sheets secret '{secret_handle}': {exc}",
            ) from exc

        return GoogleSheetsConnector(params)

    # ------------------------------------------------------------------
    # File-based kinds — require path within project_root sandbox
    # ------------------------------------------------------------------
    raw_path = connection.get("path", "")

    if not raw_path:
        raise ValidationError(
            code=-32000,
            message=(
                f"Connection descriptor for kind {kind!r} missing 'path'. "
                "Supported file-based kinds: sqlite, csv, tsv. "
                "For AWS Postgres use kind 'aws-postgres' with 'secret_handle'."
            ),
        )

    try:
        safe_path = validate_path_within_root(raw_path, project_root)
    except SecurityError as exc:
        raise ValidationError(code=-32000, message=f"Path sandbox violation: {exc}") from exc
    except FileNotFoundError as exc:
        raise ValidationError(code=-32000, message=f"Source file not found: {raw_path}") from exc

    if kind == "sqlite":
        return SQLiteConnector(safe_path, connection_descriptor=connection)
    elif kind in ("csv", "tsv"):
        return CsvConnector(safe_path)
    else:
        raise ValidationError(
            code=-32000,
            message=f"Unsupported connection kind: {kind!r}. Supported: sqlite, csv, tsv, aws-postgres",
        )


@error_boundary
def list_source_connections(store: GraphStore, params: dict[str, Any]) -> list[dict[str, Any]] | dict[str, Any]:
    """List Data Source nodes that have explorable connection descriptors."""
    validated = validate_tool_input("list_source_connections", params, TOOL_SCHEMAS["list_source_connections"])

    try:
        all_graphs = [g.id for g in store.list_graphs()]
        if not all_graphs:
            return []

        graph_ids = [validated["graph_id"]] if validated.get("graph_id") else all_graphs
        limit, offset, compact = _pagination_params(validated)
        result: list[dict[str, Any]] = []

        for gid in graph_ids:
            try:
                rows = store.query_nodes(gid, type="Data Source")
            except GraphNotFoundError:
                continue
            for row in rows:
                details = row.details or {}
                connection = details.get("connection")
                if connection and isinstance(connection, dict):
                    item = {
                        "graph_id": gid,
                        "node_id": row.id,
                        "label": row.label,
                    }
                    if not compact:
                        item["connection"] = redact_secrets(connection)
                    result.append(item)
    except Exception as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc

    page, next_offset = _page(result, limit=limit, offset=offset)
    return {"connections": page, "total": len(result), "limit": limit, "offset": offset, "next_offset": next_offset}


def _build_doc_bundle(store: GraphStore, graph_id: str, node_id: str) -> dict[str, Any]:
    """DDS-4/DDS-5: Build a joined documentation bundle from child table nodes.

    Returns a compact bundle with per-table columns/fields markdown, sections,
    relationships, and schema_baseline status — no connector needed, no raw FS.
    """
    try:
        all_nodes = store.query_nodes(graph_id)
    except Exception as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc

    node_lookup = {n.id: n for n in all_nodes if n.id}
    source_node = node_lookup.get(node_id)
    if source_node is None:
        raise ValidationError(code=-32000, message=f"Node '{node_id}' not found in graph '{graph_id}'")

    # Collect child nodes (table-level) by parent_id
    child_nodes = sorted(
        [n for n in all_nodes if n.parent_id == node_id],
        key=lambda n: (n.label or n.id or "").lower(),
    )

    tables: list[dict[str, Any]] = []
    for child in child_nodes:
        sections = child.card_sections or []
        columns_markdown = ""
        section_list: list[dict[str, Any]] = []

        def _section_order(s: Any) -> int:
            if isinstance(s, dict):
                return int(s.get("order", 0))
            return int(getattr(s, "order", 0))

        def _section_field(s: Any, field: str) -> str:
            if isinstance(s, dict):
                return str(s.get(field) or "")
            return str(getattr(s, field, "") or "")

        for section in sorted(sections, key=_section_order):
            title = _section_field(section, "title")
            content = _section_field(section, "content")
            section_list.append({"title": title, "content": content})
            title_norm = title.strip().lower()
            if title_norm in ("columns / fields", "columns/fields", "columns", "fields"):
                columns_markdown = content

        child_details = child.details or {}
        tables.append(
            {
                "node_id": child.id,
                "label": child.label or child.id or "",
                "sections": section_list,
                "columns_markdown": columns_markdown,
                "purpose": child_details.get("what", ""),
                "owner": child_details.get("where", ""),
                "refresh": child_details.get("learned", ""),
                "schema_baseline_status": (
                    "baseline-present"
                    if isinstance(child_details.get("schema_baseline"), dict)
                    else "no-baseline"
                ),
            }
        )

    # Collect edges incident to source node for relationships summary
    try:
        all_edges = store.query_edges(graph_id)
    except Exception:
        all_edges = []

    relationships: list[dict[str, Any]] = []
    for edge in all_edges:
        if edge.source == node_id or edge.target == node_id:
            other_id = edge.target if edge.source == node_id else edge.source
            other_node = node_lookup.get(other_id)
            relationships.append(
                {
                    "edge_label": edge.label or "",
                    "source_id": edge.source,
                    "target_id": edge.target,
                    "other_id": other_id,
                    "other_label": other_node.label if other_node else other_id,
                }
            )

    source_details = source_node.details or {}
    return {
        "level": "documentation",
        "graph_id": graph_id,
        "source": {
            "node_id": node_id,
            "label": source_node.label or node_id,
            "schema_baseline": source_details.get("schema_baseline"),
        },
        "tables": tables,
        "relationships": relationships,
    }


def _build_internal_bundle(store: GraphStore, graph_id: str, node_id: str) -> dict[str, Any]:
    try:
        rows = store.query_nodes(graph_id)
    except GraphNotFoundError as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc
    source = next((row for row in rows if row.id == node_id), None)
    if source is None:
        raise ValidationError(code=-32000, message=f"Node '{node_id}' not found in graph '{graph_id}'")
    if source.type != EntityType.DATA_SOURCE.value:
        raise ValidationError(code=-32000, message=f"Node '{node_id}' is not a Data Source")

    source_dict = _node_to_dict(source)
    source_kind = _source_kind_from_node(source_dict)
    return {
        "level": "internal",
        "graph_id": graph_id,
        "source": {
            "node_id": node_id,
            "label": source.label or node_id,
            "details": source.details or {},
        },
        "template": grounding.source_kind_hierarchy_template(source_kind),
        "internal_subtree": _build_internal_subtree(rows, node_id),
    }


@error_boundary
def explore_source(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    """Explore a connected data source by dispatching to the right connector.

    - level='documentation': returns joined doc bundle from child nodes (no connector needed)
    - No container/table args: describe + list_containers
    - container only: list_tables(container)
    - container + table: schema + 5-row preview
    """
    validated = validate_tool_input("explore_source", params, TOOL_SCHEMAS["explore_source"])
    graph_id = validated["graph_id"]
    node_id = validated["node_id"]
    container = validated.get("container")
    table = validated.get("table")
    level = validated.get("level")

    # DDS-4: documentation level is handled before connector resolution —
    # it reads child nodes from the graph store (no raw FS, no connector).
    if level == "documentation":
        return _build_doc_bundle(store, graph_id, node_id)
    if level == "internal":
        return _build_internal_bundle(store, graph_id, node_id)

    # Get the raw (unredacted) connection descriptor — _resolve_connector needs
    # the real secret_handle value for aws-postgres dispatch. The connector
    # itself enforces that credentials never appear in any response (INV-1).
    raw_connection = _get_node_connection(store, graph_id, node_id)
    project_root = _project_root_from_store_path(store.path)
    connector = _resolve_connector(raw_connection, project_root)

    try:
        if container is None:
            # Level 0: describe + list containers
            result: dict[str, Any] = {
                "level": "source",
                "describe": connector.describe(),
                "containers": connector.list_containers(),
            }
        elif table is None:
            # Level 1: list tables in container
            result = {
                "level": "container",
                "container": container,
                "tables": connector.list_tables(container),
            }
        else:
            # Level 2: schema + preview
            schema = connector.get_table_schema(container, table)
            preview = connector.preview(container, table, limit=5)
            result = {
                "level": "table",
                "container": container,
                "table": table,
                "schema": schema,
                "preview": preview,
            }
            # E (change detection): emit ONLY at level==table. Read-only — the
            # baseline is persisted to the graph by the documenter via
            # update_node, never to the source here.
            if should_emit_change_detection(level="table"):
                baseline, has_prior_doc = _get_node_change_detection_state(
                    store, graph_id, node_id
                )
                # A multi-table source stores schema_baseline as a per-table map;
                # select the entry for THIS table (flat single-table baselines
                # pass through unchanged) so the verdict/delta compare like to like.
                scoped_baseline = scope_baseline_for_table(baseline, table)
                # Connector schema is single-table ({"columns": [...]}); scope it
                # under the real table name so the verdict/delta carries it.
                live_schema = {"tables": {table: {"columns": schema.get("columns", [])}}}
                result["change_detection"] = build_change_detection(
                    live_schema=live_schema,
                    baseline=scoped_baseline,
                    has_prior_doc=has_prior_doc,
                )
    except (FileNotFoundError, ValueError, Exception) as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc

    return redact_secrets(result)


@error_boundary
def query_source(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    """Execute a SELECT-only SQL query against an SQLite data source.

    Only SQLite sources are supported. The SQL must be a single SELECT or
    WITH...SELECT statement. Results are capped at 200 rows.
    """
    validated = validate_tool_input("query_source", params, TOOL_SCHEMAS["query_source"])
    graph_id = validated["graph_id"]
    node_id = validated["node_id"]
    sql = validated["sql"]
    limit = int(validated.get("limit") or 200)

    connection = _get_node_connection(store, graph_id, node_id)
    kind = connection.get("kind", "").lower()

    if kind not in ("sqlite", "aws-postgres"):
        raise ValidationError(
            code=-32000,
            message=(
                f"query_source supports SQLite and aws-postgres sources, got kind={kind!r}. "
                "For CSV sources, use explore_source to preview data."
            ),
        )

    project_root = _project_root_from_store_path(store.path)
    connector = _resolve_connector(connection, project_root)

    try:
        result = connector.query(sql, limit=limit)
        return result
    except ValueError as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc
    except Exception as exc:
        raise ValidationError(code=-32000, message=f"Query error: {exc}") from exc


def _safe_log_error(store: GraphStore, tool_name: str, payload: dict[str, Any]) -> None:
    try:
        store.log_audit(tool_name, payload, "error")
    except Exception:
        return


TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    "list_graphs": {
        "handler": list_graphs,
        "schema": TOOL_SCHEMAS["list_graphs"],
        "description": "List available graph metadata",
        "rw": "read",
        "requires_ai_agent": False,
    },
    "create_graph": {
        "handler": create_graph,
        "schema": TOOL_SCHEMAS["create_graph"],
        "description": "Create an empty graph/vault (non-destructive)",
        "rw": "write",
        "requires_ai_agent": False,
    },
    "import_graph": {
        "handler": import_graph,
        "schema": TOOL_SCHEMAS["import_graph"],
        "description": "Import graph JSON from a project-local file",
        "rw": "write",
        "requires_ai_agent": False,
    },
    "list_nodes": {
        "handler": list_nodes,
        "schema": TOOL_SCHEMAS["list_nodes"],
        "description": "List graph nodes with optional filters",
        "rw": "read",
        "requires_ai_agent": False,
    },
    "list_data_sources": {
        "handler": list_data_sources,
        "schema": TOOL_SCHEMAS["list_data_sources"],
        "description": "List only Data Source nodes for a graph",
        "rw": "read",
        "requires_ai_agent": False,
    },
    "get_node": {
        "handler": get_node,
        "schema": TOOL_SCHEMAS["get_node"],
        "description": "Get one node by id",
        "rw": "read",
        "requires_ai_agent": False,
    },
    "search_graph": {
        "handler": search_graph,
        "schema": TOOL_SCHEMAS["search_graph"],
        "description": "Search nodes by substring over label/type/details",
        "rw": "read",
        "requires_ai_agent": False,
    },
    "update_node": {
        "handler": update_node,
        "schema": TOOL_SCHEMAS["update_node"],
        "description": "Create/update node fields and preserve unspecified values",
        "rw": "write",
        "requires_ai_agent": False,
    },
    "add_edge": {
        "handler": add_edge,
        "schema": TOOL_SCHEMAS["add_edge"],
        "description": "Create/update an edge between existing nodes",
        "rw": "write",
        "requires_ai_agent": False,
    },
    "delete_node": {
        "handler": delete_node,
        "schema": TOOL_SCHEMAS["delete_node"],
        "description": "Delete one node by id and emit a live delete event",
        "rw": "write",
        "requires_ai_agent": False,
    },
    "delete_edge": {
        "handler": delete_edge,
        "schema": TOOL_SCHEMAS["delete_edge"],
        "description": "Delete edges between source and target and emit a live delete event",
        "rw": "write",
        "requires_ai_agent": False,
    },
    "suggest_connections": {
        "handler": suggest_connections,
        "schema": TOOL_SCHEMAS["suggest_connections"],
        "description": "Rank compatible nodes for one node so the agent can decide which edges to add",
        "rw": "read",
        "requires_ai_agent": False,
    },
    "assess_completeness": {
        "handler": assess_completeness,
        "schema": TOOL_SCHEMAS["assess_completeness"],
        "description": "Report missing/underspecified entity types and a pre-mapping recommendation",
        "rw": "read",
        "requires_ai_agent": False,
    },
    "get_weak_edges": {
        "handler": get_weak_edges,
        "schema": TOOL_SCHEMAS["get_weak_edges"],
        "description": "List edges with confidence below max_confidence (default 0.4) for periodic audit",
        "rw": "read",
        "requires_ai_agent": False,
    },
    "snapshot_edges": {
        "handler": snapshot_edges,
        "schema": TOOL_SCHEMAS["snapshot_edges"],
        "description": "Read a bounded, retrieval-shaped snapshot of graph edges",
        "rw": "read",
        "requires_ai_agent": False,
    },
    "list_workspaces": {
        "handler": list_workspaces,
        "schema": TOOL_SCHEMAS["list_workspaces"],
        "description": "List globally registered workspaces (project folders) and mark the active one",
        "rw": "read",
        "requires_ai_agent": False,
    },
    "open_workspace": {
        "handler": open_workspace,
        "schema": TOOL_SCHEMAS["open_workspace"],
        "description": "Switch the active workspace to a registered project folder",
        "rw": "write",
        "requires_ai_agent": False,
    },
    "run_elicit": {
        "handler": run_elicit,
        "schema": TOOL_SCHEMAS["run_elicit"],
        "description": "Return elicit grounding context",
        "rw": "read",
        "requires_ai_agent": False,
    },
    "map_connections": {
        "handler": map_connections,
        "schema": TOOL_SCHEMAS["map_connections"],
        "description": "Return map grounding context",
        "rw": "read",
        "requires_ai_agent": False,
    },
    "generate_brd": {
        "handler": generate_brd,
        "schema": TOOL_SCHEMAS["generate_brd"],
        "description": "Return brd grounding context",
        "rw": "read",
        "requires_ai_agent": False,
    },
    "list_source_connections": {
        "handler": list_source_connections,
        "schema": TOOL_SCHEMAS["list_source_connections"],
        "description": "List Data Source nodes that have explorable connection descriptors",
        "rw": "read",
        "requires_ai_agent": False,
    },
    "explore_source": {
        "handler": explore_source,
        "schema": TOOL_SCHEMAS["explore_source"],
        "description": "Explore a connected data source (describe/containers/tables/schema+preview)",
        "rw": "read",
        "requires_ai_agent": False,
    },
    "query_source": {
        "handler": query_source,
        "schema": TOOL_SCHEMAS["query_source"],
        "description": "Execute a SELECT-only SQL query against an SQLite data source (capped at 200 rows)",
        "rw": "read",
        "requires_ai_agent": False,
    },
    "list_secret_handles": {
        "handler": list_secret_handles,
        "schema": TOOL_SCHEMAS["list_secret_handles"],
        "description": "List workspace secret handles and redacted metadata (admin only)",
        "rw": "read",
        "requires_ai_agent": False,
    },
    "validate_secret_handle": {
        "handler": validate_secret_handle,
        "schema": TOOL_SCHEMAS["validate_secret_handle"],
        "description": "Validate a workspace secret handle (dry-run by default; probe opt-in)",
        "rw": "read",
        "requires_ai_agent": False,
    },
}
