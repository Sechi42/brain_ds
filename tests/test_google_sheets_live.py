"""PR3-T8 — Opt-in live integration test for Google Sheets connector.

Skipped unless ``BRAINDS_GSHEETS_LIVE_ARN`` environment variable is set.

Usage:
    BRAINDS_GSHEETS_LIVE_ARN=arn:aws:secretsmanager:us-east-2:123:secret:gsheets/sa \\
    BRAINDS_GSHEETS_LIVE_SPREADSHEET_ID=1AbC... \\
    BRAINDS_GSHEETS_LIVE_SHEET_RANGE=Sheet1!A1:Z \\
    uv run pytest tests/test_google_sheets_live.py -m gsheets_live -v

This test:
  1. Calls AwsGoogleSheetsAdapter.resolve() against a real AWS ARN.
  2. Instantiates GoogleSheetsConnector with the resolved params.
  3. Verifies describe() / list_containers() / list_tables() / preview() work.
  4. Verifies NO write methods are called (structural — connector has none).
"""
from __future__ import annotations

import os
import pytest


_LIVE_ARN = os.getenv("BRAINDS_GSHEETS_LIVE_ARN")
_LIVE_SPREADSHEET_ID = os.getenv("BRAINDS_GSHEETS_LIVE_SPREADSHEET_ID")
_LIVE_SHEET_RANGE = os.getenv("BRAINDS_GSHEETS_LIVE_SHEET_RANGE", "Sheet1!A1:Z")


pytestmark = pytest.mark.gsheets_live


@pytest.mark.skipif(
    not _LIVE_ARN,
    reason="BRAINDS_GSHEETS_LIVE_ARN not set — skip live Google Sheets integration test",
)
def test_live_google_sheets_adapter_resolve():
    """Resolve a real SA from AWS Secrets Manager."""
    from brain_ds.connectors.secrets.providers.aws_google_sheets import AwsGoogleSheetsAdapter

    metadata = {
        "secret_id": _LIVE_ARN,
        "spreadsheet_id": _LIVE_SPREADSHEET_ID or "placeholder",
        "sheet_range": _LIVE_SHEET_RANGE,
    }

    adapter = AwsGoogleSheetsAdapter()
    result = adapter.resolve("live-handle", metadata)

    assert "service_account_info" in result
    assert result["spreadsheet_id"] == metadata["spreadsheet_id"]
    assert result["sheet_range"] == metadata["sheet_range"]
    sa = result["service_account_info"]
    assert "type" in sa
    assert sa["type"] == "service_account"


@pytest.mark.skipif(
    not _LIVE_ARN or not _LIVE_SPREADSHEET_ID,
    reason="BRAINDS_GSHEETS_LIVE_ARN + BRAINDS_GSHEETS_LIVE_SPREADSHEET_ID not set",
)
def test_live_google_sheets_connector_describe():
    """Connect to a real spreadsheet and call describe()."""
    from brain_ds.connectors.secrets.providers.aws_google_sheets import AwsGoogleSheetsAdapter
    from brain_ds.connectors.google_sheets_connector import GoogleSheetsConnector

    metadata = {
        "secret_id": _LIVE_ARN,
        "spreadsheet_id": _LIVE_SPREADSHEET_ID,
        "sheet_range": _LIVE_SHEET_RANGE,
    }

    adapter = AwsGoogleSheetsAdapter()
    params = adapter.resolve("live-handle", metadata)

    connector = GoogleSheetsConnector(params)
    result = connector.describe()

    assert result["kind"] == "google-sheets"
    assert "title" in result
    assert "url" in result
    assert "service_account_info" not in result  # INV-1


@pytest.mark.skipif(
    not _LIVE_ARN or not _LIVE_SPREADSHEET_ID,
    reason="BRAINDS_GSHEETS_LIVE_ARN + BRAINDS_GSHEETS_LIVE_SPREADSHEET_ID not set",
)
def test_live_google_sheets_connector_list_tables():
    """Connect to a real spreadsheet and list worksheet tabs."""
    from brain_ds.connectors.secrets.providers.aws_google_sheets import AwsGoogleSheetsAdapter
    from brain_ds.connectors.google_sheets_connector import GoogleSheetsConnector

    metadata = {
        "secret_id": _LIVE_ARN,
        "spreadsheet_id": _LIVE_SPREADSHEET_ID,
        "sheet_range": _LIVE_SHEET_RANGE,
    }

    adapter = AwsGoogleSheetsAdapter()
    params = adapter.resolve("live-handle", metadata)

    connector = GoogleSheetsConnector(params)
    containers = connector.list_containers()
    assert len(containers) == 1

    tables = connector.list_tables(containers[0])
    assert isinstance(tables, list)
    assert len(tables) >= 1


@pytest.mark.skipif(
    not _LIVE_ARN or not _LIVE_SPREADSHEET_ID,
    reason="BRAINDS_GSHEETS_LIVE_ARN + BRAINDS_GSHEETS_LIVE_SPREADSHEET_ID not set",
)
def test_live_google_sheets_connector_preview():
    """Connect to a real spreadsheet and preview the first sheet."""
    from brain_ds.connectors.secrets.providers.aws_google_sheets import AwsGoogleSheetsAdapter
    from brain_ds.connectors.google_sheets_connector import GoogleSheetsConnector

    metadata = {
        "secret_id": _LIVE_ARN,
        "spreadsheet_id": _LIVE_SPREADSHEET_ID,
        "sheet_range": _LIVE_SHEET_RANGE,
    }

    adapter = AwsGoogleSheetsAdapter()
    params = adapter.resolve("live-handle", metadata)

    connector = GoogleSheetsConnector(params)
    containers = connector.list_containers()
    tables = connector.list_tables(containers[0])
    assert len(tables) >= 1

    result = connector.preview(containers[0], tables[0], limit=10)
    assert "columns" in result
    assert "rows" in result
    assert "truncated" in result
    assert len(result["rows"]) <= 50
