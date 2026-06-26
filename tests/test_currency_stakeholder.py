from brain_ds.currency.stakeholder import resolve_owner


def test_owner_resolved_via_owned_by_edge():
    nodes_by_id = {
        "kpi-1": {"id": "kpi-1", "type": "KPI", "label": "Gross Margin"},
        "role-finance": {"id": "role-finance", "type": "ROLE", "label": "Finance Director"},
    }
    edges = [
        {"source": "kpi-1", "target": "role-finance", "label": "OWNED_BY"},
    ]

    assert resolve_owner("kpi-1", edges, nodes_by_id) == "Finance Director"


def test_owner_resolved_via_canonical_owned_by_edge():
    nodes_by_id = {
        "kpi-1": {"id": "kpi-1", "type": "KPI", "label": "Gross Margin"},
        "role-finance": {"id": "role-finance", "type": "ROLE", "label": "Finance Director"},
    }
    edges = [
        {"source": "kpi-1", "target": "role-finance", "label": "owned-by"},
    ]

    assert resolve_owner("kpi-1", edges, nodes_by_id) == "Finance Director"


def test_owner_resolved_via_canonical_owns_edge():
    nodes_by_id = {
        "data-1": {"id": "data-1", "type": "Data Source", "label": "Warehouse"},
        "person-1": {"id": "person-1", "type": "PERSON", "label": "Sam Rivera"},
    }
    edges = [
        {"source": "person-1", "target": "data-1", "label": "owns"},
    ]

    assert resolve_owner("data-1", edges, nodes_by_id) == "Sam Rivera"


def test_no_owner_edge_returns_unknown_without_dropping_question():
    nodes_by_id = {
        "risk-1": {"id": "risk-1", "type": "RISK", "label": "Forecast risk"},
    }

    assert resolve_owner("risk-1", [], nodes_by_id) == "unknown"
