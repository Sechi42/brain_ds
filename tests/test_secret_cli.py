"""Phase 2 TDD tests for the `brain_ds secret` CLI surface."""
from __future__ import annotations

import io
import json
import socket
from pathlib import Path

from brain_ds.ui.cli import main


def _pg_metadata(secret_ref: str = "BRAINDS_PG_PWD") -> str:
    return json.dumps(
        {
            "host": "127.0.0.1",
            "port": 5432,
            "database": "warehouse",
            "username": "etl",
            "sslmode": "require",
            "secret_ref": secret_ref,
        }
    )


def _aws_metadata_missing_region() -> str:
    return json.dumps({"secret_id": "prod/db/password"})


def _gs_metadata(service_account_ref: str = "BRAINDS_GSA_JSON") -> str:
    return json.dumps(
        {
            "spreadsheet_id": "abc123",
            "sheet_range": "A1:C10",
            "service_account_ref": service_account_ref,
        }
    )


class TestSecretList:
    """WS-CAT-02: list handles without echoing raw values."""

    def test_list_prints_handle_and_kind(self, tmp_path: Path, capsys, monkeypatch) -> None:
        monkeypatch.setenv("BRAINDS_PG_PWD", "super-secret-list")
        assert main(
            [
                "secret",
                "add",
                "--project-root",
                str(tmp_path),
                "--kind",
                "postgres",
                "--handle",
                "warehouse_ro",
                "--metadata-json",
                _pg_metadata(),
                "--value-env",
                "BRAINDS_PG_PWD",
            ]
        ) == 0

        rc = main(["secret", "list", "--project-root", str(tmp_path)])
        captured = capsys.readouterr()

        assert rc == 0
        assert "warehouse_ro" in captured.out
        assert "postgres" in captured.out
        assert "super-secret-list" not in captured.out
        assert "super-secret-list" not in captured.err


class TestSecretAdd:
    """WS-CAT-01/02: add stores metadata in manifest and raw value in values file."""

    def test_add_stores_value_separate_from_manifest(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("BRAINDS_PG_PWD", "raw-value-9999")
        rc = main(
            [
                "secret",
                "add",
                "--project-root",
                str(tmp_path),
                "--kind",
                "postgres",
                "--handle",
                "warehouse_ro",
                "--metadata-json",
                _pg_metadata(),
                "--value-env",
                "BRAINDS_PG_PWD",
            ]
        )

        assert rc == 0
        manifest = json.loads((tmp_path / ".brain_ds" / "secrets.json").read_text(encoding="utf-8"))
        values = json.loads((tmp_path / ".brain_ds" / "secrets.values.json").read_text(encoding="utf-8"))

        assert any(entry["handle"] == "warehouse_ro" for entry in manifest["entries"])
        assert "raw-value-9999" not in json.dumps(manifest)
        assert values["values"]["warehouse_ro"] == "raw-value-9999"

    def test_add_reads_value_from_stdin(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("stdin-secret-value\n"))
        rc = main(
            [
                "secret",
                "add",
                "--project-root",
                str(tmp_path),
                "--kind",
                "postgres",
                "--handle",
                "stdin_pg",
                "--metadata-json",
                _pg_metadata("BRAINDS_STDIN_PWD"),
                "--value-stdin",
            ]
        )

        assert rc == 0
        values = json.loads((tmp_path / ".brain_ds" / "secrets.values.json").read_text(encoding="utf-8"))
        assert values["values"]["stdin_pg"] == "stdin-secret-value"


class TestSecretValidate:
    """WS-CAT-02 / 2.7: dry-run by default; --probe is explicit opt-in."""

    def test_validate_dry_run_passes_for_valid_entry(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("BRAINDS_PG_PWD", "irrelevant")
        main(
            [
                "secret",
                "add",
                "--project-root",
                str(tmp_path),
                "--kind",
                "postgres",
                "--handle",
                "warehouse_ro",
                "--metadata-json",
                _pg_metadata(),
                "--value-env",
                "BRAINDS_PG_PWD",
            ]
        )

        rc = main(["secret", "validate", "--project-root", str(tmp_path)])
        assert rc == 0
        rc = main(["secret", "validate", "--project-root", str(tmp_path), "--dry-run"])
        assert rc == 0

    def test_validate_reports_schema_error_naming_handle_and_field(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        monkeypatch.setenv("BRAINDS_BROKEN_AWS", "unused")
        main(
            [
                "secret",
                "add",
                "--project-root",
                str(tmp_path),
                "--kind",
                "aws-secrets",
                "--handle",
                "broken_aws",
                "--metadata-json",
                _aws_metadata_missing_region(),
                "--value-env",
                "BRAINDS_BROKEN_AWS",
            ]
        )

        rc = main(["secret", "validate", "--project-root", str(tmp_path)])
        captured = capsys.readouterr()

        assert rc == 1
        assert "broken_aws" in captured.err
        assert "region" in captured.err

    def test_validate_does_not_probe_without_explicit_flag(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("BRAINDS_PG_PWD", "irrelevant")
        main(
            [
                "secret",
                "add",
                "--project-root",
                str(tmp_path),
                "--kind",
                "postgres",
                "--handle",
                "warehouse_ro",
                "--metadata-json",
                _pg_metadata(),
                "--value-env",
                "BRAINDS_PG_PWD",
            ]
        )

        calls = []
        monkeypatch.setattr(
            socket,
            "create_connection",
            lambda *args, **kwargs: calls.append(args) or None,
        )

        rc = main(["secret", "validate", "--project-root", str(tmp_path)])
        assert rc == 0
        assert calls == []

    def test_validate_probe_attempts_real_connectivity(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("BRAINDS_PG_PWD", "irrelevant")
        main(
            [
                "secret",
                "add",
                "--project-root",
                str(tmp_path),
                "--kind",
                "postgres",
                "--handle",
                "warehouse_ro",
                "--metadata-json",
                _pg_metadata(),
                "--value-env",
                "BRAINDS_PG_PWD",
            ]
        )

        def fake_probe(*args, **kwargs):
            raise ConnectionRefusedError("probe refused")

        monkeypatch.setattr(socket, "create_connection", fake_probe)

        rc = main(["secret", "validate", "--project-root", str(tmp_path), "--probe"])
        assert rc == 1


class TestSecretRemove:
    """WS-CAT-02: remove deletes handle and value."""

    def test_remove_deletes_entry(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("BRAINDS_PG_PWD", "to-delete")
        main(
            [
                "secret",
                "add",
                "--project-root",
                str(tmp_path),
                "--kind",
                "postgres",
                "--handle",
                "delete_me",
                "--metadata-json",
                _pg_metadata("BRAINDS_PG_PWD"),
                "--value-env",
                "BRAINDS_PG_PWD",
            ]
        )

        rc = main(["secret", "remove", "--project-root", str(tmp_path), "--handle", "delete_me"])
        assert rc == 0

        values = json.loads((tmp_path / ".brain_ds" / "secrets.values.json").read_text(encoding="utf-8"))
        assert "delete_me" not in values["values"]


class TestSecretRedaction:
    """Security invariant: Google Sheets JSON private_key/client_secret never reach CLI output."""

    def test_google_credentials_not_in_list_or_validate_output(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        service_account = (
            '{"client_email":"x@example.com","private_key":"PRIVATE_KEY_VALUE",'
            '"client_secret":"CLIENT_SECRET_VALUE"}'
        )
        monkeypatch.setenv("BRAINDS_GSA_JSON", service_account)
        main(
            [
                "secret",
                "add",
                "--project-root",
                str(tmp_path),
                "--kind",
                "google-sheets-json",
                "--handle",
                "sales_q3",
                "--metadata-json",
                _gs_metadata(),
                "--value-env",
                "BRAINDS_GSA_JSON",
            ]
        )

        main(["secret", "list", "--project-root", str(tmp_path)])
        main(["secret", "validate", "--project-root", str(tmp_path)])
        captured = capsys.readouterr()

        combined = captured.out + captured.err
        assert "PRIVATE_KEY_VALUE" not in combined
        assert "CLIENT_SECRET_VALUE" not in combined
