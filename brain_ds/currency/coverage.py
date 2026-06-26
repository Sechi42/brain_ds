"""Coverage metric helpers for temporal currency assessment."""

from __future__ import annotations

from typing import Any

DATA_INTERNAL_TYPES = {"DATACONTAINER", "DATAFIELD", "DATA_CONTAINER", "DATA_FIELD"}


def coverage_score(assessed: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute confirmed-within-window coverage, excluding DATA_INTERNAL nodes."""
    totals: dict[str, dict[str, int]] = {}
    covered_total = 0
    assessed_total = 0

    for item in assessed:
        entity_type = str(item.get("entity_type", "UNKNOWN"))
        if _normalize(entity_type) in DATA_INTERNAL_TYPES:
            continue

        assessed_total += 1
        bucket = totals.setdefault(entity_type, {"covered": 0, "total": 0})
        bucket["total"] += 1

        if _is_covered(item):
            covered_total += 1
            bucket["covered"] += 1

    by_type = {
        entity_type: {
            "covered": counts["covered"],
            "total": counts["total"],
            "coverage": _ratio(counts["covered"], counts["total"]),
        }
        for entity_type, counts in totals.items()
    }
    return {"overall": _ratio(covered_total, assessed_total), "by_type": by_type}


def _ratio(covered: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round(covered / total, 6)


def _is_covered(item: dict[str, Any]) -> bool:
    if "confirmed_within_window" in item:
        return bool(item["confirmed_within_window"])
    return str(item.get("staleness_class", "")).lower() == "current"


def _normalize(value: str) -> str:
    return value.strip().upper().replace(" ", "_")
