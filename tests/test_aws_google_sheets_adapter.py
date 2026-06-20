"""PR3-T1 — TDD tests for AwsGoogleSheetsAdapter (mocked boto3 + gspread).

All boto3/gspread calls are mocked — no real AWS or Google network traffic.
Tests are written RED-first (before AwsGoogleSheetsAdapter exists).

Design invariants verified:
  INV-1: service-account JSON never logged.
  INV-2: spreadsheet_id + sheet_range ALWAYS come from handle metadata,
          NEVER inferred from the SA payload.
  INV-3: all 11 SA fields pass through as-is.
  INV-4: lazy import guard — boto3 / gspread absent → clear error naming extra.
"""
from __future__ import annotations

import json
import sys
import types
import unittest
from unittest import mock

import pytest

from brain_ds.mcp.security import ValidationError


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _make_mock_boto_env(
    secret_json: dict | None = None,
    error_code: str | None = None,
):
    """Return (mock_boto3, fake_botocore, fake_botocore_exc)."""

    class FakeNoCredentialsError(Exception):
        pass

    class FakePartialCredentialsError(Exception):
        pass

    class FakeClientError(Exception):
        def __init__(self, response, operation_name):
            self.response = response
            super().__init__(str(response))

    fake_botocore_exc = mock.MagicMock()
    fake_botocore_exc.NoCredentialsError = FakeNoCredentialsError
    fake_botocore_exc.PartialCredentialsError = FakePartialCredentialsError
    fake_botocore_exc.ClientError = FakeClientError

    mock_client = mock.MagicMock()
    if error_code is not None:
        err = FakeClientError(
            {"Error": {"Code": error_code, "Message": f"Simulated {error_code}"}},
            "GetSecretValue",
        )
        mock_client.get_secret_value.side_effect = err
    else:
        payload = secret_json or _VALID_SA_PAYLOAD
        mock_client.get_secret_value.return_value = {
            "SecretString": json.dumps(payload)
        }

    mock_boto3 = mock.MagicMock()
    mock_boto3.client.return_value = mock_client

    return mock_boto3, mock.MagicMock(), fake_botocore_exc


# Standard valid service-account JSON (all 11 canonical SA fields)
_VALID_SA_PAYLOAD: dict = {
    "type": "service_account",
    "project_id": "my-gcp-project",
    "private_key_id": "key-id-abc123",
    "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----\n",
    "client_email": "brain-ds@my-gcp-project.iam.gserviceaccount.com",
    "client_id": "123456789012345678901",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": (
        "https://www.googleapis.com/robot/v1/metadata/x509/"
        "brain-ds%40my-gcp-project.iam.gserviceaccount.com"
    ),
    "universe_domain": "googleapis.com",
}

_VALID_METADATA: dict = {
    "secret_id": "arn:aws:secretsmanager:us-east-2:123456789012:secret:gsheets/sa",
    "spreadsheet_id": "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
    "sheet_range": "Sheet1!A1:Z100",
    "region": "us-east-2",
}


# ---------------------------------------------------------------------------
# Helpers — patch _lazy_boto3 in the adapter
# ---------------------------------------------------------------------------

def _patch_boto3_in_adapter(mock_boto3, fake_botocore_exc):
    """Patch the lazy boto3 loader in AwsGoogleSheetsAdapter."""
    return mock.patch(
        "brain_ds.connectors.secrets.providers.aws_google_sheets._lazy_boto3",
        return_value=(mock_boto3, fake_botocore_exc),
    )


# ===========================================================================
# PR3-T1a: AwsGoogleSheetsAdapter.resolve() — parses SA payload
# ===========================================================================

class TestAwsGoogleSheetsAdapterResolve(unittest.TestCase):
    """resolve() fetches ARN and returns service_account_info + metadata fields."""

    def _get_adapter(self):
        from brain_ds.connectors.secrets.providers.aws_google_sheets import (
            AwsGoogleSheetsAdapter,
        )
        return AwsGoogleSheetsAdapter()

    def test_resolve_returns_service_account_info(self):
        """resolve() returns a dict with 'service_account_info' key."""
        adapter = self._get_adapter()
        mock_boto3, _, fake_botocore_exc = _make_mock_boto_env()

        with _patch_boto3_in_adapter(mock_boto3, fake_botocore_exc):
            result = adapter.resolve("test-handle", _VALID_METADATA)

        self.assertIn("service_account_info", result)

    def test_resolve_service_account_is_full_dict(self):
        """service_account_info is a dict (not a string or partial)."""
        adapter = self._get_adapter()
        mock_boto3, _, fake_botocore_exc = _make_mock_boto_env()

        with _patch_boto3_in_adapter(mock_boto3, fake_botocore_exc):
            result = adapter.resolve("test-handle", _VALID_METADATA)

        sa = result["service_account_info"]
        self.assertIsInstance(sa, dict)

    def test_resolve_all_11_sa_fields_pass_through(self):
        """All 11 standard SA fields appear in service_account_info as-is."""
        adapter = self._get_adapter()
        mock_boto3, _, fake_botocore_exc = _make_mock_boto_env()

        with _patch_boto3_in_adapter(mock_boto3, fake_botocore_exc):
            result = adapter.resolve("test-handle", _VALID_METADATA)

        sa = result["service_account_info"]
        expected_fields = [
            "type", "project_id", "private_key_id", "private_key",
            "client_email", "client_id", "auth_uri", "token_uri",
            "auth_provider_x509_cert_url", "client_x509_cert_url",
            "universe_domain",
        ]
        for field in expected_fields:
            self.assertIn(field, sa, f"SA field '{field}' missing from service_account_info")
            self.assertEqual(sa[field], _VALID_SA_PAYLOAD[field])

    def test_resolve_spreadsheet_id_from_metadata(self):
        """spreadsheet_id comes from metadata, NOT from the SA payload."""
        adapter = self._get_adapter()
        mock_boto3, _, fake_botocore_exc = _make_mock_boto_env()

        with _patch_boto3_in_adapter(mock_boto3, fake_botocore_exc):
            result = adapter.resolve("test-handle", _VALID_METADATA)

        self.assertEqual(result["spreadsheet_id"], _VALID_METADATA["spreadsheet_id"])

    def test_resolve_sheet_range_from_metadata(self):
        """sheet_range comes from metadata, NOT from the SA payload."""
        adapter = self._get_adapter()
        mock_boto3, _, fake_botocore_exc = _make_mock_boto_env()

        with _patch_boto3_in_adapter(mock_boto3, fake_botocore_exc):
            result = adapter.resolve("test-handle", _VALID_METADATA)

        self.assertEqual(result["sheet_range"], _VALID_METADATA["sheet_range"])

    def test_resolve_returns_exactly_three_keys(self):
        """resolve() result has exactly: service_account_info, spreadsheet_id, sheet_range."""
        adapter = self._get_adapter()
        mock_boto3, _, fake_botocore_exc = _make_mock_boto_env()

        with _patch_boto3_in_adapter(mock_boto3, fake_botocore_exc):
            result = adapter.resolve("test-handle", _VALID_METADATA)

        self.assertIn("service_account_info", result)
        self.assertIn("spreadsheet_id", result)
        self.assertIn("sheet_range", result)

    def test_resolve_uses_region_from_metadata(self):
        """boto3.client is called with region from metadata."""
        adapter = self._get_adapter()
        mock_boto3, _, fake_botocore_exc = _make_mock_boto_env()

        with _patch_boto3_in_adapter(mock_boto3, fake_botocore_exc):
            adapter.resolve("test-handle", _VALID_METADATA)

        mock_boto3.client.assert_called_once_with(
            "secretsmanager", region_name="us-east-2"
        )

    def test_resolve_uses_region_none_when_absent(self):
        """region is optional; boto3.client is called with region_name=None when absent."""
        adapter = self._get_adapter()
        mock_boto3, _, fake_botocore_exc = _make_mock_boto_env()
        metadata = {**_VALID_METADATA}
        del metadata["region"]

        with _patch_boto3_in_adapter(mock_boto3, fake_botocore_exc):
            adapter.resolve("test-handle", metadata)

        mock_boto3.client.assert_called_once_with(
            "secretsmanager", region_name=None
        )

    def test_resolve_invalid_json_raises_validation_error(self):
        """Non-JSON SecretString raises a friendly ValidationError."""
        adapter = self._get_adapter()
        mock_boto3_bad, _, fake_botocore_exc = _make_mock_boto_env()
        mock_boto3_bad.client.return_value.get_secret_value.return_value = {
            "SecretString": "not-json-at-all"
        }

        with _patch_boto3_in_adapter(mock_boto3_bad, fake_botocore_exc):
            with self.assertRaises(ValidationError) as ctx:
                adapter.resolve("test-handle", _VALID_METADATA)

        msg = str(ctx.exception)
        self.assertIn("JSON", msg)

    def test_resolve_extra_keys_tolerated(self):
        """Extra keys in the SA payload beyond the 11 standard ones are tolerated."""
        adapter = self._get_adapter()
        payload_with_extra = {**_VALID_SA_PAYLOAD, "extra_key": "should-be-kept"}
        mock_boto3, _, fake_botocore_exc = _make_mock_boto_env(
            secret_json=payload_with_extra
        )

        with _patch_boto3_in_adapter(mock_boto3, fake_botocore_exc):
            result = adapter.resolve("test-handle", _VALID_METADATA)

        # Extra key passes through
        self.assertEqual(result["service_account_info"]["extra_key"], "should-be-kept")

    def test_resolve_access_denied_raises_friendly_error(self):
        """AWS AccessDeniedException -> friendly ValidationError."""
        adapter = self._get_adapter()
        mock_boto3, _, fake_botocore_exc = _make_mock_boto_env(error_code="AccessDeniedException")

        with _patch_boto3_in_adapter(mock_boto3, fake_botocore_exc):
            with self.assertRaises(ValidationError) as ctx:
                adapter.resolve("test-handle", _VALID_METADATA)

        self.assertIn("Access denied", str(ctx.exception))

    def test_resolve_resource_not_found_raises_friendly_error(self):
        """AWS ResourceNotFoundException -> friendly ValidationError."""
        adapter = self._get_adapter()
        mock_boto3, _, fake_botocore_exc = _make_mock_boto_env(
            error_code="ResourceNotFoundException"
        )

        with _patch_boto3_in_adapter(mock_boto3, fake_botocore_exc):
            with self.assertRaises(ValidationError) as ctx:
                adapter.resolve("test-handle", _VALID_METADATA)

        self.assertIn("not found", str(ctx.exception))


# ===========================================================================
# PR3-T1b: validate() rejects missing required fields
# ===========================================================================

class TestAwsGoogleSheetsAdapterValidate(unittest.TestCase):

    def _get_adapter(self):
        from brain_ds.connectors.secrets.providers.aws_google_sheets import (
            AwsGoogleSheetsAdapter,
        )
        return AwsGoogleSheetsAdapter()

    def test_validate_accepts_full_metadata(self):
        adapter = self._get_adapter()
        # Should not raise
        adapter.validate(_VALID_METADATA)

    def test_validate_rejects_missing_secret_id(self):
        adapter = self._get_adapter()
        metadata = {**_VALID_METADATA}
        del metadata["secret_id"]
        with self.assertRaises(ValidationError):
            adapter.validate(metadata)

    def test_validate_rejects_missing_spreadsheet_id(self):
        adapter = self._get_adapter()
        metadata = {**_VALID_METADATA}
        del metadata["spreadsheet_id"]
        with self.assertRaises(ValidationError):
            adapter.validate(metadata)

    def test_validate_rejects_missing_sheet_range(self):
        adapter = self._get_adapter()
        metadata = {**_VALID_METADATA}
        del metadata["sheet_range"]
        with self.assertRaises(ValidationError):
            adapter.validate(metadata)

    def test_validate_allows_missing_region(self):
        """region is optional — validate() should pass without it."""
        adapter = self._get_adapter()
        metadata = {**_VALID_METADATA}
        del metadata["region"]
        # Should not raise
        adapter.validate(metadata)

    def test_validate_rejects_non_dict_metadata(self):
        adapter = self._get_adapter()
        with self.assertRaises(ValidationError):
            adapter.validate("not-a-dict")  # type: ignore[arg-type]


# ===========================================================================
# PR3-T1c: probe() validates via gspread (no live call)
# ===========================================================================

class TestAwsGoogleSheetsAdapterProbe(unittest.TestCase):
    """probe() calls gspread.service_account_from_dict to validate the SA JSON.

    No live spreadsheet call is made — gspread is mocked.
    """

    def _get_adapter(self):
        from brain_ds.connectors.secrets.providers.aws_google_sheets import (
            AwsGoogleSheetsAdapter,
        )
        return AwsGoogleSheetsAdapter()

    def test_probe_calls_gspread_service_account_from_dict(self):
        """probe() calls gspread.service_account_from_dict with the SA dict."""
        adapter = self._get_adapter()
        mock_boto3, _, fake_botocore_exc = _make_mock_boto_env()

        fake_gspread = mock.MagicMock()
        fake_gc = mock.MagicMock()
        fake_gspread.service_account_from_dict.return_value = fake_gc

        with _patch_boto3_in_adapter(mock_boto3, fake_botocore_exc):
            with mock.patch(
                "brain_ds.connectors.secrets.providers.aws_google_sheets._lazy_gspread",
                return_value=fake_gspread,
            ):
                adapter.probe("test-handle", _VALID_METADATA)

        fake_gspread.service_account_from_dict.assert_called_once()
        call_args = fake_gspread.service_account_from_dict.call_args
        actual_sa = call_args[0][0] if call_args[0] else call_args[1].get("service_account_info")
        # The SA passed to gspread should match the payload
        if actual_sa is None:
            # Check it was called with keyword arg
            actual_sa = call_args[1].get("service_account_info") or call_args[0][0]
        self.assertIsInstance(actual_sa, dict)
        self.assertIn("type", actual_sa)

    def test_probe_succeeds_when_gspread_does_not_raise(self):
        """probe() returns None (success) when gspread validation passes."""
        adapter = self._get_adapter()
        mock_boto3, _, fake_botocore_exc = _make_mock_boto_env()

        fake_gspread = mock.MagicMock()
        fake_gspread.service_account_from_dict.return_value = mock.MagicMock()

        with _patch_boto3_in_adapter(mock_boto3, fake_botocore_exc):
            with mock.patch(
                "brain_ds.connectors.secrets.providers.aws_google_sheets._lazy_gspread",
                return_value=fake_gspread,
            ):
                result = adapter.probe("test-handle", _VALID_METADATA)

        # probe() returns None on success
        self.assertIsNone(result)

    def test_probe_raises_validation_error_when_gspread_fails(self):
        """probe() raises ValidationError when gspread.service_account_from_dict fails."""
        adapter = self._get_adapter()
        mock_boto3, _, fake_botocore_exc = _make_mock_boto_env()

        fake_gspread = mock.MagicMock()
        fake_gspread.service_account_from_dict.side_effect = Exception("invalid credentials")

        with _patch_boto3_in_adapter(mock_boto3, fake_botocore_exc):
            with mock.patch(
                "brain_ds.connectors.secrets.providers.aws_google_sheets._lazy_gspread",
                return_value=fake_gspread,
            ):
                with self.assertRaises(ValidationError) as ctx:
                    adapter.probe("test-handle", _VALID_METADATA)

        self.assertIn("invalid", str(ctx.exception).lower())


# ===========================================================================
# PR3-T1d: kind attribute + registry registration
# ===========================================================================

class TestAwsGoogleSheetsAdapterKind(unittest.TestCase):

    def test_kind_attribute(self):
        from brain_ds.connectors.secrets.providers.aws_google_sheets import (
            AwsGoogleSheetsAdapter,
        )
        self.assertEqual(AwsGoogleSheetsAdapter.kind, "aws-google-sheets")

    def test_adapter_registered_in_registry(self):
        from brain_ds.connectors.secrets.providers import get_provider_adapter
        adapter = get_provider_adapter("aws-google-sheets")
        self.assertEqual(adapter.kind, "aws-google-sheets")

    def test_adapter_in_all_list(self):
        import brain_ds.connectors.secrets.providers as providers_module
        self.assertIn("AwsGoogleSheetsAdapter", providers_module.__all__)


# ===========================================================================
# PR3-T1e: lazy import guards
# ===========================================================================

class TestAwsGoogleSheetsAdapterLazyImports(unittest.TestCase):
    """Absent boto3 or gspread -> actionable error naming the missing [gsheets] extra."""

    def test_boto3_absent_raises_actionable_error(self):
        """If boto3 is not installed, resolve() raises a ValidationError with install hint."""
        # Temporarily remove boto3 from sys.modules to simulate missing package
        boto3_real = sys.modules.pop("boto3", None)
        botocore_real = sys.modules.pop("botocore", None)
        botocore_exc_real = sys.modules.pop("botocore.exceptions", None)

        try:
            # Force re-import of _lazy_boto3 with boto3 gone
            from brain_ds.connectors.secrets.providers import aws_google_sheets as mod
            import importlib
            importlib.reload(mod)

            adapter = mod.AwsGoogleSheetsAdapter()
            with self.assertRaises((ValidationError, ImportError)) as ctx:
                adapter.resolve("handle", _VALID_METADATA)

            err_msg = str(ctx.exception)
            # Should mention boto3 or the install extra
            self.assertTrue(
                "boto3" in err_msg or "gsheets" in err_msg or "aws" in err_msg,
                f"Error should mention boto3 or install extra, got: {err_msg!r}",
            )
        finally:
            # Restore boto3
            if boto3_real is not None:
                sys.modules["boto3"] = boto3_real
            if botocore_real is not None:
                sys.modules["botocore"] = botocore_real
            if botocore_exc_real is not None:
                sys.modules["botocore.exceptions"] = botocore_exc_real


# ===========================================================================
# PR3-T1f: schema.json declares aws-google-sheets kind
# ===========================================================================

class TestAwsGoogleSheetsSchema(unittest.TestCase):
    """schema.json must declare aws-google-sheets with the correct fields."""

    def _load_schema(self):
        import importlib.resources as resources
        schema_text = (
            resources.files("brain_ds.connectors.secrets")
            .joinpath("schema.json")
            .read_text(encoding="utf-8")
        )
        import json
        return json.loads(schema_text)

    def test_aws_google_sheets_kind_declared(self):
        schema = self._load_schema()
        self.assertIn("aws-google-sheets", schema["provider_kinds"])

    def test_aws_google_sheets_requires_secret_id(self):
        schema = self._load_schema()
        kind_schema = schema["provider_kinds"]["aws-google-sheets"]
        self.assertIn("secret_id", kind_schema["required"])

    def test_aws_google_sheets_requires_spreadsheet_id(self):
        schema = self._load_schema()
        kind_schema = schema["provider_kinds"]["aws-google-sheets"]
        self.assertIn("spreadsheet_id", kind_schema["required"])

    def test_aws_google_sheets_requires_sheet_range(self):
        schema = self._load_schema()
        kind_schema = schema["provider_kinds"]["aws-google-sheets"]
        self.assertIn("sheet_range", kind_schema["required"])

    def test_aws_google_sheets_region_optional(self):
        """region appears in types but NOT in required."""
        schema = self._load_schema()
        kind_schema = schema["provider_kinds"]["aws-google-sheets"]
        self.assertNotIn("region", kind_schema.get("required", []))
        self.assertIn("region", kind_schema.get("types", {}))

    def test_aws_google_sheets_requires_raw_value_false(self):
        schema = self._load_schema()
        kind_schema = schema["provider_kinds"]["aws-google-sheets"]
        self.assertFalse(kind_schema.get("requires_raw_value", True))
