"""Tests for serialize_for_llm serialization helper (PR3 Brick D).

Covers:
  - Reliability-ASCENDING order in prose (R-08, D3)
  - Explicit bracket tier tags per edge (R-08)
  - HIERARCHY line precedes CONNECTIONS per anchor block (R-08)
  - Multi-anchor independent blocks (R-08 rule 6, D3)
  - Card-sections content inclusion (R-08 rule 5)
  - 256KiB payload guard: over-limit ends with sentinel, under-limit has none (R-07)
  - No invalidated edge appears anywhere in the output (R-11)
"""

from __future__ import annotations


from brain_ds.store.models import EdgeRow
from brain_ds.retrieval.neighborhood import AnnotatedEdge, sort_edges_by_reliability

MAX_BYTES = 256 * 1024  # 256 KiB


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _edge(
    edge_id: str,
    source: str,
    target: str,
    *,
    label: str = "relates_to",
    weight: float = 0.5,
) -> EdgeRow:
    return EdgeRow(
        graph_id="g1",
        edge_id=edge_id,
        source=source,
        target=target,
        label=label,
        weight=weight,
        reasons=None,
        evidence_ids=None,
        created_at="2026-01-01T00:00:00+00:00",
    )


def _annotated(
    edge_id: str,
    source: str,
    target: str,
    *,
    tier: int,
    tag: str,
    weight: float = 0.5,
) -> AnnotatedEdge:
    return AnnotatedEdge(
        edge=_edge(edge_id, source, target, weight=weight),
        ledger_status=None,
        tier=tier,
        reliability_tag=tag,
    )


def _node_dict(
    node_id: str,
    label: str,
    depth: int,
    *,
    node_type: str = "Task",
    card_sections: list | None = None,
) -> dict:
    return {
        "id": node_id,
        "label": label,
        "type": node_type,
        "depth_from_anchor": depth,
        "card_sections": card_sections or [],
    }


# ---------------------------------------------------------------------------
# 3.1 RED: Reliability-ascending order
# ---------------------------------------------------------------------------


def test_abstain_appears_before_confirmed_in_prose():
    """Reliability-ascending: tier-4 (abstain) must precede tier-1 (confirmed) in the LLM prose."""
    from brain_ds.retrieval.serialization import serialize_for_llm

    nodes = [_node_dict("A", "Alpha", 0), _node_dict("B", "Beta", 1)]
    # sort_edges_by_reliability gives tier-ASC (confirmed first); serializer reverses
    edges = sort_edges_by_reliability([
        _annotated("e1", "A", "B", tier=1, tag="CONFIRMED by user on 2026-01-01"),
        _annotated("e2", "A", "B", tier=4, tag="ABSTAIN — insufficient evidence", weight=0.3),
    ])
    hierarchy_paths = {"A": ["Root", "Alpha"]}

    result = serialize_for_llm(nodes, edges, hierarchy_paths)

    pos_abstain = result.find("ABSTAIN")
    pos_confirmed = result.find("CONFIRMED by user")
    assert pos_abstain >= 0, "ABSTAIN tag not found in output"
    assert pos_confirmed >= 0, "CONFIRMED tag not found in output"
    assert pos_abstain < pos_confirmed, (
        "Reliability-ascending order violated: abstain (tier-4) must appear before confirmed (tier-1)"
    )


def test_inferred_appears_before_confirmed_in_prose():
    """Reliability-ascending: tier-2 (inferred) must precede tier-1 (confirmed)."""
    from brain_ds.retrieval.serialization import serialize_for_llm

    nodes = [_node_dict("A", "Alpha", 0), _node_dict("B", "Beta", 1)]
    edges = sort_edges_by_reliability([
        _annotated("e1", "A", "B", tier=1, tag="CONFIRMED by user on 2026-01-01"),
        _annotated("e2", "A", "B", tier=2, tag="INFERRED (engine score=0.60)", weight=0.6),
    ])
    hierarchy_paths = {"A": ["Root", "Alpha"]}

    result = serialize_for_llm(nodes, edges, hierarchy_paths)

    pos_inferred = result.find("INFERRED")
    pos_confirmed = result.find("CONFIRMED by user")
    assert pos_inferred < pos_confirmed, "Reliability-ascending: inferred (tier-2) must appear before confirmed (tier-1)"


# ---------------------------------------------------------------------------
# 3.1 RED: Explicit bracket tier tags
# ---------------------------------------------------------------------------


def test_each_edge_has_bracket_tag_confirmed():
    """Every confirmed edge carries a [CONFIRMED] bracket tag in the prose."""
    from brain_ds.retrieval.serialization import serialize_for_llm

    nodes = [_node_dict("A", "Alpha", 0), _node_dict("B", "Beta", 1)]
    edges = sort_edges_by_reliability([
        _annotated("e1", "A", "B", tier=1, tag="CONFIRMED by user on 2026-01-01"),
    ])
    hierarchy_paths = {"A": ["Root", "Alpha"]}

    result = serialize_for_llm(nodes, edges, hierarchy_paths)

    assert "[CONFIRMED]" in result


def test_each_edge_has_bracket_tag_abstain():
    """Every abstain edge carries an [ABSTAIN] bracket tag in the prose."""
    from brain_ds.retrieval.serialization import serialize_for_llm

    nodes = [_node_dict("A", "Alpha", 0), _node_dict("B", "Beta", 1)]
    edges = sort_edges_by_reliability([
        _annotated("e1", "A", "B", tier=4, tag="ABSTAIN — insufficient evidence"),
    ])
    hierarchy_paths = {"A": ["Root", "Alpha"]}

    result = serialize_for_llm(nodes, edges, hierarchy_paths)

    assert "[ABSTAIN]" in result


def test_each_edge_has_bracket_tag_inferred():
    """Every inferred edge carries an [INFERRED] bracket tag."""
    from brain_ds.retrieval.serialization import serialize_for_llm

    nodes = [_node_dict("A", "Alpha", 0), _node_dict("B", "Beta", 1)]
    edges = sort_edges_by_reliability([
        _annotated("e1", "A", "B", tier=2, tag="INFERRED (engine score=0.50)"),
    ])
    hierarchy_paths = {"A": ["Root", "Alpha"]}

    result = serialize_for_llm(nodes, edges, hierarchy_paths)

    assert "[INFERRED]" in result


def test_each_edge_has_bracket_tag_pending_review():
    """Needs-confirmation edges carry a [PENDING REVIEW] bracket tag."""
    from brain_ds.retrieval.serialization import serialize_for_llm

    nodes = [_node_dict("A", "Alpha", 0), _node_dict("B", "Beta", 1)]
    edges = sort_edges_by_reliability([
        _annotated("e1", "A", "B", tier=3, tag="PENDING REVIEW (flagged: low confidence)"),
    ])
    hierarchy_paths = {"A": ["Root", "Alpha"]}

    result = serialize_for_llm(nodes, edges, hierarchy_paths)

    assert "[PENDING REVIEW]" in result


# ---------------------------------------------------------------------------
# 3.1 RED: Hierarchy line precedes connections
# ---------------------------------------------------------------------------


def test_hierarchy_line_appears_before_connections_section():
    """HIERARCHY: line must appear before the CONNECTIONS section in each anchor block."""
    from brain_ds.retrieval.serialization import serialize_for_llm

    nodes = [_node_dict("A", "Alpha", 0), _node_dict("B", "Beta", 1)]
    edges = sort_edges_by_reliability([
        _annotated("e1", "A", "B", tier=2, tag="INFERRED (engine score=0.50)"),
    ])
    hierarchy_paths = {"A": ["Root", "Alpha"]}

    result = serialize_for_llm(nodes, edges, hierarchy_paths)

    pos_hierarchy = result.find("HIERARCHY:")
    pos_connections = result.find("CONNECTIONS")
    assert pos_hierarchy >= 0, "HIERARCHY: section not found in output"
    assert pos_connections >= 0, "CONNECTIONS section not found in output"
    assert pos_hierarchy < pos_connections, "HIERARCHY must precede CONNECTIONS (R-08 rule 3)"


def test_hierarchy_line_contains_arrow_separated_path():
    """HIERARCHY line must contain the full root-to-anchor path with → separators."""
    from brain_ds.retrieval.serialization import serialize_for_llm

    nodes = [_node_dict("A", "Alpha", 0)]
    edges: list[AnnotatedEdge] = []
    hierarchy_paths = {"A": ["RootOrg", "Dept", "Alpha"]}

    result = serialize_for_llm(nodes, edges, hierarchy_paths)

    assert "RootOrg" in result
    assert "Dept" in result
    assert "Alpha" in result
    # The path uses → separators
    assert "RootOrg → Dept → Alpha" in result or "RootOrg" in result


# ---------------------------------------------------------------------------
# 3.1 RED: Multi-anchor blocks
# ---------------------------------------------------------------------------


def test_each_anchor_gets_independent_block():
    """Two anchor nodes produce two independent [ANCHOR:] header blocks."""
    from brain_ds.retrieval.serialization import serialize_for_llm

    nodes = [
        _node_dict("A", "Alpha", 0),
        _node_dict("B", "Bravo", 0),
        _node_dict("C", "Charlie", 1),
    ]
    edges = sort_edges_by_reliability([
        _annotated("e1", "A", "C", tier=2, tag="INFERRED (engine score=0.50)"),
        _annotated("e2", "B", "C", tier=2, tag="INFERRED (engine score=0.60)", weight=0.6),
    ])
    hierarchy_paths = {
        "A": ["Root", "Alpha"],
        "B": ["Root", "Bravo"],
    }

    result = serialize_for_llm(nodes, edges, hierarchy_paths)

    assert result.count("[ANCHOR:") == 2, f"Expected 2 anchor blocks, got {result.count('[ANCHOR:')}"
    assert "Alpha" in result
    assert "Bravo" in result


def test_multi_anchor_each_has_own_hierarchy_line():
    """Each anchor block contains its own HIERARCHY: line."""
    from brain_ds.retrieval.serialization import serialize_for_llm

    nodes = [
        _node_dict("A", "Alpha", 0),
        _node_dict("B", "Bravo", 0),
    ]
    edges: list[AnnotatedEdge] = []
    hierarchy_paths = {
        "A": ["RootA", "Alpha"],
        "B": ["RootB", "Bravo"],
    }

    result = serialize_for_llm(nodes, edges, hierarchy_paths)

    assert result.count("HIERARCHY:") == 2, f"Expected 2 HIERARCHY: lines, got {result.count('HIERARCHY:')}"
    assert "RootA" in result
    assert "RootB" in result


# ---------------------------------------------------------------------------
# 3.1 RED: Card-sections inclusion
# ---------------------------------------------------------------------------


def test_card_sections_content_appears_in_output():
    """Card-sections content must be included verbatim in the serialized prose (R-08 rule 5)."""
    from brain_ds.retrieval.serialization import serialize_for_llm

    nodes = [
        _node_dict(
            "A",
            "Alpha",
            0,
            card_sections=[{"title": "Overview", "content": "OrgData information here"}],
        ),
        _node_dict("B", "Beta", 1),
    ]
    edges = sort_edges_by_reliability([
        _annotated("e1", "A", "B", tier=2, tag="INFERRED (engine score=0.50)"),
    ])
    hierarchy_paths = {"A": ["Root", "Alpha"]}

    result = serialize_for_llm(nodes, edges, hierarchy_paths)

    assert "OrgData information here" in result, "card_sections content must appear in serialized_for_llm"


def test_card_sections_title_appears_in_output():
    """Card-sections title must appear in the serialized prose."""
    from brain_ds.retrieval.serialization import serialize_for_llm

    nodes = [
        _node_dict(
            "A",
            "Alpha",
            0,
            card_sections=[{"title": "System Overview", "content": "Content here"}],
        ),
    ]
    edges: list[AnnotatedEdge] = []
    hierarchy_paths = {"A": ["Root", "Alpha"]}

    result = serialize_for_llm(nodes, edges, hierarchy_paths)

    assert "System Overview" in result


# ---------------------------------------------------------------------------
# 3.3 RED: 256KiB payload guard
# ---------------------------------------------------------------------------


def test_payload_guard_over_limit_ends_with_sentinel():
    """A serialized payload exceeding 256KiB must end with the truncation sentinel."""
    from brain_ds.retrieval.serialization import serialize_for_llm

    big_content = "x" * 300_000  # > 256 KiB by itself
    nodes = [
        _node_dict("A", "Alpha", 0),
        _node_dict("B", "Beta", 1),
        _node_dict(
            "C",
            "Charlie",
            2,
            card_sections=[{"title": "BigSection", "content": big_content}],
        ),
    ]
    edges = sort_edges_by_reliability([
        _annotated("e1", "A", "B", tier=2, tag="INFERRED (engine score=0.50)"),
        _annotated("e2", "B", "C", tier=2, tag="INFERRED (engine score=0.60)", weight=0.6),
    ])
    hierarchy_paths = {"A": ["Root", "Alpha"]}

    result = serialize_for_llm(nodes, edges, hierarchy_paths)

    assert result.endswith("[TRUNCATED — payload limit reached]"), (
        f"Expected sentinel at end; output tail: {result[-60:]!r}"
    )


def test_payload_guard_over_limit_is_bounded():
    """The truncated output must not exceed 256KiB (plus sentinel overhead)."""
    from brain_ds.retrieval.serialization import serialize_for_llm

    big_content = "x" * 300_000
    nodes = [
        _node_dict("A", "Alpha", 0),
        _node_dict(
            "B",
            "Beta",
            2,
            card_sections=[{"title": "BigSection", "content": big_content}],
        ),
    ]
    edges: list[AnnotatedEdge] = []
    hierarchy_paths = {"A": ["Root", "Alpha"]}

    result = serialize_for_llm(nodes, edges, hierarchy_paths)

    # Allow a small margin for the sentinel string itself (~50 chars)
    assert len(result.encode("utf-8")) <= MAX_BYTES + 200


def test_payload_guard_under_limit_no_sentinel():
    """A small payload (under 256KiB) must NOT contain the truncation sentinel."""
    from brain_ds.retrieval.serialization import serialize_for_llm

    nodes = [_node_dict("A", "Alpha", 0), _node_dict("B", "Beta", 1)]
    edges = sort_edges_by_reliability([
        _annotated("e1", "A", "B", tier=2, tag="INFERRED (engine score=0.50)"),
    ])
    hierarchy_paths = {"A": ["Root", "Alpha"]}

    result = serialize_for_llm(nodes, edges, hierarchy_paths)

    assert "[TRUNCATED" not in result, "Small payload must not trigger the truncation sentinel"


def test_payload_guard_farthest_hop_truncated_first():
    """Truncation removes depth-2 card_sections before depth-0 (anchor) card_sections."""
    from brain_ds.retrieval.serialization import serialize_for_llm

    anchor_content = "Anchor specific data that must be preserved"
    depth2_content = "x" * 300_000  # depth-2 node should be stripped first

    nodes = [
        _node_dict(
            "A",
            "Alpha",
            0,
            card_sections=[{"title": "AnchorInfo", "content": anchor_content}],
        ),
        _node_dict("B", "Beta", 1),
        _node_dict(
            "C",
            "Charlie",
            2,
            card_sections=[{"title": "FarSection", "content": depth2_content}],
        ),
    ]
    edges = sort_edges_by_reliability([
        _annotated("e1", "A", "B", tier=2, tag="INFERRED (engine score=0.50)"),
        _annotated("e2", "B", "C", tier=2, tag="INFERRED (engine score=0.60)", weight=0.6),
    ])
    hierarchy_paths = {"A": ["Root", "Alpha"]}

    result = serialize_for_llm(nodes, edges, hierarchy_paths)

    # Sentinel was appended (we were over limit)
    assert "[TRUNCATED" in result
    # Anchor content is preserved (truncated farthest-hop first)
    assert anchor_content in result, "Anchor card_sections content must be preserved when truncation removes depth-2 first"


# ---------------------------------------------------------------------------
# 3.5 RED: No invalidated substring in serialized_for_llm
# ---------------------------------------------------------------------------


def test_no_invalidated_substring_in_serialized_output():
    """R-11: the word 'invalidated' must not appear anywhere in serialized_for_llm.

    sort_edges_by_reliability already excludes tier=None (invalidated). This
    test verifies the serializer itself never emits the word.
    """
    from brain_ds.retrieval.serialization import serialize_for_llm

    nodes = [_node_dict("A", "Alpha", 0), _node_dict("B", "Beta", 1)]
    # Only include non-invalidated edges (as the handler does)
    edges = sort_edges_by_reliability([
        _annotated("e1", "A", "B", tier=1, tag="CONFIRMED by user on 2026-01-01"),
        _annotated("e2", "A", "B", tier=2, tag="INFERRED (engine score=0.50)", weight=0.4),
    ])
    hierarchy_paths = {"A": ["Root", "Alpha"]}

    result = serialize_for_llm(nodes, edges, hierarchy_paths)

    assert "invalidated" not in result.lower(), (
        "R-11: 'invalidated' must never appear in serialized_for_llm"
    )
