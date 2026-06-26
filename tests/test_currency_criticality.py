"""Tests for pure currency criticality scoring."""

from __future__ import annotations


def test_high_centrality_brd_node_outscores_isolated_node():
    """Central, dependent-heavy, BRD-referenced nodes rank above isolated peers."""
    from brain_ds.currency.criticality import criticality_score

    central_adjacency = {"A": {f"n{i}" for i in range(15)}}
    isolated_adjacency = {"B": {"n1", "n2"}}

    central = criticality_score(
        "A",
        central_adjacency,
        in_degree=8,
        incident_weights=[0.9, 0.8, 0.7],
        type_weight=0.7,
        brd_ref=True,
        kpi_feed=False,
    )
    isolated = criticality_score(
        "B",
        isolated_adjacency,
        in_degree=0,
        incident_weights=[0.2],
        type_weight=0.7,
        brd_ref=False,
        kpi_feed=False,
    )

    assert central > isolated


def test_criticality_score_is_pure_for_same_inputs():
    """The same graph signals always produce the same float score."""
    from brain_ds.currency.criticality import criticality_score

    adjacency = {"KPI-1": {"Dept", "Dashboard", "Owner"}}
    kwargs = {
        "in_degree": 4,
        "incident_weights": [0.5, 0.6, 0.7],
        "type_weight": 0.9,
        "brd_ref": False,
        "kpi_feed": True,
    }

    first = criticality_score("KPI-1", adjacency, **kwargs)
    second = criticality_score("KPI-1", adjacency, **kwargs)

    assert first == second
    assert 0.0 <= first <= 1.0
