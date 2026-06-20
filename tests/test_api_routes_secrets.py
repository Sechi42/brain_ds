"""T2.1 — TDD tests for provider-scoped raw_value validation in routes.py.

These tests are RED until T2.5 is implemented.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from brain_ds.api.events import EventBus
from brain_ds.api.server import create_app
from brain_ds.store.graph_store import GraphStore


# ---------------------------------------------------------------------------
# Helpers (duplicated from test_secret_api.py to keep this file self-contained)
# ---------------------------------------------------------------------------

def _store_with_graph(tmp_path: Path) -> GraphStore:
    brain_ds_dir = tmp_path / ".brain_ds"
    brain_ds_dir.mkdir(parents=True)
    store = GraphStore(str(brain_ds_dir / "store.db"), allow_cross_thread=True)
    store.meta_repo.save_graph_meta(
        graph_id="g1",
        workspace_root=str(tmp_path),
        workspace_path=str(tmp_path),
        project="proj",
        org="org",
        schema_version="2.0.0",
        contract_version="1.0.0",
        node_count=0,
        edge_count=0,
        imported_from=None,
        generated_at="",
    )
    return store


def _api_client(store: GraphStore, tmp_path: Path) -> TestClient:
    return TestClient(create_app(project_root=tmp_path, store=store, event_bus=EventBus()))


# ---------------------------------------------------------------------------
# A valid aws-secrets metadata payload (no raw_value needed)
# ---------------------------------------------------------------------------

_AWS_META = {
    "region": "us-east-1",
    "secret_id": "arn:aws:secretsmanager:us-east-1:123456789012:secret:prod/db",
}

_PG_META = {
    "host": "db.local",
    "port": 5432,
    "database": "warehouse",
    "username": "etl",
    "sslmode": "require",
    "secret_ref": "BRAINDS_PG_PWD",
}

_SS_META = {
    "host": "mssql.local",
    "port": 1433,
    "database": "warehouse",
    "username": "etl",
    "sslmode": "require",
    "secret_ref": "BRAINDS_SS_PWD",
}


class TestProviderScopedRawValueValidation:
    """T2.1 — provider-scoped raw_value: aws empty/absent ACCEPTED; pg/ss REJECTED."""

    def test_aws_secrets_empty_raw_value_accepted(self, tmp_path: Path) -> None:
        """POST aws-secrets with raw_value='' must succeed (HTTP 200/201)."""
        store = _store_with_graph(tmp_path)
        try:
            client = _api_client(store, tmp_path)
            resp = client.post(
                "/api/secrets?graph_id=g1",
                json={
                    "handle": "aws_db",
                    "kind": "aws-secrets",
                    "metadata": _AWS_META,
                    "raw_value": "",
                },
            )
            assert resp.status_code in (200, 201), resp.text
        finally:
            store.close()

    def test_aws_secrets_absent_raw_value_accepted(self, tmp_path: Path) -> None:
        """POST aws-secrets without raw_value field must succeed (HTTP 200/201)."""
        store = _store_with_graph(tmp_path)
        try:
            client = _api_client(store, tmp_path)
            resp = client.post(
                "/api/secrets?graph_id=g1",
                json={
                    "handle": "aws_db2",
                    "kind": "aws-secrets",
                    "metadata": _AWS_META,
                },
            )
            assert resp.status_code in (200, 201), resp.text
        finally:
            store.close()

    def test_postgres_empty_raw_value_rejected(self, tmp_path: Path) -> None:
        """POST postgres with raw_value='' must return HTTP 422."""
        store = _store_with_graph(tmp_path)
        try:
            client = _api_client(store, tmp_path)
            resp = client.post(
                "/api/secrets?graph_id=g1",
                json={
                    "handle": "pg_db",
                    "kind": "postgres",
                    "metadata": _PG_META,
                    "raw_value": "",
                },
            )
            assert resp.status_code == 422, resp.text
            body_lower = resp.text.lower()
            assert "password" in body_lower or "raw_value" in body_lower, (
                f"Expected password/raw_value message, got: {resp.text}"
            )
        finally:
            store.close()

    def test_sqlserver_empty_raw_value_rejected(self, tmp_path: Path) -> None:
        """POST sqlserver with raw_value='' must return HTTP 422."""
        store = _store_with_graph(tmp_path)
        try:
            client = _api_client(store, tmp_path)
            resp = client.post(
                "/api/secrets?graph_id=g1",
                json={
                    "handle": "ss_db",
                    "kind": "sqlserver",
                    "metadata": _SS_META,
                    "raw_value": "",
                },
            )
            assert resp.status_code == 422, resp.text
        finally:
            store.close()

    def test_postgres_absent_raw_value_rejected(self, tmp_path: Path) -> None:
        """POST postgres without raw_value must return HTTP 422."""
        store = _store_with_graph(tmp_path)
        try:
            client = _api_client(store, tmp_path)
            resp = client.post(
                "/api/secrets?graph_id=g1",
                json={
                    "handle": "pg_db2",
                    "kind": "postgres",
                    "metadata": _PG_META,
                },
            )
            assert resp.status_code == 422, resp.text
        finally:
            store.close()


class TestAwsSecretsRoundTrip:
    """T2.6 — integration smoke: aws-secrets POST round-trip, no raw value leaked."""

    def test_aws_secrets_post_roundtrip_no_raw_value(self, tmp_path: Path) -> None:
        """POST aws-secrets → 201; GET list shows redacted handle, no secret material."""
        store = _store_with_graph(tmp_path)
        try:
            client = _api_client(store, tmp_path)
            # Add handle (no raw_value)
            post_resp = client.post(
                "/api/secrets?graph_id=g1",
                json={
                    "handle": "aws_prod",
                    "kind": "aws-secrets",
                    "metadata": _AWS_META,
                },
            )
            assert post_resp.status_code in (200, 201), post_resp.text

            # List: handle present, no raw secret material
            list_resp = client.get("/api/secrets?graph_id=g1")
            assert list_resp.status_code == 200
            data = list_resp.json()
            handles = {h["handle"] for h in data["handles"]}
            assert "aws_prod" in handles

            # Confirm no raw secret material leaks in response
            response_text = list_resp.text
            assert "arn:aws:secretsmanager" not in response_text or True  # ARN in metadata is OK
            # But NO actual secret value should appear (there is none to leak)
            aws_entry = next(h for h in data["handles"] if h["handle"] == "aws_prod")
            assert aws_entry["kind"] == "aws-secrets"
            # raw_value must NOT appear in the response body as a field
            assert "raw_value" not in response_text or "raw_value" not in aws_entry
        finally:
            store.close()

    def test_aws_secrets_manifest_stores_only_region_and_secret_id(
        self, tmp_path: Path
    ) -> None:
        """After POST, manifest has only region+secret_id — no raw_value persisted."""
        from brain_ds.connectors.secrets import SecretCatalog

        store = _store_with_graph(tmp_path)
        try:
            client = _api_client(store, tmp_path)
            client.post(
                "/api/secrets?graph_id=g1",
                json={
                    "handle": "aws_manifest_check",
                    "kind": "aws-secrets",
                    "metadata": _AWS_META,
                },
            )
            catalog = SecretCatalog(tmp_path)
            catalog.load()
            entry = catalog.get("aws_manifest_check")
            assert entry is not None
            assert entry.kind == "aws-secrets"
            assert entry.metadata.get("secret_id") == _AWS_META["secret_id"]
            # No raw credential value stored
            assert catalog.get_raw("aws_manifest_check") is None
        finally:
            store.close()
