"""Pure neighborhood and reliability-ranking helpers for graph retrieval."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from brain_ds.scoring.similarity import _adjacency
from brain_ds.store.models import EdgeRow, NodeRow

DEPTH_MAX = 2
HIERARCHY_MAX_HOPS = 20

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
