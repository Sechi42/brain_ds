from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
import unicodedata
from pathlib import Path
from typing import Any

import brain_ds.mcp.grounding as grounding
import brain_ds.scoring.similarity as similarity
import brain_ds.workspaces as workspace_registry
from brain_ds.connectors import CsvConnector, SQLiteConnector
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


def _normalize_query(text: str) -> str:
    """Normalize text for accent-insensitive comparison."""
    nfd = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")


@error_boundary
def search_graph(store: GraphStore, params: dict[str, Any]) -> list[dict[str, Any]] | dict[str, Any]:
    validated = validate_tool_input("search_graph", params, TOOL_SCHEMAS["search_graph"])
    graph_id = validated["graph_id"]
    raw_query = validated["query"].strip()

    try:
        rows = store.query_nodes(graph_id)
    except GraphNotFoundError as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc

    # Attempt FTS5 search first
    fts_ids = store.search_nodes_fts(graph_id, raw_query)

    if fts_ids is not None and len(fts_ids) > 0:
        id_set = set(fts_ids)
        return [_node_to_dict(row) for row in rows if row.id in id_set]

    # Fallback: Python substring scan (accent-insensitive)
    query = _normalize_query(raw_query)

    def _match(row: Any) -> bool:
        return (
            query in _normalize_query(row.label)
            or query in _normalize_query(row.type)
            or query in _normalize_query(_details_text(row.details))
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
def suggest_connections(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    validated = validate_tool_input("suggest_connections", params, TOOL_SCHEMAS["suggest_connections"])
    graph_id = validated["graph_id"]
    node_id = validated["node_id"]

    try:
        nodes = store.query_nodes(graph_id)
        edges = store.query_edges(graph_id)
    except GraphNotFoundError as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc

    try:
        return similarity.suggest_connections_for_node(
            nodes,
            edges,
            node_id,
            threshold=validated.get("threshold", similarity.DEFAULT_THRESHOLD),
            limit=validated.get("limit", similarity.DEFAULT_LIMIT),
        )
    except KeyError as exc:
        raise ValidationError(code=-32000, message=f"Node '{node_id}' not found in graph '{graph_id}'") from exc


@error_boundary
def list_workspaces(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    validate_tool_input("list_workspaces", params, TOOL_SCHEMAS["list_workspaces"])
    active_root = _project_root_from_store_path(store.path).resolve()
    active_key = workspace_registry.normalize_root(active_root)

    entries: list[dict[str, Any]] = []
    active_registered = False
    for entry in workspace_registry.list_workspaces():
        is_active = workspace_registry.normalize_root(entry["path"]) == active_key
        active_registered = active_registered or is_active
        entries.append({**entry, "active": is_active})

    return {
        "active_project_root": str(active_root),
        "active_registered": active_registered,
        "workspaces": entries,
    }


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
    payload["workspace"] = grounding.build_workspace_context(store)
    return payload


@error_boundary
def map_connections(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    validate_tool_input("map_connections", params, TOOL_SCHEMAS["map_connections"])
    payload = grounding.map_connections_context()
    payload["workspace"] = grounding.build_workspace_context(store)
    return payload


@error_boundary
def generate_brd(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    validate_tool_input("generate_brd", params, TOOL_SCHEMAS["generate_brd"])
    payload = grounding.generate_brd_context()
    payload["workspace"] = grounding.build_workspace_context(store)
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
                "Set details.connection = {{kind: 'sqlite'|'csv', path: '...'}} to enable exploration."
            ),
        )
    return connection


def _resolve_connector(connection: dict[str, Any], project_root: Path):
    """Resolve and validate a connector from a connection descriptor."""
    kind = connection.get("kind", "").lower()
    raw_path = connection.get("path", "")

    if not raw_path:
        raise ValidationError(code=-32000, message="Connection descriptor missing 'path'")

    try:
        safe_path = validate_path_within_root(raw_path, project_root)
    except SecurityError as exc:
        raise ValidationError(code=-32000, message=f"Path sandbox violation: {exc}") from exc
    except FileNotFoundError as exc:
        raise ValidationError(code=-32000, message=f"Source file not found: {raw_path}") from exc

    if kind == "sqlite":
        return SQLiteConnector(safe_path)
    elif kind in ("csv", "tsv"):
        return CsvConnector(safe_path)
    else:
        raise ValidationError(
            code=-32000,
            message=f"Unsupported connection kind: {kind!r}. Supported: sqlite, csv, tsv",
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
                    result.append({
                        "graph_id": gid,
                        "node_id": row.id,
                        "label": row.label,
                        "connection": connection,
                    })
    except Exception as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc

    return result


@error_boundary
def explore_source(store: GraphStore, params: dict[str, Any]) -> dict[str, Any]:
    """Explore a connected data source by dispatching to the right connector.

    - No container/table args: describe + list_containers
    - container only: list_tables(container)
    - container + table: schema + 5-row preview
    """
    validated = validate_tool_input("explore_source", params, TOOL_SCHEMAS["explore_source"])
    graph_id = validated["graph_id"]
    node_id = validated["node_id"]
    container = validated.get("container")
    table = validated.get("table")

    connection = _get_node_connection(store, graph_id, node_id)
    project_root = _project_root_from_store_path(store.path)
    connector = _resolve_connector(connection, project_root)

    try:
        if container is None:
            # Level 0: describe + list containers
            return {
                "level": "source",
                "describe": connector.describe(),
                "containers": connector.list_containers(),
            }
        elif table is None:
            # Level 1: list tables in container
            return {
                "level": "container",
                "container": container,
                "tables": connector.list_tables(container),
            }
        else:
            # Level 2: schema + preview
            schema = connector.get_table_schema(container, table)
            preview = connector.preview(container, table, limit=5)
            return {
                "level": "table",
                "container": container,
                "table": table,
                "schema": schema,
                "preview": preview,
            }
    except (FileNotFoundError, ValueError, Exception) as exc:
        raise ValidationError(code=-32000, message=str(exc)) from exc


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

    if kind != "sqlite":
        raise ValidationError(
            code=-32000,
            message=f"query_source only supports SQLite sources, got kind={kind!r}. "
                    "For CSV sources, use explore_source to preview data.",
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
}
