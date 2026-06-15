"""Phase 2 TDD tests for secret provider adapters."""
from __future__ import annotations

import os
from unittest import mock

import pytest

from brain_ds.connectors.secrets.providers import (
    AwsSecretsAdapter,
    GoogleSheetsJsonAdapter,
    PostgresAdapter,
    SqlServerAdapter,
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
    """2.3: AWS Secrets Manager adapter validates region/secret_id."""

    def test_validate_rejects_missing_region(self) -> None:
        adapter = AwsSecretsAdapter()
        with pytest.raises(ValidationError) as excinfo:
            adapter.validate({"secret_id": "prod/db/password"})

        assert "region" in str(excinfo.value)

    def test_validate_accepts_complete_metadata(self) -> None:
        adapter = AwsSecretsAdapter()
        adapter.validate({"region": "us-east-1", "secret_id": "prod/db/password"})

    def test_resolve_returns_env_value(self) -> None:
        adapter = AwsSecretsAdapter()
        metadata = {"region": "us-east-1", "secret_id": "prod/db/password", "secret_ref": "BRAINDS_AWS_SECRET"}

        with mock.patch.dict(os.environ, {"BRAINDS_AWS_SECRET": "aws-secret-value"}, clear=False):
            result = adapter.resolve("aws_db", metadata)

        assert result["region"] == "us-east-1"
        assert result["secret_id"] == "prod/db/password"
        assert result["secret_value"] == "aws-secret-value"


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
