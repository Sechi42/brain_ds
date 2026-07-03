"""Phase 4a TDD tests for the UI-facing secret API."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from brain_ds.api.events import EventBus
from brain_ds.api.server import create_app
from brain_ds.connectors.secrets import SecretCatalog, SecretEntry
from brain_ds.store.graph_store import GraphStore

_CANARY = "ui-secret-canary-8888"


def _store_with_graph(tmp_path: Path) -> GraphStore:
    brain_ds_dir = tmp_path / ".brain_ds"
    brain_ds_dir.mkdir(parents=True)
    store = GraphStore(str(brain_ds_dir / "store.db"), allow_cross_thread=True)
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


def _seed_catalog(store: GraphStore) -> SecretCatalog:
    root = Path(store.path).parent.parent
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
    return catalog


def _api_client(store: GraphStore, tmp_path: Path) -> TestClient:
    app = create_app(project_root=tmp_path, store=store, event_bus=EventBus())
    app.state.secret_admin_enabled = True
    return TestClient(app)


class TestListSecrets:
    """GET /api/secrets returns redacted handles; no raw values leak."""

    def test_list_secrets_requires_graph_id(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            client = _api_client(store, tmp_path)
            response = client.get("/api/secrets")
            assert response.status_code == 422
        finally:
            store.close()

    def test_list_secrets_returns_handles_and_redacts_metadata(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            _seed_catalog(store)
            client = _api_client(store, tmp_path)
            response = client.get("/api/secrets?graph_id=graph-secrets&agent_scope=workspace_admin")

            assert response.status_code == 200
            data = response.json()
            handles = {entry["handle"] for entry in data["handles"]}
            assert handles == {"warehouse_ro"}
            wh = data["handles"][0]
            assert wh["kind"] == "postgres"
            assert wh["metadata"]["secret_ref"] == "***"
            assert wh["metadata"]["host"] == "db.local"
        finally:
            store.close()

    def test_canary_raw_value_not_in_list_response(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            _seed_catalog(store)
            client = _api_client(store, tmp_path)
            response = client.get("/api/secrets?graph_id=graph-secrets&agent_scope=workspace_admin")

            assert response.status_code == 200
            body = response.text
            assert _CANARY not in body
            assert "BRAINDS_WH_PWD" not in body
        finally:
            store.close()

    def test_invalid_manifest_fails_closed(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            manifest_path = tmp_path / ".brain_ds" / "secrets.json"
            manifest_path.write_text(
                json.dumps({"schema_version": "1.0", "entries": [{"handle": "broken"}]}),
                encoding="utf-8",
            )
            client = _api_client(store, tmp_path)
            response = client.get("/api/secrets?graph_id=graph-secrets&agent_scope=workspace_admin")

            assert response.status_code == 400
            assert "manifest" in response.text.lower() or "schema" in response.text.lower()
        finally:
            store.close()


class TestAddSecret:
    """POST /api/secrets stores a new handle and raw value."""

    def test_add_secret_creates_entry(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            client = _api_client(store, tmp_path)
            response = client.post(
                "/api/secrets?graph_id=graph-secrets&agent_scope=workspace_admin",
                json={
                    "handle": "sales_q3",
                    "kind": "postgres",
                    "metadata": {
                        "host": "db.local",
                        "port": 5432,
                        "database": "warehouse",
                        "username": "etl",
                        "sslmode": "require",
                        "secret_ref": "BRAINDS_WH_PWD",
                    },
                    "raw_value": "PG_PASSWORD_VALUE",
                },
            )

            assert response.status_code == 201
            body = response.json()
            assert body["handle"] == "sales_q3"
            assert "PG_PASSWORD_VALUE" not in response.text

            catalog = SecretCatalog(tmp_path)
            catalog.load()
            entry = catalog.get("sales_q3")
            assert entry is not None
            assert entry.kind == "postgres"
            assert catalog.get_raw("sales_q3") == "PG_PASSWORD_VALUE"
        finally:
            store.close()

    def test_add_secret_missing_handle_returns_422(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            client = _api_client(store, tmp_path)
            response = client.post(
                "/api/secrets?graph_id=graph-secrets&agent_scope=workspace_admin",
                json={"kind": "postgres", "metadata": {"host": "db.local"}},
            )
            assert response.status_code == 422
        finally:
            store.close()


class TestAddSecretValidation:
    """POST /api/secrets rejects invalid payloads before persistence."""

    def _valid_postgres_payload(self, **overrides):
        payload = {
            "handle": "sales_q3",
            "kind": "postgres",
            "metadata": {
                "host": "db.local",
                "port": 5432,
                "database": "warehouse",
                "username": "etl",
                "sslmode": "require",
                "secret_ref": "BRAINDS_WH_PWD",
            },
            "raw_value": "PG_PASSWORD_VALUE",
        }
        payload.update(overrides)
        return payload

    def test_unknown_kind_returns_422(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            client = _api_client(store, tmp_path)
            response = client.post(
                "/api/secrets?graph_id=graph-secrets&agent_scope=workspace_admin",
                json=self._valid_postgres_payload(kind="unknown-provider"),
            )
            assert response.status_code == 422
        finally:
            store.close()

    def test_missing_required_metadata_returns_422(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            client = _api_client(store, tmp_path)
            response = client.post(
                "/api/secrets?graph_id=graph-secrets&agent_scope=workspace_admin",
                json=self._valid_postgres_payload(
                    kind="postgres",
                    metadata={"host": "db.local"},
                    raw_value="super-secret",
                ),
            )
            assert response.status_code == 422
        finally:
            store.close()

    def test_missing_raw_value_returns_422(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            client = _api_client(store, tmp_path)
            payload = self._valid_postgres_payload()
            payload.pop("raw_value")
            response = client.post(
                "/api/secrets?graph_id=graph-secrets&agent_scope=workspace_admin",
                json=payload,
            )
            assert response.status_code == 422
        finally:
            store.close()

    def test_empty_raw_value_returns_422(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            client = _api_client(store, tmp_path)
            response = client.post(
                "/api/secrets?graph_id=graph-secrets&agent_scope=workspace_admin",
                json=self._valid_postgres_payload(raw_value=""),
            )
            assert response.status_code == 422
        finally:
            store.close()


class TestRemoveSecret:
    """DELETE /api/secrets/{handle} removes the entry and its raw value."""

    def test_remove_secret_deletes_entry(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            _seed_catalog(store)
            client = _api_client(store, tmp_path)
            response = client.delete("/api/secrets/warehouse_ro?graph_id=graph-secrets&agent_scope=workspace_admin")
            assert response.status_code == 204

            list_response = client.get("/api/secrets?graph_id=graph-secrets&agent_scope=workspace_admin")
            assert list_response.json()["handles"] == []
        finally:
            store.close()


class TestSecretSchema:
    """GET /api/secrets/schema exposes provider metadata contracts."""

    def test_schema_endpoint_returns_provider_kinds(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            client = _api_client(store, tmp_path)
            response = client.get("/api/secrets/schema?graph_id=graph-secrets")
            assert response.status_code == 200
            data = response.json()
            assert "postgres" in data["provider_kinds"]
            assert "host" in data["provider_kinds"]["postgres"]["required"]
        finally:
            store.close()
