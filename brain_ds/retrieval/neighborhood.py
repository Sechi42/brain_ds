"""Pure neighborhood and reliability-ranking helpers for graph retrieval."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

from brain_ds.scoring.similarity import _adjacency
from brain_ds.store.models import EdgeRow, NodeRow

DEPTH_MAX = 2
HIERARCHY_MAX_HOPS = 20
DEFAULT_ROUTE_MEMBER_LIMIT = 25

_STATUS_TIER = {
    "confirmed": 1,
    "inferred": 2,
    "needs-confirmation": 3,
    "abstain": 4,
}


@dataclass(slots=True)
class AnnotatedEdge:
    """Edge plus retrieval reliability metadata."""

    edge: EdgeRow
    ledger_status: str | None
    tier: int | None
    reliability_tag: str = ""
    tag_detail: str = ""


@dataclass(slots=True)
class ClusterRoute:
    """Semantic cluster selected as a retrieval route."""

    id: str
    name: str
    status: str
    summary: str
    anchor_ids: list[str]
    member_ids: list[str]
    routing_weight: float


def build_adjacency(edges: list[EdgeRow]) -> dict[str, set[str]]:
    """Build the same undirected adjacency map used by similarity scoring."""
    return _adjacency(edges)


def expand_neighborhood(
    anchor_ids: list[str],
    adjacency: dict[str, set[str]],
    *,
    depth: int,
) -> dict[str, int]:
    """BFS from anchors, returning each node's minimum depth from any anchor."""
    max_depth = max(1, min(int(depth), DEPTH_MAX))
    depth_by_node: dict[str, int] = {}
    queue: deque[tuple[str, int]] = deque()

    for anchor_id in anchor_ids:
        if anchor_id in depth_by_node:
            continue
        depth_by_node[anchor_id] = 0
        queue.append((anchor_id, 0))

    while queue:
        node_id, current_depth = queue.popleft()
        if current_depth >= max_depth:
            continue
        for neighbor_id in sorted(adjacency.get(node_id, set())):
            next_depth = current_depth + 1
            previous_depth = depth_by_node.get(neighbor_id)
            if previous_depth is not None and previous_depth <= next_depth:
                continue
            depth_by_node[neighbor_id] = next_depth
            queue.append((neighbor_id, next_depth))

    return depth_by_node


def ledger_status_to_tier(status: str | None) -> int | None:
    """Map a latest ledger status to retrieval tier; invalidated is excluded."""
    if status is None:
        return 2
    if status == "invalidated":
        return None
    return _STATUS_TIER.get(status)


def sort_edges_by_reliability(annotated_edges: list[AnnotatedEdge]) -> list[AnnotatedEdge]:
    """Sort response edges by tier ASC and weight DESC, excluding invalidated."""
    included = [edge for edge in annotated_edges if edge.tier is not None]
    return sorted(
        included,
        key=lambda annotated: (
            annotated.tier if annotated.tier is not None else 999,
            -(annotated.edge.weight or 0.0),
        ),
    )


def walk_hierarchy_path(anchor_id: str, nodes_by_id: dict[str, NodeRow]) -> list[str]:
    """Walk parent_id links from anchor to root and return root-to-anchor labels."""
    path: list[str] = []
    current_id: str | None = anchor_id
    hops = 0

    while current_id is not None:
        node = nodes_by_id.get(current_id)
        if node is None:
            break
        path.append(node.label)
        hops += 1
        current_id = node.parent_id
        if current_id is not None and hops >= HIERARCHY_MAX_HOPS:
            path.append("[hierarchy truncated]")
            break

    return list(reversed(path))


def select_cluster_routes(
    query: str | None,
    clusters: list[Any],
    members_by_cluster: dict[str, list[str]],
    nodes_by_id: dict[str, NodeRow],
    *,
    limit: int,
    member_limit: int = DEFAULT_ROUTE_MEMBER_LIMIT,
) -> list[ClusterRoute]:
    """Select semantic cluster routes using summaries, anchors, and memberships."""
    if not query:
        return []
    tokens = [token for token in _tokens(query) if len(token) > 2]
    if not tokens:
        return []

    ranked: list[tuple[float, str, ClusterRoute]] = []
    for cluster in clusters:
        metadata = cluster.metadata or {}
        status = str(metadata.get("status") or "confirmed")
        if status in {"archived", "rejected"}:
            continue
        selected_member_ids = [node_id for node_id in members_by_cluster.get(cluster.id, []) if node_id in nodes_by_id]
        primary_anchor = metadata.get("primary_anchor_id")
        anchor_ids = [primary_anchor] if isinstance(primary_anchor, str) and primary_anchor in nodes_by_id else []
        if not anchor_ids:
            anchor_ids = selected_member_ids[:1]
        if not anchor_ids:
            continue

        searchable = _cluster_search_text(cluster, metadata, selected_member_ids, nodes_by_id)
        token_hits = sum(1 for token in tokens if token in searchable)
        if token_hits == 0:
            continue

        status_weight = 1.0 if status == "confirmed" else 0.65 if status == "proposed" else 0.8
        confidence = metadata.get("quality_signals", {}).get("confidence") if isinstance(metadata.get("quality_signals"), dict) else None
        confidence_boost = float(confidence) * 0.1 if isinstance(confidence, int | float) else 0.0
        score = token_hits + status_weight + confidence_boost
        ranked.append(
            (
                score,
                cluster.id,
                ClusterRoute(
                    id=cluster.id,
                    name=cluster.name,
                    status=status,
                    summary=str(metadata.get("summary") or cluster.description or ""),
                    anchor_ids=anchor_ids,
                    member_ids=selected_member_ids[: max(0, int(member_limit))],
                    routing_weight=status_weight,
                ),
            )
        )

    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [route for _, _, route in ranked[: max(1, limit)]]


def cluster_routes_to_dict(routes: list[ClusterRoute]) -> dict[str, Any]:
    """Serialize selected routes for the MCP response."""
    if not routes:
        return {"mode": "bfs", "clusters": []}
    return {
        "mode": "cluster",
        "clusters": [
            {
                "id": route.id,
                "name": route.name,
                "status": route.status,
                "summary": route.summary,
                "anchor_ids": route.anchor_ids,
                "member_ids": route.member_ids,
                "routing_weight": route.routing_weight,
            }
            for route in routes
        ],
    }


def _tokens(text: str) -> list[str]:
    return [part.strip().lower() for part in text.replace("/", " ").replace("-", " ").split()]


def _cluster_search_text(
    cluster: Any,
    metadata: dict[str, Any],
    member_ids: list[str],
    nodes_by_id: dict[str, NodeRow],
) -> str:
    parts = [cluster.name, cluster.description or "", str(metadata.get("summary") or "")]
    primary_anchor = metadata.get("primary_anchor_id")
    if isinstance(primary_anchor, str) and primary_anchor in nodes_by_id:
        parts.append(nodes_by_id[primary_anchor].label)
    for node_id in member_ids:
        node = nodes_by_id.get(node_id)
        if node is not None:
            parts.append(node.label)
            parts.append(node.type)
    return " ".join(parts).lower()
