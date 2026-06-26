from datetime import datetime, timezone

from brain_ds.currency.propagation import apply_propagation_downrank
from brain_ds.currency.staleness import classify_staleness


def test_propagation_no_auto_confirm():
    ledger_writes: list[dict[str, str]] = []
    emitted_verdicts: list[str] = []
    candidates = [
        {"node_id": "node-b", "priority": 1.0, "staleness_class": "stale"},
        {"node_id": "node-c", "priority": 0.8, "staleness_class": "stale"},
    ]
    adjacency = {
        "node-a": {"node-b", "node-c", "node-d", "node-e"},
        "node-b": {"node-a", "node-c", "node-d", "node-e"},
        "node-c": {"node-a", "node-x"},
    }

    reranked = apply_propagation_downrank(candidates, {"node-a"}, adjacency)

    by_id = {candidate["node_id"]: candidate for candidate in reranked}
    assert by_id["node-b"]["priority"] == 0.82
    assert by_id["node-b"]["staleness_class"] == "stale"
    assert ledger_writes == []
    assert emitted_verdicts == []
    assert classify_staleness(
        "KPI",
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        now=datetime(2026, 6, 25, tzinfo=timezone.utc),
    ) == "stale"


def test_lightly_connected_neighbor_unaffected():
    candidates = [
        {"node_id": "node-b", "priority": 1.0, "staleness_class": "stale"},
        {"node_id": "node-c", "priority": 0.8, "staleness_class": "stale"},
    ]
    adjacency = {
        "node-a": {"node-b", "node-c", "node-d", "node-e"},
        "node-b": {"node-a", "node-c", "node-d", "node-e"},
        "node-c": {"node-a", "node-x"},
    }

    reranked = apply_propagation_downrank(candidates, {"node-a"}, adjacency)

    by_id = {candidate["node_id"]: candidate for candidate in reranked}
    assert by_id["node-c"]["priority"] == 0.8
    assert [candidate["node_id"] for candidate in reranked] == ["node-b", "node-c"]
