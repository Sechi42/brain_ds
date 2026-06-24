from __future__ import annotations

from pathlib import Path

from brain_ds.store.models import LedgerRow


def _ledger_row(
    target_id: str,
    status: str,
    *,
    row_id: int = 1,
    label: str = "uses",
    weight: float | None = 0.8,
    initial: float | None = None,
    source_type: str = "Team",
    target_type_name: str = "Data Source",
    provenance: str = "hand_labeled",
) -> LedgerRow:
    return LedgerRow(
        id=row_id,
        graph_id="g1",
        target_type="edge",
        target_id=target_id,
        status=status,
        initial_confidence=initial,
        current_confidence=weight,
        relationship_label=label,
        source_node_id="src",
        target_node_id="dst",
        source_node_type=source_type,
        target_node_type=target_type_name,
        evidence_ids=[f"ev-{target_id}"],
        captured_by="human",
        captured_at="2026-01-01T00:00:00+00:00",
        confirmed_at=None,
        confirmed_by=None,
        flagged_reason=None,
        gold_rationale=None,
        provenance=provenance,
    )


def test_should_flag_for_confirmation_truth_table():
    from brain_ds.verify.ledger_calibration import _should_flag_for_confirmation

    assert _should_flag_for_confirmation(
        label="owns",
        source_type="Role",
        target_type="Data Source",
        weight=0.8,
    ) == "sensitive_ownership_transition"
    assert _should_flag_for_confirmation(
        label="owned-by",
        source_type="Data Source",
        target_type="Role",
        weight=0.8,
    ) == "sensitive_ownership_transition"
    assert _should_flag_for_confirmation(
        label="uses",
        source_type="Team",
        target_type="Data Source",
        weight=0.5,
    ) == "low_confidence_abstain_band"
    assert _should_flag_for_confirmation(
        label="uses",
        source_type="Team",
        target_type="Data Source",
        weight=0.9,
        verifier_findings=[{"severity": "CRITICAL", "message": "bad evidence"}],
    ) == "verifier_critical_finding"
    assert _should_flag_for_confirmation(
        label="uses",
        source_type="Team",
        target_type="Data Source",
        weight=0.9,
        verifier_findings=[{"severity": "WARNING"}],
    ) is None


def test_ledger_to_gold_records_maps_verdict_statuses_and_skips_pre_verdicts():
    from brain_ds.verify.ledger_calibration import ledger_to_gold_records

    rows = [
        _ledger_row("e1", "confirmed", row_id=1, label="uses", weight=0.9),
        _ledger_row("e2", "invalidated", row_id=2, label="owns", weight=0.3),
        _ledger_row("e3", "abstain", row_id=3, label="uses", weight=0.5),
        _ledger_row("e4", "inferred", row_id=4, label="uses", weight=0.75),
        _ledger_row("e5", "needs-confirmation", row_id=5, label="owns", weight=0.6),
        _ledger_row("e6", "confirmed", row_id=6, label="uses", weight=None, initial=0.42),
    ]

    records = ledger_to_gold_records(rows)

    assert [record.edge_id for record in records] == ["e1", "e2", "e3", "e6"]
    assert {record.edge_id: record.gold_verdict for record in records} == {
        "e1": "valid",
        "e2": "invalid",
        "e3": "abstain",
        "e6": "valid",
    }
    assert {record.edge_id: record.weight for record in records}["e6"] == 0.42
    assert records[0].gold_rationale == "ledger:confirmed by=human"
    assert records[0].evidence_ids == ("ev-e1",)


def test_ledger_to_gold_records_latest_row_wins_before_verdict_filter():
    from brain_ds.verify.ledger_calibration import ledger_to_gold_records

    older_confirmed = _ledger_row("e99", "confirmed", row_id=7)
    newer_needs_confirmation = _ledger_row("e99", "needs-confirmation", row_id=9)
    newer_confirmed = _ledger_row("e100", "confirmed", row_id=10, weight=1.4)
    older_invalidated = _ledger_row("e100", "invalidated", row_id=8, weight=0.2)

    records = ledger_to_gold_records([
        older_confirmed,
        newer_needs_confirmation,
        newer_confirmed,
        older_invalidated,
    ])

    assert [record.edge_id for record in records] == ["e100"]
    assert records[0].gold_verdict == "valid"
    assert records[0].weight == 1.0


class _LedgerStore:
    def __init__(self, rows: list[LedgerRow]) -> None:
        self._rows = rows

    def query_ledger_latest(self, graph_id: str):
        assert graph_id == "g1"
        return self._rows


def _seed_line(edge_id: str, label: str, verdict: str, weight: float) -> str:
    return (
        '{'
        f'"edge_id":"{edge_id}","graph_id":"gold","label":"{label}",'
        '"source_type":"Team","target_type":"Data Source",'
        f'"weight":{weight},"evidence_ids":["seed"],'
        f'"gold_verdict":"{verdict}","gold_rationale":"seed {verdict}",'
        '"provenance":"seed"'
        '}'
    )


def test_calibrate_from_ledger_supplements_only_sparse_labels(monkeypatch, tmp_path: Path):
    from brain_ds.verify import ledger_calibration

    uses_rows = [
        _ledger_row(
            f"uses-{idx}",
            "confirmed" if idx % 2 else "invalidated",
            row_id=idx,
            label="uses",
            weight=0.8 if idx % 2 else 0.2,
        )
        for idx in range(1, 13)
    ]
    owns_rows = [
        _ledger_row(
            f"owns-{idx}",
            "confirmed" if idx % 2 else "invalidated",
            row_id=100 + idx,
            label="owns",
            weight=0.85 if idx % 2 else 0.15,
        )
        for idx in range(1, 6)
    ]
    seed_path = tmp_path / "seed.jsonl"
    seed_path.write_text(
        "\n".join(
            [
                _seed_line("seed-owns-valid", "owns", "valid", 0.9),
                _seed_line("seed-owns-invalid", "owns", "invalid", 0.1),
                _seed_line("seed-uses-valid", "uses", "valid", 0.91),
                _seed_line("seed-depends-valid", "depends-on", "valid", 0.91),
            ]
        ),
        encoding="utf-8",
    )
    captured: dict[str, list] = {}

    def fake_calibrate_edges(records, *, run_id=None):
        captured["records"] = list(records)
        return "report"

    monkeypatch.setattr(ledger_calibration, "calibrate_edges", fake_calibrate_edges)

    report = ledger_calibration.calibrate_from_ledger(
        "g1",
        _LedgerStore([*uses_rows, *owns_rows]),
        global_seed_path=seed_path,
    )

    records = captured["records"]
    assert report == "report"
    assert sum(1 for record in records if record.label == "uses") == 12
    assert sum(1 for record in records if record.label == "owns") == 7
    assert "seed-owns-valid" in {record.edge_id for record in records}
    assert "seed-uses-valid" not in {record.edge_id for record in records}
    assert "seed-depends-valid" in {record.edge_id for record in records}


def test_append_only_state_transitions_preserve_history_and_latest_state():
    from brain_ds.store.graph_store import GraphStore

    store = GraphStore(":memory:")
    store.create_graph("g1", name="g1", project="test")
    try:
        ids = [
            store.append_ledger(
                "g1",
                target_id="e-transition",
                status=status,
                provenance="seed",
                captured_at=f"2026-01-01T00:00:0{idx}+00:00",
            )
            for idx, status in enumerate(
                ["inferred", "needs-confirmation", "confirmed", "invalidated", "abstain"],
                start=1,
            )
        ]

        history = store.query_ledger("g1")
        latest = store.query_ledger_latest("g1")

        assert [row.id for row in history] == ids
        assert [row.status for row in history] == [
            "inferred",
            "needs-confirmation",
            "confirmed",
            "invalidated",
            "abstain",
        ]
        assert len(latest) == 1
        assert latest[0].id == ids[-1]
        assert latest[0].status == "abstain"
    finally:
        store.close()
