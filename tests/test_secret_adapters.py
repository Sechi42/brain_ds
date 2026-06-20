"""Phase 2 TDD tests for secret provider adapters."""
from __future__ import annotations

import os
from unittest import mock

import pytest

from brain_ds.connectors.secrets.providers import (
    AwsSecretsAdapter,
    GoogleSheetsJsonAdapter,
    IamCredentialAdapter,
    IamRoleAdapter,
    MockGoogleSheetsJsonAdapter,
    MockPostgresAdapter,
    PostgresAdapter,
    SqlServerAdapter,
    SqliteAdapter,
    get_provider_adapter,
)
from brain_ds.mcp.security import ValidationError


class TestPostgresAdapter:
    """WS-CAT-03 / 2.2: Postgres metadata validation and env-var resolution."""

    def test_validate_rejects_missing_fields(self) -> None:
        adapter = PostgresAdapter()
        metadata = {
            "host": "db.local",
            "database": "warehouse",
            "username": "etl",
        }

        with pytest.raises(ValidationError) as excinfo:
            adapter.validate(metadata)

        message = str(excinfo.value)
        assert "port" in message
        assert "sslmode" in message

    def test_validate_accepts_complete_metadata(self) -> None:
        adapter = PostgresAdapter()
        adapter.validate(_complete_pg_metadata())

    def test_resolve_returns_env_credentials(self) -> None:
        adapter = PostgresAdapter()
        metadata = _complete_pg_metadata(secret_ref="BRAINDS_PG_PWD")

        with mock.patch.dict(os.environ, {"BRAINDS_PG_PWD": "super-secret-pg"}, clear=False):
            result = adapter.resolve("warehouse_ro", metadata)

        assert result["host"] == "db.local"
        assert result["port"] == 5432
        assert result["database"] == "warehouse"
        assert result["username"] == "etl"
        assert result["password"] == "super-secret-pg"
        assert result["sslmode"] == "require"

    def test_resolve_requires_secret_ref(self) -> None:
        adapter = PostgresAdapter()
        metadata = _complete_pg_metadata()
        del metadata["secret_ref"]

        with pytest.raises(ValidationError):
            adapter.resolve("warehouse_ro", metadata)


class TestSqlServerAdapter:
    """2.2: SQL Server adapter follows the same shape as Postgres."""

    def test_validate_rejects_missing_sslmode(self) -> None:
        adapter = SqlServerAdapter()
        metadata = {
            "host": "mssql.local",
            "port": 1433,
            "database": "warehouse",
            "username": "etl",
        }

        with pytest.raises(ValidationError) as excinfo:
            adapter.validate(metadata)

        assert "sslmode" in str(excinfo.value)

    def test_resolve_returns_env_credentials(self) -> None:
        adapter = SqlServerAdapter()
        metadata = _complete_pg_metadata(secret_ref="BRAINDS_MSSQL_PWD", port=1433)

        with mock.patch.dict(os.environ, {"BRAINDS_MSSQL_PWD": "mssql-secret"}, clear=False):
            result = adapter.resolve("mssql_ro", metadata)

        assert result["password"] == "mssql-secret"
        assert result["port"] == 1433


class TestAwsSecretsAdapter:
    """2.3: AWS Secrets Manager adapter validates secret_id; region is optional.

    PR2 (A2): boto3 is now used for live resolution; region is OPTIONAL per A2-R3.
    Legacy env-var resolution removed.  See tests/test_aws_secrets_adapter.py for
    full error-mapping coverage.
    """

    def test_validate_rejects_missing_secret_id(self) -> None:
        adapter = AwsSecretsAdapter()
        with pytest.raises(ValidationError) as excinfo:
            adapter.validate({"region": "us-east-1"})  # secret_id missing

        assert "secret_id" in str(excinfo.value)

    def test_validate_accepts_complete_metadata(self) -> None:
        adapter = AwsSecretsAdapter()
        adapter.validate({"region": "us-east-1", "secret_id": "prod/db/password"})

    def test_validate_accepts_metadata_without_region(self) -> None:
        """region is optional (A2-R3); validate must succeed without it."""
        adapter = AwsSecretsAdapter()
        adapter.validate({"secret_id": "prod/db/password"})  # no region — OK

    def test_resolve_requires_boto3_when_not_installed(self) -> None:
        """resolve() raises a friendly ValidationError when boto3 is absent (A2-R4)."""
        import sys
        adapter = AwsSecretsAdapter()
        metadata = {"region": "us-east-1", "secret_id": "prod/db/password"}

        with mock.patch.dict(sys.modules, {"boto3": None}):
            with pytest.raises(ValidationError) as excinfo:
                adapter.resolve("aws_db", metadata)

        assert "boto3" in str(excinfo.value).lower()


class TestGoogleSheetsAdapter:
    """2.4: Google Sheets JSON credential adapter."""

    def test_validate_rejects_missing_range(self) -> None:
        adapter = GoogleSheetsJsonAdapter()
        with pytest.raises(ValidationError) as excinfo:
            adapter.validate(
                {"spreadsheet_id": "abc123", "service_account_ref": "BRAINDS_GSA"}
            )

        assert "sheet_range" in str(excinfo.value)

    def test_resolve_returns_service_account_json(self) -> None:
        adapter = GoogleSheetsJsonAdapter()
        metadata = {
            "spreadsheet_id": "abc123",
            "sheet_range": "A1:C10",
            "service_account_ref": "BRAINDS_GSA",
        }
        service_account = '{"client_email":"x@example.com","private_key":"-----BEGIN PRIVATE KEY-----"}'

        with mock.patch.dict(
            os.environ, {"BRAINDS_GSA": service_account}, clear=False
        ):
            result = adapter.resolve("sales_q3", metadata)

        assert result["spreadsheet_id"] == "abc123"
        assert result["sheet_range"] == "A1:C10"
        assert "private_key" in result["service_account_json"]


class TestMockPostgresAdapter:
    """TEST-SEC-01: fixture adapter for deterministic E2E probes."""

    def test_validate_rejects_missing_fields(self) -> None:
        adapter = MockPostgresAdapter()
        with pytest.raises(ValidationError) as excinfo:
            adapter.validate({"host": "127.0.0.1"})
        assert "port" in str(excinfo.value)

    def test_resolve_returns_redacted_descriptor(self) -> None:
        adapter = MockPostgresAdapter()
        metadata = _complete_pg_metadata(secret_ref=None)
        result = adapter.resolve("mock_wh", metadata)
        assert result["host"] == "db.local"
        assert "password" not in result

    def test_probe_is_a_safe_no_op(self) -> None:
        adapter = MockPostgresAdapter()
        metadata = _complete_pg_metadata(secret_ref=None)
        adapter.probe("mock_wh", metadata)


class TestMockGoogleSheetsAdapter:
    """TEST-SEC-01: fixture adapter for deterministic E2E probes."""

    def test_probe_is_a_safe_no_op(self) -> None:
        adapter = MockGoogleSheetsJsonAdapter()
        metadata = {
            "spreadsheet_id": "abc123",
            "sheet_range": "A1:C10",
            "service_account_ref": "BRAINDS_GSA_MOCK",
        }
        adapter.probe("mock_gs", metadata)


class TestSqliteAdapter:
    """SQLite adapter validates path metadata."""

    def test_validate_rejects_missing_path(self) -> None:
        adapter = SqliteAdapter()
        with pytest.raises(ValidationError) as excinfo:
            adapter.validate({})
        assert "path" in str(excinfo.value)

    def test_validate_accepts_path(self) -> None:
        adapter = SqliteAdapter()
        adapter.validate({"path": "/tmp/warehouse.sqlite"})

    def test_resolve_returns_path(self) -> None:
        adapter = SqliteAdapter()
        result = adapter.resolve("local_db", {"path": "/tmp/warehouse.sqlite"})
        assert result["path"] == "/tmp/warehouse.sqlite"


class TestIamRoleAdapter:
    """IAM role adapter validates role_arn."""

    def test_validate_rejects_missing_role_arn(self) -> None:
        adapter = IamRoleAdapter()
        with pytest.raises(ValidationError) as excinfo:
            adapter.validate({})
        assert "role_arn" in str(excinfo.value)

    def test_validate_rejects_malformed_role_arn(self) -> None:
        adapter = IamRoleAdapter()
        with pytest.raises(ValidationError) as excinfo:
            adapter.validate({"role_arn": "not-an-arn"})
        assert "arn:" in str(excinfo.value)

    def test_probe_requires_env_var(self) -> None:
        adapter = IamRoleAdapter()
        with pytest.raises(ValidationError):
            adapter.probe("iam_role", {"role_arn": "arn:aws:iam::123:role/Admin"})


class TestIamCredentialAdapter:
    """IAM credential adapter validates access_key_id + session_token_ref."""

    def test_validate_rejects_missing_fields(self) -> None:
        adapter = IamCredentialAdapter()
        with pytest.raises(ValidationError) as excinfo:
            adapter.validate({"access_key_id": "AKIA"})
        assert "session_token_ref" in str(excinfo.value)

    def test_probe_requires_env_vars(self) -> None:
        adapter = IamCredentialAdapter()
        with pytest.raises(ValidationError):
            adapter.probe(
                "iam_creds",
                {"access_key_id": "AKIA", "session_token_ref": "BRAINDS_TOKEN"},
            )


class TestProviderRegistry:
    """Adapter registry resolves kind to implementation."""

    def test_get_provider_adapter_returns_postgres(self) -> None:
        assert isinstance(get_provider_adapter("postgres"), PostgresAdapter)

    def test_get_provider_adapter_returns_sqlserver(self) -> None:
        assert isinstance(get_provider_adapter("sqlserver"), SqlServerAdapter)

    def test_get_provider_adapter_returns_aws(self) -> None:
        assert isinstance(get_provider_adapter("aws-secrets"), AwsSecretsAdapter)

    def test_get_provider_adapter_returns_google(self) -> None:
        assert isinstance(get_provider_adapter("google-sheets-json"), GoogleSheetsJsonAdapter)

    def test_get_provider_adapter_returns_sqlite(self) -> None:
        assert isinstance(get_provider_adapter("sqlite"), SqliteAdapter)

    def test_get_provider_adapter_returns_iam_role(self) -> None:
        assert isinstance(get_provider_adapter("iam-role"), IamRoleAdapter)

    def test_get_provider_adapter_returns_iam_credential(self) -> None:
        assert isinstance(get_provider_adapter("iam-credential"), IamCredentialAdapter)

    def test_get_provider_adapter_returns_mock_postgres(self) -> None:
        assert isinstance(get_provider_adapter("mock-postgres"), MockPostgresAdapter)

    def test_get_provider_adapter_returns_mock_google(self) -> None:
        assert isinstance(get_provider_adapter("mock-google-sheets-json"), MockGoogleSheetsJsonAdapter)

    def test_get_provider_adapter_rejects_unknown_kind(self) -> None:
        with pytest.raises(ValidationError):
            get_provider_adapter("unknown-provider")


def _complete_pg_metadata(secret_ref: str | None = "BRAINDS_WH_PWD", port: int = 5432) -> dict:
    metadata: dict = {
        "host": "db.local",
        "port": port,
        "database": "warehouse",
        "username": "etl",
        "sslmode": "require",
    }
    if secret_ref is not None:
        metadata["secret_ref"] = secret_ref
    return metadata
