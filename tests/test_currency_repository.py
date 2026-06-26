from __future__ import annotations

from datetime import datetime, timezone

from brain_ds.store.graph_store import GraphStore


def test_query_node_currency_evidence_batches_node_and_edge_reads() -> None:
    store = GraphStore(":memory:")
    store.create_graph("g1")
    documented_at = "2026-05-01T00:00:00+00:00"
    captured_at = datetime(2026, 6, 1, tzinfo=timezone.utc).isoformat()

    for index in range(25):
        store.upsert_node(
            "g1",
            {
                "id": f"node-{index:02d}",
                "label": f"Node {index:02d}",
                "type": "Data Source",
                "details": {"schema_baseline": {"last_documented_at": documented_at}},
            },
        )
        store.append_ledger(
            "g1",
            target_type="node",
            target_id=f"node-{index:02d}",
            status="confirmed",
            provenance="seed",
            captured_at=captured_at,
            confirmed_at=captured_at,
        )

    store.upsert_edge("g1", {"edge_id": "edge-1", "source": "node-00", "target": "node-01", "label": "depends-on"})
    store.append_ledger(
        "g1",
        target_type="edge",
        target_id="edge-1",
        status="confirmed",
        provenance="seed",
        captured_at=captured_at,
    )

    statements: list[str] = []
    store.conn.set_trace_callback(statements.append)

    result = store.query_node_currency_evidence("g1", [f"node-{index:02d}" for index in range(25)])

    select_statements = [sql for sql in statements if sql.lstrip().upper().startswith("SELECT")]
    assert set(result) == {f"node-{index:02d}" for index in range(25)}
    assert result["node-00"]["ledger_status"] == "confirmed"
    assert result["node-00"]["ledger_confirmed_at"] == captured_at
    assert result["node-00"]["schema_baseline_last_documented_at"] == documented_at
    assert set(result["node-00"]["edge_evidence"]) == {"edge-1"}
    assert len(select_statements) <= 5

    store.close()


def test_query_node_currency_evidence_chunks_large_node_batches() -> None:
    store = GraphStore(":memory:")
    store.create_graph("g1")

    node_ids = [f"node-{index:04d}" for index in range(1001)]
    for node_id in node_ids:
        store.upsert_node(
            "g1",
            {
                "id": node_id,
                "label": node_id,
                "type": "Data Source",
                "details": {},
            },
        )

    store.upsert_edge("g1", {"edge_id": "edge-first-last", "source": node_ids[0], "target": node_ids[-1], "label": "depends-on"})

    statements: list[str] = []
    store.conn.set_trace_callback(statements.append)

    result = store.query_node_currency_evidence("g1", node_ids)

    node_selects = [sql for sql in statements if "FROM nodes" in sql]
    edge_selects = [sql for sql in statements if "FROM edges" in sql]
    assert set(result) == set(node_ids)
    assert set(result[node_ids[0]]["edge_evidence"]) == {"edge-first-last"}
    assert set(result[node_ids[-1]]["edge_evidence"]) == {"edge-first-last"}
    assert len(node_selects) == 2
    assert len(edge_selects) == 3

    store.close()
