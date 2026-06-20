from __future__ import annotations

from datetime import UTC, datetime
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from brain_ds.api.events import EventBus
from brain_ds.connectors.secrets import SecretCatalog, SecretEntry, SecretManifestError, get_provider_adapter
from brain_ds.connectors.secrets.redaction import redact_secrets
from brain_ds.mcp.security import SecurityError, ValidationError, is_workspace_admin
from brain_ds.mcp import tools as mcp_tools
from brain_ds.store.errors import GraphNotFoundError
from brain_ds.store.graph_store import GraphStore


def _algorithmic_search_score(query: str, row: dict[str, Any], rank: int) -> float:
    """Stable browser-facing score for search_graph rows that do not expose one."""
    explicit = row.get("score")
    if isinstance(explicit, int | float):
        return float(explicit)
    normalized_query = query.strip().lower()
    label = str(row.get("label") or "").lower()
    node_type = str(row.get("type") or "").lower()
    details = " ".join(str(value).lower() for value in (row.get("details") or {}).values())
    score = 1.0 / (rank + 1)
    if normalized_query:
        if label == normalized_query:
            score += 100.0
        elif label.startswith(normalized_query):
            score += 80.0
        elif normalized_query in label:
            score += 60.0
        elif normalized_query in node_type:
            score += 40.0
        elif normalized_query in details:
            score += 30.0
        tokens = [token for token in normalized_query.split() if token]
        if tokens and all(token in f"{label} {node_type} {details}" for token in tokens):
            score += 20.0
    return round(score, 6)


def _search_graph_api_result(query: str, raw_rows: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_rows, list):
        return []
    rows: list[dict[str, Any]] = []
    for rank, item in enumerate(raw_rows):
        if not isinstance(item, dict):
            continue
        score = _algorithmic_search_score(query, item, rank)
        rows.append(
            {
                "id": str(item.get("id") or ""),
                "label": str(item.get("label") or item.get("id") or ""),
                "type": str(item.get("type") or ""),
                "score": score,
            }
        )
    rows = [row for row in rows if row["id"]]
    rows.sort(key=lambda row: (-float(row["score"]), row["label"], row["id"]))
    return rows


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _workspace_root_for_graph(store: GraphStore, graph_id: str) -> Path:
    meta = next((m for m in store.meta_repo.list_graphs() if m.id == graph_id), None)
    if meta is None:
        raise GraphNotFoundError(f"Graph '{graph_id}' not found")
    if meta.workspace_root:
        return Path(meta.workspace_root)
    path = Path(store.path)
    if path.parent.name == ".brain_ds":
        return path.parent.parent
    return path.parent


def _load_secret_catalog(store: GraphStore, graph_id: str) -> SecretCatalog:
    root = _workspace_root_for_graph(store, graph_id)
    catalog = SecretCatalog(root)
    catalog.load()
    return catalog


def _redacted_secret_handles(catalog: SecretCatalog) -> list[dict[str, Any]]:
    return [
        {
            "handle": entry.handle,
            "kind": entry.kind,
            "created_at": entry.created_at,
            "metadata": redact_secrets(entry.metadata),
        }
        for entry in catalog.list_handles()
    ]


def _secret_permission_denied() -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={
            "status": "permission_denied",
            "detail": "Permisos insuficientes: se requiere workspace_admin para gestionar secretos.",
        },
    )


def _require_workspace_admin(agent_scope: str | None) -> JSONResponse | None:
    try:
        is_workspace_admin({"agent_scope": agent_scope} if agent_scope is not None else {})
    except SecurityError:
        return _secret_permission_denied()
    return None


def _validate_secret_entry(catalog: SecretCatalog, entry: SecretEntry, *, probe: bool) -> dict[str, str]:
    try:
        adapter = get_provider_adapter(entry.kind)
        adapter.validate(entry.metadata)
        if probe:
            adapter.probe(entry.handle, entry.metadata)
    except ValidationError as exc:
        return {
            "status": "error",
            "connection": "probe_failed" if probe else "not_probed",
            "message": f"No se pudo validar la conexión de forma segura: {exc}",
        }
    return {
        "status": "ok",
        "connection": "probed" if probe else "not_probed",
        "message": "Validación segura OK; la conexión respondió correctamente."
        if probe
        else "Validación segura OK; contrato del proveedor verificado.",
    }


def create_router(*, store: GraphStore, event_bus: EventBus) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/nodes")
    def list_nodes(
        graph_id: str,
        type: str | None = None,
        supertype: str | None = None,
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            nodes = store.query_nodes(graph_id, type=type, supertype=supertype, parent_id=parent_id)
        except GraphNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "graph_id": graph_id,
            "nodes": [
                {
                    "id": item.id,
                    "label": item.label,
                    "type": item.type,
                    "supertype": item.supertype,
                    "details": item.details,
                    "card_sections": item.card_sections,
                    "editable_fields": item.editable_fields,
                    "evidence_ids": item.evidence_ids,
                    "layout_hint": item.layout_hint,
                    "parent_id": item.parent_id,
                    "depth": item.depth,
                    "created_at": item.created_at,
                    "modified_at": item.modified_at,
                }
                for item in nodes
            ],
        }

    @router.post("/nodes", status_code=201)
    async def create_node(payload: dict[str, Any]) -> dict[str, Any]:
        graph_id = str(payload["graph_id"])
        node = dict(payload["node"])
        try:
            store.upsert_node(graph_id, node)
        except GraphNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        await event_bus.publish("node.created", graph_id, node)
        return {"graph_id": graph_id, "node": node, "timestamp": _utc_timestamp()}

    @router.patch("/nodes/{node_id}")
    async def patch_node(node_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        graph_id = str(payload["graph_id"])
        changes = dict(payload.get("changes") or {})
        try:
            existing_nodes = store.query_nodes(graph_id)
        except GraphNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        existing = next((item for item in existing_nodes if item.id == node_id), None)
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found in graph '{graph_id}'")
        # If caller sends changes.details as a dict, merge it into the existing
        # details rather than replacing the whole blob.  This lets the UI save a
        # single field (e.g. details.notes) without touching other details fields.
        if "details" in changes and isinstance(changes["details"], dict):
            existing_details = dict(existing.details or {})
            existing_details.update(changes["details"])
            changes = {**changes, "details": existing_details}
        node_payload = {"id": node_id, **changes}
        try:
            store.upsert_node(graph_id, node_payload)
        except GraphNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        refreshed = next((asdict(item) for item in store.query_nodes(graph_id) if item.id == node_id), None)
        if refreshed is None:
            raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found in graph '{graph_id}'")
        await event_bus.publish("node.updated", graph_id, refreshed)
        return {"graph_id": graph_id, "node": refreshed, "timestamp": _utc_timestamp()}

    @router.get("/edges")
    def list_edges(graph_id: str, source: str | None = None, target: str | None = None) -> dict[str, Any]:
        try:
            edges = store.query_edges(graph_id, source=source, target=target)
        except GraphNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "graph_id": graph_id,
            "edges": [
                {
                    "edge_id": item.edge_id,
                    "source": item.source,
                    "target": item.target,
                    "label": item.label,
                    "weight": item.weight,
                    "reasons": item.reasons,
                    "evidence_ids": item.evidence_ids,
                    "created_at": item.created_at,
                }
                for item in edges
            ],
        }

    @router.post("/edges", status_code=201)
    async def create_edge(payload: dict[str, Any]) -> dict[str, Any]:
        graph_id = str(payload["graph_id"])
        edge = dict(payload["edge"])
        try:
            store.upsert_edge(graph_id, edge)
        except GraphNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        await event_bus.publish("edge.created", graph_id, edge)
        return {"graph_id": graph_id, "edge": edge, "timestamp": _utc_timestamp()}

    @router.get("/search")
    def search(graph_id: str, q: str) -> dict[str, Any]:
        query = q.strip()
        if not query:
            raise HTTPException(status_code=422, detail="Query must be a non-empty string")
        result = mcp_tools.search_graph(store, {"graph_id": graph_id, "query": query})
        if isinstance(result, dict) and "code" in result and "message" in result:
            raise HTTPException(status_code=404, detail=result["message"])
        return {"graph_id": graph_id, "query": query, "results": _search_graph_api_result(query, result)}

    @router.get("/secrets")
    def list_secrets(graph_id: str, agent_scope: str | None = None) -> Any:
        denied = _require_workspace_admin(agent_scope)
        if denied is not None:
            return denied
        try:
            catalog = _load_secret_catalog(store, graph_id)
        except GraphNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except SecretManifestError as exc:
            raise HTTPException(status_code=400, detail=f"Secret manifest error: {exc}") from exc
        handles = _redacted_secret_handles(catalog)
        status = "ready" if handles else "empty"
        payload: dict[str, Any] = {"graph_id": graph_id, "status": status, "handles": handles}
        if not handles:
            payload["message"] = "No hay secretos configurados en este workspace."
        return payload

    @router.get("/secrets/schema")
    def secret_schema(graph_id: str) -> dict[str, Any]:
        try:
            _workspace_root_for_graph(store, graph_id)
        except GraphNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        catalog = SecretCatalog(_workspace_root_for_graph(store, graph_id))
        return {
            "graph_id": graph_id,
            "schema_version": catalog.schema["schema_version"],
            "provider_kinds": catalog.schema["provider_kinds"],
        }

    @router.post("/secrets", status_code=201)
    def add_secret(
        graph_id: str,
        payload: dict[str, Any],
        agent_scope: str | None = None,
        probe: bool = False,
    ) -> Any:
        denied = _require_workspace_admin(agent_scope)
        if denied is not None:
            return denied
        try:
            catalog = _load_secret_catalog(store, graph_id)
        except GraphNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except SecretManifestError as exc:
            raise HTTPException(status_code=400, detail=f"Secret manifest error: {exc}") from exc
        for field in ("handle", "kind", "metadata"):
            if field not in payload:
                raise HTTPException(status_code=422, detail=f"Missing required field: {field}")
        handle_value = payload["handle"]
        if not isinstance(handle_value, str) or not handle_value.strip():
            raise HTTPException(status_code=422, detail="Field 'handle' must be a non-empty string")
        kind_value = payload["kind"]
        if not isinstance(kind_value, str) or not kind_value.strip():
            raise HTTPException(status_code=422, detail="Field 'kind' must be a non-empty string")
        metadata_value = payload["metadata"]
        if not isinstance(metadata_value, dict):
            raise HTTPException(status_code=422, detail="Field 'metadata' must be an object")

        # Provider-scoped raw_value validation (A2-D4):
        # Read requires_raw_value from schema for this kind (default true when absent).
        # Only providers with requires_raw_value=false (e.g. aws-secrets) may omit raw_value.
        kind_schema = catalog.schema.get("provider_kinds", {}).get(kind_value, {})
        provider_requires_raw_value = kind_schema.get("requires_raw_value", True)
        raw_value: str | None = payload.get("raw_value") or None
        if provider_requires_raw_value:
            if not isinstance(raw_value, str) or not raw_value:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Field 'raw_value' (password/credential) must be a non-empty string "
                        f"for provider kind '{kind_value}'."
                    ),
                )

        # Fail fast on unknown kinds and invalid metadata so the manifest is never
        # persisted in an inconsistent state. Adapters own the per-kind contract.
        try:
            adapter = get_provider_adapter(kind_value)
            adapter.validate(metadata_value)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid secret payload: {exc}") from exc
        entry = SecretEntry(
            handle=handle_value.strip(),
            kind=kind_value,
            metadata=dict(metadata_value),
        )
        try:
            catalog.add(entry, raw_value=raw_value)
        except (SecretManifestError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"Invalid secret payload: {exc}") from exc
        validation = _validate_secret_entry(catalog, entry, probe=probe)
        return {"graph_id": graph_id, "handle": entry.handle, "created_at": entry.created_at, "validation": validation}

    @router.delete("/secrets/{handle}")
    def remove_secret(graph_id: str, handle: str, agent_scope: str | None = None) -> Any:
        denied = _require_workspace_admin(agent_scope)
        if denied is not None:
            return denied
        try:
            catalog = _load_secret_catalog(store, graph_id)
        except GraphNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except SecretManifestError as exc:
            raise HTTPException(status_code=400, detail=f"Secret manifest error: {exc}") from exc
        if catalog.get(handle) is None:
            raise HTTPException(status_code=404, detail=f"Secret handle '{handle}' not found")
        catalog.remove(handle)
        return Response(status_code=204)

    # -------------------------------------------------------------------------
    # B4 — Read-only AI routes (thin adapters over existing MCP tool handlers)
    # No new MCP tools registered; CC-2 honored.
    # -------------------------------------------------------------------------

    @router.get("/ai/suggestions")
    def ai_suggestions(graph_id: str, node_id: str) -> dict[str, Any]:
        """GET /api/ai/suggestions?graph_id=&node_id=

        Wraps the existing suggest_connections MCP tool handler server-side so
        the browser can call it over HTTP.  Read-only; no write side-effects.

        The handler is decorated with @error_boundary, which means tool-level
        errors (not found, validation) are returned as {"code": ..., "message": ...}
        dicts rather than raised exceptions.  We detect these and convert them to
        proper HTTP 4xx responses.
        """
        result = mcp_tools.suggest_connections(store, {"graph_id": graph_id, "node_id": node_id})
        if isinstance(result, dict) and "code" in result and "message" in result and "suggestions" not in result:
            raise HTTPException(status_code=404, detail=result["message"])
        return result

    @router.get("/ai/completeness")
    def ai_completeness(graph_id: str, node_id: str | None = None) -> dict[str, Any]:
        """GET /api/ai/completeness?graph_id=&node_id=(optional)

        Wraps the existing assess_completeness MCP tool handler server-side.
        assess_completeness is a graph-level assessment; node_id is accepted for
        UI context but not forwarded to the handler (the handler does not use it).
        Read-only; no write side-effects.

        Same error-boundary unwrapping as /ai/suggestions.
        """
        result = mcp_tools.assess_completeness(store, {"graph_id": graph_id})
        if isinstance(result, dict) and "code" in result and "message" in result and "completeness_matrix" not in result:
            raise HTTPException(status_code=404, detail=result["message"])
        return result

    @router.websocket("/events")
    async def events_stream(websocket: WebSocket) -> None:
        graph_id = websocket.query_params.get("graph_id")
        if not graph_id:
            await websocket.close(code=1008)
            return

        await websocket.accept()
        queue = event_bus.subscribe()
        try:
            while True:
                event = await queue.get()
                if event["graph_id"] != graph_id:
                    continue
                await websocket.send_json(event)
        except WebSocketDisconnect:
            return
        finally:
            event_bus.unsubscribe(queue)

    return router
