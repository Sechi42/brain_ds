from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from brain_ds.mcp.tools import add_edge
from brain_ds.store.graph_store import GraphStore


@pytest.fixture
def store():
    temp_dir = tempfile.TemporaryDirectory()
    graph_store = GraphStore(str(Path(temp_dir.name) / "store.db"))
    graph_store.create_graph("g1", name="g1", project="test")
    graph_store.upsert_node(
        "g1",
        {"id": "role-1", "label": "Analytics Role", "type": "Role", "details": {}},
    )
    graph_store.upsert_node(
        "g1",
        {"id": "ds-1", "label": "Warehouse", "type": "Data Source", "details": {}},
    )
    graph_store.upsert_node(
        "g1",
        {"id": "team-1", "label": "Analytics Team", "type": "Team", "details": {}},
    )
    try:
        yield graph_store
    finally:
        graph_store.close()
        temp_dir.cleanup()


def test_add_edge_appends_inferred_ledger_row_with_weight(store: GraphStore):
    result = add_edge(
        store,
        {
            "graph_id": "g1",
            "source": "team-1",
            "target": "ds-1",
            "label": "uses",
            "weight": 0.75,
            "evidence": ["ev-1"],
        },
    )

    rows = store.query_ledger_latest("g1")
    assert result["edge_id"] == rows[0].target_id
    assert rows[0].status == "inferred"
    assert rows[0].initial_confidence == 0.75
    assert rows[0].current_confidence == 0.75
    assert rows[0].captured_by == "mapper"
    assert rows[0].provenance == "seed"
    assert rows[0].relationship_label == "uses"
    assert rows[0].source_node_type == "Team"
    assert rows[0].target_node_type == "Data Source"
    assert rows[0].evidence_ids == ["ev-1"]
    assert rows[0].captured_at


def test_add_edge_without_weight_appends_import_ledger_row_with_null_confidence(store: GraphStore):
    add_edge(store, {"graph_id": "g1", "source": "team-1", "target": "ds-1", "label": "uses"})

    rows = store.query_ledger_latest("g1")
    assert rows[0].initial_confidence is None
    assert rows[0].current_confidence is None
    assert rows[0].captured_by == "import"
    assert rows[0].status == "inferred"


def test_add_edge_ledger_failure_does_not_block_edge_write(monkeypatch, store: GraphStore):
    def fail_append_ledger(*args, **kwargs):
        raise RuntimeError("ledger unavailable")

    monkeypatch.setattr(store, "append_ledger", fail_append_ledger)

    result = add_edge(
        store,
        {"graph_id": "g1", "source": "team-1", "target": "ds-1", "label": "uses", "weight": 0.75},
    )

    assert result["source"] == "team-1"
    assert store.query_edges("g1", source="team-1", target="ds-1")
    assert store.query_ledger_latest("g1") == []


def test_add_edge_sensitive_label_appends_needs_confirmation(store: GraphStore):
    add_edge(
        store,
        {"graph_id": "g1", "source": "role-1", "target": "ds-1", "label": "owns", "weight": 0.8},
    )

    rows = store.query_ledger_latest("g1")
    assert rows[0].status == "needs-confirmation"
    assert rows[0].flagged_reason == "sensitive_ownership_transition"
