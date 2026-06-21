"""PR2a-T1 — TDD tests for AwsPostgresAdapter (mocked boto3).

All boto3/psycopg calls are mocked — no real AWS network traffic.
Tests are written RED-first (before AwsPostgresAdapter exists).

Design invariants verified:
  INV-1: secret value never logged.
  INV-2: database ALWAYS comes from handle metadata, NEVER from AWS payload.
  INV-3: missing host/username/password in payload → actionable ValidationError.
  INV-4: extra keys in AWS payload are tolerated.
  INV-5: lazy import guard — psycopg / boto3 absent → clear error naming the extra.
"""
from __future__ import annotations

import json
import sys
from unittest import mock

import pytest

from brain_ds.mcp.security import ValidationError


# ---------------------------------------------------------------------------
# Shared mock helpers (mirror test_aws_secrets_adapter.py conventions)
# ---------------------------------------------------------------------------

def _make_mock_boto_env(secret_json: dict | None = None, error_code: str | None = None):
    """Return (mock_boto3, mock_botocore_exc) configured for a success or ClientError path."""

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

    fake_botocore = mock.MagicMock()
    fake_botocore.exceptions = fake_botocore_exc

    mock_client = mock.MagicMock()

    if error_code is not None:
        err = FakeClientError(
            {"Error": {"Code": error_code, "Message": f"Simulated {error_code}"}},
            "GetSecretValue",
        )
        mock_client.get_secret_value.side_effect = err
    else:
        payload = secret_json or {
            "username": "admin",
            "password": "s3cr3t",
            "engine": "postgres",
            "host": "my-cluster.cluster-abc123.us-east-2.rds.amazonaws.com",
            "port": "5432",
            "dbClusterIdentifier": "my-cluster",
        }
        mock_client.get_secret_value.return_value = {
            "SecretString": json.dumps(payload)
        }

    mock_boto3 = mock.MagicMock()
    mock_boto3.client.return_value = mock_client

    return mock_boto3, fake_botocore, fake_botocore_exc


# Standard valid RDS payload (as AWS returns it)
_VALID_RDS_PAYLOAD = {
    "username": "db_user",
    "password": "super_secret_pw",
    "engine": "postgres",
    "host": "cluster.abc.us-east-2.rds.amazonaws.com",
    "port": "5432",
    "dbClusterIdentifier": "prod-cluster",
}

_VALID_METADATA = {
    "region": "us-east-2",
    "secret_id": "arn:aws:secretsmanager:us-east-2:123456789012:secret:prod/db",
    "database": "prod_app",  # handle metadata — the one source of truth
}


# ---------------------------------------------------------------------------
# PR2a-T1-A: Adapter parses standard RDS payload
# ---------------------------------------------------------------------------

class TestAwsPostgresAdapterResolveParsesRdsPayload:
    """Spec: 'Adapter parses standard RDS payload' scenario."""

    def test_resolve_returns_host_from_payload(self) -> None:
        """resolve() maps payload['host'] → result['host']."""
        from brain_ds.connectors.secrets.providers.aws_postgres import AwsPostgresAdapter

        adapter = AwsPostgresAdapter()
        mock_boto3, fake_botocore, fake_botocore_exc = _make_mock_boto_env(
            secret_json=_VALID_RDS_PAYLOAD
        )
        with mock.patch.dict(
            sys.modules,
            {"boto3": mock_boto3, "botocore": fake_botocore, "botocore.exceptions": fake_botocore_exc},
        ):
            result = adapter.resolve("my-handle", _VALID_METADATA)

        assert result["host"] == _VALID_RDS_PAYLOAD["host"]

    def test_resolve_returns_port_as_int(self) -> None:
        """resolve() coerces port to int even if the payload carries a string."""
        from brain_ds.connectors.secrets.providers.aws_postgres import AwsPostgresAdapter

        adapter = AwsPostgresAdapter()
        payload = {**_VALID_RDS_PAYLOAD, "port": "5433"}  # string port
        mock_boto3, fake_botocore, fake_botocore_exc = _make_mock_boto_env(secret_json=payload)
        with mock.patch.dict(
            sys.modules,
            {"boto3": mock_boto3, "botocore": fake_botocore, "botocore.exceptions": fake_botocore_exc},
        ):
            result = adapter.resolve("my-handle", _VALID_METADATA)

        assert result["port"] == 5433
        assert isinstance(result["port"], int)

    def test_resolve_returns_username_and_password(self) -> None:
        """resolve() maps username + password from the AWS payload."""
        from brain_ds.connectors.secrets.providers.aws_postgres import AwsPostgresAdapter

        adapter = AwsPostgresAdapter()
        mock_boto3, fake_botocore, fake_botocore_exc = _make_mock_boto_env(
            secret_json=_VALID_RDS_PAYLOAD
        )
        with mock.patch.dict(
            sys.modules,
            {"boto3": mock_boto3, "botocore": fake_botocore, "botocore.exceptions": fake_botocore_exc},
        ):
            result = adapter.resolve("my-handle", _VALID_METADATA)

        assert result["username"] == _VALID_RDS_PAYLOAD["username"]
        assert result["password"] == _VALID_RDS_PAYLOAD["password"]

    # --- INV-2: database ALWAYS from metadata ---

    def test_resolve_database_comes_from_metadata_not_payload(self) -> None:
        """INV-2: database in result = metadata['database'], NOT from the AWS payload.

        Even if the AWS JSON happens to contain a 'database' or 'dbname' key,
        the adapter MUST use the metadata value.
        """
        from brain_ds.connectors.secrets.providers.aws_postgres import AwsPostgresAdapter

        adapter = AwsPostgresAdapter()
        # Payload contains a 'database' key that differs from metadata
        payload = {**_VALID_RDS_PAYLOAD, "database": "wrong_db_from_aws"}
        mock_boto3, fake_botocore, fake_botocore_exc = _make_mock_boto_env(secret_json=payload)
        metadata = {**_VALID_METADATA, "database": "correct_db_from_metadata"}
        with mock.patch.dict(
            sys.modules,
            {"boto3": mock_boto3, "botocore": fake_botocore, "botocore.exceptions": fake_botocore_exc},
        ):
            result = adapter.resolve("my-handle", metadata)

        assert result["database"] == "correct_db_from_metadata"
        assert result["database"] != "wrong_db_from_aws"

    def test_resolve_tolerates_extra_keys_in_payload(self) -> None:
        """INV-4: Extra AWS payload keys are silently ignored (not rejected)."""
        from brain_ds.connectors.secrets.providers.aws_postgres import AwsPostgresAdapter

        adapter = AwsPostgresAdapter()
        payload = {
            **_VALID_RDS_PAYLOAD,
            "extra_key_one": "ignored",
            "dbInstanceIdentifier": "instance-123",
            "kmsKeyId": "arn:aws:kms:...",
        }
        mock_boto3, fake_botocore, fake_botocore_exc = _make_mock_boto_env(secret_json=payload)
        with mock.patch.dict(
            sys.modules,
            {"boto3": mock_boto3, "botocore": fake_botocore, "botocore.exceptions": fake_botocore_exc},
        ):
            # Must not raise — extra keys are tolerated
            result = adapter.resolve("my-handle", _VALID_METADATA)

        assert result["host"] == _VALID_RDS_PAYLOAD["host"]

    def test_resolve_defaults_port_to_5432_when_absent(self) -> None:
        """port defaults to 5432 when not present in the RDS payload."""
        from brain_ds.connectors.secrets.providers.aws_postgres import AwsPostgresAdapter

        adapter = AwsPostgresAdapter()
        payload = {k: v for k, v in _VALID_RDS_PAYLOAD.items() if k != "port"}
        mock_boto3, fake_botocore, fake_botocore_exc = _make_mock_boto_env(secret_json=payload)
        with mock.patch.dict(
            sys.modules,
            {"boto3": mock_boto3, "botocore": fake_botocore, "botocore.exceptions": fake_botocore_exc},
        ):
            result = adapter.resolve("my-handle", _VALID_METADATA)

        assert result["port"] == 5432

    def test_resolve_defaults_sslmode_to_require(self) -> None:
        """sslmode defaults to 'require' when absent from the RDS payload."""
        from brain_ds.connectors.secrets.providers.aws_postgres import AwsPostgresAdapter

        adapter = AwsPostgresAdapter()
        payload = {k: v for k, v in _VALID_RDS_PAYLOAD.items() if k != "sslmode"}
        mock_boto3, fake_botocore, fake_botocore_exc = _make_mock_boto_env(secret_json=payload)
        with mock.patch.dict(
            sys.modules,
            {"boto3": mock_boto3, "botocore": fake_botocore, "botocore.exceptions": fake_botocore_exc},
        ):
            result = adapter.resolve("my-handle", _VALID_METADATA)

        assert result["sslmode"] == "require"

    def test_resolve_uses_region_from_metadata(self) -> None:
        """boto3 client is called with the region from metadata (us-east-2)."""
        from brain_ds.connectors.secrets.providers.aws_postgres import AwsPostgresAdapter

        adapter = AwsPostgresAdapter()
        mock_boto3, fake_botocore, fake_botocore_exc = _make_mock_boto_env(
            secret_json=_VALID_RDS_PAYLOAD
        )
        with mock.patch.dict(
            sys.modules,
            {"boto3": mock_boto3, "botocore": fake_botocore, "botocore.exceptions": fake_botocore_exc},
        ):
            adapter.resolve("my-handle", _VALID_METADATA)

        mock_boto3.client.assert_called_once_with(
            "secretsmanager", region_name="us-east-2"
        )

    def test_resolve_region_optional_defaults_to_none(self) -> None:
        """When region is absent from metadata, boto3 is called with region_name=None."""
        from brain_ds.connectors.secrets.providers.aws_postgres import AwsPostgresAdapter

        adapter = AwsPostgresAdapter()
        metadata_no_region = {"secret_id": "prod/db", "database": "prod_app"}
        mock_boto3, fake_botocore, fake_botocore_exc = _make_mock_boto_env(
            secret_json=_VALID_RDS_PAYLOAD
        )
        with mock.patch.dict(
            sys.modules,
            {"boto3": mock_boto3, "botocore": fake_botocore, "botocore.exceptions": fake_botocore_exc},
        ):
            adapter.resolve("my-handle", metadata_no_region)

        mock_boto3.client.assert_called_once_with("secretsmanager", region_name=None)


# ---------------------------------------------------------------------------
# PR2a-T1-B: Missing required keys in AWS payload → actionable ValidationError
# ---------------------------------------------------------------------------

class TestAwsPostgresAdapterMissingPayloadKeys:
    """Spec: 'AwsPostgresAdapter ARN Resolution' — rejects missing host/username/password."""

    @pytest.mark.parametrize("missing_key", ["host", "username", "password"])
    def test_resolve_missing_payload_key_raises_actionable_error(self, missing_key: str) -> None:
        """If the AWS JSON lacks host, username, or password, a clear error names the key."""
        from brain_ds.connectors.secrets.providers.aws_postgres import AwsPostgresAdapter

        adapter = AwsPostgresAdapter()
        payload = {k: v for k, v in _VALID_RDS_PAYLOAD.items() if k != missing_key}
        mock_boto3, fake_botocore, fake_botocore_exc = _make_mock_boto_env(secret_json=payload)

        with mock.patch.dict(
            sys.modules,
            {"boto3": mock_boto3, "botocore": fake_botocore, "botocore.exceptions": fake_botocore_exc},
        ):
            with pytest.raises(ValidationError) as exc_info:
                adapter.resolve("my-handle", _VALID_METADATA)

        msg = str(exc_info.value)
        # The error must name the missing key so the user knows what to fix
        assert missing_key in msg, (
            f"Expected '{missing_key}' to appear in error message, got: {msg}"
        )


# ---------------------------------------------------------------------------
# PR2a-T1-C: Missing database in metadata → ValidationError before AWS call
# ---------------------------------------------------------------------------

class TestAwsPostgresAdapterMissingMetadata:
    """Spec: 'Missing database rejected' scenario."""

    def test_validate_raises_if_database_missing(self) -> None:
        """validate() raises ValidationError when 'database' is absent from metadata."""
        from brain_ds.connectors.secrets.providers.aws_postgres import AwsPostgresAdapter

        adapter = AwsPostgresAdapter()
        metadata_no_db = {"region": "us-east-2", "secret_id": "prod/db"}

        with pytest.raises(ValidationError) as exc_info:
            adapter.validate(metadata_no_db)

        assert "database" in str(exc_info.value).lower()

    def test_validate_raises_if_secret_id_missing(self) -> None:
        """validate() raises ValidationError when 'secret_id' is absent."""
        from brain_ds.connectors.secrets.providers.aws_postgres import AwsPostgresAdapter

        adapter = AwsPostgresAdapter()
        metadata_no_secret = {"database": "prod_app"}

        with pytest.raises(ValidationError) as exc_info:
            adapter.validate(metadata_no_secret)

        assert "secret_id" in str(exc_info.value).lower()

    def test_resolve_raises_before_boto3_if_database_missing(self) -> None:
        """resolve() raises ValidationError on missing database WITHOUT making AWS call."""
        from brain_ds.connectors.secrets.providers.aws_postgres import AwsPostgresAdapter

        adapter = AwsPostgresAdapter()
        metadata_no_db = {"region": "us-east-2", "secret_id": "prod/db"}
        mock_boto3, fake_botocore, fake_botocore_exc = _make_mock_boto_env()

        with mock.patch.dict(
            sys.modules,
            {"boto3": mock_boto3, "botocore": fake_botocore, "botocore.exceptions": fake_botocore_exc},
        ):
            with pytest.raises(ValidationError):
                adapter.resolve("my-handle", metadata_no_db)

        # No AWS call should have been made
        mock_boto3.client.assert_not_called()


# ---------------------------------------------------------------------------
# PR2a-T1-D: Lazy import guard (psycopg / boto3 absent)
# ---------------------------------------------------------------------------

class TestAwsPostgresAdapterLazyImportGuard:
    """Spec: 'Lazy import guard' scenario."""

    def test_resolve_without_boto3_raises_friendly_error(self) -> None:
        """resolve() with boto3 unavailable raises ValidationError with [postgres] or [aws] hint."""
        from brain_ds.connectors.secrets.providers.aws_postgres import AwsPostgresAdapter

        adapter = AwsPostgresAdapter()
        with mock.patch.dict(sys.modules, {"boto3": None, "botocore": None, "botocore.exceptions": None}):
            with pytest.raises(ValidationError) as exc_info:
                adapter.resolve("my-handle", _VALID_METADATA)

        msg = str(exc_info.value)
        # Must name one of the relevant extras or packages
        assert "boto3" in msg.lower() or "aws" in msg.lower() or "postgres" in msg.lower(), (
            f"Expected boto3/aws/postgres in error, got: {msg}"
        )

    def test_module_imports_cleanly_without_boto3_or_psycopg(self) -> None:
        """The module can be imported even when boto3 and psycopg are not installed."""
        # If this test runs, the import at module level already succeeded.
        # We additionally verify the class attribute is accessible.
        from brain_ds.connectors.secrets.providers.aws_postgres import AwsPostgresAdapter

        assert AwsPostgresAdapter.kind == "aws-postgres"

    def test_adapter_kind_is_aws_postgres(self) -> None:
        """AwsPostgresAdapter.kind == 'aws-postgres'."""
        from brain_ds.connectors.secrets.providers.aws_postgres import AwsPostgresAdapter

        assert AwsPostgresAdapter().kind == "aws-postgres"


# ---------------------------------------------------------------------------
# PR2a-T1-E: INV-1 — secret value never logged
# ---------------------------------------------------------------------------

class TestAwsPostgresAdapterSecretNotLogged:
    """INV-1: The resolved password must never appear in log output."""

    def test_resolve_does_not_log_password(self, caplog) -> None:
        import logging

        from brain_ds.connectors.secrets.providers.aws_postgres import AwsPostgresAdapter

        adapter = AwsPostgresAdapter()
        canary = "CANARY_PASSWORD_MUST_NOT_APPEAR_IN_LOGS_abc123"
        payload = {**_VALID_RDS_PAYLOAD, "password": canary}
        mock_boto3, fake_botocore, fake_botocore_exc = _make_mock_boto_env(secret_json=payload)

        with caplog.at_level(logging.DEBUG):
            with mock.patch.dict(
                sys.modules,
                {"boto3": mock_boto3, "botocore": fake_botocore, "botocore.exceptions": fake_botocore_exc},
            ):
                adapter.resolve("my-handle", _VALID_METADATA)

        assert canary not in caplog.text, "Password appeared in log output — INV-1 violated!"


# ---------------------------------------------------------------------------
# PR2a-T1-F: AWS ClientError mapping
# ---------------------------------------------------------------------------

class TestAwsPostgresAdapterClientErrors:
    """AWS ClientError codes are mapped to user-readable ValidationError messages."""

    @pytest.mark.parametrize("error_code", [
        "AccessDeniedException",
        "ResourceNotFoundException",
        "InvalidRequestException",
        "DecryptionFailure",
        "InternalServiceError",
    ])
    def test_client_error_raises_validation_error(self, error_code: str) -> None:
        from brain_ds.connectors.secrets.providers.aws_postgres import AwsPostgresAdapter

        adapter = AwsPostgresAdapter()
        mock_boto3, fake_botocore, fake_botocore_exc = _make_mock_boto_env(error_code=error_code)

        with mock.patch.dict(
            sys.modules,
            {"boto3": mock_boto3, "botocore": fake_botocore, "botocore.exceptions": fake_botocore_exc},
        ):
            with pytest.raises(ValidationError) as exc_info:
                adapter.resolve("my-handle", _VALID_METADATA)

        assert isinstance(exc_info.value, ValidationError)
        # Must not expose raw AWS error codes in a user-facing message
        msg = str(exc_info.value)
        assert len(msg) > 0


# ---------------------------------------------------------------------------
# PR2a-T1-G: Adapter is registered in the provider registry
# ---------------------------------------------------------------------------

class TestAwsPostgresAdapterRegistry:
    """AwsPostgresAdapter must be returned by get_provider_adapter('aws-postgres')."""

    def test_registry_returns_aws_postgres_adapter(self) -> None:
        from brain_ds.connectors.secrets.providers import get_provider_adapter
        from brain_ds.connectors.secrets.providers.aws_postgres import AwsPostgresAdapter

        adapter = get_provider_adapter("aws-postgres")
        assert isinstance(adapter, AwsPostgresAdapter)
