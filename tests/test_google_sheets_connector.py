"""PR3-T5 — TDD tests for GoogleSheetsConnector + _resolve_connector aws-google-sheets dispatch.

All gspread calls are mocked — no real Google API traffic.
Tests are written RED-first (before GoogleSheetsConnector exists).

Design invariants verified:
  INV-R1: No write call is ever made (list/get/preview only).
  INV-R2: list_containers returns the spreadsheet title (single item).
  INV-R3: list_tables returns worksheet tab names.
  INV-R4: preview is capped at 50 rows.
  INV-R5: describe() returns title/url without credentials.
"""
from __future__ import annotations

import json
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch


class _FakeSheetsRequest:
    def __init__(self, response):
        self._response = response

    def execute(self):
        return self._response


class _FakeValuesResource:
    def __init__(self, values_by_range):
        self.values_by_range = values_by_range
        self.batch_get_calls = []

    def batchGet(self, **kwargs):
        self.batch_get_calls.append(kwargs)
        value_ranges = []
        for range_name in kwargs.get("ranges", []):
            value_ranges.append(
                {
                    "range": range_name,
                    "values": self.values_by_range.get(range_name, []),
                }
            )
        return _FakeSheetsRequest({"valueRanges": value_ranges})


class _FakeSpreadsheetsResource:
    def __init__(self, metadata, values_by_range):
        self.metadata = metadata
        self.values_resource = _FakeValuesResource(values_by_range)
        self.get_calls = []

    def get(self, **kwargs):
        self.get_calls.append(kwargs)
        return _FakeSheetsRequest(self.metadata)

    def values(self):
        return self.values_resource


class _FakeSheetsService:
    def __init__(self, metadata, values_by_range):
        self.spreadsheets_resource = _FakeSpreadsheetsResource(metadata, values_by_range)

    def spreadsheets(self):
        return self.spreadsheets_resource



def _rich_api_fixture():
    metadata = {
        "spreadsheetId": "sheet-123",
        "properties": {"title": "Finance Workbook"},
        "sheets": [
            {
                "properties": {
                    "sheetId": 101,
                    "title": "Budget",
                    "index": 0,
                    "gridProperties": {
                        "rowCount": 100,
                        "columnCount": 6,
                        "frozenRowCount": 1,
                        "frozenColumnCount": 1,
                        "hideGridlines": False,
                    },
                    "hidden": False,
                },
                "charts": [
                    {"chartId": 7, "spec": {"title": "Spend by Month"}},
                ],
                "protectedRanges": [
                    {"protectedRangeId": 55, "range": {"sheetId": 101, "startRowIndex": 0, "endRowIndex": 1}, "description": "Headers"},
                ],
                "filterViews": [
                    {"filterViewId": 88, "title": "Active budget", "range": {"sheetId": 101, "startColumnIndex": 0, "endColumnIndex": 3}},
                ],
                "developerMetadata": [
                    {"metadataId": 9, "metadataKey": "owner", "metadataValue": "finance"},
                ],
            },
            {
                "properties": {
                    "sheetId": 202,
                    "title": "Empty",
                    "index": 1,
                    "gridProperties": {"rowCount": 0, "columnCount": 0},
                    "hidden": True,
                }
            },
        ],
    }
    display_values = {
        "Budget!A1:Z50": [
            ["month", "amount", "variance"],
            ["Jan", "100", "10"],
            ["Feb", "125", "=B3-B2"],
        ],
        "Empty!A1:Z50": [],
    }
    formula_values = {
        "Budget!A1:Z50": [
            ["month", "amount", "variance"],
            ["Jan", "100", "=B2-90"],
            ["Feb", "125", "=B3-B2"],
        ],
        "Empty!A1:Z50": [],
    }
    return metadata, display_values, formula_values


def _many_rows_api_fixture(
    row_count: int = 60,
    range_name: str = "'Large Data'!A1:Z50",
    value_row_count: int | None = None,
):
    if value_row_count is None:
        value_row_count = row_count
    metadata = {
        "spreadsheetId": "sheet-many",
        "properties": {"title": "Large Workbook"},
        "sheets": [
            {
                "properties": {
                    "sheetId": 303,
                    "title": "Large Data",
                    "index": 0,
                    "gridProperties": {"rowCount": row_count + 1, "columnCount": 2},
                }
            }
        ],
    }
    values = {
        range_name: [["id", "value"]] + [[str(i), f"v{i}"] for i in range(1, value_row_count + 1)],
    }
    return metadata, values, values


def _special_titles_api_fixture():
    metadata = {
        "spreadsheetId": "sheet-special",
        "properties": {"title": "Special Workbook"},
        "sheets": [
            {"properties": {"sheetId": 404, "title": "Sales Q1", "index": 0, "gridProperties": {"rowCount": 2, "columnCount": 2}}},
            {"properties": {"sheetId": 405, "title": "Owner's View", "index": 1, "gridProperties": {"rowCount": 2, "columnCount": 2}}},
        ],
    }
    display_values = {
        "'Sales Q1'!A1:Z50": [["id", "amount"], ["1", "100"]],
        "'Owner''s View'!A1:Z50": [["owner", "status"], ["Ada", "active"]],
    }
    return metadata, display_values, display_values


def _make_direct_api_connector():
    metadata, display_values, formula_values = _rich_api_fixture()
    display_service = _FakeSheetsService(metadata, display_values)
    formula_service = _FakeSheetsService(metadata, formula_values)

    def fake_builder(service_account_info):
        assert service_account_info["private_key"] == _VALID_PARAMS["service_account_info"]["private_key"]
        return display_service

    from brain_ds.connectors.google_sheets_connector import GoogleSheetsConnector

    params = dict(_VALID_PARAMS)
    params["sheet_range"] = "Budget!A1:Z50"
    params["api_builder"] = fake_builder
    params["formula_api_builder"] = lambda service_account_info: formula_service
    params["use_direct_api"] = True
    return GoogleSheetsConnector(params), display_service, formula_service


# ---------------------------------------------------------------------------
# Helpers — build a fake gspread module
# ---------------------------------------------------------------------------

def _make_fake_gspread(
    spreadsheet_title: str = "My Spreadsheet",
    spreadsheet_url: str = "https://docs.google.com/spreadsheets/d/1AbC",
    worksheet_titles: list[str] | None = None,
    worksheet_rows: list[list] | None = None,
) -> types.ModuleType:
    """Build a minimal gspread stub sufficient for GoogleSheetsConnector tests."""
    if worksheet_titles is None:
        worksheet_titles = ["Sheet1", "Sheet2"]
    if worksheet_rows is None:
        worksheet_rows = [
            ["id", "name", "amount"],  # header row
            ["1", "Alice", "100.00"],
            ["2", "Bob", "200.00"],
        ]

    gspread = types.ModuleType("gspread")

    class FakeWorksheet:
        def __init__(self, title: str, rows: list[list]):
            self.title = title
            self._rows = rows

        def get_all_values(self) -> list[list]:
            return self._rows

        def row_values(self, row_num: int) -> list:
            if row_num <= len(self._rows):
                return self._rows[row_num - 1]
            return []

        def get(self, range_str: str, **kwargs) -> list[list]:
            """Simulate a range read — returns available rows."""
            return self._rows

        # Ensure no write methods are invoked — if they are, the test should fail.
        def update(self, *args, **kwargs):
            raise AssertionError("update() was called — write operations are PROHIBITED")

        def append_row(self, *args, **kwargs):
            raise AssertionError("append_row() was called — write operations are PROHIBITED")

        def clear(self, *args, **kwargs):
            raise AssertionError("clear() was called — write operations are PROHIBITED")

        def delete_rows(self, *args, **kwargs):
            raise AssertionError("delete_rows() was called — write operations are PROHIBITED")

    class FakeSpreadsheet:
        def __init__(self):
            self.title = spreadsheet_title
            self.url = spreadsheet_url
            self._worksheets = [
                FakeWorksheet(t, worksheet_rows) for t in worksheet_titles
            ]

        def worksheets(self):
            # gspread API: worksheets() is a method, not a property.
            return self._worksheets

        def get_worksheet(self, index: int) -> FakeWorksheet:
            return self._worksheets[index]

        def worksheet(self, title: str) -> FakeWorksheet:
            for ws in self._worksheets:
                if ws.title == title:
                    return ws
            raise KeyError(f"Worksheet not found: {title}")

    class FakeGClient:
        def __init__(self):
            self._spreadsheet = FakeSpreadsheet()

        def open_by_key(self, key: str) -> FakeSpreadsheet:
            return self._spreadsheet

    fake_gc = FakeGClient()

    def service_account_from_dict(sa_info, **kwargs):
        return fake_gc

    gspread.service_account_from_dict = service_account_from_dict
    gspread.Client = FakeGClient

    return gspread, fake_gc


_VALID_PARAMS: dict = {
    "service_account_info": {
        "type": "service_account",
        "project_id": "my-project",
        "private_key_id": "key-id",
        "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----\n",
        "client_email": "brain-ds@my-project.iam.gserviceaccount.com",
        "client_id": "123456789",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/...",
        "universe_domain": "googleapis.com",
    },
    "spreadsheet_id": "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
    "sheet_range": "Sheet1!A1:Z100",
}


def _patch_gspread_in_connector(fake_gspread):
    """Patch the lazy gspread loader in GoogleSheetsConnector."""
    return patch(
        "brain_ds.connectors.google_sheets_connector._lazy_gspread",
        return_value=fake_gspread,
    )


def _make_connector(params: dict | None = None, fake_gspread=None, fake_gc=None):
    """Instantiate GoogleSheetsConnector with mocked gspread."""
    if params is None:
        params = _VALID_PARAMS
    if fake_gspread is None:
        fake_gspread, fake_gc = _make_fake_gspread()

    with _patch_gspread_in_connector(fake_gspread):
        from brain_ds.connectors.google_sheets_connector import GoogleSheetsConnector
        return GoogleSheetsConnector(params), fake_gspread, fake_gc


# ===========================================================================
# PR3-T5a: describe() returns title and url
# ===========================================================================

class TestGoogleSheetsConnectorDescribe(unittest.TestCase):

    def test_describe_returns_title(self):
        fake_gspread, fake_gc = _make_fake_gspread(spreadsheet_title="Budget 2024")
        connector, _, _ = _make_connector(fake_gspread=fake_gspread, fake_gc=fake_gc)

        with _patch_gspread_in_connector(fake_gspread):
            result = connector.describe()

        self.assertIn("title", result)
        self.assertEqual(result["title"], "Budget 2024")

    def test_describe_returns_url(self):
        fake_gspread, fake_gc = _make_fake_gspread(
            spreadsheet_url="https://docs.google.com/spreadsheets/d/1XYZ"
        )
        connector, _, _ = _make_connector(fake_gspread=fake_gspread, fake_gc=fake_gc)

        with _patch_gspread_in_connector(fake_gspread):
            result = connector.describe()

        self.assertIn("url", result)
        self.assertEqual(result["url"], "https://docs.google.com/spreadsheets/d/1XYZ")

    def test_describe_includes_kind(self):
        fake_gspread, fake_gc = _make_fake_gspread()
        connector, _, _ = _make_connector(fake_gspread=fake_gspread, fake_gc=fake_gc)

        with _patch_gspread_in_connector(fake_gspread):
            result = connector.describe()

        self.assertIn("kind", result)
        self.assertEqual(result["kind"], "google-sheets")

    def test_describe_excludes_credentials(self):
        """describe() must NOT include service_account_info or private_key."""
        fake_gspread, fake_gc = _make_fake_gspread()
        connector, _, _ = _make_connector(fake_gspread=fake_gspread, fake_gc=fake_gc)

        with _patch_gspread_in_connector(fake_gspread):
            result = connector.describe()

        result_str = str(result)
        self.assertNotIn("private_key", result_str)
        self.assertNotIn("service_account_info", result_str)


# ===========================================================================
# PR3-T5b: list_containers() returns spreadsheet title
# ===========================================================================

class TestGoogleSheetsConnectorListContainers(unittest.TestCase):

    def test_list_containers_returns_list_with_one_entry(self):
        fake_gspread, fake_gc = _make_fake_gspread(spreadsheet_title="ERP Data")
        connector, _, _ = _make_connector(fake_gspread=fake_gspread, fake_gc=fake_gc)

        with _patch_gspread_in_connector(fake_gspread):
            result = connector.list_containers()

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)

    def test_list_containers_value_is_spreadsheet_title(self):
        fake_gspread, fake_gc = _make_fake_gspread(spreadsheet_title="ERP Data")
        connector, _, _ = _make_connector(fake_gspread=fake_gspread, fake_gc=fake_gc)

        with _patch_gspread_in_connector(fake_gspread):
            result = connector.list_containers()

        self.assertEqual(result[0], "ERP Data")


# ===========================================================================
# PR3-T5c: list_tables() returns worksheet tab names
# ===========================================================================

class TestGoogleSheetsConnectorListTables(unittest.TestCase):

    def test_list_tables_returns_worksheet_names(self):
        fake_gspread, fake_gc = _make_fake_gspread(
            worksheet_titles=["Ventas", "Inventario", "Clientes"]
        )
        connector, _, _ = _make_connector(fake_gspread=fake_gspread, fake_gc=fake_gc)

        with _patch_gspread_in_connector(fake_gspread):
            result = connector.list_tables("ERP Data")

        self.assertEqual(result, ["Ventas", "Inventario", "Clientes"])

    def test_list_tables_returns_all_tabs(self):
        fake_gspread, fake_gc = _make_fake_gspread(
            worksheet_titles=["Sheet1", "Sheet2"]
        )
        connector, _, _ = _make_connector(fake_gspread=fake_gspread, fake_gc=fake_gc)

        with _patch_gspread_in_connector(fake_gspread):
            result = connector.list_tables("My Spreadsheet")

        self.assertIn("Sheet1", result)
        self.assertIn("Sheet2", result)
        self.assertEqual(len(result), 2)


# ===========================================================================
# PR3-T5d: get_table_schema() returns header row as columns
# ===========================================================================

class TestGoogleSheetsConnectorGetTableSchema(unittest.TestCase):

    def test_get_table_schema_returns_columns(self):
        fake_gspread, fake_gc = _make_fake_gspread(
            worksheet_rows=[
                ["id", "name", "amount"],
                ["1", "Alice", "100"],
            ]
        )
        connector, _, _ = _make_connector(fake_gspread=fake_gspread, fake_gc=fake_gc)

        with _patch_gspread_in_connector(fake_gspread):
            result = connector.get_table_schema("My Spreadsheet", "Sheet1")

        self.assertIn("columns", result)
        col_names = [c["name"] for c in result["columns"]]
        self.assertIn("id", col_names)
        self.assertIn("name", col_names)
        self.assertIn("amount", col_names)

    def test_get_table_schema_columns_have_required_keys(self):
        """Each column dict has name, type, sample, meaning keys."""
        fake_gspread, fake_gc = _make_fake_gspread(
            worksheet_rows=[
                ["col_a", "col_b"],
                ["val1", "42"],
            ]
        )
        connector, _, _ = _make_connector(fake_gspread=fake_gspread, fake_gc=fake_gc)

        with _patch_gspread_in_connector(fake_gspread):
            result = connector.get_table_schema("My Spreadsheet", "Sheet1")

        for col in result["columns"]:
            self.assertIn("name", col)
            self.assertIn("type", col)
            self.assertIn("sample", col)
            self.assertIn("meaning", col)

    def test_get_table_schema_sample_from_first_data_row(self):
        """sample field comes from first data row (row 2 after header)."""
        fake_gspread, fake_gc = _make_fake_gspread(
            worksheet_rows=[
                ["id"],
                ["42"],
            ]
        )
        connector, _, _ = _make_connector(fake_gspread=fake_gspread, fake_gc=fake_gc)

        with _patch_gspread_in_connector(fake_gspread):
            result = connector.get_table_schema("My Spreadsheet", "Sheet1")

        col = result["columns"][0]
        self.assertEqual(col["sample"], "42")


# ===========================================================================
# PR3-T5e: preview() reads cell range, capped at 50
# ===========================================================================

class TestGoogleSheetsConnectorPreview(unittest.TestCase):

    def test_preview_returns_rows_and_columns(self):
        fake_gspread, fake_gc = _make_fake_gspread(
            worksheet_rows=[
                ["id", "name"],
                ["1", "Alice"],
                ["2", "Bob"],
            ]
        )
        connector, _, _ = _make_connector(fake_gspread=fake_gspread, fake_gc=fake_gc)

        with _patch_gspread_in_connector(fake_gspread):
            result = connector.preview("My Spreadsheet", "Sheet1")

        self.assertIn("rows", result)
        self.assertIn("columns", result)
        self.assertIn("truncated", result)

    def test_preview_columns_from_header_row(self):
        fake_gspread, fake_gc = _make_fake_gspread(
            worksheet_rows=[
                ["product_id", "price"],
                ["SKU-001", "99.99"],
            ]
        )
        connector, _, _ = _make_connector(fake_gspread=fake_gspread, fake_gc=fake_gc)

        with _patch_gspread_in_connector(fake_gspread):
            result = connector.preview("My Spreadsheet", "Sheet1")

        self.assertIn("product_id", result["columns"])
        self.assertIn("price", result["columns"])

    def test_preview_capped_at_50_rows(self):
        """preview() never returns more than 50 data rows."""
        many_rows = [["id"]] + [[str(i)] for i in range(60)]  # header + 60 data rows
        fake_gspread, fake_gc = _make_fake_gspread(worksheet_rows=many_rows)
        connector, _, _ = _make_connector(fake_gspread=fake_gspread, fake_gc=fake_gc)

        with _patch_gspread_in_connector(fake_gspread):
            result = connector.preview("My Spreadsheet", "Sheet1", limit=100)

        self.assertLessEqual(len(result["rows"]), 50)
        self.assertTrue(result["truncated"])

    def test_preview_does_not_call_write_methods(self):
        """preview() must never invoke update/append_row/clear on the worksheet."""
        fake_gspread, fake_gc = _make_fake_gspread()
        connector, _, _ = _make_connector(fake_gspread=fake_gspread, fake_gc=fake_gc)

        # This test would raise AssertionError if any write method is called
        # because FakeWorksheet.update/append_row/clear all raise AssertionError.
        with _patch_gspread_in_connector(fake_gspread):
            result = connector.preview("My Spreadsheet", "Sheet1")

        # If we got here, no write was attempted
        self.assertIn("rows", result)


# ===========================================================================
# PR3-T5f: ReadOnlyConnector ABC compliance
# ===========================================================================

class TestGoogleSheetsConnectorABCCompliance(unittest.TestCase):

    def test_implements_readonly_connector_abc(self):
        fake_gspread, fake_gc = _make_fake_gspread()
        connector, _, _ = _make_connector(fake_gspread=fake_gspread, fake_gc=fake_gc)

        from brain_ds.connectors.base import ReadOnlyConnector
        self.assertIsInstance(connector, ReadOnlyConnector)

    def test_has_describe_method(self):
        fake_gspread, fake_gc = _make_fake_gspread()
        connector, _, _ = _make_connector(fake_gspread=fake_gspread, fake_gc=fake_gc)
        self.assertTrue(callable(getattr(connector, "describe", None)))

    def test_has_list_containers_method(self):
        fake_gspread, fake_gc = _make_fake_gspread()
        connector, _, _ = _make_connector(fake_gspread=fake_gspread, fake_gc=fake_gc)
        self.assertTrue(callable(getattr(connector, "list_containers", None)))

    def test_has_list_tables_method(self):
        fake_gspread, fake_gc = _make_fake_gspread()
        connector, _, _ = _make_connector(fake_gspread=fake_gspread, fake_gc=fake_gc)
        self.assertTrue(callable(getattr(connector, "list_tables", None)))

    def test_has_get_table_schema_method(self):
        fake_gspread, fake_gc = _make_fake_gspread()
        connector, _, _ = _make_connector(fake_gspread=fake_gspread, fake_gc=fake_gc)
        self.assertTrue(callable(getattr(connector, "get_table_schema", None)))

    def test_has_preview_method(self):
        fake_gspread, fake_gc = _make_fake_gspread()
        connector, _, _ = _make_connector(fake_gspread=fake_gspread, fake_gc=fake_gc)
        self.assertTrue(callable(getattr(connector, "preview", None)))


# ===========================================================================
# PR3-T5g: _resolve_connector dispatches aws-google-sheets
# ===========================================================================

class TestResolveConnectorAwsGoogleSheetsDispatch(unittest.TestCase):
    """_resolve_connector with kind='aws-google-sheets' returns a GoogleSheetsConnector."""

    def _make_store_with_secret(self, project_root, handle, kind, metadata):
        from pathlib import Path
        import importlib.resources as resources

        brain_ds_dir = Path(project_root) / ".brain_ds"
        brain_ds_dir.mkdir(parents=True, exist_ok=True)

        schema_text = (
            resources.files("brain_ds.connectors.secrets")
            .joinpath("schema.json")
            .read_text(encoding="utf-8")
        )
        schema = json.loads(schema_text)
        schema_version = schema["schema_version"]

        manifest = {
            "schema_version": schema_version,
            "entries": [
                {
                    "handle": handle,
                    "kind": kind,
                    "metadata": metadata,
                    "created_at": "2024-01-01T00:00:00Z",
                }
            ],
        }
        manifest_path = brain_ds_dir / "secrets.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def test_resolve_connector_dispatches_aws_google_sheets(self):
        """kind='aws-google-sheets' -> GoogleSheetsConnector (adapter monkeypatched)."""
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            tmproot = Path(tmpdir)
            self._make_store_with_secret(
                tmproot,
                handle="test-gsheets-handle",
                kind="aws-google-sheets",
                metadata={
                    "secret_id": "arn:aws:secretsmanager:us-east-2:123:secret:gsheets/sa",
                    "spreadsheet_id": "1AbC",
                    "sheet_range": "Sheet1!A1:Z100",
                    "region": "us-east-2",
                },
            )

            connection = {
                "kind": "aws-google-sheets",
                "secret_handle": "test-gsheets-handle",
                "spreadsheet_id": "1AbC",
                "sheet_range": "Sheet1!A1:Z100",
            }

            fake_params = {
                "service_account_info": {"type": "service_account"},
                "spreadsheet_id": "1AbC",
                "sheet_range": "Sheet1!A1:Z100",
            }

            from brain_ds.connectors.secrets.providers.aws_google_sheets import (
                AwsGoogleSheetsAdapter,
            )

            fake_gspread, _ = _make_fake_gspread()

            with patch.object(AwsGoogleSheetsAdapter, "resolve", return_value=fake_params):
                with _patch_gspread_in_connector(fake_gspread):
                    from brain_ds.mcp.tools import _resolve_connector
                    result = _resolve_connector(connection, tmproot)

            self.assertEqual(type(result).__name__, "GoogleSheetsConnector")

    def test_resolve_connector_aws_google_sheets_missing_handle_raises(self):
        """aws-google-sheets without secret_handle raises an error."""
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            connection = {
                "kind": "aws-google-sheets",
                # missing secret_handle
                "spreadsheet_id": "1AbC",
            }

            from brain_ds.mcp.tools import _resolve_connector
            with self.assertRaises(Exception):
                _resolve_connector(connection, Path(tmpdir))

    def test_resolve_connector_aws_google_sheets_unknown_handle_raises(self):
        """aws-google-sheets with unknown handle raises an error."""
        from pathlib import Path
        import importlib.resources as resources

        with tempfile.TemporaryDirectory() as tmpdir:
            tmproot = Path(tmpdir)
            schema_text = (
                resources.files("brain_ds.connectors.secrets")
                .joinpath("schema.json")
                .read_text(encoding="utf-8")
            )
            schema = json.loads(schema_text)
            brain_ds_dir = tmproot / ".brain_ds"
            brain_ds_dir.mkdir(parents=True, exist_ok=True)
            (brain_ds_dir / "secrets.json").write_text(
                json.dumps({"schema_version": schema["schema_version"], "entries": []}),
                encoding="utf-8",
            )

            connection = {
                "kind": "aws-google-sheets",
                "secret_handle": "nonexistent-handle",
            }

            from brain_ds.mcp.tools import _resolve_connector
            with self.assertRaises(Exception):
                _resolve_connector(connection, tmproot)

    def test_resolve_connector_error_message_lists_aws_google_sheets(self):
        """_get_node_connection error message lists aws-google-sheets as supported kind."""
        from brain_ds.mcp.tools import _get_node_connection
        from brain_ds.mcp.security import ValidationError

        # We can't easily call _get_node_connection without a real store,
        # but we can check the function raises and the message mentions the kind.
        # Use a minimal mock store.
        mock_store = MagicMock()
        mock_store.get_graph.return_value = {"id": "g1"}

        # Patch get_node to return a node with no connection
        from unittest.mock import patch as up
        with up("brain_ds.mcp.tools.get_node.__wrapped__") as mock_get:
            mock_get.return_value = {"id": "n1", "details": {}}  # no connection key
            try:
                _get_node_connection(mock_store, "g1", "n1")
                self.fail("Expected ValidationError")
            except ValidationError as e:
                msg = str(e)
                self.assertIn("aws-google-sheets", msg)

    def test_resolve_connector_sqlite_still_works_after_gsheets_branch(self):
        """sqlite dispatch still works after adding aws-google-sheets branch."""
        import sqlite3
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(str(db_path))
            conn.execute("CREATE TABLE t (id INTEGER)")
            conn.commit()
            conn.close()

            connection = {"kind": "sqlite", "path": str(db_path)}

            from brain_ds.mcp.tools import _resolve_connector
            result = _resolve_connector(connection, Path(tmpdir))

            self.assertEqual(type(result).__name__, "SQLiteConnector")


class TestGoogleSheetsDirectApiProfile(unittest.TestCase):
    def test_parse_google_sheet_url_accepts_gid_from_fragment_and_query(self):
        from brain_ds.connectors.google_sheets_api import parse_google_sheet_url

        fragment = parse_google_sheet_url("https://docs.google.com/spreadsheets/d/sheet-123/edit#gid=456")
        query = parse_google_sheet_url("https://docs.google.com/spreadsheets/d/sheet-abc/view?gid=789")

        self.assertEqual(fragment["spreadsheet_id"], "sheet-123")
        self.assertEqual(fragment["gid"], "456")
        self.assertEqual(query["spreadsheet_id"], "sheet-abc")
        self.assertEqual(query["gid"], "789")

    def test_parse_google_sheet_url_rejects_non_sheet_urls(self):
        from brain_ds.connectors.google_sheets_api import parse_google_sheet_url
        from brain_ds.mcp.security import ValidationError

        with self.assertRaises(ValidationError):
            parse_google_sheet_url("https://docs.google.com/document/d/not-a-sheet/edit")

    def test_sheet_profile_maps_grid_headers_samples_and_formula_cells(self):
        connector, _display_service, formula_service = _make_direct_api_connector()

        profile = connector.sheet_profile("Budget")

        self.assertEqual(profile["spreadsheet_id"], "sheet-123")
        self.assertEqual(profile["title"], "Budget")
        self.assertEqual(profile["gid"], "101")
        self.assertEqual(profile["grid"]["row_count"], 100)
        self.assertEqual(profile["grid"]["frozen_row_count"], 1)
        self.assertEqual(profile["headers"], ["month", "amount", "variance"])
        self.assertEqual(profile["samples"][0], {"month": "Jan", "amount": "100", "variance": "10"})
        self.assertEqual(profile["formulas"], [{"row": 2, "column": "variance", "formula": "=B2-90"}, {"row": 3, "column": "variance", "formula": "=B3-B2"}])
        self.assertEqual(
            formula_service.spreadsheets_resource.values_resource.batch_get_calls[0]["valueRenderOption"],
            "FORMULA",
        )

    def test_sheet_profile_maps_charts_protected_filter_and_metadata(self):
        connector, display_service, _formula_service = _make_direct_api_connector()

        profile = connector.sheet_profile("Budget")

        self.assertEqual(profile["charts"], [{"chart_id": 7, "title": "Spend by Month"}])
        self.assertEqual(profile["protected_ranges"][0]["description"], "Headers")
        self.assertEqual(profile["filter_views"], [{"filter_view_id": 88, "title": "Active budget"}])
        self.assertEqual(profile["developer_metadata"], [{"metadata_id": 9, "key": "owner", "value": "finance"}])
        self.assertIn("sheets.properties", display_service.spreadsheets_resource.get_calls[0]["fields"])
        self.assertIn("sheets.charts", display_service.spreadsheets_resource.get_calls[0]["fields"])

    def test_sheet_profile_records_limitations_for_empty_or_unsupported_surfaces(self):
        connector, _display_service, _formula_service = _make_direct_api_connector()

        profile = connector.sheet_profile("Empty")
        self.assertIn("No values returned for range Empty!A1:Z50", profile["limitations"])
        self.assertIn("Apps Script metadata is unavailable from the Sheets API profile", profile["limitations"])

    def test_direct_api_preserves_readonly_methods_without_secret_leakage(self):
        connector, _display_service, _formula_service = _make_direct_api_connector()

        self.assertEqual(connector.list_containers(), ["Finance Workbook"])
        self.assertEqual(connector.list_tables("Finance Workbook"), ["Budget", "Empty"])
        self.assertEqual(connector.get_table_schema("Finance Workbook", "Budget")["columns"][1]["sample"], "100")
        self.assertEqual(connector.preview("Finance Workbook", "Budget", limit=1)["rows"], [{"month": "Jan", "amount": "100", "variance": "10"}])
        self.assertNotIn("private_key", str(connector.describe()))
        self.assertNotIn(_VALID_PARAMS["service_account_info"]["private_key"], str(connector.sheet_profile("Budget")))

    def test_direct_api_quotes_special_sheet_titles_in_a1_ranges(self):
        from brain_ds.connectors.google_sheets_connector import GoogleSheetsConnector

        metadata, display_values, formula_values = _special_titles_api_fixture()
        display_service = _FakeSheetsService(metadata, display_values)
        formula_service = _FakeSheetsService(metadata, formula_values)
        params = dict(_VALID_PARAMS)
        params.pop("sheet_range")
        params.update(
            {
                "spreadsheet_id": "sheet-special",
                "sheet_range": "A1:Z50",
                "api_builder": lambda _info: display_service,
                "formula_api_builder": lambda _info: formula_service,
                "use_direct_api": True,
            }
        )

        connector = GoogleSheetsConnector(params)
        self.assertEqual(connector.preview("Special Workbook", "Sales Q1", limit=1)["rows"], [{"id": "1", "amount": "100"}])
        self.assertEqual(connector.preview("Special Workbook", "Owner's View", limit=1)["rows"], [{"owner": "Ada", "status": "active"}])
        ranges = display_service.spreadsheets_resource.values_resource.batch_get_calls[0]["ranges"]
        self.assertIn("'Sales Q1'!A1:Z50", ranges)
        self.assertIn("'Owner''s View'!A1:Z50", ranges)

    def test_direct_api_default_profile_range_includes_header_plus_50_data_rows(self):
        from brain_ds.connectors.google_sheets_connector import GoogleSheetsConnector

        metadata, display_values, formula_values = _many_rows_api_fixture(
            row_count=60,
            range_name="'Large Data'!A1:Z51",
            value_row_count=50,
        )
        display_service = _FakeSheetsService(metadata, display_values)
        formula_service = _FakeSheetsService(metadata, formula_values)
        params = dict(_VALID_PARAMS)
        params.pop("sheet_range")
        params.update(
            {
                "spreadsheet_id": "sheet-many",
                "api_builder": lambda _info: display_service,
                "formula_api_builder": lambda _info: formula_service,
                "use_direct_api": True,
            }
        )

        connector = GoogleSheetsConnector(params)
        preview = connector.preview("Large Workbook", "Large Data", limit=50)

        self.assertEqual(len(preview["rows"]), 50)
        self.assertEqual(preview["rows"][0], {"id": "1", "value": "v1"})
        self.assertEqual(preview["rows"][49], {"id": "50", "value": "v50"})
        self.assertTrue(preview["truncated"])
        ranges = display_service.spreadsheets_resource.values_resource.batch_get_calls[0]["ranges"]
        self.assertEqual(ranges, ["'Large Data'!A1:Z51"])

    def test_connector_accepts_legacy_service_account_json_params(self):
        from brain_ds.connectors.google_sheets_connector import GoogleSheetsConnector

        fake_gspread, _fake_gc = _make_fake_gspread()
        params = {
            "service_account_json": json.dumps(_VALID_PARAMS["service_account_info"]),
            "spreadsheet_id": "1AbC",
            "sheet_range": "Sheet1!A1:Z100",
        }

        with _patch_gspread_in_connector(fake_gspread):
            connector = GoogleSheetsConnector(params)

        self.assertEqual(connector.list_tables("My Spreadsheet"), ["Sheet1", "Sheet2"])

    def test_resolve_connector_preserves_legacy_google_sheets_json_env_ref(self):
        from pathlib import Path

        from brain_ds.connectors.secrets.catalog import SecretCatalog, SecretEntry

        with tempfile.TemporaryDirectory() as tmpdir:
            tmproot = Path(tmpdir)
            catalog = SecretCatalog(tmproot)
            catalog.add(
                SecretEntry(
                    handle="legacy-google-handle",
                    kind="google-sheets-json",
                    metadata={
                        "spreadsheet_id": "sheet-legacy",
                        "sheet_range": "Sheet1!A1:Z50",
                        "service_account_ref": "LEGACY_GOOGLE_SHEETS_JSON",
                    },
                    created_at="2024-01-01T00:00:00Z",
                )
            )

            fake_gspread, _fake_gc = _make_fake_gspread()
            from brain_ds.mcp.tools import _resolve_connector

            with patch.dict(
                "os.environ",
                {"LEGACY_GOOGLE_SHEETS_JSON": json.dumps(_VALID_PARAMS["service_account_info"])},
                clear=False,
            ):
                with _patch_gspread_in_connector(fake_gspread):
                    connector = _resolve_connector(
                        {"kind": "google-sheets-json", "secret_handle": "legacy-google-handle"},
                        tmproot,
                    )

            self.assertEqual(type(connector).__name__, "GoogleSheetsConnector")
            self.assertEqual(connector.list_tables("My Spreadsheet"), ["Sheet1", "Sheet2"])

    def test_resolve_connector_dispatches_google_sheets_json_with_raw_secret(self):
        from pathlib import Path

        from brain_ds.connectors.secrets.catalog import SecretCatalog, SecretEntry
        from brain_ds.connectors.secrets.providers.google_sheets import GoogleSheetsJsonAdapter

        with tempfile.TemporaryDirectory() as tmpdir:
            tmproot = Path(tmpdir)
            catalog = SecretCatalog(tmproot)
            catalog.add(
                SecretEntry(
                    handle="google-handle",
                    kind="google-sheets-json",
                    metadata={
                        "spreadsheet_id": "sheet-123",
                        "sheet_range": "Budget!A1:Z50",
                        "credential_type": "service_account",
                        "project_id": "my-project",
                    },
                    created_at="2024-01-01T00:00:00Z",
                ),
                raw_value=json.dumps(_VALID_PARAMS["service_account_info"]),
            )

            from brain_ds.mcp.tools import _resolve_connector

            metadata, display_values, _formula_values = _rich_api_fixture()
            service = _FakeSheetsService(metadata, display_values)
            with patch.object(GoogleSheetsJsonAdapter, "resolve", return_value={"service_account_info": _VALID_PARAMS["service_account_info"], "spreadsheet_id": "sheet-123", "sheet_range": "Budget!A1:Z50", "api_builder": lambda _info: service, "use_direct_api": True}):
                result = _resolve_connector({"kind": "google-sheets-json", "secret_handle": "google-handle"}, tmproot)

            self.assertEqual(type(result).__name__, "GoogleSheetsConnector")
            self.assertEqual(result.list_tables("Finance Workbook"), ["Budget", "Empty"])
