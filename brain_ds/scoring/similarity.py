"""Server-side connection suggestions: deterministic compatibility scoring.

Powers the `suggest_connections` MCP tool. Given one focus node, ranks every
other node in the graph by connection compatibility so an AI agent can decide
which edges to create without re-reading the whole graph into its context.

Scoring is deterministic and dependency-free so it stays fast at thousands of
nodes: one nodes query, one edges query, one tokenization pass.
"""

from __future__ import annotations

from typing import Any

from brain_ds.scoring.factors import _tokens
from brain_ds.store.models import EdgeRow, NodeRow

# Canonical directed suggestion per entity-type pair, derived from the
# deterministic CONNECTION_RULES in skills/map-connections/SKILL.md.
# Key: frozenset of the two entity types. Value: (source_type, target_type, label).
TYPE_PAIR_SUGGESTIONS: dict[frozenset[str], tuple[str, str, str]] = {
    frozenset({"Organization", "Department"}): ("Organization", "Department", "owns"),
    frozenset({"Department", "Role"}): ("Department", "Role", "owns"),
    frozenset({"Role", "Data Source"}): ("Role", "Data Source", "uses"),
    frozenset({"Department", "Data Source"}): ("Department", "Data Source", "uses"),
    frozenset({"Heuristic", "Department"}): ("Heuristic", "Department", "shared-with"),
    frozenset({"Heuristic", "Role"}): ("Role", "Heuristic", "uses"),
    frozenset({"Tacit Knowledge", "Role"}): ("Tacit Knowledge", "Role", "owned-by"),
    frozenset({"Problem / Improvement Area", "Data Source"}): (
        "Data Source",
        "Problem / Improvement Area",
        "degraded-by",
    ),
    frozenset({"Problem / Improvement Area", "Role"}): (
        "Role",
        "Problem / Improvement Area",
        "blocked-by",
    ),
    frozenset({"Project", "Department"}): ("Project", "Department", "owned-by"),
    frozenset({"Project", "Risk"}): ("Project", "Risk", "blocked-by"),
    frozenset({"Decision", "Project"}): ("Project", "Decision", "decided-by"),
    frozenset({"Decision", "Risk"}): ("Risk", "Decision", "decided-by"),
    frozenset({"KPI", "Department"}): ("KPI", "Department", "owned-by"),
    frozenset({"KPI", "Role"}): ("Role", "KPI", "accountable"),
    frozenset({"KPI", "Data Source"}): ("KPI", "Data Source", "measured-by"),
    frozenset({"KPI", "Problem / Improvement Area"}): (
        "KPI",
        "Problem / Improvement Area",
        "degraded-by",
    ),
    frozenset({"Solution", "KPI"}): ("Solution", "KPI", "improves"),
    frozenset({"Solution", "Problem / Improvement Area"}): (
        "Solution",
        "Problem / Improvement Area",
        "resolves",
    ),
    frozenset({"Decision", "KPI"}): ("Decision", "KPI", "targets"),
    frozenset({"Decision", "Solution"}): ("Solution", "Decision", "decided-by"),
}

# Fallback when the pair has no canonical rule but lexical overlap is strong.
DEFAULT_SUGGESTED_LABEL = "shared-with"

TYPE_AFFINITY_MAPPED = 1.0
TYPE_AFFINITY_UNMAPPED = 0.35

WEIGHT_TYPE_AFFINITY = 0.45
WEIGHT_LEXICAL = 0.45
WEIGHT_NEIGHBORS = 0.10

DEFAULT_THRESHOLD = 0.30
DEFAULT_LIMIT = 10
MAX_LIMIT = 50
_SECTION_CONTENT_CAP = 400


def node_text_tokens(node: NodeRow) -> set[str]:
    parts: list[str] = [node.label or "", node.type or ""]
    for value in (node.details or {}).values():
        parts.append(str(value))
    for section in node.card_sections or []:
        if isinstance(section, dict):
            parts.append(str(section.get("title", "")))
            parts.append(str(section.get("content", ""))[:_SECTION_CONTENT_CAP])
    return _tokens(" ".join(parts))


def _lexical_similarity(focus_tokens: set[str], other_tokens: set[str]) -> tuple[float, list[str]]:
    if not focus_tokens or not other_tokens:
        return 0.0, []
    overlap = focus_tokens & other_tokens
    if not overlap:
        return 0.0, []
    # Overlap coefficient instead of Jaccard: a short label matching inside a
    # long Data Source card should still score high.
    score = len(overlap) / min(len(focus_tokens), len(other_tokens))
    return min(score, 1.0), sorted(overlap)


def _adjacency(edges: list[EdgeRow]) -> dict[str, set[str]]:
    neighbors: dict[str, set[str]] = {}
    for edge in edges:
        neighbors.setdefault(edge.source, set()).add(edge.target)
        neighbors.setdefault(edge.target, set()).add(edge.source)
    return neighbors


def _suggestion_for_pair(focus: NodeRow, other: NodeRow) -> tuple[str, str, str, bool]:
    """Return (source_id, target_id, label, is_mapped) oriented per canonical rule."""
    rule = TYPE_PAIR_SUGGESTIONS.get(frozenset({focus.type, other.type}))
    if rule is None:
        return focus.id, other.id, DEFAULT_SUGGESTED_LABEL, False
    source_type, _target_type, label = rule
    if focus.type == source_type:
        return focus.id, other.id, label, True
    return other.id, focus.id, label, True


def suggest_connections_for_node(
    nodes: list[NodeRow],
    edges: list[EdgeRow],
    node_id: str,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    limit = max(1, min(int(limit), MAX_LIMIT))
    threshold = min(max(float(threshold), 0.0), 1.0)

    focus = next((node for node in nodes if node.id == node_id), None)
    if focus is None:
        raise KeyError(node_id)

    neighbors = _adjacency(edges)
    connected = neighbors.get(focus.id, set())
    focus_tokens = node_text_tokens(focus)

    candidates: list[dict[str, Any]] = []
    for other in nodes:
        if other.id == focus.id or other.id in connected:
            continue

        source_id, target_id, label, is_mapped = _suggestion_for_pair(focus, other)
        type_affinity = TYPE_AFFINITY_MAPPED if is_mapped else TYPE_AFFINITY_UNMAPPED
        lexical, shared_tokens = _lexical_similarity(focus_tokens, node_text_tokens(other))
        shared_neighbors = connected & neighbors.get(other.id, set())
        neighbor_score = min(len(shared_neighbors) / 3.0, 1.0)

        score = (
            WEIGHT_TYPE_AFFINITY * type_affinity
            + WEIGHT_LEXICAL * lexical
            + WEIGHT_NEIGHBORS * neighbor_score
        )
        if score < threshold:
            continue

        reason_parts: list[str] = []
        if is_mapped:
            reason_parts.append(f"type rule: {focus.type} <-> {other.type} ({label})")
        if shared_tokens:
            reason_parts.append("shared tokens: " + ", ".join(shared_tokens[:6]))
        if shared_neighbors:
            reason_parts.append(f"{len(shared_neighbors)} shared neighbor(s)")
        if not reason_parts:
            reason_parts.append("weak generic compatibility")

        candidates.append(
            {
                "node_id": other.id,
                "label": other.label,
                "type": other.type,
                "score": round(score, 4),
                "suggested_edge": {"source": source_id, "target": target_id, "label": label},
                "reason": "; ".join(reason_parts),
            }
        )

    candidates.sort(key=lambda item: (-item["score"], item["node_id"]))
    above_threshold = len(candidates)
    returned = candidates[:limit]
    effective_threshold = returned[-1]["score"] if above_threshold > limit else threshold

    return {
        "node_id": focus.id,
        "node_label": focus.label,
        "node_type": focus.type,
        "threshold": threshold,
        "effective_threshold": effective_threshold,
        "candidates_above_threshold": above_threshold,
        "returned": len(returned),
        "already_connected": sorted(connected),
        "suggestions": returned,
    }
