from brain_ds.currency.coverage import coverage_score


def test_pending_counts_as_gap():
    assessed = [
        {"node_id": f"current-{index}", "entity_type": "KPI", "staleness_class": "current"}
        for index in range(8)
    ] + [
        {"node_id": "stale-1", "entity_type": "KPI", "staleness_class": "stale"},
        {"node_id": "pending-1", "entity_type": "KPI", "staleness_class": "pending"},
    ]

    result = coverage_score(assessed)

    assert result["overall"] == 0.8
    assert result["by_type"]["KPI"] == {
        "covered": 8,
        "total": 10,
        "coverage": 0.8,
    }


def test_data_internal_nodes_excluded_from_denominator_and_numerator():
    assessed = [
        {"node_id": "kpi-1", "entity_type": "KPI", "staleness_class": "current"},
        {"node_id": "kpi-2", "entity_type": "KPI", "staleness_class": "current"},
        {"node_id": "kpi-3", "entity_type": "KPI", "staleness_class": "current"},
        {"node_id": "risk-1", "entity_type": "RISK", "staleness_class": "stale"},
        {"node_id": "risk-2", "entity_type": "RISK", "staleness_class": "unknown"},
        {"node_id": "container-1", "entity_type": "DataContainer", "staleness_class": "current"},
        {"node_id": "field-1", "entity_type": "DataField", "staleness_class": "current"},
    ]

    result = coverage_score(assessed)

    assert result["overall"] == 0.6
    assert "DataContainer" not in result["by_type"]
    assert "DataField" not in result["by_type"]


def test_recent_needs_confirmation_is_not_covered_without_human_confirmation():
    assessed = [
        {
            "node_id": "pending-ledger-1",
            "entity_type": "KPI",
            "staleness_class": "current",
            "ledger_status": "needs-confirmation",
            "confirmed_within_window": False,
        },
        {
            "node_id": "confirmed-1",
            "entity_type": "KPI",
            "staleness_class": "current",
            "ledger_status": "confirmed",
            "confirmed_within_window": True,
        },
    ]

    result = coverage_score(assessed)

    assert result["overall"] == 0.5
    assert result["by_type"]["KPI"] == {"covered": 1, "total": 2, "coverage": 0.5}
