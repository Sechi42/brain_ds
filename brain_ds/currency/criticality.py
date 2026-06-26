"""Pure criticality scoring for currency gap prioritization."""

from __future__ import annotations

WEIGHTS: dict[str, float] = {
    "degree": 0.25,
    "dependents": 0.20,
    "incident_weight": 0.20,
    "type": 0.20,
    "brd_ref": 0.10,
    "kpi_feed": 0.05,
}


def criticality_score(
    node: str,
    adjacency: dict[str, set[str]],
    *,
    in_degree: int,
    incident_weights: list[float],
    type_weight: float,
    brd_ref: bool,
    kpi_feed: bool,
    weights: dict[str, float] = WEIGHTS,
) -> float:
    """Return a normalized criticality score from existing graph signals."""
    degree_score = _bounded_ratio(len(adjacency.get(node, set())), 15)
    dependent_score = _bounded_ratio(in_degree, 10)
    weight_score = _average_clamped(incident_weights)
    raw = (
        weights["degree"] * degree_score
        + weights["dependents"] * dependent_score
        + weights["incident_weight"] * weight_score
        + weights["type"] * _clamp(type_weight)
        + weights["brd_ref"] * float(brd_ref)
        + weights["kpi_feed"] * float(kpi_feed)
    )
    return round(_clamp(raw), 6)


def _bounded_ratio(value: int, maximum: int) -> float:
    return _clamp(value / maximum if maximum else 0.0)


def _average_clamped(values: list[float]) -> float:
    if not values:
        return 0.0
    return _clamp(sum(_clamp(value) for value in values) / len(values))


def _clamp(value: float) -> float:
    return max(0.0, min(float(value), 1.0))
