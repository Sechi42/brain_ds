from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _node(node_id: str, *, entity_type: str = "KPI") -> dict:
    return {"id": node_id, "label": node_id, "type": entity_type,
            "details": {"where": "ops", "learned": "grounded"},
            "created_at": "2026-01-01T00:00:00+00:00",
            "modified_at": "2026-01-01T00:00:00+00:00"}


def test_aggregate_gaps_applies_top_n_cap_in_priority_order() -> None:
    from brain_ds.currency.gaps import aggregate_gaps

    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    nodes = [_node(f"kpi-{index:02d}") for index in range(50)]
    ledger_evidence = {node["id"]: {"captured_at": now - timedelta(days=90 + i)} for i, node in enumerate(nodes)}
    adjacency = {node["id"]: {f"neighbor-{n}" for n in range(i % 16)} for i, node in enumerate(nodes)}

    result = aggregate_gaps(nodes, adjacency, ledger_evidence, top_n=10, now=now)

    assert len(result["ranked_gaps"]) == 10
    priorities = [gap["priority"] for gap in result["ranked_gaps"]]
    assert priorities == sorted(priorities, reverse=True)


def test_aggregate_gaps_ranks_unknown_alongside_stale_candidates() -> None:
    from brain_ds.currency.gaps import aggregate_gaps

    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    unknown_a = _node("unknown-a")
    unknown_b = _node("unknown-b")
    unknown_a.pop("created_at")
    unknown_a.pop("modified_at")
    unknown_b.pop("created_at")
    unknown_b.pop("modified_at")
    nodes = [_node("stale-a"), _node("stale-b"), _node("stale-c"), unknown_a, unknown_b]
    ledger_evidence = {
        "stale-a": {"captured_at": now - timedelta(days=90)},
        "stale-b": {"captured_at": now - timedelta(days=95)},
        "stale-c": {"captured_at": now - timedelta(days=100)},
    }

    result = aggregate_gaps(nodes, {}, ledger_evidence, top_n=10, now=now)

    assert {gap["node_id"] for gap in result["ranked_gaps"]} == {"stale-a", "stale-b", "stale-c", "unknown-a", "unknown-b"}
    assert {gap["staleness_class"] for gap in result["ranked_gaps"]} == {"stale", "unknown"}


def test_aggregate_gaps_merges_stale_and_sparse_into_one_entry() -> None:
    from brain_ds.currency.gaps import aggregate_gaps

    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    nodes = [_node("sparse-stale")]
    ledger_evidence = {"sparse-stale": {"captured_at": now - timedelta(days=90)}}

    result = aggregate_gaps(nodes, {}, ledger_evidence, sparse_node_ids={"sparse-stale"}, top_n=10, now=now)

    assert len(result["ranked_gaps"]) == 1
    assert result["ranked_gaps"][0]["node_id"] == "sparse-stale"
    assert result["ranked_gaps"][0]["gap_kind"] == ["staleness", "sparseness"]


def test_aggregate_gaps_does_not_treat_recent_needs_confirmation_as_current() -> None:
    from brain_ds.currency.gaps import aggregate_gaps

    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    nodes = [_node("pending-kpi")]
    ledger_evidence = {
        "pending-kpi": {
            "ledger_status": "needs-confirmation",
            "ledger_captured_at": now - timedelta(days=1),
            "modified_at": now - timedelta(days=90),
            "created_at": now - timedelta(days=90),
        }
    }

    result = aggregate_gaps(nodes, {}, ledger_evidence, top_n=10, now=now)

    assert result["coverage"]["overall"] == 0.0
    assert result["ranked_gaps"][0]["node_id"] == "pending-kpi"
    assert result["ranked_gaps"][0]["staleness_class"] == "stale"


def test_aggregate_gaps_unifies_structural_and_calibration_gap_entries() -> None:
    from brain_ds.currency.gaps import aggregate_gaps

    result = aggregate_gaps(
        [],
        {},
        {},
        structural_missing_types=["Risk"],
        calibration_gap_labels=["owned-by"],
    )

    gaps_by_kind = {tuple(gap["gap_kind"]): gap for gap in result["ranked_gaps"]}

    assert ("structural",) in gaps_by_kind
    assert gaps_by_kind[("structural",)]["node_id"] == "missing:Risk"
    assert gaps_by_kind[("structural",)]["stakeholder_tags"] == ["unknown"]
    assert ("calibration",) in gaps_by_kind
    assert gaps_by_kind[("calibration",)]["node_id"] == "calibration:owned-by"
    assert gaps_by_kind[("calibration",)]["staleness_class"] == "unknown"
