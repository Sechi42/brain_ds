from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import brain_ds.mcp.grounding as grounding
from brain_ds.mcp.security import (
    TOOL_SCHEMAS,
    SecurityError,
    ValidationError,
    error_boundary,
    validate_card_sections,
    validate_path_within_root,
    validate_tool_input,
)
from brain_ds.store.errors import GraphAlreadyExistsError, GraphNotFoundError, StoreError
from brain_ds.store.graph_store import GraphStore


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


def _receipt_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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


@error_boundary
def search_graph(store: GraphStore, params: dict[str, Any]) -> list[dict[str, Any]] | dict[str, Any]:
    validated = validate_tool_input("search_graph", params, TOOL_SCHEMAS["search_graph"])
    graph_id = validated["graph_id"]
    query = validated["query"].strip().lower()

    try:
        rows = store.query_nodes(graph_id)
    except GraphNotFoundError as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc

    def _match(row: Any) -> bool:
        return (
            query in row.label.lower()
            or query in row.type.lower()
            or query in _details_text(row.details)
        )

    return [_node_to_dict(row) for row in rows if _match(row)]


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
        for field in ("label", "type", "details", "card_sections", "supertype"):
            if field in validated:
                payload[field] = validated[field]

        store.upsert_node(graph_id, payload)
        result = get_node.__wrapped__(store, {"graph_id": graph_id, "node_id": node_id})
        store.log_audit("update_node", validated, "ok")
        store.enqueue_event(
            "node.created" if is_create else "node.updated",
            graph_id,
            result,
        )
        changed_fields = [field for field in ("label", "type", "details", "card_sections", "supertype") if field in validated]
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
            get_node.__wrapped__(store, {"graph_id": graph_id, "node_id": validated["source"]})
        except ValidationError as exc:
            if exc.message.startswith("Graph '"):
                raise
            raise ValidationError(code=-32000, message=f"Source node '{validated['source']}' not found")

        try:
            get_node.__wrapped__(store, {"graph_id": graph_id, "node_id": validated["target"]})
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
        if "reasons" in validated:
            edge_input["reasons"] = validated["reasons"]

        store.upsert_edge(graph_id, edge_input)
        edge = store.query_edges(graph_id, source=validated["source"], target=validated["target"])[-1]
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
def run_elicit(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    validate_tool_input("run_elicit", params, TOOL_SCHEMAS["run_elicit"])
    return grounding.elicit_context()


@error_boundary
def map_connections(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    validate_tool_input("map_connections", params, TOOL_SCHEMAS["map_connections"])
    return grounding.map_connections_context()


@error_boundary
def generate_brd(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    validate_tool_input("generate_brd", params, TOOL_SCHEMAS["generate_brd"])
    return grounding.generate_brd_context()


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
}
