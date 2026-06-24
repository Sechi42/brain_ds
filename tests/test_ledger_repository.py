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
    """After all migrations, schema version must be 7 and confidence_ledger must exist."""
    store = _open_store()
    conn = store.conn

    # schema version must be 7 (v7 adds node-fact descriptor columns)
    row = conn.execute(
        "SELECT value FROM store_meta WHERE key = 'schema_version'"
    ).fetchone()
    assert row is not None, "store_meta has no schema_version row"
    assert int(row[0]) == 7, f"Expected schema_version=7, got {row[0]}"

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

# ---------------------------------------------------------------------------
# P1-T13  RED — target_type='node' append and query_latest_per_target scoping
#          (R-NF-01, R-NF-02, SCEN-NF-01, SCEN-CL-01)
# ---------------------------------------------------------------------------

def test_append_node_target_type_and_scoping():
    """Appending target_type='node' rows and querying with target_type='node'
    must return only node rows; querying with target_type='edge' excludes them.

    Also verifies that the new fact descriptor fields round-trip correctly.
    """
    from brain_ds.store.repository import LedgerRepository

    store = _open_store()
    _create_graph(store)
    repo = LedgerRepository(store.conn)

    # Append a node-fact row with descriptor fields
    node_id = repo.append(
        graph_id="g1",
        target_id="n7",
        target_type="node",
        status="inferred",
        provenance="generated",
        captured_at=datetime.now(timezone.utc).isoformat(),
        fact_label="department",
        fact_path="node.department",
        fact_value="Engineering",
        fact_subject_type="Role",
    )

    # Also append an edge row
    edge_id = repo.append(
        graph_id="g1",
        target_id="e1",
        target_type="edge",
        status="inferred",
        provenance="seed",
        captured_at=datetime.now(timezone.utc).isoformat(),
    )

    # query_latest_per_target with target_type='node' must return only the node row
    node_latest = repo.query_latest_per_target("g1", target_type="node")
    assert len(node_latest) == 1, f"Expected 1 node row, got {len(node_latest)}"
    assert node_latest[0].target_id == "n7"
    assert node_latest[0].target_type == "node"

    # fact descriptor fields must round-trip
    assert node_latest[0].fact_label == "department", "fact_label must round-trip"
    assert node_latest[0].fact_path == "node.department", "fact_path must round-trip"
    assert node_latest[0].fact_value == "Engineering", "fact_value must round-trip"
    assert node_latest[0].fact_subject_type == "Role", "fact_subject_type must round-trip"

    # query_latest_per_target with target_type='edge' (default) excludes node rows
    edge_latest = repo.query_latest_per_target("g1", target_type="edge")
    target_ids = {r.target_id for r in edge_latest}
    assert "n7" not in target_ids, "Node row must not appear in edge query"
    assert "e1" in target_ids, "Edge row must appear in edge query"

    # query_by_graph also scopes by target_type (default='edge')
    edge_rows = repo.query_by_graph("g1", target_type="edge")
    assert all(r.target_type == "edge" for r in edge_rows)

    node_rows = repo.query_by_graph("g1", target_type="node")
    assert all(r.target_type == "node" for r in node_rows)
    assert len(node_rows) == 1

    store.close()


def test_node_fact_descriptors_null_for_edge_rows():
    """Edge rows must have NULL fact descriptor fields (backwards compatible)."""
    from brain_ds.store.repository import LedgerRepository

    store = _open_store()
    _create_graph(store)
    repo = LedgerRepository(store.conn)

    row_id = repo.append(
        graph_id="g1",
        target_id="e99",
        target_type="edge",
        status="inferred",
        provenance="seed",
        captured_at=datetime.now(timezone.utc).isoformat(),
    )

    rows = repo.query_by_graph("g1", target_type="edge")
    assert len(rows) == 1
    row = rows[0]
    assert row.fact_label is None
    assert row.fact_path is None
    assert row.fact_value is None
    assert row.fact_subject_type is None

    store.close()


def test_tool_count_unchanged():
    """TOOL_REGISTRY must have exactly 27 tools after PR2 changes."""
    from brain_ds.mcp.tools import TOOL_REGISTRY

    assert len(TOOL_REGISTRY) == 27, (
        f"Expected 27 MCP tools, got {len(TOOL_REGISTRY)}. "
        "PR2 must add list_pending_confirmations and resolve_confirmation."
    )


# ---------------------------------------------------------------------------
# P3-T03  RED — GraphStore pass-throughs for list_pending_confirmations
#          and resolve_confirmation
# ---------------------------------------------------------------------------

def test_graph_store_list_pending_confirmations_pass_through():
    """GraphStore.list_pending_confirmations delegates to LedgerRepository."""
    store = _open_store()
    _create_graph(store, "g1")
    now = datetime.now(timezone.utc).isoformat()

    # No pending rows yet
    pending = store.list_pending_confirmations("g1")
    assert pending == []

    # Append a needs-confirmation row
    store.append_ledger(
        graph_id="g1", target_id="n42", target_type="node",
        status="needs-confirmation", provenance="generated", captured_at=now,
    )

    pending = store.list_pending_confirmations("g1")
    assert len(pending) == 1
    assert pending[0].target_id == "n42"
    assert pending[0].status == "needs-confirmation"

    store.close()


def test_graph_store_resolve_confirmation_pass_through():
    """GraphStore.resolve_confirmation delegates to LedgerRepository and appends."""
    store = _open_store()
    _create_graph(store, "g1")
    now = datetime.now(timezone.utc).isoformat()

    prior_id = store.append_ledger(
        graph_id="g1", target_id="n7", target_type="node",
        status="needs-confirmation", provenance="generated", captured_at=now,
    )

    result = store.resolve_confirmation(
        graph_id="g1", target_type="node", target_id="n7",
        outcome="confirmed", resolved_by="alice", gold_rationale="Verified",
    )
    assert result["previous_id"] == prior_id
    assert result["appended_id"] > prior_id
    assert result["status"] == "confirmed"

    # The resolved target must no longer appear in pending
    pending = store.list_pending_confirmations("g1")
    assert pending == []

    store.close()


def test_graph_store_resolve_confirmation_read_only_raises():
    """resolve_confirmation on a read-only store must raise (write guard)."""
    import tempfile
    from pathlib import Path as _Path

    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(_Path(tmp) / "store.db")
        with GraphStore(db_path) as rw:
            rw.create_graph("g1", name="g1", project="test")

        with GraphStore(db_path, read_only=True) as ro:
            import pytest as _pytest
            with _pytest.raises(Exception):
                ro.resolve_confirmation(
                    graph_id="g1", target_type="node", target_id="n1",
                    outcome="confirmed", resolved_by="x", gold_rationale="y",
                )


# ---------------------------------------------------------------------------
# P3-T01  RED — list_pending_confirmations latest-only (R-CW-03, SCEN-CW-02)
# ---------------------------------------------------------------------------

def test_list_pending_confirmations_returns_only_latest_pending():
    """list_pending_confirmations must return latest-per-target rows whose
    latest status is 'needs-confirmation'.  Already-resolved targets are excluded.

    SCEN-CW-02: row 5 needs-confirmation (n1), row 6 confirmed (n1, newer),
    row 7 needs-confirmation (n2) → only row 7 is returned.
    """
    from brain_ds.store.repository import LedgerRepository

    store = _open_store()
    _create_graph(store)
    repo = LedgerRepository(store.conn)
    now = datetime.now(timezone.utc).isoformat()

    # n1: needs-confirmation then confirmed — must be excluded
    repo.append(graph_id="g1", target_id="n1", target_type="node",
                status="needs-confirmation", provenance="generated", captured_at=now)
    repo.append(graph_id="g1", target_id="n1", target_type="node",
                status="confirmed", provenance="hand_labeled", captured_at=now,
                captured_by="human")

    # n2: only needs-confirmation — must be included
    id_n2 = repo.append(graph_id="g1", target_id="n2", target_type="node",
                         status="needs-confirmation", provenance="generated", captured_at=now)

    pending = repo.list_pending_confirmations("g1")
    assert len(pending) == 1, f"Expected 1 pending row, got {len(pending)}"
    assert pending[0].id == id_n2
    assert pending[0].target_id == "n2"
    assert pending[0].status == "needs-confirmation"

    store.close()


def test_list_pending_confirmations_is_graph_wide_and_ordered_by_id():
    """list_pending_confirmations covers both edge and node target_types,
    ordered id ASC, and scoped to the requested graph_id.
    """
    from brain_ds.store.repository import LedgerRepository

    store = _open_store()
    _create_graph(store, "g1")
    _create_graph(store, "g2")
    repo = LedgerRepository(store.conn)
    now = datetime.now(timezone.utc).isoformat()

    id_a = repo.append(graph_id="g1", target_id="e-A", target_type="edge",
                       status="needs-confirmation", provenance="generated", captured_at=now)
    id_b = repo.append(graph_id="g1", target_id="n-B", target_type="node",
                       status="needs-confirmation", provenance="generated", captured_at=now)
    # g2 row — must NOT appear in g1 results
    repo.append(graph_id="g2", target_id="n-X", target_type="node",
                status="needs-confirmation", provenance="generated", captured_at=now)

    pending = repo.list_pending_confirmations("g1")
    assert len(pending) == 2, f"Expected 2 pending rows for g1, got {len(pending)}"
    assert [r.id for r in pending] == [id_a, id_b], "Must be ordered id ASC"
    assert all(r.graph_id == "g1" for r in pending)

    store.close()


def test_list_pending_confirmations_empty_when_none():
    """Returns empty list when no pending rows exist."""
    from brain_ds.store.repository import LedgerRepository

    store = _open_store()
    _create_graph(store)
    repo = LedgerRepository(store.conn)

    pending = repo.list_pending_confirmations("g1")
    assert pending == []

    store.close()


# ---------------------------------------------------------------------------
# P3-T02  RED — resolve_confirmation append-only (R-CW-01, R-CW-04, SCEN-CW-01)
# ---------------------------------------------------------------------------

def test_resolve_confirmation_appends_new_row_and_does_not_mutate_prior():
    """SCEN-CW-01: prior row is byte-identical after resolution; a new row is appended.

    The new row must have:
    - status = outcome
    - captured_by = 'human'
    - confirmed_by = resolved_by argument
    - confirmed_at set (non-None)
    - gold_rationale set
    - provenance = 'hand_labeled'
    """
    from brain_ds.store.repository import LedgerRepository

    store = _open_store()
    _create_graph(store)
    repo = LedgerRepository(store.conn)
    now = datetime.now(timezone.utc).isoformat()

    prior_id = repo.append(
        graph_id="g1", target_id="n42", target_type="node",
        status="needs-confirmation", provenance="generated", captured_at=now,
        fact_label="department",
    )

    # Snapshot the raw prior row before resolution
    prior_raw = store.conn.execute(
        "SELECT * FROM confidence_ledger WHERE id=?", (prior_id,)
    ).fetchone()

    result = repo.resolve_confirmation(
        graph_id="g1",
        target_type="node",
        target_id="n42",
        outcome="confirmed",
        resolved_by="alice",
        gold_rationale="Verified in org chart",
    )

    # Result contract
    assert result["previous_id"] == prior_id
    appended_id = result["appended_id"]
    assert appended_id > prior_id
    assert result["status"] == "confirmed"

    # Prior row must be byte-identical
    prior_raw_after = store.conn.execute(
        "SELECT * FROM confidence_ledger WHERE id=?", (prior_id,)
    ).fetchone()
    assert prior_raw == prior_raw_after, "Prior row was mutated — append-only violated"

    # New row must have correct fields
    new_raw = store.conn.execute(
        "SELECT status, captured_by, confirmed_by, confirmed_at, gold_rationale, provenance "
        "FROM confidence_ledger WHERE id=?", (appended_id,)
    ).fetchone()
    assert new_raw[0] == "confirmed"
    assert new_raw[1] == "human"
    assert new_raw[2] == "alice"
    assert new_raw[3] is not None, "confirmed_at must be set"
    assert new_raw[4] == "Verified in org chart"
    assert new_raw[5] == "hand_labeled"

    store.close()


def test_resolve_confirmation_rejects_invalid_outcome():
    """SCEN-CW-03: invalid outcome returns error and appends NO row."""
    from brain_ds.store.repository import LedgerRepository

    store = _open_store()
    _create_graph(store)
    repo = LedgerRepository(store.conn)
    now = datetime.now(timezone.utc).isoformat()

    repo.append(graph_id="g1", target_id="n1", target_type="node",
                status="needs-confirmation", provenance="generated", captured_at=now)

    count_before = store.conn.execute(
        "SELECT COUNT(*) FROM confidence_ledger"
    ).fetchone()[0]

    import pytest as _pytest
    with _pytest.raises(ValueError, match="outcome"):
        repo.resolve_confirmation(
            graph_id="g1", target_type="node", target_id="n1",
            outcome="maybe", resolved_by="alice", gold_rationale="",
        )

    count_after = store.conn.execute(
        "SELECT COUNT(*) FROM confidence_ledger"
    ).fetchone()[0]
    assert count_after == count_before, "No row must be appended on invalid outcome"

    store.close()


def test_resolve_confirmation_rejects_when_no_pending_row():
    """Error when no needs-confirmation row exists for the target."""
    from brain_ds.store.repository import LedgerRepository

    store = _open_store()
    _create_graph(store)
    repo = LedgerRepository(store.conn)

    import pytest as _pytest
    with _pytest.raises(ValueError, match="No pending"):
        repo.resolve_confirmation(
            graph_id="g1", target_type="node", target_id="n99",
            outcome="confirmed", resolved_by="alice", gold_rationale="ok",
        )

    store.close()


def test_resolve_confirmation_rejects_when_latest_not_pending():
    """Error when latest row for target is not needs-confirmation (already resolved)."""
    from brain_ds.store.repository import LedgerRepository

    store = _open_store()
    _create_graph(store)
    repo = LedgerRepository(store.conn)
    now = datetime.now(timezone.utc).isoformat()

    repo.append(graph_id="g1", target_id="n1", target_type="node",
                status="needs-confirmation", provenance="generated", captured_at=now)
    repo.append(graph_id="g1", target_id="n1", target_type="node",
                status="confirmed", provenance="hand_labeled", captured_at=now,
                captured_by="human")

    import pytest as _pytest
    with _pytest.raises(ValueError, match="not.*needs-confirmation|already"):
        repo.resolve_confirmation(
            graph_id="g1", target_type="node", target_id="n1",
            outcome="confirmed", resolved_by="bob", gold_rationale="ok",
        )

    store.close()


def test_resolve_confirmation_accepts_all_valid_outcomes():
    """confirmed, invalidated, abstain are all accepted."""
    from brain_ds.store.repository import LedgerRepository

    store = _open_store()
    _create_graph(store)
    repo = LedgerRepository(store.conn)
    now = datetime.now(timezone.utc).isoformat()

    for i, outcome in enumerate(["confirmed", "invalidated", "abstain"]):
        target_id = f"n{i}"
        repo.append(graph_id="g1", target_id=target_id, target_type="node",
                    status="needs-confirmation", provenance="generated", captured_at=now)
        result = repo.resolve_confirmation(
            graph_id="g1", target_type="node", target_id=target_id,
            outcome=outcome, resolved_by="alice", gold_rationale="test",
        )
        assert result["status"] == outcome

    store.close()
