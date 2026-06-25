"""Reliability-ascending LLM prose serializer for retrieve_context (R-08, R-07).

Design decisions (from design doc):
- D3: Each anchor produces an independent ANCHOR+HIERARCHY+CONNECTIONS block.
- D4: Truncation removes farthest-hop card_sections first (depth DESC),
      ties broken by longest card_sections bytes first.
      Only card_sections content is stripped; labels, tags, edges are never touched.
- The 256KiB constant is re-declared here to avoid coupling to verify.edge_snapshot.
"""

from __future__ import annotations

from brain_ds.retrieval.neighborhood import AnnotatedEdge

# 256 KiB — mirrors MAX_SNAPSHOT_PAYLOAD_BYTES in verify.edge_snapshot
_MAX_PAYLOAD_BYTES = 256 * 1024
_TRUNCATION_SENTINEL = "[TRUNCATED — payload limit reached]"

# Maps reliability tier to the bracket label used in prose.
_TIER_BRACKET = {
    1: "[CONFIRMED]",
    2: "[INFERRED]",
    3: "[PENDING REVIEW]",
    4: "[ABSTAIN]",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def serialize_for_llm(
    nodes: list[dict],
    edges: list[AnnotatedEdge],
    hierarchy_paths: dict[str, list[str]],
) -> str:
    """Build reliability-ascending LLM prose for a retrieved subgraph.

    Parameters
    ----------
    nodes:
        Subgraph node dicts — ``{id, label, type, depth_from_anchor, card_sections}``.
        Anchors are those whose ``id`` is a key in *hierarchy_paths*.
    edges:
        Annotated edges sorted ``(tier ASC, weight DESC)`` by
        ``sort_edges_by_reliability``.  The serializer reverses them so that
        most-trusted (confirmed) appears last — *reliability-ascending* (R-08).
    hierarchy_paths:
        Map of ``anchor_node_id → [root_label, ..., anchor_label]`` label chain.

    Returns
    -------
    str
        Prose string bounded by 256 KiB.  If truncated, ends with the sentinel.
    """
    nodes_by_id: dict[str, dict] = {n["id"]: n for n in nodes}
    anchor_ids: list[str] = list(hierarchy_paths.keys())

    full_text = _render_all(anchor_ids, nodes_by_id, edges, hierarchy_paths, suppressed=set())
    if len(full_text.encode("utf-8")) <= _MAX_PAYLOAD_BYTES:
        return full_text

    # Truncation needed — D4: farthest-hop card_sections stripped first.
    truncated = _apply_truncation(anchor_ids, nodes_by_id, edges, hierarchy_paths, full_text)
    return truncated


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _render_all(
    anchor_ids: list[str],
    nodes_by_id: dict[str, dict],
    edges: list[AnnotatedEdge],
    hierarchy_paths: dict[str, list[str]],
    suppressed: set[str],  # node IDs whose card_sections are suppressed
) -> str:
    """Render all anchor blocks joined by blank lines."""
    # Reliability-ascending: reverse the already (tier ASC, weight DESC) sorted list.
    ascending_edges = list(reversed(edges))

    blocks: list[str] = []
    for anchor_id in anchor_ids:
        anchor_node = nodes_by_id.get(anchor_id)
        if anchor_node is None:
            continue
        block = _render_anchor_block(
            anchor_node,
            nodes_by_id,
            ascending_edges,
            hierarchy_paths.get(anchor_id, [anchor_node["label"]]),
            suppressed,
        )
        blocks.append(block)

    return "\n\n".join(blocks)


def _render_anchor_block(
    anchor: dict,
    nodes_by_id: dict[str, dict],
    ascending_edges: list[AnnotatedEdge],  # already reversed to tier-4 first
    path: list[str],
    suppressed: set[str],
) -> str:
    """Render one ANCHOR + HIERARCHY + CONNECTIONS + NODE DETAILS block."""
    anchor_id = anchor["id"]
    anchor_label = anchor["label"]
    anchor_type = anchor.get("type", "")

    depth_from_root = max(0, len(path) - 1)
    parent_label = path[-2] if len(path) > 1 else "root"

    lines: list[str] = []

    # --- Header ---
    lines.append(
        f"[ANCHOR: {anchor_type} \"{anchor_label}\" — {anchor_id}"
        f" — depth={depth_from_root} under {parent_label}]"
    )
    lines.append("")

    # --- Hierarchy ---
    hierarchy_str = " → ".join(path)
    lines.append(f"HIERARCHY: {hierarchy_str}")
    lines.append("")

    # --- Connections ---
    lines.append("CONNECTIONS (reliability-ascending — most trusted last):")
    if ascending_edges:
        for idx, ae in enumerate(ascending_edges, start=1):
            source_label = _label(nodes_by_id, ae.edge.source)
            target_label = _label(nodes_by_id, ae.edge.target)
            bracket = _TIER_BRACKET.get(ae.tier or 0, "[UNKNOWN]")
            line = (
                f"  {idx}. {bracket} {source_label} → {ae.edge.label} →"
                f" {target_label} (score={ae.edge.weight:.2f}) {ae.reliability_tag}"
            )
            lines.append(line)
    else:
        lines.append("  (no connections)")
    lines.append("")

    # --- Node details (card_sections) ---
    lines.append("NODE DETAILS:")
    # Show card_sections for all nodes in the subgraph (anchor first, then others)
    all_node_ids = list(nodes_by_id.keys())
    rendered_any = False
    for node_id in all_node_ids:
        node = nodes_by_id[node_id]
        sections = node.get("card_sections") or []
        if node_id in suppressed or not sections:
            continue
        lines.append(f"  [{node['label']} ({node.get('type', '')})]")
        for section in sections:
            title = section.get("title", "")
            content = section.get("content", "")
            if title:
                lines.append(f"  {title}: {content}")
            elif content:
                lines.append(f"  {content}")
        rendered_any = True

    if not rendered_any:
        lines.append("  (no node details)")

    return "\n".join(lines)


def _label(nodes_by_id: dict[str, dict], node_id: str) -> str:
    """Return a node's label, falling back to its raw ID if not in the map."""
    node = nodes_by_id.get(node_id)
    if node is None:
        return node_id
    return node.get("label", node_id)


# ---------------------------------------------------------------------------
# Truncation (D4)
# ---------------------------------------------------------------------------


def _apply_truncation(
    anchor_ids: list[str],
    nodes_by_id: dict[str, dict],
    edges: list[AnnotatedEdge],
    hierarchy_paths: dict[str, list[str]],
    full_text: str,
) -> str:
    """Strip card_sections from farthest-hop nodes until under 256 KiB, then append sentinel.

    D4: truncate depth DESC, then longest card_sections bytes DESC within each depth.
    Only card_sections CONTENT is removed; labels, edges, and hierarchy lines survive.
    """
    full_bytes = len(full_text.encode("utf-8"))
    sentinel_bytes = len(_TRUNCATION_SENTINEL.encode("utf-8"))
    target = _MAX_PAYLOAD_BYTES - sentinel_bytes

    # Build a sorted list of nodes to strip (farthest-hop first, longest first).
    def _card_size(n: dict) -> int:
        sections = n.get("card_sections") or []
        return sum(
            len((s.get("title", "") + s.get("content", "")).encode("utf-8"))
            for s in sections
        )

    candidates = [
        (n["depth_from_anchor"], _card_size(n), n["id"])
        for n in nodes_by_id.values()
        if _card_size(n) > 0
    ]
    # Sort: depth DESC (farthest first), then card_size DESC (largest first), then id for stability
    candidates.sort(key=lambda t: (-t[0], -t[1], t[2]))

    suppressed: set[str] = set()
    bytes_freed = 0
    needed = full_bytes - target

    for depth, size, node_id in candidates:
        suppressed.add(node_id)
        bytes_freed += size
        if bytes_freed >= needed:
            break

    result = _render_all(anchor_ids, nodes_by_id, edges, hierarchy_paths, suppressed)
    # Append sentinel
    result = result.rstrip("\n") + "\n" + _TRUNCATION_SENTINEL
    return result
