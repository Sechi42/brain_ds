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
import json
from pathlib import Path

import pytest


_LIVE_ARN = os.getenv("BRAINDS_GSHEETS_LIVE_ARN")
_LIVE_SPREADSHEET_ID = os.getenv("BRAINDS_GSHEETS_LIVE_SPREADSHEET_ID")
_LIVE_SHEET_RANGE = os.getenv("BRAINDS_GSHEETS_LIVE_SHEET_RANGE", "Sheet1!A1:Z")
_TOPETE_ACCEPTANCE = os.getenv("BRAINDS_TOPETE_LIVE_ACCEPTANCE") == "1"
_TOPETE_WORKSPACE = os.getenv("BRAINDS_TOPETE_WORKSPACE")
_TOPETE_GRAPH_ID = os.getenv("BRAINDS_TOPETE_GRAPH_ID")
_TOPETE_SOURCE_NODE_ID = os.getenv("BRAINDS_TOPETE_SOURCE_NODE_ID")
_TOPETE_SOURCE_LABEL = os.getenv("BRAINDS_TOPETE_SOURCE_LABEL", "")


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


def _topete_store_path() -> Path:
    assert _TOPETE_WORKSPACE is not None
    return Path(_TOPETE_WORKSPACE) / ".brain_ds" / "store.db"


def _topete_source_node_id(store, graph_id: str) -> str:
    if _TOPETE_SOURCE_NODE_ID:
        return _TOPETE_SOURCE_NODE_ID
    sources = store.query_nodes(graph_id, type="Data Source")
    if _TOPETE_SOURCE_LABEL:
        sources = [row for row in sources if _TOPETE_SOURCE_LABEL.lower() in row.label.lower()]
    compatible = [
        row
        for row in sources
        if str(
            (row.details or {}).get("kind")
            or (row.details or {}).get("source_kind")
            or ((row.details or {}).get("connection") or {}).get("kind")
            or ((row.details or {}).get("secret_binding") or {}).get("provider_kind")
            or ""
        ).lower()
        in {"google-sheets", "google_sheets", "sheets", "google-sheets-json"}
    ]
    assert len(compatible) == 1
    return str(compatible[0].id)


@pytest.mark.skipif(
    not _TOPETE_ACCEPTANCE or not _TOPETE_WORKSPACE or not _TOPETE_GRAPH_ID,
    reason="Set BRAINDS_TOPETE_LIVE_ACCEPTANCE=1 plus workspace/graph env vars for guarded Topete live acceptance",
)
def test_live_topete_action_flow_validates_profiles_and_redacts_payloads():
    """Guarded PR7 live acceptance for the action-based source connection path."""
    from brain_ds.connectors.secrets import SecretCatalog
    from brain_ds.mcp.tools import explore_source, list_source_connections
    from brain_ds.store.graph_store import GraphStore

    store = GraphStore(str(_topete_store_path()))
    try:
        store.secret_admin_enabled = True
        graph_id = str(_TOPETE_GRAPH_ID)
        source_node_id = _topete_source_node_id(store, graph_id)
        catalog = SecretCatalog(Path(_TOPETE_WORKSPACE))
        catalog.load()

        candidate_secrets = list_source_connections(
            store,
            {
                "action": "candidate_secrets",
                "graph_id": graph_id,
                "source_node_id": source_node_id,
            },
        )
        assert candidate_secrets["status"] == "ok"
        sheets_secrets = [
            item
            for item in candidate_secrets["secrets"]
            if item["provider_kind"] == "google-sheets-json"
        ]
        assert len(sheets_secrets) >= 1
        secret_ref = sheets_secrets[0]["secret_ref"]

        candidate_sources = list_source_connections(
            store,
            {"action": "candidate_sources", "graph_id": graph_id, "secret_ref": secret_ref},
        )
        assert candidate_sources["status"] == "ok"
        assert source_node_id in {source["node_id"] for source in candidate_sources["sources"]}

        existing_status = list_source_connections(
            store,
            {"action": "status", "graph_id": graph_id, "source_node_id": source_node_id},
        )
        if existing_status.get("binding", {}).get("validation_status") == "valid":
            bound = existing_status
            validated = existing_status
        else:
            bound = list_source_connections(
                store,
                {
                    "action": "bind",
                    "graph_id": graph_id,
                    "source_node_id": source_node_id,
                    "secret_ref": secret_ref,
                    "provider_inputs": {"spreadsheet_ref": "live-workbook"},
                },
            )
            assert bound["binding"]["validation_status"] == "unvalidated"
            validated = list_source_connections(
                store,
                {"action": "validate", "graph_id": graph_id, "source_node_id": source_node_id},
            )
        assert "binding" in validated, {key: validated.get(key) for key in ("status", "error_code", "retryable")}
        assert validated["binding"]["validation_status"] == "valid"
        status = list_source_connections(
            store,
            {"action": "status", "graph_id": graph_id, "source_node_id": source_node_id},
        )
        assert status["binding"]["validation_status"] == "valid"

        source_level = explore_source(store, {"graph_id": graph_id, "node_id": source_node_id})
        assert source_level["level"] == "source"
        assert source_level["describe"]["kind"] == "google-sheets"
        containers = source_level["containers"]
        assert len(containers) == 1

        container_level = explore_source(
            store, {"graph_id": graph_id, "node_id": source_node_id, "container": containers[0]}
        )
        tables = container_level["tables"]
        profiles = container_level["sheet_profiles"]
        assert len(tables) == len(profiles)
        assert len(profiles) >= 1
        for profile in profiles:
            grid = profile["grid"]
            assert grid["row_count"] >= 0
            assert grid["column_count"] >= 0
            assert "google-sheets-api" == profile["provenance"]["source"]
            assert len(profile["samples"]) <= 50

        serialized = json.dumps(
            [candidate_secrets, candidate_sources, bound, validated, status, source_level, container_level],
            default=str,
        )
        assert "private_key" not in serialized
        assert "client_email" not in serialized
        for entry in catalog.list_handles():
            assert entry.handle not in serialized
            spreadsheet_id = (entry.metadata or {}).get("spreadsheet_id")
            if spreadsheet_id:
                assert str(spreadsheet_id) not in serialized
    finally:
        store.close()
