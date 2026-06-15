"""Phase 3 TDD tests for the MCP secret boundary."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from brain_ds.connectors.secrets import SecretCatalog, SecretEntry
from brain_ds.connectors.secrets.providers import PostgresAdapter
from brain_ds.mcp.tools import (
    explore_source,
    list_secret_handles,
    list_source_connections,
    validate_secret_handle,
)
from brain_ds.store.graph_store import GraphStore

_CANARY = "mcp-secret-canary-7777"


def _project_root(store: GraphStore) -> Path:
    return Path(store.path).parent.parent


def _seed_catalog(store: GraphStore) -> SecretCatalog:
    root = _project_root(store)
    catalog = SecretCatalog(root)
    catalog.add(
        SecretEntry(
            handle="warehouse_ro",
            kind="postgres",
            metadata={
                "host": "db.local",
                "port": 5432,
                "database": "warehouse",
                "username": "etl",
                "sslmode": "require",
                "secret_ref": "BRAINDS_WH_PWD",
            },
        ),
        raw_value=_CANARY,
    )
    catalog.add(
        SecretEntry(
            handle="sales_q3",
            kind="google-sheets-json",
            metadata={
                "spreadsheet_id": "abc123",
                "sheet_range": "A1:C10",
                "service_account_ref": "BRAINDS_GSA",
            },
        ),
        raw_value='{"private_key":"GS_PRIVATE_KEY_VALUE"}',
    )
    return catalog


def _store_with_graph(tmp_path: Path) -> GraphStore:
    brain_ds_dir = tmp_path / ".brain_ds"
    brain_ds_dir.mkdir(parents=True)
    store = GraphStore(str(brain_ds_dir / "store.db"))
    store.meta_repo.save_graph_meta(
        graph_id="graph-secrets",
        workspace_root=str(tmp_path),
        workspace_path=str(tmp_path),
        project="project-secrets",
        org="org-secrets",
        schema_version="2.0.0",
        contract_version="1.0.0",
        node_count=0,
        edge_count=0,
        imported_from=None,
        generated_at="",
    )
    return store


class TestListSecretHandles:
    """MCP-SEC-01: admin lists handles; non-admin is denied; no raw values leak."""

    def test_admin_lists_handles_and_redacts_metadata(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            _seed_catalog(store)
            result = list_secret_handles(store, {"agent_scope": "workspace_admin"})

            handles = {entry["handle"] for entry in result["handles"]}
            assert handles == {"warehouse_ro", "sales_q3"}

            wh = next(entry for entry in result["handles"] if entry["handle"] == "warehouse_ro")
            assert wh["kind"] == "postgres"
            assert wh["metadata"]["secret_ref"] == "***"
            assert wh["metadata"]["host"] == "db.local"
        finally:
            store.close()

    def test_non_admin_denied_security_error(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            _seed_catalog(store)
            result = list_secret_handles(store, {"agent_scope": "workspace_member"})

            assert result["code"] == -32001
            assert "workspace_admin" in result["message"]
            assert _CANARY not in json.dumps(result)
        finally:
            store.close()

    def test_missing_scope_denied(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            _seed_catalog(store)
            result = list_secret_handles(store, {})

            assert result["code"] == -32001
        finally:
            store.close()

    def test_canary_raw_value_not_in_output(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            _seed_catalog(store)
            result = list_secret_handles(store, {"agent_scope": "workspace_admin"})

            serialized = json.dumps(result, default=str)
            assert _CANARY not in serialized
            assert "GS_PRIVATE_KEY_VALUE" not in serialized
            assert "BRAINDS_WH_PWD" not in serialized
        finally:
            store.close()


class TestValidateSecretHandle:
    """MCP-SEC-02: validate handle existence and schema without exposing raw values."""

    def test_admin_valid_handle_returns_valid(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            _seed_catalog(store)
            result = validate_secret_handle(
                store, {"handle": "warehouse_ro", "agent_scope": "workspace_admin"}
            )

            assert result["valid"] is True
            assert "warehouse_ro" in result["reason"]
            assert _CANARY not in json.dumps(result)
        finally:
            store.close()

    def test_admin_missing_handle_returns_invalid(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            _seed_catalog(store)
            result = validate_secret_handle(
                store, {"handle": "missing", "agent_scope": "workspace_admin"}
            )

            assert result["valid"] is False
            assert "missing" in result["reason"]
        finally:
            store.close()

    def test_admin_schema_error_names_handle_and_field(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            catalog = SecretCatalog(_project_root(store))
            catalog.add(
                SecretEntry(
                    handle="broken_pg",
                    kind="postgres",
                    metadata={
                        "host": "db.local",
                        "port": 5432,
                        "database": "d",
                        "username": "u",
                        "sslmode": "require",
                        "secret_ref": "BRAINDS_TEST_PWD",
                    },
                ),
                raw_value="x",
            )

            # Simulate a manual edit that strips a required field so we can
            # exercise the validate path; the catalog now rejects such edits
            # via add(), so we go through the manifest file directly.
            manifest_path = _project_root(store) / ".brain_ds" / "secrets.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["entries"][0]["metadata"].pop("sslmode")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = validate_secret_handle(
                store, {"handle": "broken_pg", "agent_scope": "workspace_admin"}
            )

            assert result["valid"] is False
            assert "broken_pg" in result["reason"]
            assert "sslmode" in result["reason"]
        finally:
            store.close()

    def test_non_admin_denied(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            _seed_catalog(store)
            result = validate_secret_handle(
                store, {"handle": "warehouse_ro", "agent_scope": "workspace_member"}
            )

            assert result["code"] == -32001
        finally:
            store.close()

    def test_probe_only_with_explicit_flag(self, tmp_path: Path, monkeypatch) -> None:
        store = _store_with_graph(tmp_path)
        try:
            _seed_catalog(store)
            calls = []
            monkeypatch.setattr(
                PostgresAdapter,
                "probe",
                lambda _self, handle, metadata: calls.append(handle) or None,
            )

            dry = validate_secret_handle(
                store, {"handle": "warehouse_ro", "agent_scope": "workspace_admin"}
            )
            assert dry["valid"] is True
            assert calls == []

            probed = validate_secret_handle(
                store,
                {"handle": "warehouse_ro", "agent_scope": "workspace_admin", "probe": True},
            )
            assert probed["valid"] is True
            assert calls == ["warehouse_ro"]
        finally:
            store.close()

    def test_probe_rejected_for_non_admin(self, tmp_path: Path, monkeypatch) -> None:
        store = _store_with_graph(tmp_path)
        try:
            _seed_catalog(store)
            calls = []
            monkeypatch.setattr(
                PostgresAdapter,
                "probe",
                lambda _self, handle, metadata: calls.append(handle) or None,
            )

            result = validate_secret_handle(
                store,
                {"handle": "warehouse_ro", "agent_scope": "workspace_member", "probe": True},
            )

            assert result["code"] == -32001
            assert calls == []
        finally:
            store.close()

    def test_reason_never_contains_raw_value(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            _seed_catalog(store)
            result = validate_secret_handle(
                store, {"handle": "warehouse_ro", "agent_scope": "workspace_admin"}
            )

            assert _CANARY not in json.dumps(result)
        finally:
            store.close()


class TestAuditLogging:
    """MCP-SEC-06: secret tool calls are appended to the audit log."""

    def _audit_count(self, store: GraphStore) -> int:
        row = store.conn.execute("SELECT COUNT(*) FROM tools_audit").fetchone()
        return int(row[0])

    def test_list_secret_handles_logs_success(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            _seed_catalog(store)
            before = self._audit_count(store)
            list_secret_handles(store, {"agent_scope": "workspace_admin"})
            after = self._audit_count(store)
            assert after == before + 1

            row = store.conn.execute(
                "SELECT tool_name, result_status FROM tools_audit ORDER BY id DESC LIMIT 1"
            ).fetchone()
            assert row[0] == "list_secret_handles"
            assert row[1] == "ok"
        finally:
            store.close()

    def test_denied_call_logs_error(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            _seed_catalog(store)
            before = self._audit_count(store)
            list_secret_handles(store, {"agent_scope": "workspace_member"})
            after = self._audit_count(store)
            assert after == before + 1

            row = store.conn.execute(
                "SELECT tool_name, result_status FROM tools_audit ORDER BY id DESC LIMIT 1"
            ).fetchone()
            assert row[0] == "list_secret_handles"
            assert row[1] == "error"
        finally:
            store.close()


class TestSourceConnectionRedaction:
    """MCP-SEC-05: list_source_connections redacts secret-bearing connection keys."""

    def test_redacts_secret_ref_and_password(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            store.upsert_node(
                "graph-secrets",
                {
                    "id": "DS-PG",
                    "label": "Postgres DS",
                    "type": "Data Source",
                    "supertype": "data",
                    "details": {
                        "connection": {
                            "kind": "postgres",
                            "host": "db.local",
                            "password": _CANARY,
                            "secret_ref": "BRAINDS_WH_PWD",
                        }
                    },
                },
            )

            result = list_source_connections(store, {"graph_id": "graph-secrets"})
            serialized = json.dumps(result, default=str)

            assert _CANARY not in serialized
            assert "BRAINDS_WH_PWD" not in serialized
            assert "postgres" in serialized
            assert "db.local" in serialized
        finally:
            store.close()


class TestExploreSourceRedaction:
    """MCP-SEC-04: explore_source redacts secret material from payloads."""

    def test_redacts_connection_descriptor_in_error(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            store.upsert_node(
                "graph-secrets",
                {
                    "id": "DS-PG",
                    "label": "Postgres DS",
                    "type": "Data Source",
                    "supertype": "data",
                    "details": {
                        "connection": {
                            "kind": "postgres",
                            "host": "db.local",
                            "password": _CANARY,
                            "secret_ref": "BRAINDS_WH_PWD",
                        }
                    },
                },
            )

            result = explore_source(store, {"graph_id": "graph-secrets", "node_id": "DS-PG"})
            serialized = json.dumps(result, default=str)

            assert _CANARY not in serialized
            assert "BRAINDS_WH_PWD" not in serialized
        finally:
            store.close()


class TestManifestFailClosed:
    """WS-CAT-04: invalid manifest schema closes the secret MCP surface."""

    def test_list_secret_handles_fails_closed_on_invalid_manifest(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            manifest_path = tmp_path / ".brain_ds" / "secrets.json"
            manifest_path.write_text(
                json.dumps({"schema_version": "1.0", "entries": [{"handle": "broken"}]}),
                encoding="utf-8",
            )

            result = list_secret_handles(store, {"agent_scope": "workspace_admin"})

            assert "code" in result
            assert result["code"] == -32000
            assert "manifest" in result["message"].lower() or "schema" in result["message"].lower()
        finally:
            store.close()
