"""Server-side connection suggestions: deterministic compatibility scoring.

Powers the `suggest_connections` MCP tool. Given one focus node, ranks every
other node in the graph by connection compatibility so an AI agent can decide
which edges to create without re-reading the whole graph into its context.

Scoring is deterministic and dependency-free so it stays fast at thousands of
nodes: one nodes query, one edges query, one tokenization pass.
"""

from __future__ import annotations

from typing import Any

from brain_ds.scoring.factors import _tokens, evidence_count, explicit_reference
from brain_ds.store.models import EdgeRow, NodeRow

# Canonical directed suggestion per entity-type pair, derived from the
# deterministic CONNECTION_RULES in skills/map-connections/SKILL.md.
# Key: frozenset of the two entity types. Value: (source_type, target_type, label).
TYPE_PAIR_SUGGESTIONS: dict[frozenset[str], tuple[str, str, str]] = {
    frozenset({"Organization", "Department"}): ("Organization", "Department", "owns"),
    frozenset({"Department", "Role"}): ("Department", "Role", "owns"),
    frozenset({"Role", "Data Source"}): ("Role", "Data Source", "uses"),
    frozenset({"Department", "Data Source"}): ("Department", "Data Source", "uses"),
    frozenset({"Heuristic", "Department"}): ("Department", "Heuristic", "uses"),
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
    # Coverage expansion: the most common real-domain pairs used to fall into
    # the shared-with fallback. Each now has a canonical directed rule.
    frozenset({"Organization", "Role"}): ("Organization", "Role", "owns"),
    frozenset({"Organization", "Data Source"}): ("Organization", "Data Source", "owns"),
    frozenset({"Organization", "Project"}): ("Organization", "Project", "owns"),
    frozenset({"Organization", "KPI"}): ("Organization", "KPI", "owns"),
    frozenset({"Risk", "Data Source"}): ("Risk", "Data Source", "creates-risk"),
    frozenset({"Project", "Solution"}): ("Solution", "Project", "decided-by"),
    frozenset({"Heuristic", "Data Source"}): ("Heuristic", "Data Source", "uses"),
    frozenset({"Tacit Knowledge", "Data Source"}): ("Tacit Knowledge", "Data Source", "uses"),
    # Genuinely symmetric pairs: lineage between sources, peers sharing artifacts.
    frozenset({"Data Source"}): ("Data Source", "Data Source", "depends-on"),
    frozenset({"Role"}): ("Role", "Role", "shared-with"),
}

# There is NO silent fallback label anymore. A pair without canonical rule is
# flagged for human/agent review instead of being dressed up as "shared-with".
REVIEW_NEEDED_LABEL = "review-needed"

# "shared-with" is only earned by unmapped pairs with genuinely strong lexical
# evidence: combined score above this floor AND at least this many meaningful
# shared tokens (stopwords are already stripped by the tokenizer).
SHARED_WITH_MIN_SCORE = 0.70
SHARED_WITH_MIN_TOKENS = 3

TYPE_AFFINITY_MAPPED = 1.0
TYPE_AFFINITY_UNMAPPED = 0.35

WEIGHT_TYPE_AFFINITY = 0.40
WEIGHT_NEIGHBORS = 0.10

# Evidence-aware lexical/evidence split: high-impact relationships must be
# backed by captured evidence, not token overlap — a label like "owns" with a
# great lexical score and zero evidence stays below the default threshold.
# Weak/descriptive labels keep lexical as the dominant signal.
HIGH_IMPACT_LABELS = frozenset(
    {"owns", "owned-by", "creates-risk", "blocked-by", "decided-by", "degraded-by", "resolves"}
)
WEIGHT_LEXICAL_DEFAULT = 0.40
WEIGHT_EVIDENCE_DEFAULT = 0.10
WEIGHT_LEXICAL_HIGH_IMPACT = 0.10
WEIGHT_EVIDENCE_HIGH_IMPACT = 0.40

DEFAULT_THRESHOLD = 0.55
DEFAULT_MIN_SHARED_TOKENS = 2
DEFAULT_LIMIT = 10
MAX_LIMIT = 50
_SECTION_CONTENT_CAP = 400

# Sparse-node gate: a node without a concrete "where" or still marked
# Underspecified must be elicited before it earns automatic edges.
SPARSE_BLOCK_REASON = "blocked: sparse node — fill in 'where' field first"
LOW_SIGNAL_DETAIL_VALUES = frozenset({"ok", "n/a", "na", "none", "unknown"})


def is_sparse(node: NodeRow) -> bool:
    """True when the node lacks grounding: empty details.where or a details.learned
    that still starts with "Underspecified"."""
    details = node.details or {}
    where = str(details.get("where") or "").strip()
    learned = str(details.get("learned") or "").strip()
    return not where or learned.lower().startswith("underspecified")


def node_text_tokens(node: NodeRow) -> set[str]:
    parts: list[str] = [node.label or "", node.type or ""]
    for value in (node.details or {}).values():
        text = str(value or "").strip()
        if text.lower() in LOW_SIGNAL_DETAIL_VALUES:
            continue
        parts.append(text)
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


def _pair_evidence(
    focus: NodeRow, other: NodeRow, evidence_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Evidence items referenced by either node of the candidate pair."""
    ids: list[str] = []
    for node in (focus, other):
        for evidence_id in node.evidence_ids or []:
            ids.append(str(evidence_id))
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for evidence_id in ids:
        if evidence_id in seen:
            continue
        seen.add(evidence_id)
        item = evidence_by_id.get(evidence_id)
        if item is not None:
            items.append(item)
    return items


def _evidence_score(
    focus: NodeRow, other: NodeRow, pair_items: list[dict[str, Any]]
) -> tuple[float, int]:
    """Strongest evidence signal for the pair: explicit mention beats raw count."""
    if not pair_items:
        return 0.0, 0
    count_score, _ = evidence_count(pair_items)
    ref_score, _ = explicit_reference((focus.label or "", other.label or ""), pair_items)
    return max(count_score, ref_score), len(pair_items)


def _suggestion_for_pair(focus: NodeRow, other: NodeRow) -> tuple[str, str, str, bool]:
    """Return (source_id, target_id, label, is_mapped) oriented per canonical rule."""
    rule = TYPE_PAIR_SUGGESTIONS.get(frozenset({focus.type, other.type}))
    if rule is None:
        return focus.id, other.id, REVIEW_NEEDED_LABEL, False
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
    minimum_shared_tokens: int = DEFAULT_MIN_SHARED_TOKENS,
    evidence_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    limit = max(1, min(int(limit), MAX_LIMIT))
    threshold = min(max(float(threshold), 0.0), 1.0)
    minimum_shared_tokens = max(0, int(minimum_shared_tokens))
    evidence_by_id: dict[str, dict[str, Any]] = {
        str(item.get("id") or item.get("evidence_id")): item
        for item in (evidence_items or [])
        if item.get("id") or item.get("evidence_id")
    }

    focus = next((node for node in nodes if node.id == node_id), None)
    if focus is None:
        raise KeyError(node_id)

    neighbors = _adjacency(edges)
    connected = neighbors.get(focus.id, set())
    focus_tokens = node_text_tokens(focus)
    focus_sparse = is_sparse(focus)

    candidates: list[dict[str, Any]] = []
    review_needed_count = 0
    blocked_sparse_count = 0
    for other in nodes:
        if other.id == focus.id or other.id in connected:
            continue

        source_id, target_id, label, is_mapped = _suggestion_for_pair(focus, other)
        type_affinity = TYPE_AFFINITY_MAPPED if is_mapped else TYPE_AFFINITY_UNMAPPED
        lexical, shared_tokens = _lexical_similarity(focus_tokens, node_text_tokens(other))
        shared_neighbors = connected & neighbors.get(other.id, set())
        neighbor_score = min(len(shared_neighbors) / 3.0, 1.0)
        evidence_score, evidence_n = _evidence_score(
            focus, other, _pair_evidence(focus, other, evidence_by_id)
        )

        if label in HIGH_IMPACT_LABELS:
            lexical_weight, evidence_weight = WEIGHT_LEXICAL_HIGH_IMPACT, WEIGHT_EVIDENCE_HIGH_IMPACT
        else:
            lexical_weight, evidence_weight = WEIGHT_LEXICAL_DEFAULT, WEIGHT_EVIDENCE_DEFAULT

        score = (
            WEIGHT_TYPE_AFFINITY * type_affinity
            + lexical_weight * lexical
            + evidence_weight * evidence_score
            + WEIGHT_NEIGHBORS * neighbor_score
        )

        if label == "shared-with" and (
            score < SHARED_WITH_MIN_SCORE or len(shared_tokens) < SHARED_WITH_MIN_TOKENS
        ):
            continue

        if score < threshold:
            continue

        # Unmapped pairs need real lexical evidence: without a canonical type
        # rule, fewer than minimum_shared_tokens meaningful shared tokens is
        # noise, no matter how high the composite score climbs.
        if not is_mapped and len(shared_tokens) < minimum_shared_tokens:
            continue

        reason_parts: list[str] = []
        if is_mapped:
            reason_parts.append(f"type rule: {focus.type} <-> {other.type} ({label})")
        else:
            # "shared-with" must be earned; everything else stays review-needed
            # so the agent cannot silently promote a no-rule pair to an edge.
            if score > SHARED_WITH_MIN_SCORE and len(shared_tokens) >= SHARED_WITH_MIN_TOKENS:
                label = "shared-with"
                reason_parts.append(
                    f"no canonical type rule for {focus.type} <-> {other.type}; "
                    f"strong lexical evidence ({len(shared_tokens)} shared tokens)"
                )
            else:
                label = REVIEW_NEEDED_LABEL
                reason_parts.append(
                    f"no canonical type rule for {focus.type} <-> {other.type}; "
                    "lexical evidence too weak to auto-suggest a relationship"
                )
                review_needed_count += 1
        if shared_tokens:
            reason_parts.append("shared tokens: " + ", ".join(shared_tokens[:6]))
        if evidence_n:
            reason_parts.append(f"{evidence_n} evidence item(s), evidence score {evidence_score:.2f}")
        elif label in HIGH_IMPACT_LABELS:
            reason_parts.append("no evidence captured — high-impact label needs evidence before acceptance")
        if shared_neighbors:
            reason_parts.append(f"{len(shared_neighbors)} shared neighbor(s)")

        # Sparse gate runs last so the candidate stays visible (the user should
        # see the node exists) but arrives blocked instead of edge-ready.
        if focus_sparse or is_sparse(other):
            label = REVIEW_NEEDED_LABEL
            reason_parts.insert(0, SPARSE_BLOCK_REASON)
            blocked_sparse_count += 1

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
        "minimum_shared_tokens": minimum_shared_tokens,
        "effective_threshold": effective_threshold,
        "candidates_above_threshold": above_threshold,
        "returned": len(returned),
        "review_needed": review_needed_count,
        "blocked_sparse": blocked_sparse_count,
        "already_connected": sorted(connected),
        "suggestions": returned,
    }
