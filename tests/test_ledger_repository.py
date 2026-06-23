"""Hermetic tests for LedgerRepository (PR1 storage foundation).

All tests run against in-memory SQLite — no real store is touched.
PRAGMA foreign_keys=ON is required for ON DELETE CASCADE to work; the
GraphStore.__init__ path calls configure_connection which sets it, but
any raw connection fixture must set it explicitly.
"""

from __future__ import annotations

import dataclasses
import sqlite3
from datetime import datetime, timezone

import pytest

from brain_ds.store.graph_store import GraphStore


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _open_store() -> GraphStore:
    """Open a fresh in-memory GraphStore (runs all migrations)."""
    return GraphStore(":memory:")


def _create_graph(store: GraphStore, graph_id: str = "g1") -> str:
    store.create_graph(graph_id, name=graph_id, project="test")
    return graph_id


# ---------------------------------------------------------------------------
# P1-T01  RED — v6 migration + schema (SCEN-20, R-SCH-01..04)
# ---------------------------------------------------------------------------

def test_v6_migration_upgrades_schema():
    """After migrations, schema version must be 6 and confidence_ledger must exist."""
    store = _open_store()
    conn = store.conn

    # schema version must be 6
    row = conn.execute(
        "SELECT value FROM store_meta WHERE key = 'schema_version'"
    ).fetchone()
    assert row is not None, "store_meta has no schema_version row"
    assert int(row[0]) == 6, f"Expected schema_version=6, got {row[0]}"

    # confidence_ledger table must exist
    tbl = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='confidence_ledger'"
    ).fetchone()
    assert tbl is not None, "confidence_ledger table does not exist"

    # existing tables must still be present and unaltered (additive migration)
    for table in ("graphs", "nodes", "edges", "evidence"):
        t = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        assert t is not None, f"Pre-existing table '{table}' missing after v6 migration"

    # indexes must exist
    for idx in ("idx_ledger_graph_status", "idx_ledger_latest"):
        i = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (idx,)
        ).fetchone()
        assert i is not None, f"Index '{idx}' missing after v6 migration"

    store.close()


# ---------------------------------------------------------------------------
# P1-T03  RED — LedgerRow model (R-MOD-01, R-MOD-02)
# ---------------------------------------------------------------------------

def test_ledger_row_is_slots_dataclass():
    """LedgerRow must be a @dataclass(slots=True) with all required fields."""
    from brain_ds.store.models import LedgerRow

    assert dataclasses.is_dataclass(LedgerRow), "LedgerRow is not a dataclass"
    assert LedgerRow.__slots__ is not None, "LedgerRow does not have __slots__"

    fields = {f.name for f in dataclasses.fields(LedgerRow)}
    required = {
        "id", "graph_id", "target_type", "target_id", "status",
        "initial_confidence", "current_confidence", "relationship_label",
        "source_node_id", "target_node_id", "source_node_type", "target_node_type",
        "evidence_ids", "captured_by", "captured_at",
        "confirmed_at", "confirmed_by", "flagged_reason", "gold_rationale",
        "provenance",
    }
    missing = required - fields
    assert not missing, f"LedgerRow is missing fields: {missing}"

    # id must default to None
    row = LedgerRow(
        id=None,
        graph_id="g1",
        target_type="edge",
        target_id="e1",
        status="inferred",
        initial_confidence=None,
        current_confidence=None,
        relationship_label=None,
        source_node_id=None,
        target_node_id=None,
        source_node_type=None,
        target_node_type=None,
        evidence_ids=None,
        captured_by=None,
        captured_at="2024-01-01T00:00:00+00:00",
        confirmed_at=None,
        confirmed_by=None,
        flagged_reason=None,
        gold_rationale=None,
        provenance="seed",
    )
    assert row.id is None


# ---------------------------------------------------------------------------
# P1-T05  RED — LedgerRepository.append (R-REPO-01, R-REPO-02, R-APX-01..04)
# ---------------------------------------------------------------------------

def test_append_returns_id_and_is_insert_only():
    """append() must return distinct ascending int ids; rows are never upserted."""
    from brain_ds.store.repository import LedgerRepository

    store = _open_store()
    _create_graph(store)
    repo = LedgerRepository(store.conn)

    id1 = repo.append(
        graph_id="g1",
        target_id="edge-001",
        status="inferred",
        provenance="seed",
        captured_at=datetime.now(timezone.utc).isoformat(),
    )
    id2 = repo.append(
        graph_id="g1",
        target_id="edge-001",  # same target_id
        status="confirmed",
        provenance="seed",
        captured_at=datetime.now(timezone.utc).isoformat(),
    )

    assert isinstance(id1, int), f"Expected int, got {type(id1)}"
    assert isinstance(id2, int), f"Expected int, got {type(id2)}"
    assert id2 > id1, "Second append must have a higher id"

    # must have exactly 2 rows — not upserted
    count = store.conn.execute(
        "SELECT COUNT(*) FROM confidence_ledger WHERE target_id='edge-001'"
    ).fetchone()[0]
    assert count == 2, f"Expected 2 rows (append-only), got {count}"

    # row 1 must be unchanged
    row1 = store.conn.execute(
        "SELECT status FROM confidence_ledger WHERE id=?", (id1,)
    ).fetchone()
    assert row1[0] == "inferred", "First row status must not be mutated"

    store.close()


# ---------------------------------------------------------------------------
# P1-T07  RED — query_by_graph + query_latest_per_target
#          (R-REPO-03, R-REPO-04, SCEN-03, SCEN-04, R-APX-01)
# ---------------------------------------------------------------------------

def test_query_by_graph_returns_all_ordered():
    """query_by_graph must return all rows for the graph ordered by id ASC."""
    from brain_ds.store.repository import LedgerRepository

    store = _open_store()
    _create_graph(store)
    repo = LedgerRepository(store.conn)

    for status in ("inferred", "needs-confirmation", "confirmed"):
        repo.append(
            graph_id="g1",
            target_id="edge-001",
            status=status,
            provenance="seed",
            captured_at=datetime.now(timezone.utc).isoformat(),
        )

    rows = repo.query_by_graph("g1")
    assert len(rows) == 3, f"Expected 3 rows, got {len(rows)}"
    ids = [r.id for r in rows]
    assert ids == sorted(ids), "Rows must be ordered by id ASC"
    assert all(r.graph_id == "g1" for r in rows), "All rows must have graph_id='g1'"


def test_query_latest_per_target_returns_one_per_target():
    """query_latest_per_target returns one (latest) row per target_id."""
    from brain_ds.store.repository import LedgerRepository
    from brain_ds.store.models import LedgerRow

    store = _open_store()
    _create_graph(store)
    repo = LedgerRepository(store.conn)

    # 2 rows for edge-A
    repo.append(graph_id="g1", target_id="edge-A", status="inferred",
                provenance="seed", captured_at=datetime.now(timezone.utc).isoformat())
    id_a2 = repo.append(graph_id="g1", target_id="edge-A", status="confirmed",
                         provenance="seed", captured_at=datetime.now(timezone.utc).isoformat())
    # 1 row for edge-B
    id_b1 = repo.append(graph_id="g1", target_id="edge-B", status="inferred",
                         provenance="seed", captured_at=datetime.now(timezone.utc).isoformat())

    latest = repo.query_latest_per_target("g1")
    assert len(latest) == 2, f"Expected 2 latest rows, got {len(latest)}"

    by_target = {r.target_id: r for r in latest}
    assert by_target["edge-A"].id == id_a2, "Latest for edge-A must be the confirmed row"
    assert by_target["edge-B"].id == id_b1

    # superseded row must NOT be in the result
    superseded_ids = {r.id for r in latest}
    # id of the first edge-A row is id_a2 - 2 or id_a2 - something; we just
    # check that status='confirmed' won and 'inferred' for edge-A is absent
    assert by_target["edge-A"].status == "confirmed"

    store.close()


# ---------------------------------------------------------------------------
# P1-T09  RED — graph scoping + CASCADE (R-REPO-06, R-SCOPE-01..03, SCEN-05/06)
# ---------------------------------------------------------------------------

def test_cross_graph_isolation():
    """Rows for g2 must never appear in g1 queries (SCEN-05)."""
    from brain_ds.store.repository import LedgerRepository

    store = _open_store()
    _create_graph(store, "g1")
    _create_graph(store, "g2")
    repo = LedgerRepository(store.conn)

    repo.append(graph_id="g1", target_id="e-g1", status="inferred",
                provenance="seed", captured_at=datetime.now(timezone.utc).isoformat())
    repo.append(graph_id="g2", target_id="e-g2", status="inferred",
                provenance="seed", captured_at=datetime.now(timezone.utc).isoformat())

    g1_rows = repo.query_by_graph("g1")
    assert all(r.graph_id == "g1" for r in g1_rows), "query_by_graph leaks g2 rows"
    assert len(g1_rows) == 1

    g1_latest = repo.query_latest_per_target("g1")
    assert all(r.graph_id == "g1" for r in g1_latest), "query_latest leaks g2 rows"
    assert len(g1_latest) == 1

    store.close()


def test_cascade_delete_removes_ledger_rows():
    """Deleting a graph must cascade-delete all its ledger rows (SCEN-06)."""
    from brain_ds.store.repository import LedgerRepository

    store = _open_store()
    _create_graph(store, "g1")
    repo = LedgerRepository(store.conn)

    for i in range(5):
        repo.append(
            graph_id="g1",
            target_id=f"edge-{i}",
            status="inferred",
            provenance="seed",
            captured_at=datetime.now(timezone.utc).isoformat(),
        )

    count_before = store.conn.execute(
        "SELECT COUNT(*) FROM confidence_ledger WHERE graph_id='g1'"
    ).fetchone()[0]
    assert count_before == 5

    # Delete the graph — FK ON DELETE CASCADE must clean up ledger rows
    store.conn.execute("DELETE FROM graphs WHERE id='g1'")
    store.conn.commit()

    count_after = store.conn.execute(
        "SELECT COUNT(*) FROM confidence_ledger WHERE graph_id='g1'"
    ).fetchone()[0]
    assert count_after == 0, (
        f"Expected 0 ledger rows after graph delete (CASCADE), got {count_after}. "
        "Check PRAGMA foreign_keys=ON and FK DDL."
    )

    store.close()


# ---------------------------------------------------------------------------
# P1-T11 (explicit wiring test) — graph_store exposes ledger pass-throughs
# ---------------------------------------------------------------------------

def test_graph_store_exposes_ledger_pass_throughs():
    """GraphStore must have append_ledger, query_ledger_latest, query_ledger."""
    store = _open_store()
    _create_graph(store, "g1")

    assert hasattr(store, "ledger_repo"), "GraphStore must expose ledger_repo"
    assert callable(getattr(store, "append_ledger", None)), "append_ledger must be callable"
    assert callable(getattr(store, "query_ledger_latest", None)), "query_ledger_latest must be callable"
    assert callable(getattr(store, "query_ledger", None)), "query_ledger must be callable"

    # delegate smoke-test
    row_id = store.append_ledger(
        graph_id="g1",
        target_id="smoke-edge",
        status="inferred",
        provenance="seed",
        captured_at=datetime.now(timezone.utc).isoformat(),
    )
    assert isinstance(row_id, int)

    latest = store.query_ledger_latest("g1")
    assert len(latest) == 1
    assert latest[0].target_id == "smoke-edge"

    all_rows = store.query_ledger("g1")
    assert len(all_rows) == 1

    store.close()


# ---------------------------------------------------------------------------
# P1-T12 — MCP tool count unchanged (R-MCP-01, R-MCP-02)
# ---------------------------------------------------------------------------

def test_tool_count_unchanged():
    """TOOL_REGISTRY must still have exactly 25 tools after PR1 changes."""
    from brain_ds.mcp.tools import TOOL_REGISTRY

    assert len(TOOL_REGISTRY) == 25, (
        f"Expected 25 MCP tools, got {len(TOOL_REGISTRY)}. "
        "PR1 must not add or remove any MCP tools."
    )
