"""Pure staleness classification helpers for graph currency."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

STALENESS_THRESHOLDS: dict[str, int] = {
    "DATA_SOURCE": 30,
    "ORGANIZATION": 90,
    "DEPARTMENT": 90,
    "ROLE": 90,
    "PROBLEM": 60,
    "PROBLEM_IMPROVEMENT_AREA": 60,
    "KPI": 60,
    "SOLUTION": 60,
    "DECISION": 60,
    "RISK": 60,
    "PROJECT": 60,
    "HEURISTIC": 180,
    "TACIT_KNOWLEDGE": 180,
}


def resolve_last_seen(
    *,
    ledger_status: str | None = None,
    ledger_confirmed_at: datetime | str | None = None,
    ledger_captured_at: datetime | str | None = None,
    schema_baseline_last_documented_at: datetime | str | None = None,
    modified_at: datetime | str | None = None,
    created_at: datetime | str | None = None,
) -> datetime | None:
    """Pick the best currency timestamp using the Brick-E precedence order."""
    if ledger_status == "confirmed" and ledger_confirmed_at is not None:
        return _as_datetime(ledger_confirmed_at)
    for candidate in (
        ledger_captured_at,
        schema_baseline_last_documented_at,
        modified_at,
        created_at,
    ):
        if candidate is not None:
            return _as_datetime(candidate)
    return None


def classify_staleness(
    target_kind: str,
    last_seen_at: datetime | str | None,
    threshold_days: int | None = None,
    *,
    thresholds: dict[str, int] | None = None,
    now: datetime | str | None = None,
) -> str:
    """Classify a target as current, stale, or unknown against its freshness window."""
    last_seen = _as_datetime(last_seen_at)
    if last_seen is None:
        return "unknown"

    window_days = threshold_days
    if window_days is None:
        window_days = _threshold_for(target_kind, thresholds)

    reference = _as_datetime(now) or datetime.now(timezone.utc)
    age_days = (reference - last_seen).total_seconds() / 86_400
    return "stale" if age_days > window_days else "current"


def _threshold_for(target_kind: str, thresholds: dict[str, int] | None) -> int:
    normalized = _normalize_kind(target_kind)
    overrides = {_normalize_kind(key): value for key, value in (thresholds or {}).items()}
    return overrides.get(normalized, STALENESS_THRESHOLDS.get(normalized, 60))


def _normalize_kind(value: Any) -> str:
    return str(value or "UNKNOWN").strip().upper().replace(" ", "_").replace("/", "_")


def _as_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
