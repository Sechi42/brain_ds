"""Pure priority-only propagation helpers for currency questions."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def apply_propagation_downrank(
    candidates: list[dict[str, Any]],
    confirmed_node_ids: Iterable[str],
    adjacency: dict[str, set[str]],
    *,
    alpha: float = 0.3,
    overlap_threshold: float = 0.5,
) -> list[dict[str, Any]]:
    """Return candidates with heavy-neighbor question priority softly down-ranked.

    This function is intentionally pure: it accepts no store/writer dependency,
    emits no verdict, and only returns adjusted candidate dictionaries.
    """
    confirmed = {str(node_id) for node_id in confirmed_node_ids}
    adjusted = []

    for candidate in candidates:
        node_id = str(candidate.get("node_id", ""))
        strongest_overlap = max(
            (_jaccard(adjacency.get(node_id, set()), adjacency.get(confirmed_id, set()))
             for confirmed_id in confirmed),
            default=0.0,
        )
        next_candidate = dict(candidate)
        if strongest_overlap >= overlap_threshold:
            priority = float(next_candidate.get("priority", 0.0))
            next_candidate["priority"] = round(priority * (1 - alpha * strongest_overlap), 6)
        adjusted.append(next_candidate)

    return sorted(adjusted, key=lambda item: float(item.get("priority", 0.0)), reverse=True)


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 0.0
    return len(left & right) / len(left | right)
