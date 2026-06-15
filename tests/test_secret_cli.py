"""Phase 2 TDD tests for the `brain_ds secret` CLI surface."""
from __future__ import annotations

import io
import json
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



