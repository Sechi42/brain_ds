"""Stakeholder ownership resolution for currency question tags."""

from __future__ import annotations

from typing import Any

OWNER_EDGE_LABELS = {"OWNS", "OWNED_BY"}
OWNER_NODE_TYPES = {"ROLE", "PERSON"}


def resolve_owner(
    node_id: str,
    edges: list[dict[str, Any]],
    nodes_by_id: dict[str, dict[str, Any]],
) -> str:
    """Resolve a question owner through OWNS/OWNED_BY edges, or return unknown."""
    for edge in edges:
        label = _normalize(edge.get("label"))
        if label not in OWNER_EDGE_LABELS:
            continue

        owner_id = _owner_id_for_edge(node_id, edge, label)
        owner = nodes_by_id.get(owner_id or "", {})
        if _normalize(owner.get("type")) in OWNER_NODE_TYPES:
            return str(owner.get("label") or owner.get("id") or "unknown")

    return "unknown"


def _owner_id_for_edge(node_id: str, edge: dict[str, Any], label: str) -> str | None:
    source = str(edge.get("source", ""))
    target = str(edge.get("target", ""))
    if label == "OWNED_BY" and source == node_id:
        return target
    if label == "OWNS" and target == node_id:
        return source
    return None


def _normalize(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "_").replace("-", "_")
