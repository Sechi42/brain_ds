from __future__ import annotations

from datetime import UTC, datetime
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from brain_ds.api.events import EventBus
from brain_ds.store.errors import GraphNotFoundError
from brain_ds.store.graph_store import GraphStore


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


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
