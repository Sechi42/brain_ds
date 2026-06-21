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

import sys
import types
import unittest
from unittest.mock import MagicMock, patch, call

import pytest


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
        import json
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
        import tempfile
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
        import tempfile
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
        import tempfile, json
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
        import tempfile
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
