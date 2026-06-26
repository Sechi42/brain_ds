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
from brain_ds.currency.gaps import aggregate_gaps
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
from brain_ds.dossier.assembler import assemble_kpi_dossier
from brain_ds.dossier.business_models import BusinessDossierRequest
from brain_ds.dossier.business_read_path import build_business_dossier_payload
from brain_ds.dossier.models import DossierGapInputs, DossierGraphView, KpiDossier, LimitationsFacet
from brain_ds.dossier.serialization import serialize_dossier
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
from brain_ds.verify.ledger_calibration import _should_flag_for_confirmation, calibrate_from_ledger
from brain_ds.retrieval.neighborhood import (
    AnnotatedEdge,
    build_adjacency,
    cluster_routes_to_dict,
    expand_neighborhood,
    ledger_status_to_tier,
    select_cluster_routes,
    sort_edges_by_reliability,
    walk_hierarchy_path,
)
from brain_ds.retrieval.hybrid_router import HybridRetrievalRouter
from brain_ds.retrieval.models import RetrievalCandidate, RetrievalRequest
from brain_ds.retrieval.serialization import serialize_for_llm
from brain_ds.scoring.retrieval import SignalScores


logger = logging.getLogger(__name__)

_KPI_DOSSIER_NODE_BUDGET = 1_000
_KPI_DOSSIER_EDGE_BUDGET = 3_000
_BUSINESS_DOSSIER_QUERY_MAX = 500


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
            grounding.invalidate_graph_calibration(graph_id)
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
        calibration_report = grounding.get_graph_calibration_report(graph_id, store)
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
def get_kpi_dossier(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    """Return a read-only KPI dossier assembled from graph state."""
    validated = validate_tool_input("get_kpi_dossier", params, TOOL_SCHEMAS["get_kpi_dossier"])
    graph_id = validated["graph_id"]
    kpi_node_id = validated["kpi_node_id"]

    try:
        nodes = store.query_nodes(graph_id)
        edges = store.query_edges(graph_id)
    except GraphNotFoundError as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc

    nodes_by_id = {node.id: node for node in nodes}
    kpi = nodes_by_id.get(kpi_node_id)
    if kpi is None:
        raise ValidationError(code=-32000, message=f"Node '{kpi_node_id}' not found in graph '{graph_id}'")
    if kpi.type != EntityType.KPI.value:
        actual_type = kpi.type.replace(" ", "") if isinstance(kpi.type, str) else kpi.type
        raise ValidationError(code=-32602, message=f"Node '{kpi_node_id}' is not a KPI; actual type is {actual_type}")

    if len(nodes) > _KPI_DOSSIER_NODE_BUDGET or len(edges) > _KPI_DOSSIER_EDGE_BUDGET:
        return serialize_dossier(
            KpiDossier(
                kpi=kpi,
                limitations=LimitationsFacet(
                    truncated=True,
                    truncation_reason=(
                        f"Skipped expensive dossier scans because graph size exceeds PR1 guard "
                        f"(nodes={len(nodes)}/{_KPI_DOSSIER_NODE_BUDGET}, edges={len(edges)}/{_KPI_DOSSIER_EDGE_BUDGET})"
                    ),
                ),
            )
        )

    children_by_parent: dict[str | None, list[Any]] = {}
    for node in nodes:
        children_by_parent.setdefault(node.parent_id, []).append(node)

    edge_ids = [edge.edge_id for edge in edges]
    ledger = store.query_ledger_latest_for_targets(graph_id, edge_ids) if edge_ids else {}
    view = DossierGraphView(
        nodes_by_id=nodes_by_id,
        adjacency=build_adjacency(edges),
        children_by_parent=children_by_parent,
        edges=edges,
        ledger_status_by_target={target_id: row.status for target_id, row in ledger.items()},
    )

    completeness_result = assess_completeness(store, {"graph_id": graph_id})
    currency_result = assess_currency(store, {"graph_id": graph_id, "scope": kpi_node_id, "mode": "scoped", "top_n": 10})
    weak_result = get_weak_edges(store, {"graph_id": graph_id})
    pending_result = list_pending_confirmations(store, {"graph_id": graph_id})
    weak_edges = [
        {
            "from_node": item.get("source"),
            "to_node": item.get("target"),
            "relationship": item.get("label"),
            "confidence": item.get("confidence"),
            "source": "get_weak_edges",
        }
        for item in weak_result.get("weak_edges", [])
        if item.get("source") == kpi_node_id or item.get("target") == kpi_node_id
    ]
    gaps = DossierGapInputs(
        completeness=_extract_completeness_gaps(completeness_result),
        currency=_extract_currency_gaps(currency_result),
        weak_edges=weak_edges,
        unconfirmed_lineage=_extract_pending_lineage(pending_result, kpi_node_id=kpi_node_id),
    )
    dossier = assemble_kpi_dossier(view, gaps, kpi_node_id=kpi_node_id, depth=2)
    return serialize_dossier(dossier)


@error_boundary
def get_business_dossier(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    """Return a query-first business dossier; append questions only on explicit request."""
    validated = validate_tool_input("get_business_dossier", params, TOOL_SCHEMAS["get_business_dossier"])
    query = str(validated["query"]).strip()
    if not query:
        raise ValidationError(code=-32602, message="query must not be empty")
    request = BusinessDossierRequest(
        graph_id=validated["graph_id"],
        query=query[:_BUSINESS_DOSSIER_QUERY_MAX],
        limit=validated.get("limit", 10),
        max_alternatives=validated.get("max_alternatives", 3),
        create_pending_questions=validated.get("create_pending_questions", False),
        stakeholder_owner=validated.get("stakeholder_owner", ""),
    )

    try:
        nodes = store.query_nodes(request.graph_id)
        edges = store.query_edges(request.graph_id)
    except GraphNotFoundError as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc

    nodes_by_id = {node.id: node for node in nodes}
    children_by_parent: dict[str | None, list[Any]] = {}
    for node in nodes:
        children_by_parent.setdefault(node.parent_id, []).append(node)
    edge_ids = [edge.edge_id for edge in edges]
    ledger = store.query_ledger_latest_for_targets(request.graph_id, edge_ids) if edge_ids else {}
    graph_view = DossierGraphView(
        nodes_by_id=nodes_by_id,
        adjacency=build_adjacency(edges),
        children_by_parent=children_by_parent,
        edges=edges,
        ledger_status_by_target={target_id: row.status for target_id, row in ledger.items()},
    )

    candidates = _business_retrieval_candidates(store, request.graph_id, request.query, nodes, limit=request.limit)
    cluster_routes = _safe_cluster_routes(
        store,
        graph_id=request.graph_id,
        query=request.query,
        nodes_by_id=nodes_by_id,
        member_limit=request.limit,
    )
    gaps = _business_gap_inputs(store, request.graph_id)
    payload = build_business_dossier_payload(
        graph_view=graph_view,
        gaps=gaps,
        query=request.query,
        candidates=candidates,
        cluster_routes=cluster_routes,
        max_alternatives=request.max_alternatives,
        depth=2,
    )
    if request.create_pending_questions:
        payload["pending_questions_created"] = _append_business_pending_questions(
            store,
            graph_id=request.graph_id,
            proposals=_relevant_business_question_proposals(payload),
            stakeholder_owner=request.stakeholder_owner,
        )
    return payload


def _business_retrieval_candidates(
    store: GraphStore,
    graph_id: str,
    query: str,
    nodes: list[Any],
    *,
    limit: int,
) -> list[RetrievalCandidate]:
    lexical_rows = _search_graph_lexical_rows(store, graph_id, query, nodes)
    ordered_ids = [item["id"] for item in lexical_rows if isinstance(item.get("id"), str)]
    if not ordered_ids:
        ordered_ids = [node.id for node in nodes]
    node_by_id = {node.id: node for node in nodes}
    candidate_count = max(1, len(ordered_ids))
    candidates: list[RetrievalCandidate] = []
    for rank, node_id in enumerate(ordered_ids[:limit]):
        node = node_by_id.get(node_id)
        if node is None:
            continue
        lexical = 1.0 - (rank / candidate_count)
        candidates.append(
            RetrievalCandidate(
                id=node.id,
                label=node.label,
                signals=SignalScores(lexical=lexical, semantic=0.0, governance=1.0, graph=0.0),
                metadata={"type": node.type},
            )
        )
    return candidates


def _business_gap_inputs(store: GraphStore, graph_id: str) -> DossierGapInputs:
    completeness_result = assess_completeness(store, {"graph_id": graph_id})
    currency_result = assess_currency(store, {"graph_id": graph_id, "mode": "open", "top_n": 10})
    weak_result = get_weak_edges(store, {"graph_id": graph_id})
    return DossierGapInputs(
        completeness=_extract_completeness_gaps(completeness_result),
        currency=_extract_currency_gaps(currency_result),
        weak_edges=[
            {
                "from_node": item.get("source"),
                "to_node": item.get("target"),
                "relationship": item.get("label"),
                "confidence": item.get("confidence"),
                "source": "get_weak_edges",
            }
            for item in weak_result.get("weak_edges", [])
        ],
        unconfirmed_lineage=[],
    )


def _append_business_pending_questions(
    store: GraphStore,
    *,
    graph_id: str,
    proposals: list[dict[str, Any]],
    stakeholder_owner: str,
) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for proposal in proposals:
        result = insert_pending_question.__wrapped__(
            store,
            {
                "graph_id": graph_id,
                "target_node_id": proposal.get("target_node_id"),
                "gap_kind": str(proposal.get("gap_kind") or "business-link"),
                "entity_type": proposal.get("entity_type"),
                "question_text": str(proposal.get("question_text") or "Please confirm this business relationship."),
                "stakeholder_owner": stakeholder_owner or str(proposal.get("stakeholder_owner") or ""),
            },
        )
        receipts.append(result)
    return receipts


def _relevant_business_question_proposals(payload: dict[str, Any]) -> list[dict[str, Any]]:
    relevant_ids: set[str] = set()
    for interpretation in payload.get("interpretations", []) or []:
        if not isinstance(interpretation, dict):
            continue
        relevant_ids.update(str(item) for item in interpretation.get("entity_ids", []) or [])
        relevant_ids.update(str(item) for item in interpretation.get("evidence_ids", []) or [])
    for section in (payload.get("dossier") or {}).values():
        for item in section or []:
            if isinstance(item, dict) and item.get("id"):
                relevant_ids.add(str(item["id"]))
    for item in payload.get("evidence_sources", []) or []:
        if isinstance(item, dict) and item.get("id"):
            relevant_ids.add(str(item["id"]))
    return [
        proposal
        for proposal in payload.get("pending_question_proposals", []) or []
        if isinstance(proposal, dict) and str(proposal.get("target_node_id") or "") in relevant_ids
    ]


def _extract_completeness_gaps(result: dict[str, Any]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for item in result.get("missing_for_brd", []) or []:
        gaps.append({"gap_type": "missing_entity_type", "description": f"Missing or underspecified {item}", "source": "assess_completeness"})
    for item in result.get("underspecified_nodes", []) or []:
        gaps.append({"gap_type": "underspecified_node", "description": f"Node {item} is underspecified", "source": "assess_completeness"})
    return gaps


def _extract_currency_gaps(result: dict[str, Any]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for item in result.get("gaps", []) or result.get("criticality_ranked_gaps", []) or []:
        if isinstance(item, dict):
            gaps.append(
                {
                    "description": str(item.get("description") or item.get("gap") or item),
                    "criticality": str(item.get("criticality") or item.get("severity") or "medium"),
                    "source": "assess_currency",
                }
            )
    return gaps


def _extract_pending_lineage(result: dict[str, Any], *, kpi_node_id: str) -> list[dict[str, Any]]:
    lineage: list[dict[str, Any]] = []
    for row in result.get("confirmations", []) or []:
        if not isinstance(row, dict):
            continue
        relationship = row.get("relationship_label")
        from_node = row.get("source_node_id")
        to_node = row.get("target_node_id")
        if relationship != "measured-from" or from_node != kpi_node_id or not isinstance(to_node, str):
            continue
        lineage.append(
            {
                "candidate_id": str(row.get("target_id") or row.get("id") or f"{from_node}->{to_node}:{relationship}"),
                "from_node": from_node,
                "to_node": to_node,
                "relationship": relationship,
                "source": "insert_pending_question",
            }
        )
    return lineage


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
def assess_currency(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    """Assess temporal currency gaps for a graph without writing to the store."""
    validated = validate_tool_input("assess_currency", params, TOOL_SCHEMAS["assess_currency"])
    graph_id = validated["graph_id"]
    mode = str(validated.get("mode") or "open")
    if mode not in {"open", "scoped"}:
        raise ValidationError(code=-32602, message="mode must be 'open' or 'scoped'")
    top_n = int(validated.get("top_n") or 10)
    if top_n < 1:
        raise ValidationError(code=-32602, message="top_n must be a positive integer")

    try:
        nodes = store.query_nodes(graph_id)
        edges = store.query_edges(graph_id)
        target_nodes = _currency_scope_nodes(nodes, edges, mode=mode, scope=validated.get("scope"))
        evidence = store.query_node_currency_evidence(graph_id, [node.id for node in target_nodes])
    except GraphNotFoundError as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc

    completeness_result = completeness.assess_graph_completeness(nodes)
    sparse_node_ids = set(completeness_result.get("underspecified_nodes", []))
    calibration_report = calibrate_from_ledger(graph_id, store)
    edge_dicts = [_edge_to_dict(edge) for edge in edges]
    result = aggregate_gaps(
        target_nodes,
        build_adjacency(edges),
        evidence,
        validated.get("thresholds"),
        top_n=top_n,
        sparse_node_ids=sparse_node_ids,
        question_bank={
            node.type: grounding.select_questions_for_gap("staleness", node.type)
            for node in target_nodes
        },
        edges=edge_dicts,
        structural_missing_types=(
            list(completeness_result.get("missing_for_brd", [])) if mode == "open" else []
        ),
        calibration_gap_labels=(
            _currency_calibration_gap_labels(calibration_report) if mode == "open" else []
        ),
    )
    return {"graph_id": graph_id, **result}


@error_boundary
def insert_pending_question(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    """Persist a deferred currency-elicitation question without writing ledger evidence."""
    validated = validate_tool_input("insert_pending_question", params, TOOL_SCHEMAS["insert_pending_question"])
    graph_id = validated["graph_id"]
    gap_kind = validated["gap_kind"].strip()
    question_text = validated["question_text"].strip()
    if not gap_kind:
        raise ValidationError(code=-32602, message="gap_kind must not be empty")
    if not question_text:
        raise ValidationError(code=-32602, message="question_text must not be empty")

    try:
        pending_id = store.insert_pending_question(
            graph_id,
            target_node_id=validated.get("target_node_id"),
            gap_kind=gap_kind,
            entity_type=validated.get("entity_type"),
            question_text=question_text,
            stakeholder_owner=validated.get("stakeholder_owner"),
        )
        result = {
            "id": pending_id,
            "graph_id": graph_id,
            "target_node_id": validated.get("target_node_id"),
            "gap_kind": gap_kind,
            "entity_type": validated.get("entity_type"),
            "question_text": question_text,
            "stakeholder_owner": validated.get("stakeholder_owner"),
            "status": "pending",
        }
        store.log_audit("insert_pending_question", validated, "ok")
        _enqueue_tool_receipt(
            store,
            graph_id=graph_id,
            tool="insert_pending_question",
            status="ok",
            target_id=validated.get("target_node_id"),
            params_summary=f"gap_kind={gap_kind}",
        )
        return result
    except StoreError as exc:
        _safe_log_error(store, "insert_pending_question", validated)
        raise ValidationError(code=-32000, message=str(exc)) from exc


def _currency_calibration_gap_labels(report: Any) -> list[str]:
    labels = []
    for label, metrics in getattr(report, "classes", {}).items():
        if int(getattr(metrics, "examples", 0) or 0) < 3:
            labels.append(str(label))
    return labels


def _currency_scope_nodes(nodes: list[Any], edges: list[Any], *, mode: str, scope: Any) -> list[Any]:
    if mode != "scoped":
        return nodes
    if not isinstance(scope, str) or not scope.strip():
        raise ValidationError(code=-32602, message="scope is required when mode is 'scoped'")
    node_ids = {node.id for node in nodes}
    if scope not in node_ids:
        raise ValidationError(code=-32000, message=f"scope node '{scope}' not found")
    scoped_ids = set(expand_neighborhood([scope], build_adjacency(edges), depth=1))
    return [node for node in nodes if node.id in scoped_ids]


@error_boundary
def list_pending_confirmations(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    """Return pending confirmation rows across all target types for the graph.

    Read-only.  Returns latest-per-target rows whose latest status is
    'needs-confirmation', ordered id ASC.
    """
    validated = validate_tool_input(
        "list_pending_confirmations", params, TOOL_SCHEMAS["list_pending_confirmations"]
    )
    graph_id = validated["graph_id"]
    if not isinstance(graph_id, str):
        raise ValidationError(code=-32602, message="graph_id must be a string")
    try:
        rows = store.list_pending_confirmations(graph_id)
    except GraphNotFoundError as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc

    def _row_dict(row) -> dict[str, Any]:
        return {
            "id": row.id,
            "graph_id": row.graph_id,
            "target_type": row.target_type,
            "target_id": row.target_id,
            "status": row.status,
            "initial_confidence": row.initial_confidence,
            "current_confidence": row.current_confidence,
            "relationship_label": row.relationship_label,
            "source_node_id": row.source_node_id,
            "target_node_id": row.target_node_id,
            "source_node_type": row.source_node_type,
            "target_node_type": row.target_node_type,
            "evidence_ids": row.evidence_ids,
            "captured_by": row.captured_by,
            "captured_at": row.captured_at,
            "confirmed_at": row.confirmed_at,
            "confirmed_by": row.confirmed_by,
            "flagged_reason": row.flagged_reason,
            "gold_rationale": row.gold_rationale,
            "provenance": row.provenance,
            "fact_label": row.fact_label,
            "fact_path": row.fact_path,
            "fact_value": row.fact_value,
            "fact_subject_type": row.fact_subject_type,
        }

    confirmations = [_row_dict(r) for r in rows]
    return {"confirmations": confirmations, "total": len(confirmations)}


@error_boundary
def resolve_confirmation(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    """Resolve a pending confirmation by appending a human verdict row.

    Write tool.  Validates outcome and that the latest row for
    (graph_id, target_type, target_id) has status='needs-confirmation'.
    Never mutates prior rows — append-only.
    """
    validated = validate_tool_input(
        "resolve_confirmation", params, TOOL_SCHEMAS["resolve_confirmation"]
    )
    graph_id = validated["graph_id"]
    target_type = validated["target_type"]
    target_id = validated["target_id"]
    outcome = validated["outcome"]
    resolved_by = validated["resolved_by"]
    gold_rationale = validated["gold_rationale"]

    # Schema enum already restricts outcome to valid values, but guard explicitly
    # to match design contract (repo raises ValueError for invalid outcome).
    _VALID_OUTCOMES = {"confirmed", "invalidated", "abstain"}
    if outcome not in _VALID_OUTCOMES:
        raise ValidationError(
            code=-32602,
            message=f"outcome must be one of: {', '.join(sorted(_VALID_OUTCOMES))}",
        )

    try:
        result = store.resolve_confirmation(
            graph_id,
            target_type=target_type,
            target_id=target_id,
            outcome=outcome,
            resolved_by=resolved_by,
            gold_rationale=gold_rationale,
        )
    except GraphNotFoundError as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc
    except ValueError as exc:
        raise ValidationError(code=-32602, message=str(exc)) from exc

    grounding.invalidate_graph_calibration(graph_id)
    return result


_CLUSTER_ACTION_STATUSES = {
    "confirm": "confirmed",
    "reject": "rejected",
    "archive": "archived",
}


def _cluster_to_dict(row: Any) -> dict[str, Any]:
    return asdict(row)


def _get_cluster(store: GraphStore, graph_id: str, cluster_id: str) -> Any:
    for row in store.query_clusters(graph_id):
        if row.id == cluster_id:
            return row
    raise ValidationError(code=-32000, message=f"Cluster '{cluster_id}' not found in graph '{graph_id}'")


def _kpi_missing_source(payload: dict[str, Any], metadata: dict[str, Any]) -> bool:
    if metadata.get("primary_anchor_type") != EntityType.KPI.value:
        return False
    kpi = payload.get("kpi") if isinstance(payload.get("kpi"), dict) else {}
    return not any(kpi.get(key) or payload.get(key) for key in ("source", "sources", "tables", "fields"))


def _cluster_metadata_from_payload(payload: dict[str, Any], confidence: float | None) -> dict[str, Any]:
    kpi = payload.get("kpi") if isinstance(payload.get("kpi"), dict) else {}
    anchor_type = payload.get("primary_anchor_type") or kpi.get("primary_anchor_type")
    metadata = {
        "status": "proposed",
        "primary_anchor_id": payload.get("primary_anchor_id"),
        "primary_anchor_type": anchor_type,
        "dominant_department_id": payload.get("dominant_department_id") or kpi.get("department"),
        "supporting_anchor_ids": list(payload.get("supporting_anchor_ids") or []),
        "needs_source": False,
        "source_requirements": {
            "description": payload.get("description") or kpi.get("description"),
            "formula": kpi.get("formula") or payload.get("formula"),
            "composition": kpi.get("composition") or payload.get("composition"),
            "source": kpi.get("source") or payload.get("source"),
            "owner": kpi.get("owner") or payload.get("owner"),
        },
        "summary": payload.get("description") or kpi.get("description"),
        "quality_signals": {"confidence": confidence} if confidence is not None else {},
        "archived_reason": None,
    }
    if _kpi_missing_source(payload, metadata):
        metadata["status"] = "needs-source"
        metadata["needs_source"] = True
    return metadata


def _insert_cluster_source_question(store: GraphStore, graph_id: str, metadata: dict[str, Any], payload: dict[str, Any]) -> list[int]:
    if not metadata.get("needs_source"):
        return []
    anchor_id = metadata.get("primary_anchor_id")
    if not isinstance(anchor_id, str) or not anchor_id:
        return []
    owner = None
    kpi = payload.get("kpi") if isinstance(payload.get("kpi"), dict) else {}
    if isinstance(kpi, dict):
        owner = kpi.get("owner")
    pending_id = store.insert_pending_question(
        graph_id,
        target_node_id=anchor_id,
        gap_kind="cluster_source",
        entity_type=str(metadata.get("primary_anchor_type") or "KPI"),
        question_text="Which primary data source, table, and field measures this KPI cluster?",
        stakeholder_owner=owner,
    )
    return [pending_id]


@error_boundary
def manage_clusters(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    """Govern semantic cluster lifecycle through one consolidated write tool."""
    validated = validate_tool_input("manage_clusters", params, TOOL_SCHEMAS["manage_clusters"])
    graph_id = validated["graph_id"]
    action = validated["action"]
    payload = validated.get("payload") or {}
    if not isinstance(payload, dict):
        raise ValidationError(code=-32602, message="payload must be an object")

    try:
        pending_question_ids: list[int] = []
        related_clusters: list[dict[str, Any]] = []
        if action == "propose":
            cluster_id = payload.get("cluster_id") or validated.get("cluster_id")
            if not isinstance(cluster_id, str) or not cluster_id:
                raise ValidationError(code=-32602, message="payload.cluster_id is required for propose")
            metadata = _cluster_metadata_from_payload(payload, validated.get("confidence"))
            store.save_clusters(
                graph_id,
                [{"id": cluster_id, "name": payload.get("name") or cluster_id, "description": payload.get("description"), "metadata": metadata}],
            )
            members = [{"cluster_id": cluster_id, "node_id": node_id} for node_id in payload.get("member_node_ids") or []]
            if members:
                store.save_cluster_members(graph_id, members)
            pending_question_ids = _insert_cluster_source_question(store, graph_id, metadata, payload)
        elif action in _CLUSTER_ACTION_STATUSES:
            cluster_id = validated.get("cluster_id")
            if not cluster_id:
                raise ValidationError(code=-32602, message="cluster_id is required")
            store.update_cluster_lifecycle(graph_id, cluster_id, _CLUSTER_ACTION_STATUSES[action], reason=validated.get("reason"))
        elif action == "reformulate":
            cluster_id = validated.get("cluster_id")
            if not cluster_id:
                raise ValidationError(code=-32602, message="cluster_id is required")
            current = _get_cluster(store, graph_id, cluster_id)
            store.save_clusters(
                graph_id,
                [{"id": cluster_id, "name": payload.get("name") or current.name, "description": payload.get("description", current.description), "parent_id": current.parent_id, "metadata": current.metadata}],
            )
        elif action == "split":
            cluster_id = validated.get("cluster_id")
            new_cluster_id = payload.get("new_cluster_id")
            if not cluster_id or not isinstance(new_cluster_id, str) or not new_cluster_id:
                raise ValidationError(code=-32602, message="cluster_id and payload.new_cluster_id are required for split")
            current = _get_cluster(store, graph_id, cluster_id)
            metadata = dict(current.metadata or {})
            metadata["status"] = metadata.get("status") or "proposed"
            store.save_clusters(graph_id, [{"id": new_cluster_id, "name": payload.get("name") or new_cluster_id, "metadata": metadata}])
            related_clusters = [_cluster_to_dict(_get_cluster(store, graph_id, new_cluster_id))]
        elif action == "merge":
            cluster_id = validated.get("cluster_id")
            source_cluster_id = payload.get("source_cluster_id")
            if not cluster_id or not isinstance(source_cluster_id, str) or not source_cluster_id:
                raise ValidationError(code=-32602, message="cluster_id and payload.source_cluster_id are required for merge")
            store.update_cluster_lifecycle(graph_id, source_cluster_id, "archived", reason=f"merged into {cluster_id}")
            related_clusters = [_cluster_to_dict(_get_cluster(store, graph_id, source_cluster_id))]
        else:
            raise ValidationError(code=-32602, message="Unsupported cluster action")

        cluster_id = validated.get("cluster_id") or payload.get("cluster_id")
        cluster = _cluster_to_dict(_get_cluster(store, graph_id, str(cluster_id)))
        store.log_audit("manage_clusters", validated, "ok")
        _enqueue_tool_receipt(store, graph_id=graph_id, tool="manage_clusters", status="ok", target_id=str(cluster_id), params_summary=f"action={action} cluster={cluster_id}")
        result = {"cluster": cluster, "audit_id": f"{cluster_id}:{action}", "pending_question_ids": pending_question_ids}
        if related_clusters:
            result["related_clusters"] = related_clusters
        return result
    except (StoreError, ValueError) as exc:
        _safe_log_error(store, "manage_clusters", validated)
        raise ValidationError(code=-32000, message=str(exc)) from exc


_MAX_ANCHORS = 5


def _rank_query_anchors_with_hybrid_router(
    *,
    query: str,
    nodes_by_id: dict[str, Any],
    lexical_candidates: list[Any],
    dense_hits: list[Any],
) -> tuple[list[Any], bool]:
    """Rank query anchors through the internal router seam used by eval."""
    lexical_rank = {node.id: rank + 1 for rank, node in enumerate(lexical_candidates)}
    dense_rank = {
        hit.target_id: (rank + 1, float(getattr(hit, "score", 0.0) or 0.0))
        for rank, hit in enumerate(dense_hits)
        if getattr(hit, "target_id", None) in nodes_by_id
    }
    ordered_ids: list[str] = []
    for node in lexical_candidates:
        if node.id not in ordered_ids:
            ordered_ids.append(node.id)
    for node_id in dense_rank:
        if node_id not in ordered_ids:
            ordered_ids.append(node_id)

    if not ordered_ids:
        return [], False

    candidate_count = max(1, len(ordered_ids))
    candidates = []
    for node_id in ordered_ids:
        node = nodes_by_id[node_id]
        lex = 1.0 - ((lexical_rank[node_id] - 1) / candidate_count) if node_id in lexical_rank else 0.0
        semantic = dense_rank.get(node_id, (0, 0.0))[1]
        candidates.append(
            RetrievalCandidate(
                id=node_id,
                label=node.label,
                signals=SignalScores(lexical=lex, semantic=semantic, governance=1.0, graph=0.0),
            )
        )

    result = HybridRetrievalRouter(candidates=candidates).retrieve(
        RetrievalRequest(query=query, limit=_MAX_ANCHORS, depth=1)
    )
    return [nodes_by_id[anchor.id] for anchor in result.anchors if anchor.id in nodes_by_id], result.dense_used


def _safe_cluster_routes(
    store: GraphStore,
    *,
    graph_id: str,
    query: str | None,
    nodes_by_id: dict[str, Any],
    member_limit: int,
) -> list[Any]:
    """Gather cluster routes without letting cluster metadata failures break BFS retrieval."""
    try:
        clusters = store.query_clusters(graph_id)
        members_by_cluster: dict[str, list[str]] = {}
        for member in store.cluster_repo.list_members(graph_id):
            members_by_cluster.setdefault(member.cluster_id, []).append(member.node_id)
        return select_cluster_routes(
            query,
            clusters,
            members_by_cluster,
            nodes_by_id,
            limit=_MAX_ANCHORS,
            member_limit=member_limit,
        )
    except Exception:
        logger.debug("Cluster route gathering failed; falling back to BFS retrieval.", exc_info=True)
        return []


def _cap_depth_map(depth_map: dict[str, int], *, anchor_ids: list[str], limit: int) -> dict[str, int]:
    """Bound execution work before edge filtering and ledger lookup."""
    capped: dict[str, int] = {}
    for anchor_id in anchor_ids:
        if anchor_id in depth_map and len(capped) < limit:
            capped[anchor_id] = depth_map[anchor_id]
    for node_id, depth_value in sorted(depth_map.items(), key=lambda item: (item[1], item[0])):
        if len(capped) >= limit:
            break
        if node_id not in capped:
            capped[node_id] = depth_value
    return capped


def _rrf_anchor_fuse(lexical_ids: list[str], dense_ids: list[str]) -> list[str]:
    """Reciprocal Rank Fusion over anchor candidate lists (k=60)."""
    k = 60
    lexical_rank = {nid: rank + 1 for rank, nid in enumerate(lexical_ids)}
    dense_rank = {nid: rank + 1 for rank, nid in enumerate(dense_ids)}
    lexical_sentinel = len(lexical_ids) + 1
    candidates: list[tuple[float, str]] = []
    seen: set[str] = set()
    for nid in lexical_ids + dense_ids:
        if nid in seen:
            continue
        seen.add(nid)
        rrf = 1.0 / (k + lexical_rank.get(nid, lexical_sentinel))
        dense_rank_value = dense_rank.get(nid)
        if dense_rank_value is not None:
            rrf += 1.0 / (k + dense_rank_value)
        candidates.append((rrf, nid))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return [nid for _, nid in candidates]


@error_boundary
def retrieve_context(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    """Retrieve a reliability-annotated subgraph centred on query anchors.

    Read-only.  Accepts ``graph_id`` plus AT LEAST ONE of ``query`` (FTS5 +
    optional cosine RRF) or ``focal_node_id`` (direct anchor).  Returns the
    seven fields specified in R-03: anchors, subgraph, hierarchy_paths,
    serialized_for_llm (empty placeholder until PR3), and dense_used.
    """
    validated = validate_tool_input("retrieve_context", params, TOOL_SCHEMAS["retrieve_context"])
    graph_id = validated["graph_id"]
    query: str | None = validated.get("query") or None
    focal_node_id: str | None = validated.get("focal_node_id") or None
    limit = max(1, min(50, int(validated.get("limit", 10))))
    depth = int(validated.get("depth", 1))

    # R-01: at least one of query/focal_node_id is required.
    if not query and not focal_node_id:
        raise ValidationError(
            code=-32602,
            message="At least one of 'query' or 'focal_node_id' must be provided",
        )

    # R-02: depth must be 1 or 2.
    if depth not in (1, 2):
        raise ValidationError(code=-32602, message="depth must be 1 or 2")

    # Load all nodes for BFS adjacency and hierarchy walks.
    try:
        all_nodes = store.query_nodes(graph_id)
    except GraphNotFoundError as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc

    nodes_by_id = {n.id: n for n in all_nodes}

    # --- Anchor resolution (R-09) ---
    dense_used = False
    anchor_nodes: list[Any] = []

    if focal_node_id:
        node = nodes_by_id.get(focal_node_id)
        if node is None:
            raise ValidationError(
                code=-32000,
                message=f"focal_node_id '{focal_node_id}' not found in graph '{graph_id}'",
            )
        anchor_nodes = [node]

    if query:
        fts_ids = store.search_nodes_fts(graph_id, query)
        if fts_ids is not None and fts_ids:
            lexical_candidates = [nodes_by_id[nid] for nid in fts_ids if nid in nodes_by_id]
        else:
            norm_q = _normalize_query(query)
            lexical_candidates = [
                n for n in all_nodes
                if norm_q in _normalize_query(n.label)
                or norm_q in _normalize_query(n.type)
                or norm_q in _normalize_query(_details_text(n.details))
            ]

        model = get_default_model()
        if model is not None:
            try:
                query_vector = model.embed(query)
                dense_hits = store.nearest_to_vector(graph_id, query_vector, k=_MAX_ANCHORS * 3)
                if dense_hits:
                    query_anchors, dense_used = _rank_query_anchors_with_hybrid_router(
                        query=query,
                        nodes_by_id=nodes_by_id,
                        lexical_candidates=lexical_candidates[: _MAX_ANCHORS * 3],
                        dense_hits=dense_hits,
                    )
                else:
                    query_anchors, dense_used = _rank_query_anchors_with_hybrid_router(
                        query=query,
                        nodes_by_id=nodes_by_id,
                        lexical_candidates=lexical_candidates[: _MAX_ANCHORS * 3],
                        dense_hits=[],
                    )
            except Exception:
                query_anchors, dense_used = _rank_query_anchors_with_hybrid_router(
                    query=query,
                    nodes_by_id=nodes_by_id,
                    lexical_candidates=lexical_candidates[: _MAX_ANCHORS * 3],
                    dense_hits=[],
                )
        else:
            query_anchors, dense_used = _rank_query_anchors_with_hybrid_router(
                query=query,
                nodes_by_id=nodes_by_id,
                lexical_candidates=lexical_candidates[: _MAX_ANCHORS * 3],
                dense_hits=[],
            )

        if focal_node_id:
            seen_ids: set[str] = {n.id for n in anchor_nodes}
            for n in query_anchors:
                if n.id not in seen_ids:
                    anchor_nodes.append(n)
                    seen_ids.add(n.id)
            anchor_nodes = anchor_nodes[:_MAX_ANCHORS]
        else:
            anchor_nodes = query_anchors

    # --- Cluster/module routing (PR3) ---
    cluster_routes = _safe_cluster_routes(
        store,
        graph_id=graph_id,
        query=query,
        nodes_by_id=nodes_by_id,
        member_limit=limit,
    )
    if cluster_routes:
        routed_anchor_ids: list[str] = []
        for route in cluster_routes:
            for anchor_id in route.anchor_ids:
                if anchor_id not in routed_anchor_ids:
                    routed_anchor_ids.append(anchor_id)
        anchor_nodes = [nodes_by_id[nid] for nid in routed_anchor_ids[:_MAX_ANCHORS]]

    # --- BFS expansion (R-06, reuse PR1 helpers) ---
    anchor_ids = [n.id for n in anchor_nodes]
    edges = store.query_edges(graph_id)
    adj = build_adjacency(edges)
    depth_map = expand_neighborhood(anchor_ids, adj, depth=depth)
    for route in cluster_routes:
        for member_id in route.member_ids:
            depth_map.setdefault(member_id, 1)
    depth_map = _cap_depth_map(depth_map, anchor_ids=anchor_ids, limit=limit)

    subgraph_edges = [e for e in edges if e.source in depth_map and e.target in depth_map]
    edge_ids = [e.edge_id for e in subgraph_edges]

    # --- Batch ledger join (R-05, reuse PR1 repository method) ---
    ledger = store.query_ledger_latest_for_targets(graph_id, edge_ids)

    # --- Annotate edges; exclude invalidated (R-04) ---
    annotated_edges: list[AnnotatedEdge] = []
    for edge in subgraph_edges:
        ledger_row = ledger.get(edge.edge_id)
        status = ledger_row.status if ledger_row is not None else None
        tier = ledger_status_to_tier(status)
        if tier is None:
            continue  # invalidated — excluded from response

        if status == "confirmed":
            reliability_tag = (
                f"CONFIRMED by {ledger_row.confirmed_by or 'unknown'}"
                f" on {ledger_row.confirmed_at or 'unknown'}"
            )
        elif status == "needs-confirmation":
            reliability_tag = f"PENDING REVIEW (flagged: {ledger_row.flagged_reason or ''})"
        elif status == "abstain":
            reliability_tag = "ABSTAIN — insufficient evidence"
        elif status == "inferred" and ledger_row is not None:
            conf = ledger_row.current_confidence
            reliability_tag = f"INFERRED (score={conf:.2f})" if conf is not None else "INFERRED"
        else:
            reliability_tag = f"INFERRED (engine score={edge.weight:.2f})"

        annotated_edges.append(
            AnnotatedEdge(
                edge=edge,
                ledger_status=status,
                tier=tier,
                reliability_tag=reliability_tag,
                tag_detail="",
            )
        )

    sorted_edges = sort_edges_by_reliability(annotated_edges)

    # --- Cap subgraph nodes at limit (anchors always retained) ---
    anchor_id_set = set(anchor_ids)
    non_anchor_ids = [
        nid for nid in depth_map if nid not in anchor_id_set and nid in nodes_by_id
    ]
    budget = max(0, limit - len(anchor_nodes))
    kept_node_ids: set[str] = anchor_id_set | set(non_anchor_ids[:budget])

    subgraph_nodes = [
        {
            "id": n.id,
            "label": n.label,
            "type": n.type,
            "depth_from_anchor": depth_map.get(n.id, 0),
            "card_sections": n.card_sections or [],
        }
        for n in all_nodes
        if n.id in kept_node_ids
    ]

    edges_with_reliability = [
        {
            "source_id": ae.edge.source,
            "target_id": ae.edge.target,
            "label": ae.edge.label,
            "weight": ae.edge.weight,
            "ledger_status": ae.ledger_status,
            "reliability_tag": ae.reliability_tag,
            "tier": ae.tier,
        }
        for ae in sorted_edges
        if ae.edge.source in kept_node_ids and ae.edge.target in kept_node_ids
    ]

    # --- Hierarchy paths (R-10) ---
    hierarchy_paths = {
        anchor.id: walk_hierarchy_path(anchor.id, nodes_by_id)
        for anchor in anchor_nodes
    }

    # --- Serialize for LLM (R-08, R-07) ---
    module_route = cluster_routes_to_dict(cluster_routes)
    serialized_for_llm = serialize_for_llm(subgraph_nodes, sorted_edges, hierarchy_paths, module_route=module_route)

    return {
        "anchors": [_node_to_dict(n) for n in anchor_nodes],
        "subgraph": {
            "nodes": subgraph_nodes,
            "edges_with_reliability": edges_with_reliability,
        },
        "hierarchy_paths": hierarchy_paths,
        "module_route": module_route,
        "serialized_for_llm": serialized_for_llm,
        "dense_used": dense_used,
    }


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
    "get_kpi_dossier": {
        "handler": get_kpi_dossier,
        "schema": TOOL_SCHEMAS["get_kpi_dossier"],
        "description": "Assemble a structured KPI dossier from graph lineage and limitations",
        "rw": "read",
        "requires_ai_agent": False,
    },
    "get_business_dossier": {
        "handler": get_business_dossier,
        "schema": TOOL_SCHEMAS["get_business_dossier"],
        "description": "Assemble a query-first business dossier with optional pending-question receipts",
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
    "assess_currency": {
        "handler": assess_currency,
        "schema": TOOL_SCHEMAS["assess_currency"],
        "description": "Assess temporal currency coverage and criticality-ranked freshness gaps",
        "rw": "read",
        "requires_ai_agent": False,
    },
    "insert_pending_question": {
        "handler": insert_pending_question,
        "schema": TOOL_SCHEMAS["insert_pending_question"],
        "description": "Persist a deferred currency-elicitation question without resetting currency evidence",
        "rw": "write",
        "requires_ai_agent": False,
    },
    "manage_clusters": {
        "handler": manage_clusters,
        "schema": TOOL_SCHEMAS["manage_clusters"],
        "description": "Create and govern semantic cluster lifecycle states",
        "rw": "write",
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
    "list_pending_confirmations": {
        "handler": list_pending_confirmations,
        "schema": TOOL_SCHEMAS["list_pending_confirmations"],
        "description": "List pending human-confirmation rows (latest per target, graph-wide)",
        "rw": "read",
        "requires_ai_agent": False,
    },
    "resolve_confirmation": {
        "handler": resolve_confirmation,
        "schema": TOOL_SCHEMAS["resolve_confirmation"],
        "description": "Resolve a pending confirmation by appending a human verdict row (append-only)",
        "rw": "write",
        "requires_ai_agent": False,
    },
    "retrieve_context": {
        "handler": retrieve_context,
        "schema": TOOL_SCHEMAS["retrieve_context"],
        "description": "Retrieve a reliability-annotated subgraph centred on query anchors (BFS + ledger join)",
        "rw": "read",
        "requires_ai_agent": False,
    },
}
