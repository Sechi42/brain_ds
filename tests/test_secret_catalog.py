"""Phase 1 TDD tests for the workspace secret catalog foundation."""
from __future__ import annotations

import json
import stat
import sys
from pathlib import Path
from typing import cast

import pytest

from brain_ds.connectors.secrets import SecretCatalog, SecretEntry, SecretManifestError
from brain_ds.connectors.secrets.redaction import redact_secrets
from brain_ds.mcp.grounding import SECRET_CATALOG_CONTRACT, SECRET_REDACTION_TOKENS

_CANARY = "super-secret-canary-9999"


def _manifest_path(root: Path) -> Path:
    return root / ".brain_ds" / "secrets.json"


def _values_path(root: Path) -> Path:
    return root / ".brain_ds" / "secrets.values.json"


def _postgres_entry(handle: str = "warehouse_ro") -> SecretEntry:
    return SecretEntry(
        handle=handle,
        kind="postgres",
        metadata={
            "host": "db.local",
            "port": 5432,
            "database": "warehouse",
            "username": "etl",
            "sslmode": "require",
            "secret_ref": "BRAINDS_TEST_PWD",
        },
    )


class TestCatalogCrud:
    """WS-CAT-01: manifest persists handles and metadata, never raw values."""

    def test_add_creates_manifest_and_values_file(self, tmp_path: Path) -> None:
        catalog = SecretCatalog(tmp_path)
        catalog.add(_postgres_entry(), raw_value=_CANARY)

        assert _manifest_path(tmp_path).exists()
        assert _values_path(tmp_path).exists()

    def test_manifest_does_not_contain_raw_value(self, tmp_path: Path) -> None:
        catalog = SecretCatalog(tmp_path)
        catalog.add(_postgres_entry(), raw_value=_CANARY)

        manifest_text = _manifest_path(tmp_path).read_text(encoding="utf-8")
        assert _CANARY not in manifest_text
        assert "warehouse_ro" in manifest_text

    @pytest.mark.skipif(sys.platform == "win32", reason="Windows lacks Unix mode bits")
    def test_values_file_has_restricted_permissions(self, tmp_path: Path) -> None:
        catalog = SecretCatalog(tmp_path)
        catalog.add(_postgres_entry(), raw_value=_CANARY)

        mode = stat.S_IMODE(_values_path(tmp_path).stat().st_mode)
        assert mode == 0o600

    def test_list_handles_returns_all_entries(self, tmp_path: Path) -> None:
        catalog = SecretCatalog(tmp_path)
        catalog.add(
            SecretEntry(
                handle="pg",
                kind="postgres",
                metadata={
                    "host": "h",
                    "port": 1,
                    "database": "d",
                    "username": "u",
                    "sslmode": "disable",
                    "secret_ref": "BRAINDS_PG_TEST",
                },
            ),
            raw_value="v1",
        )
        catalog.add(
            SecretEntry(
                handle="aws",
                kind="aws-secrets",
                metadata={"region": "us-east-1", "secret_id": "my-secret"},
            ),
            raw_value="v2",
        )

        handles = {entry.handle for entry in catalog.list_handles()}
        assert handles == {"pg", "aws"}

    def test_get_returns_entry(self, tmp_path: Path) -> None:
        catalog = SecretCatalog(tmp_path)
        catalog.add(_postgres_entry(), raw_value="v")

        entry = catalog.get("warehouse_ro")
        assert entry is not None
        assert entry.handle == "warehouse_ro"
        assert entry.kind == "postgres"

    def test_remove_deletes_entry_and_value(self, tmp_path: Path) -> None:
        catalog = SecretCatalog(tmp_path)
        catalog.add(_postgres_entry(), raw_value="v")
        catalog.remove("warehouse_ro")

        assert catalog.get("warehouse_ro") is None
        values = json.loads(_values_path(tmp_path).read_text(encoding="utf-8"))
        assert "warehouse_ro" not in values

    def test_add_overwrites_existing_handle(self, tmp_path: Path) -> None:
        catalog = SecretCatalog(tmp_path)
        catalog.add(_postgres_entry(), raw_value="old")
        catalog.add(
            SecretEntry(
                handle="warehouse_ro",
                kind="postgres",
                metadata={
                    "host": "db2.local",
                    "port": 5433,
                    "database": "warehouse2",
                    "username": "etl2",
                    "sslmode": "require",
                    "secret_ref": "BRAINDS_PG_TEST",
                },
            ),
            raw_value="new",
        )

        entry = catalog.get("warehouse_ro")
        assert entry is not None
        assert entry.metadata["host"] == "db2.local"

    def test_load_rehydrates_existing_manifest(self, tmp_path: Path) -> None:
        catalog = SecretCatalog(tmp_path)
        catalog.add(_postgres_entry(), raw_value=_CANARY)

        fresh = SecretCatalog(tmp_path)
        fresh.load()
        entry = fresh.get("warehouse_ro")
        assert entry is not None
        assert entry.kind == "postgres"
        assert fresh.get_raw("warehouse_ro") == _CANARY


class TestCatalogSchemaValidation:
    """WS-CAT-04 / SI-4: manual edits are schema-validated and fail closed."""

    def test_validate_all_passes_for_valid_entries(self, tmp_path: Path) -> None:
        catalog = SecretCatalog(tmp_path)
        catalog.add(_postgres_entry(), raw_value="p")
        catalog.add(
            SecretEntry(
                handle="aws",
                kind="aws-secrets",
                metadata={"region": "us-east-1", "secret_id": "s"},
            ),
            raw_value="a",
        )
        catalog.add(
            SecretEntry(
                handle="gs",
                kind="google-sheets-json",
                metadata={
                    "spreadsheet_id": "abc",
                    "sheet_range": "A1:C10",
                    "service_account_ref": "SA_JSON",
                },
            ),
            raw_value='{"key":"val"}',
        )

        assert catalog.validate_all() == []

    def test_validate_all_reports_missing_required_metadata_field(self, tmp_path: Path) -> None:
        catalog = SecretCatalog(tmp_path)
        catalog.add(
            SecretEntry(
                handle="pg",
                kind="postgres",
                metadata={
                    "host": "h",
                    "port": 5432,
                    "database": "d",
                    "username": "u",
                    "sslmode": "require",
                    "secret_ref": "BRAINDS_PG_TEST",
                },
            ),
            raw_value="p",
        )

        # Break the manifest directly to test validate_all: the catalog now
        # refuses to add an invalid entry, so we simulate a manual edit.
        manifest_path = _manifest_path(tmp_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["entries"][0]["metadata"].pop("sslmode")
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        catalog = SecretCatalog(tmp_path)
        catalog.load()

        errors = catalog.validate_all()
        assert any("sslmode" in error for error in errors)

    def test_load_fails_closed_on_missing_kind(self, tmp_path: Path) -> None:
        _manifest_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        _manifest_path(tmp_path).write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "entries": [
                        {"handle": "broken", "metadata": {}, "created_at": "2026-01-01T00:00:00Z"}
                    ],
                }
            ),
            encoding="utf-8",
        )

        catalog = SecretCatalog(tmp_path)
        with pytest.raises(SecretManifestError):
            catalog.load()

    def test_load_fails_closed_on_unknown_kind(self, tmp_path: Path) -> None:
        _manifest_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        _manifest_path(tmp_path).write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "entries": [
                        {
                            "handle": "broken",
                            "kind": "unknown-provider",
                            "metadata": {},
                            "created_at": "2026-01-01T00:00:00Z",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        catalog = SecretCatalog(tmp_path)
        with pytest.raises(SecretManifestError):
            catalog.load()


class TestRedaction:
    """SI-6: redaction utility masks all canary key names."""

    def test_redacts_password(self) -> None:
        result = redact_secrets({"host": "db.local", "password": _CANARY})
        assert result["password"] == "***"
        assert result["host"] == "db.local"

    def test_redacts_secret_ref(self) -> None:
        result = redact_secrets({"secret_ref": "BRAINDS_PWD", "host": "db.local"})
        assert result["secret_ref"] == "***"
        assert result["host"] == "db.local"

    def test_redacts_api_key(self) -> None:
        result = redact_secrets({"api_key": _CANARY, "client_secret": _CANARY})
        assert result["api_key"] == "***"
        assert result["client_secret"] == "***"

    def test_redacts_access_key(self) -> None:
        result = redact_secrets({"access_key": _CANARY})
        assert result["access_key"] == "***"

    def test_redacts_private_key_nested_path(self) -> None:
        result = redact_secrets(
            {
                "service_account": {
                    "client_email": "x@example.com",
                    "private_key": _CANARY,
                }
            }
        )
        assert result["service_account"]["private_key"] == "***"
        assert result["service_account"]["client_email"] == "x@example.com"

    def test_redacts_dotted_private_key_field(self) -> None:
        result = redact_secrets({"service_account.private_key": _CANARY, "host": "h"})
        assert result["service_account.private_key"] == "***"
        assert result["host"] == "h"

    def test_redacts_within_lists(self) -> None:
        result = redact_secrets(
            [
                {"host": "h1", "password": "p1"},
                {"host": "h2", "token": "t1"},
            ]
        )
        assert result[0]["password"] == "***"
        assert result[1]["token"] == "***"
        assert result[0]["host"] == "h1"
        assert result[1]["host"] == "h2"

    def test_case_insensitive_match(self) -> None:
        result = redact_secrets({"PASSWORD": _CANARY, "Api_Key": _CANARY})
        assert result["PASSWORD"] == "***"
        assert result["Api_Key"] == "***"

    def test_leaves_non_secret_data_untouched(self) -> None:
        payload = {"host": "db.local", "port": 5432, "username": "etl"}
        assert redact_secrets(payload) == payload

    def test_redacts_passwd_variant(self) -> None:
        result = redact_secrets({"passwd": _CANARY})
        assert result["passwd"] == "***"

    def test_secret_handle_is_exempt_not_masked(self) -> None:
        # secret_handle is a reference/label the agent reads from a connection
        # descriptor — the real secret lives in AWS, never in the handle name.
        # It must NOT be masked even though "secret" is a redaction substring.
        result = redact_secrets(
            {"kind": "aws-postgres", "secret_handle": "grupo-topete/sit-aurora", "database": "SIT"}
        )
        assert result["secret_handle"] == "grupo-topete/sit-aurora"
        assert result["kind"] == "aws-postgres"
        assert result["database"] == "SIT"

    def test_secret_id_still_masked(self) -> None:
        # The ARN (secret_id) is admin-side metadata, not part of the agent-facing
        # descriptor — it stays redacted.
        result = redact_secrets({"secret_id": _CANARY})
        assert result["secret_id"] == "***"


class TestGroundingConstants:
    """Task 1.6: Category-2 constants for secret handle schema and provider kinds."""

    def test_secret_catalog_contract_lists_required_provider_kinds(self) -> None:
        kinds = cast(list[str], SECRET_CATALOG_CONTRACT["provider_kinds"])
        required = [
            "postgres",
            "sqlserver",
            "aws-secrets",
            "iam-role",
            "iam-credential",
            "google-sheets-json",
        ]
        for kind in required:
            assert kind in kinds, f"missing provider kind {kind}"

    def test_secret_catalog_contract_describes_manifest_paths(self) -> None:
        assert SECRET_CATALOG_CONTRACT["manifest_path"] == ".brain_ds/secrets.json"
        assert SECRET_CATALOG_CONTRACT["values_path"] == ".brain_ds/secrets.values.json"

    def test_redaction_tokens_cover_canary_keys(self) -> None:
        required = [
            "password",
            "passwd",
            "secret",
            "token",
            "api_key",
            "access_key",
            "private_key",
            "client_secret",
            "service_account.private_key",
        ]
        tokens = [t.lower() for t in cast(list[str], SECRET_REDACTION_TOKENS)]
        for token in required:
            assert token in tokens, f"missing redaction token {token}"

    def test_secret_catalog_contract_has_no_drift_tokens(self) -> None:
        """Strings use lowercase/space-separated words so the drift sweep stays clean."""
        text = json.dumps(SECRET_CATALOG_CONTRACT)
        assert "SqlServer" not in text
        assert "AwsSecrets" not in text
        assert "GoogleSheets" not in text
