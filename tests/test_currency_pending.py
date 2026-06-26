from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from brain_ds.currency.coverage import coverage_score
from brain_ds.currency.staleness import classify_staleness, resolve_last_seen
from brain_ds.mcp.tools import get_business_dossier, insert_pending_question
from brain_ds.store.graph_store import GraphStore
from brain_ds.store.migrations import v8_pending_questions


def _make_store_with_stale_node() -> GraphStore:
    store = GraphStore(":memory:")
    store.create_graph("g1")
    old_timestamp = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    store.upsert_node(
        "g1",
        {
            "id": "kpi-1",
            "label": "Revenue KPI",
            "type": "KPI",
            "details": {},
        },
    )
    store.conn.execute(
        "UPDATE nodes SET created_at = ?, modified_at = ? WHERE graph_id = ? AND id = ?",
        (old_timestamp, old_timestamp, "g1", "kpi-1"),
    )
    store.conn.commit()
    return store


def _ledger_count(store: GraphStore) -> int:
    return int(store.conn.execute("SELECT COUNT(*) FROM confidence_ledger").fetchone()[0])


def test_pending_does_not_reset_staleness() -> None:
    store = _make_store_with_stale_node()
    evidence_before = store.query_node_currency_evidence("g1", ["kpi-1"])["kpi-1"]
    last_seen_before = resolve_last_seen(**{k: evidence_before.get(k) for k in (
        "ledger_status",
        "ledger_confirmed_at",
        "ledger_captured_at",
        "schema_baseline_last_documented_at",
        "modified_at",
        "created_at",
    )})
    assert classify_staleness("KPI", last_seen_before, now=datetime.now(timezone.utc)) == "stale"

    before_ledger_rows = _ledger_count(store)
    pending_id = store.insert_pending_question(
        "g1",
        target_node_id="kpi-1",
        gap_kind="staleness",
        entity_type="KPI",
        question_text="Is this KPI still current?",
        stakeholder_owner="Finance Director",
    )

    evidence_after = store.query_node_currency_evidence("g1", ["kpi-1"])["kpi-1"]
    last_seen_after = resolve_last_seen(**{k: evidence_after.get(k) for k in (
        "ledger_status",
        "ledger_confirmed_at",
        "ledger_captured_at",
        "schema_baseline_last_documented_at",
        "modified_at",
        "created_at",
    )})
    coverage = coverage_score([
        {
            "node_id": "kpi-1",
            "entity_type": "KPI",
            "staleness_class": classify_staleness("KPI", last_seen_after, now=datetime.now(timezone.utc)),
            "pending_question_id": pending_id,
        }
    ])

    assert _ledger_count(store) == before_ledger_rows
    assert classify_staleness("KPI", last_seen_after, now=datetime.now(timezone.utc)) == "stale"
    assert coverage["overall"] == 0.0
    store.close()


def test_pending_absent_from_brick_c() -> None:
    store = _make_store_with_stale_node()

    store.insert_pending_question(
        "g1",
        target_node_id="kpi-1",
        gap_kind="staleness",
        entity_type="KPI",
        question_text="Who owns this KPI?",
        stakeholder_owner="Finance Director",
    )

    assert store.list_pending_confirmations("g1") == []
    assert [row.target_node_id for row in store.list_pending_questions("g1")] == ["kpi-1"]
    store.close()


def test_resolve_pending_does_not_write_ledger() -> None:
    store = _make_store_with_stale_node()
    pending_id = store.insert_pending_question(
        "g1",
        target_node_id="kpi-1",
        gap_kind="staleness",
        entity_type="KPI",
        question_text="Is this KPI still current?",
        stakeholder_owner="Finance Director",
    )
    before_ledger_rows = _ledger_count(store)

    result = store.resolve_pending_question(pending_id, outcome="answered", resolved_by="finance@example.com")

    assert result.status == "answered"
    assert result.resolved_by == "finance@example.com"
    assert result.resolved_at is not None
    assert _ledger_count(store) == before_ledger_rows
    assert store.list_pending_questions("g1") == []
    store.close()


def test_insert_pending_question_mcp_tool_persists_without_writing_ledger() -> None:
    store = _make_store_with_stale_node()
    before_ledger_rows = _ledger_count(store)

    result = insert_pending_question(
        store,
        {
            "graph_id": "g1",
            "target_node_id": "kpi-1",
            "gap_kind": "staleness",
            "entity_type": "KPI",
            "question_text": "Is this KPI still current?",
            "stakeholder_owner": "Finance Director",
        },
    )

    assert result["status"] == "pending"
    assert result["target_node_id"] == "kpi-1"
    assert result["gap_kind"] == "staleness"
    assert _ledger_count(store) == before_ledger_rows
    pending = store.list_pending_questions("g1")
    assert [row.id for row in pending] == [result["id"]]
    store.close()


def test_business_dossier_explicit_pending_question_creation_stays_append_only() -> None:
    store = _make_store_with_stale_node()
    store.upsert_node(
        "g1",
        {
            "id": "source-1",
            "label": "Revenue Warehouse",
            "type": "Data Source",
            "details": {"description": "Revenue source rows"},
        },
    )
    store.upsert_edge(
        "g1",
        {"source": "kpi-1", "target": "source-1", "label": "measured-by", "weight": 0.2},
    )
    before_ledger_rows = _ledger_count(store)
    before_edge_rows = len(store.query_edges("g1"))

    result = get_business_dossier(
        store,
        {
            "graph_id": "g1",
            "query": "revenue",
            "create_pending_questions": True,
            "stakeholder_owner": "Finance Director",
        },
    )

    assert len(result["pending_questions_created"]) == 1
    assert result["pending_questions_created"][0]["target_node_id"] == "source-1"
    assert result["pending_questions_created"][0]["stakeholder_owner"] == "Finance Director"
    assert len(store.query_edges("g1")) == before_edge_rows
    assert _ledger_count(store) == before_ledger_rows
    assert [row.target_node_id for row in store.list_pending_questions("g1")] == ["source-1"]
    store.close()


def test_insert_pending_question_mcp_tool_validates_contract() -> None:
    store = _make_store_with_stale_node()

    missing = insert_pending_question(store, {"graph_id": "g1", "gap_kind": "staleness"})
    extra = insert_pending_question(
        store,
        {
            "graph_id": "g1",
            "gap_kind": "staleness",
            "question_text": "Is this KPI still current?",
            "unexpected": "nope",
        },
    )

    assert missing["code"] == -32602
    assert "Missing required parameter: question_text" in missing["message"]
    assert extra["code"] == -32602
    assert "Unknown parameter: unexpected" in extra["message"]
    store.close()


def test_pending_session_boundary(tmp_path) -> None:
    db_path = tmp_path / "store.db"
    with GraphStore(str(db_path)) as store:
        store.create_graph("g1")
        store.upsert_node("g1", {"id": "risk-1", "label": "Risk", "type": "RISK", "details": {}})
        store.insert_pending_question(
            "g1",
            target_node_id="risk-1",
            gap_kind="staleness",
            entity_type="RISK",
            question_text="Is this risk still active?",
            stakeholder_owner="Risk Owner",
        )

    with GraphStore(str(db_path)) as reopened:
        pending = reopened.list_pending_questions("g1")

    assert len(pending) == 1
    assert pending[0].target_node_id == "risk-1"
    assert pending[0].stakeholder_owner == "Risk Owner"
    assert pending[0].status == "pending"


def test_v8_migration_idempotent() -> None:
    conn = sqlite3.connect(":memory:")

    v8_pending_questions(conn)
    v8_pending_questions(conn)

    table_count = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'pending_questions'"
    ).fetchone()[0]
    index_count = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'index' AND name = 'idx_pending_questions_graph_status'"
    ).fetchone()[0]

    assert table_count == 1
    assert index_count == 1
    conn.close()
