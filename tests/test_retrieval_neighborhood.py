"""Tests for pure retrieval neighborhood helpers."""

from __future__ import annotations

from brain_ds.store.models import EdgeRow, NodeRow


def _edge(edge_id: str, source: str, target: str, *, weight: float = 0.5) -> EdgeRow:
    return EdgeRow(
        graph_id="g1",
        edge_id=edge_id,
        source=source,
        target=target,
        label="relates_to",
        weight=weight,
        reasons=None,
        evidence_ids=None,
        created_at="2026-01-01T00:00:00+00:00",
    )


def _node(node_id: str, label: str, parent_id: str | None = None) -> NodeRow:
    return NodeRow(
        graph_id="g1",
        id=node_id,
        label=label,
        type="Role",
        supertype=None,
        details={},
        card_sections=None,
        editable_fields=None,
        evidence_ids=None,
        layout_hint=None,
        parent_id=parent_id,
        depth=0,
        created_at="2026-01-01T00:00:00+00:00",
        modified_at="2026-01-01T00:00:00+00:00",
    )


def test_expand_neighborhood_depth_one():
    """Depth 1 includes anchors and direct neighbors only."""
    from brain_ds.retrieval.neighborhood import build_adjacency, expand_neighborhood

    adjacency = build_adjacency([_edge("e1", "A", "B"), _edge("e2", "A", "C"), _edge("e3", "B", "D")])

    assert expand_neighborhood(["A"], adjacency, depth=1) == {"A": 0, "B": 1, "C": 1}


def test_expand_neighborhood_depth_two_keeps_min_depth_on_reencounter():
    """Depth 2 includes second-hop nodes without increasing a re-encountered anchor."""
    from brain_ds.retrieval.neighborhood import build_adjacency, expand_neighborhood

    adjacency = build_adjacency([_edge("e1", "A", "B"), _edge("e2", "A", "C"), _edge("e3", "B", "D")])

    assert expand_neighborhood(["A"], adjacency, depth=2) == {"A": 0, "B": 1, "C": 1, "D": 2}


def test_expand_neighborhood_isolated_anchor():
    """An isolated anchor returns itself at depth 0 and does not error."""
    from brain_ds.retrieval.neighborhood import expand_neighborhood

    assert expand_neighborhood(["isolated"], {}, depth=1) == {"isolated": 0}


def test_ledger_status_to_tier_truth_table():
    """Ledger statuses map to retrieval rank tiers; invalidated is excluded."""
    from brain_ds.retrieval.neighborhood import ledger_status_to_tier

    assert ledger_status_to_tier("confirmed") == 1
    assert ledger_status_to_tier("inferred") == 2
    assert ledger_status_to_tier(None) == 2
    assert ledger_status_to_tier("needs-confirmation") == 3
    assert ledger_status_to_tier("abstain") == 4
    assert ledger_status_to_tier("invalidated") is None


def test_sort_edges_by_reliability_excludes_invalidated_and_sorts_weight_desc_within_tier():
    """Sort order is tier ASC then edge weight DESC, with invalidated edges omitted."""
    from brain_ds.retrieval.neighborhood import AnnotatedEdge, sort_edges_by_reliability

    edges = [
        AnnotatedEdge(edge=_edge("confirmed-low", "A", "B", weight=0.7), ledger_status="confirmed", tier=1),
        AnnotatedEdge(edge=_edge("inferred", "A", "C", weight=0.8), ledger_status="inferred", tier=2),
        AnnotatedEdge(edge=_edge("confirmed-high", "A", "D", weight=0.9), ledger_status="confirmed", tier=1),
        AnnotatedEdge(edge=_edge("invalidated", "A", "E", weight=1.0), ledger_status="invalidated", tier=None),
        AnnotatedEdge(edge=_edge("abstain", "A", "F", weight=0.5), ledger_status="abstain", tier=4),
        AnnotatedEdge(edge=_edge("no-row", "A", "G", weight=0.6), ledger_status=None, tier=2),
    ]

    sorted_ids = [edge.edge.edge_id for edge in sort_edges_by_reliability(edges)]

    assert sorted_ids == ["confirmed-high", "confirmed-low", "inferred", "no-row", "abstain"]


def test_walk_hierarchy_path_root_only_and_three_level_chain():
    """Hierarchy walking returns root-to-anchor labels for root and nested anchors."""
    from brain_ds.retrieval.neighborhood import walk_hierarchy_path

    nodes = {
        "org": _node("org", "Org"),
        "dept": _node("dept", "Dept", parent_id="org"),
        "role": _node("role", "Role", parent_id="dept"),
    }

    assert walk_hierarchy_path("org", nodes) == ["Org"]
    assert walk_hierarchy_path("role", nodes) == ["Org", "Dept", "Role"]


def test_walk_hierarchy_path_truncates_after_twenty_hops():
    """Malformed hierarchies are bounded and marked as truncated."""
    from brain_ds.retrieval.neighborhood import HIERARCHY_MAX_HOPS, walk_hierarchy_path

    nodes: dict[str, NodeRow] = {}
    previous: str | None = None
    for index in range(HIERARCHY_MAX_HOPS + 2):
        node_id = f"n{index}"
        nodes[node_id] = _node(node_id, f"Node {index}", parent_id=previous)
        previous = node_id

    path = walk_hierarchy_path(f"n{HIERARCHY_MAX_HOPS + 1}", nodes)

    assert path[0] == "[hierarchy truncated]"
    assert path[-1] == f"Node {HIERARCHY_MAX_HOPS + 1}"
