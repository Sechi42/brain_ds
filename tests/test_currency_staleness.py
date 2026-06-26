"""Tests for temporal currency staleness helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def test_confirmed_within_window_is_current():
    """A Data Source confirmed inside its freshness window is current."""
    from brain_ds.currency.staleness import classify_staleness, resolve_last_seen

    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    last_seen = resolve_last_seen(
        ledger_status="confirmed",
        ledger_confirmed_at=now - timedelta(days=20),
        ledger_captured_at=now - timedelta(days=25),
    )

    assert classify_staleness("Data Source", last_seen, now=now) == "current"


def test_past_window_is_stale_when_only_captured_at_exists():
    """A Data Source past its freshness window is stale when captured_at is the best evidence."""
    from brain_ds.currency.staleness import classify_staleness, resolve_last_seen

    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    last_seen = resolve_last_seen(
        ledger_status="needs-confirmation",
        ledger_confirmed_at=None,
        ledger_captured_at=now - timedelta(days=45),
        modified_at=now - timedelta(days=5),
    )

    assert classify_staleness("Data Source", last_seen, now=now) == "stale"


def test_no_timestamp_available_is_unknown():
    """Missing ledger, schema baseline, and node timestamps produce unknown currency."""
    from brain_ds.currency.staleness import classify_staleness, resolve_last_seen

    now = datetime(2026, 6, 25, tzinfo=timezone.utc)

    assert resolve_last_seen() is None
    assert classify_staleness("KPI", None, now=now) == "unknown"


def test_threshold_override_takes_precedence_over_default_window():
    """Call-time thresholds override the default per-type freshness windows."""
    from brain_ds.currency.staleness import classify_staleness

    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    last_seen = now - timedelta(days=10)

    assert classify_staleness(
        "DATA_SOURCE",
        last_seen,
        thresholds={"DATA_SOURCE": 7},
        now=now,
    ) == "stale"
