"""T2.2 — TDD tests for boto3 error mapping in the aws_secrets adapter.

These tests are RED until T2.4 is implemented.
All boto3 calls are mocked — no real AWS network traffic.
"""
from __future__ import annotations

import sys
from unittest import mock

import pytest

from brain_ds.mcp.security import ValidationError


# ---------------------------------------------------------------------------
# Helpers: build a fake botocore ClientError
# ---------------------------------------------------------------------------

def _make_client_error(code: str, message: str = "error"):
    """Return a botocore.exceptions.ClientError-compatible exception."""
    # Import botocore only if available; tests mock boto3 so botocore may not
    # be installed either.  We construct the exception shape manually so tests
    # run in environments without boto3/botocore.
    try:
        import botocore.exceptions  # noqa: F401
        from botocore.exceptions import ClientError
        return ClientError({"Error": {"Code": code, "Message": message}}, "GetSecretValue")
    except ImportError:
        # Construct a stand-in with the same .response attribute shape
        exc = Exception(f"ClientError: {code} {message}")
        exc.response = {"Error": {"Code": code, "Message": message}}  # type: ignore[attr-defined]
        return exc


class TestAwsAdapterBoto3Missing:
    """A2-R4 / A2-S4: ImportError → friendly 'install brain_ds[aws]' message."""

    def test_resolve_without_boto3_raises_friendly_error(self) -> None:
        """resolve() with boto3 unavailable raises ValidationError with install hint."""
        from brain_ds.connectors.secrets.providers.aws_secrets import AwsSecretsAdapter

        adapter = AwsSecretsAdapter()
        metadata = {"region": "us-east-1", "secret_id": "prod/db"}

        # Simulate boto3 not installed by blocking the import
        with mock.patch.dict(sys.modules, {"boto3": None}):
            with pytest.raises(ValidationError) as exc_info:
                adapter.resolve("aws_handle", metadata)

        msg = str(exc_info.value).lower()
        assert "boto3" in msg, f"Expected 'boto3' in error, got: {exc_info.value}"
        assert "brain_ds[aws]" in str(exc_info.value) or "aws" in msg

    def test_probe_without_boto3_raises_friendly_error(self) -> None:
        """probe() with boto3 unavailable raises ValidationError with install hint."""
        from brain_ds.connectors.secrets.providers.aws_secrets import AwsSecretsAdapter

        adapter = AwsSecretsAdapter()
        metadata = {"region": "us-east-1", "secret_id": "prod/db"}

        with mock.patch.dict(sys.modules, {"boto3": None}):
            with pytest.raises(ValidationError) as exc_info:
                adapter.probe("aws_handle", metadata)

        assert "boto3" in str(exc_info.value).lower()


class TestAwsAdapterNoCredentials:
    """A2-R6 / A2-S5: NoCredentialsError → friendly 'no local AWS credentials' message."""

    def _make_no_creds_env(self):
        """Build mock boto3 + botocore env that raises NoCredentialsError."""
        # Define proper exception subclasses so isinstance checks work
        class FakeNoCredentialsError(Exception):
            pass

        class FakePartialCredentialsError(Exception):
            pass

        class FakeClientError(Exception):
            def __init__(self, response, operation_name):
                self.response = response
                super().__init__(str(response))

        mock_client = mock.MagicMock()
        mock_client.get_secret_value.side_effect = FakeNoCredentialsError("No credentials")

        mock_boto3 = mock.MagicMock()
        mock_boto3.client.return_value = mock_client

        fake_botocore_exc = mock.MagicMock()
        fake_botocore_exc.NoCredentialsError = FakeNoCredentialsError
        fake_botocore_exc.PartialCredentialsError = FakePartialCredentialsError
        fake_botocore_exc.ClientError = FakeClientError

        fake_botocore = mock.MagicMock()
        fake_botocore.exceptions = fake_botocore_exc

        return mock_boto3, fake_botocore, fake_botocore_exc

    def test_resolve_no_credentials_raises_friendly_error(self) -> None:
        from brain_ds.connectors.secrets.providers.aws_secrets import AwsSecretsAdapter

        adapter = AwsSecretsAdapter()
        metadata = {"region": "us-east-1", "secret_id": "prod/db"}
        mock_boto3, fake_botocore, fake_botocore_exc = self._make_no_creds_env()

        with mock.patch.dict(sys.modules, {"boto3": mock_boto3, "botocore": fake_botocore, "botocore.exceptions": fake_botocore_exc}):
            with pytest.raises(ValidationError) as exc_info:
                adapter.resolve("aws_handle", metadata)

        msg = str(exc_info.value).lower()
        assert "credential" in msg or "aws" in msg, f"Expected credentials message, got: {exc_info.value}"

    def test_probe_no_credentials_raises_friendly_error(self) -> None:
        from brain_ds.connectors.secrets.providers.aws_secrets import AwsSecretsAdapter

        adapter = AwsSecretsAdapter()
        metadata = {"region": "us-east-1", "secret_id": "prod/db"}
        mock_boto3, fake_botocore, fake_botocore_exc = self._make_no_creds_env()

        with mock.patch.dict(sys.modules, {"boto3": mock_boto3, "botocore": fake_botocore, "botocore.exceptions": fake_botocore_exc}):
            with pytest.raises(ValidationError) as exc_info:
                adapter.probe("aws_handle", metadata)

        assert "credential" in str(exc_info.value).lower() or "aws" in str(exc_info.value).lower()


class TestAwsAdapterClientError:
    """A2-R5 / A2-S6: ClientError (AccessDenied/ResourceNotFound) → user-readable, no 500, no secret leak."""

    def _make_mock_env(self, error_code: str):
        """Set up mock boto3 + botocore env that raises a ClientError."""
        # Build a real-ish ClientError class
        class FakeClientError(Exception):
            def __init__(self, response, operation_name):
                self.response = response
                super().__init__(str(response))

        err = FakeClientError(
            {"Error": {"Code": error_code, "Message": f"Simulated {error_code}"}},
            "GetSecretValue",
        )

        mock_client = mock.MagicMock()
        mock_client.get_secret_value.side_effect = err

        mock_boto3 = mock.MagicMock()
        mock_boto3.client.return_value = mock_client

        fake_botocore = mock.MagicMock()
        fake_botocore.exceptions.NoCredentialsError = type("NoCredentialsError", (Exception,), {})
        fake_botocore.exceptions.PartialCredentialsError = type("PartialCredentialsError", (Exception,), {})
        fake_botocore.exceptions.ClientError = FakeClientError

        return mock_boto3, fake_botocore

    def test_resolve_access_denied_raises_friendly_error(self) -> None:
        from brain_ds.connectors.secrets.providers.aws_secrets import AwsSecretsAdapter

        adapter = AwsSecretsAdapter()
        metadata = {"region": "us-east-1", "secret_id": "prod/db"}
        mock_boto3, fake_botocore = self._make_mock_env("AccessDeniedException")

        with mock.patch.dict(sys.modules, {"boto3": mock_boto3, "botocore": fake_botocore, "botocore.exceptions": fake_botocore.exceptions}):
            with pytest.raises(ValidationError) as exc_info:
                adapter.resolve("aws_handle", metadata)

        msg = str(exc_info.value)
        # Must be user-readable, not a raw AWS response blob
        assert "AccessDeniedException" not in msg or "access" in msg.lower(), (
            f"Error message too raw: {msg}"
        )
        # Must be a ValidationError (mapped to 422/400), NOT a re-raised ClientError
        assert isinstance(exc_info.value, ValidationError)

    def test_resolve_resource_not_found_raises_friendly_error(self) -> None:
        from brain_ds.connectors.secrets.providers.aws_secrets import AwsSecretsAdapter

        adapter = AwsSecretsAdapter()
        metadata = {"region": "us-east-1", "secret_id": "bad/arn"}
        mock_boto3, fake_botocore = self._make_mock_env("ResourceNotFoundException")

        with mock.patch.dict(sys.modules, {"boto3": mock_boto3, "botocore": fake_botocore, "botocore.exceptions": fake_botocore.exceptions}):
            with pytest.raises(ValidationError) as exc_info:
                adapter.resolve("aws_handle", metadata)

        assert isinstance(exc_info.value, ValidationError)

    def test_probe_client_error_raises_friendly_error(self) -> None:
        from brain_ds.connectors.secrets.providers.aws_secrets import AwsSecretsAdapter

        adapter = AwsSecretsAdapter()
        metadata = {"region": "us-east-1", "secret_id": "prod/db"}
        mock_boto3, fake_botocore = self._make_mock_env("AccessDeniedException")

        with mock.patch.dict(sys.modules, {"boto3": mock_boto3, "botocore": fake_botocore, "botocore.exceptions": fake_botocore.exceptions}):
            with pytest.raises(ValidationError):
                adapter.probe("aws_handle", metadata)


class TestAwsAdapterRegionOptional:
    """A2-R3 / A2-S8: absent region → boto3 called with region_name=None (uses chain default)."""

    def test_resolve_without_region_calls_boto3_with_none_region(self) -> None:
        from brain_ds.connectors.secrets.providers.aws_secrets import AwsSecretsAdapter

        adapter = AwsSecretsAdapter()
        # No region in metadata
        metadata = {"secret_id": "prod/db/password"}

        mock_client = mock.MagicMock()
        mock_client.get_secret_value.return_value = {"SecretString": "supersecret"}

        mock_boto3 = mock.MagicMock()
        mock_boto3.client.return_value = mock_client

        fake_botocore = mock.MagicMock()
        fake_botocore.exceptions.NoCredentialsError = type("NoCredentialsError", (Exception,), {})
        fake_botocore.exceptions.PartialCredentialsError = type("PartialCredentialsError", (Exception,), {})
        fake_botocore.exceptions.ClientError = type("ClientError", (Exception,), {
            "__init__": lambda self, r, op: (setattr(self, "response", r), None)[1]
        })

        with mock.patch.dict(sys.modules, {"boto3": mock_boto3, "botocore": fake_botocore, "botocore.exceptions": fake_botocore.exceptions}):
            result = adapter.resolve("aws_handle", metadata)

        # boto3.client called with region_name=None (lets boto3 use default chain)
        mock_boto3.client.assert_called_once_with("secretsmanager", region_name=None)
        # Secret value returned in-memory
        assert result["secret_value"] == "supersecret"

    def test_resolve_success_does_not_log_secret_value(
        self, tmp_path, caplog
    ) -> None:
        """The resolved secret value must NOT appear in any log line."""
        import logging
        from brain_ds.connectors.secrets.providers.aws_secrets import AwsSecretsAdapter

        adapter = AwsSecretsAdapter()
        metadata = {"region": "us-east-1", "secret_id": "prod/db"}
        secret_canary = "MY_SUPER_SECRET_CANARY_VALUE_12345"

        mock_client = mock.MagicMock()
        mock_client.get_secret_value.return_value = {"SecretString": secret_canary}

        mock_boto3 = mock.MagicMock()
        mock_boto3.client.return_value = mock_client

        fake_botocore = mock.MagicMock()
        fake_botocore.exceptions.NoCredentialsError = type("NoCredentialsError", (Exception,), {})
        fake_botocore.exceptions.PartialCredentialsError = type("PartialCredentialsError", (Exception,), {})
        fake_botocore.exceptions.ClientError = type("ClientError", (Exception,), {
            "__init__": lambda self, r, op: (setattr(self, "response", r), None)[1]
        })

        with caplog.at_level(logging.DEBUG):
            with mock.patch.dict(sys.modules, {"boto3": mock_boto3, "botocore": fake_botocore, "botocore.exceptions": fake_botocore.exceptions}):
                adapter.resolve("aws_handle", metadata)

        assert secret_canary not in caplog.text, (
            "Secret value appeared in log output — INV-1 violated!"
        )


class TestAwsAdapterSuccessPath:
    """A2-R1/R2/R9: successful resolve returns secret in-memory; no persistence."""

    def test_resolve_returns_secret_value_from_aws(self) -> None:
        from brain_ds.connectors.secrets.providers.aws_secrets import AwsSecretsAdapter

        adapter = AwsSecretsAdapter()
        metadata = {"region": "eu-west-1", "secret_id": "staging/db"}

        mock_client = mock.MagicMock()
        mock_client.get_secret_value.return_value = {"SecretString": "db-password-xyz"}

        mock_boto3 = mock.MagicMock()
        mock_boto3.client.return_value = mock_client

        fake_botocore = mock.MagicMock()
        fake_botocore.exceptions.NoCredentialsError = type("NoCredentialsError", (Exception,), {})
        fake_botocore.exceptions.PartialCredentialsError = type("PartialCredentialsError", (Exception,), {})
        fake_botocore.exceptions.ClientError = type("ClientError", (Exception,), {
            "__init__": lambda self, r, op: (setattr(self, "response", r), None)[1]
        })

        with mock.patch.dict(sys.modules, {"boto3": mock_boto3, "botocore": fake_botocore, "botocore.exceptions": fake_botocore.exceptions}):
            result = adapter.resolve("aws_handle", metadata)

        mock_boto3.client.assert_called_once_with("secretsmanager", region_name="eu-west-1")
        mock_client.get_secret_value.assert_called_once_with(SecretId="staging/db")
        assert result["secret_value"] == "db-password-xyz"
        # Region and secret_id present in result for caller context
        assert result["region"] == "eu-west-1"
        assert result["secret_id"] == "staging/db"
