from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from brain_ds.mcp.tools import assess_currency
from brain_ds.store.graph_store import GraphStore


def _store(tmp_path: Path) -> GraphStore:
    store = GraphStore(str(tmp_path / "store.db"))
    store.create_graph("g", name="Graph", project="p")
    for node_id, label in (
        ("A", "Finance KPI"),
        ("B", "Finance Source"),
        ("C", "Operations KPI"),
    ):
        store.upsert_node(
            "g",
            {
                "id": node_id,
                "label": label,
                "type": "KPI" if node_id != "B" else "Data Source",
                "supertype": "Business" if node_id != "B" else "Technology",
                "details": {"where": "team", "learned": "grounded"},
            },
        )
        store.append_ledger(
            "g",
            target_type="node",
            target_id=node_id,
            status="confirmed",
            provenance="hand_labeled",
            captured_at="2026-01-01T00:00:00+00:00",
            confirmed_at="2026-01-01T00:00:00+00:00",
            confirmed_by="tester",
        )
    store.upsert_edge("g", {"source": "A", "target": "B", "label": "measured-by", "weight": 0.9})
    return store


def test_assess_currency_read_only_guarantee(tmp_path: Path) -> None:
    store = _store(tmp_path)
    statements: list[str] = []
    store.conn.set_trace_callback(lambda sql: statements.append(sql.strip().upper()))

    result = assess_currency(store, {"graph_id": "g", "top_n": 2})

    store.conn.set_trace_callback(None)
    assert result["coverage"]["overall"] == 0.0
    assert result["ranked_gaps"]
    assert not [sql for sql in statements if sql.startswith(("INSERT", "UPDATE", "DELETE"))]


def test_assess_currency_scoped_mode_restricts_ranked_gaps_to_neighborhood(tmp_path: Path) -> None:
    store = _store(tmp_path)

    result = assess_currency(store, {"graph_id": "g", "mode": "scoped", "scope": "A", "top_n": 10})

    assert {gap["node_id"] for gap in result["ranked_gaps"]} == {"A", "B"}


def test_assess_currency_open_mode_applies_global_top_n_cap(tmp_path: Path) -> None:
    store = _store(tmp_path)

    result = assess_currency(store, {"graph_id": "g", "mode": "open", "top_n": 2})

    assert len(result["ranked_gaps"]) == 2
    assert [gap["priority"] for gap in result["ranked_gaps"]] == sorted(
        [gap["priority"] for gap in result["ranked_gaps"]],
        reverse=True,
    )


def test_assess_currency_unifies_structural_and_calibration_gaps_read_only(monkeypatch, tmp_path: Path) -> None:
    import brain_ds.mcp.tools as tools

    store = _store(tmp_path)
    calls: list[tuple[str, GraphStore]] = []

    def fake_calibrate_from_ledger(graph_id: str, store_arg: GraphStore):
        calls.append((graph_id, store_arg))
        return SimpleNamespace(classes={"owned-by": SimpleNamespace(examples=1)})

    monkeypatch.setattr(tools, "calibrate_from_ledger", fake_calibrate_from_ledger)
    statements: list[str] = []
    store.conn.set_trace_callback(lambda sql: statements.append(sql.strip().upper()))

    result = assess_currency(store, {"graph_id": "g", "top_n": 50})

    store.conn.set_trace_callback(None)
    gap_kinds = {tuple(gap["gap_kind"]) for gap in result["ranked_gaps"]}
    assert calls == [("g", store)]
    assert ("structural",) in gap_kinds
    assert ("calibration",) in gap_kinds
    assert not [sql for sql in statements if sql.startswith(("INSERT", "UPDATE", "DELETE"))]
