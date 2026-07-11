"""T2.1 — TDD tests for provider-scoped raw_value validation in routes.py.

These tests are RED until T2.5 is implemented.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from brain_ds.api.events import EventBus
from brain_ds.api.server import create_app
from brain_ds.connectors.secrets import SecretCatalog, SecretEntry
from brain_ds.connectors.secrets.binding_store import SecretBindingRecord, SecretBindingStore
from brain_ds.connectors.secrets.providers import AwsSecretsAdapter
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
    app = create_app(project_root=tmp_path, store=store, event_bus=EventBus())
    app.state.secret_admin_enabled = True
    return TestClient(app)


def _non_admin_api_client(store: GraphStore, tmp_path: Path) -> TestClient:
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

_GSHEETS_URL = "https://docs.google.com/spreadsheets/d/1oVc-jvWV1s-0dW8YNK3nlK-vn3pLF5kInnHWqRWt5Ig/edit?gid=242408990#gid=242408990"
_GSHEETS_PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----\nAPI_SENTINEL_PRIVATE_KEY\n-----END PRIVATE KEY-----\n"
_GSHEETS_CLIENT_EMAIL = "api-sentinel@example.iam.gserviceaccount.com"


def _seed_google_sheets_secret(tmp_path: Path, handle: str = "topete_final") -> None:
    catalog = SecretCatalog(tmp_path)
    catalog.add(
        SecretEntry(
            handle=handle,
            kind="google-sheets-json",
            metadata={
                "spreadsheet_id": "raw-spreadsheet-id",
                "sheet_range": "ERP!A1:Z",
                "credential_type": "service_account",
                "project_id": "topete-project",
                "email_fingerprint": "email-fp",
                "key_id_fingerprint": "key-fp",
                "universe_domain": "googleapis.com",
            },
        ),
        raw_value=_service_account_json(),
    )


def _service_account_json() -> str:
    return json.dumps(
        {
            "type": "service_account",
            "project_id": "api-project",
            "private_key_id": "api-key-id",
            "private_key": _GSHEETS_PRIVATE_KEY,
            "client_email": _GSHEETS_CLIENT_EMAIL,
            "client_id": "1234567890",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/api-sentinel",
            "universe_domain": "googleapis.com",
        }
    )


class TestProviderScopedRawValueValidation:
    """T2.1 — provider-scoped raw_value: aws empty/absent ACCEPTED; pg/ss REJECTED."""

    def test_aws_secrets_empty_raw_value_accepted(self, tmp_path: Path) -> None:
        """POST aws-secrets with raw_value='' must succeed (HTTP 200/201)."""
        store = _store_with_graph(tmp_path)
        try:
            client = _api_client(store, tmp_path)
            resp = client.post(
                "/api/secrets?graph_id=g1&agent_scope=workspace_admin",
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
                "/api/secrets?graph_id=g1&agent_scope=workspace_admin",
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
                "/api/secrets?graph_id=g1&agent_scope=workspace_admin",
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
                "/api/secrets?graph_id=g1&agent_scope=workspace_admin",
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
                "/api/secrets?graph_id=g1&agent_scope=workspace_admin",
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
                "/api/secrets?graph_id=g1&agent_scope=workspace_admin",
                json={
                    "handle": "aws_prod",
                    "kind": "aws-secrets",
                    "metadata": _AWS_META,
                },
            )
            assert post_resp.status_code in (200, 201), post_resp.text

            # List: handle present, no raw secret material
            list_resp = client.get("/api/secrets?graph_id=g1&agent_scope=workspace_admin")
            assert list_resp.status_code == 200
            data = list_resp.json()
            handles = {h["handle"] for h in data["handles"]}
            assert "aws_prod" in handles

            # Confirm no raw secret material leaks in response
            response_text = list_resp.text
            aws_entry = next(h for h in data["handles"] if h["handle"] == "aws_prod")
            assert aws_entry["kind"] == "aws-secrets"
            # Secret identifiers are redacted in API list responses, not echoed raw.
            assert aws_entry["metadata"]["secret_id"] == "***"
            assert _AWS_META["secret_id"] not in response_text
            # raw_value must NOT appear in the response body as a field
            assert "raw_value" not in response_text
        finally:
            store.close()


class TestNodePatchSecretMutationGuard:
    def test_patch_node_strips_secret_binding_and_connector_spoof_fields(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            store.upsert_node(
                "g1",
                {
                    "id": "DS-1",
                    "label": "ERP Source",
                    "type": "Data Source",
                    "details": {"owner": "ops"},
                },
            )
            client = _api_client(store, tmp_path)

            resp = client.patch(
                "/api/nodes/DS-1",
                json={
                    "graph_id": "g1",
                    "changes": {
                        "details": {
                            "description": "safe edit",
                            "secret_binding": {
                                "secret_ref": "sec_topete",
                                "validation_status": "valid",
                            },
                            "connection": {
                                "kind": "google_sheets",
                                "secret_handle": "topete_final",
                                "spreadsheet_id": "real-spreadsheet-id",
                            },
                            "provider_inputs": {"spreadsheet_ref": "sheet-alias"},
                            "validation": {"validated_at": "spoofed"},
                            "validation_status": "valid",
                            "secret_ref": "sec_topete",
                            "notes": {
                                "summary": "allowed nested note",
                                "spreadsheet_id": "nested-real-spreadsheet-id",
                            },
                        },
                        "validation_status": "valid",
                        "secret_ref": "sec_topete",
                    },
                },
            )

            assert resp.status_code == 200, resp.text
            details = resp.json()["node"]["details"]
            assert details == {
                "owner": "ops",
                "description": "safe edit",
                "notes": {"summary": "allowed nested note"},
            }
            assert "validation_status" not in resp.text
            assert "real-spreadsheet-id" not in resp.text
            assert "nested-real-spreadsheet-id" not in resp.text
            assert "topete_final" not in resp.text
        finally:
            store.close()


class TestSourceConnectionApiFlow:
    def test_api_source_connection_status_exposes_lifecycle_without_raw_identifiers(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            _seed_google_sheets_secret(tmp_path)
            store.upsert_node(
                "g1",
                {
                    "id": "DS-ERP",
                    "label": "ERP 2025",
                    "type": "Data Source",
                    "details": {"source_kind": "google-sheets"},
                },
            )
            client = _api_client(store, tmp_path)

            unbound = client.get("/api/source-connections/status?graph_id=g1&source_node_id=DS-ERP")
            assert unbound.status_code == 200
            assert unbound.json()["binding"] == {
                "validation_status": "unbound",
                "documentation_status": "not_started",
                "writeback_status": "idle",
                "requires_binding": True,
            }

            secret_ref = client.get("/api/source-connections/candidates?graph_id=g1&source_node_id=DS-ERP").json()["secrets"][0]["secret_ref"]
            SecretBindingStore(tmp_path).upsert(
                SecretBindingRecord(
                    graph_id="g1",
                    source_node_id="DS-ERP",
                    secret_ref_alias=secret_ref,
                    internal_secret_id="topete_final",
                    provider_kind="google-sheets-json",
                    provider_inputs={"spreadsheet_ref": "erp-2025"},
                    provider_mapping={"spreadsheet_id": "raw-spreadsheet-id"},
                    validation_status="valid",
                    documentation_status="documented",
                    writeback_status="written",
                    validation={"validated_at": "2026-07-03T00:00:00Z", "error_code": None},
                )
            )

            bound = client.get("/api/source-connections/status?graph_id=g1&source_node_id=DS-ERP")
            assert bound.status_code == 200
            payload = bound.json()["binding"]
            assert payload["validation_status"] == "valid"
            assert payload["documentation_status"] == "documented"
            assert payload["writeback_status"] == "written"
            assert payload["provider_inputs"] == {"spreadsheet_ref": "erp-2025"}
            assert "raw-spreadsheet-id" not in bound.text
            assert "topete_final" not in bound.text
            assert "secret_handle" not in bound.text
            assert "provider_secret_id" not in bound.text
        finally:
            store.close()

    def test_api_source_first_bind_validate_status_unbind_returns_redacted_errors(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = _store_with_graph(tmp_path)
        try:
            _seed_google_sheets_secret(tmp_path)
            store.upsert_node(
                "g1",
                {
                    "id": "DS-ERP",
                    "label": "ERP 2025",
                    "type": "Data Source",
                    "details": {"source_kind": "google-sheets"},
                },
            )
            client = _api_client(store, tmp_path)

            candidate_resp = client.get("/api/source-connections/candidates?graph_id=g1&source_node_id=DS-ERP")
            assert candidate_resp.status_code == 200, candidate_resp.text
            secret_ref = candidate_resp.json()["secrets"][0]["secret_ref"]
            assert "topete_final" not in candidate_resp.text
            assert "raw-spreadsheet-id" not in candidate_resp.text

            bind_resp = client.post(
                "/api/source-connections/bind?graph_id=g1",
                json={"source_node_id": "DS-ERP", "secret_ref": secret_ref, "provider_inputs": {"spreadsheet_ref": "erp-2025"}},
            )
            assert bind_resp.status_code == 200, bind_resp.text
            assert bind_resp.json()["binding"]["validation_status"] == "unvalidated"

            from brain_ds.connectors.secrets.providers import google_sheets as google_sheets_provider

            def _fail_probe(_self, _handle, _metadata):
                raise RuntimeError("permission denied raw-spreadsheet-id topete_final private_key")

            monkeypatch.setattr(google_sheets_provider.GoogleSheetsJsonAdapter, "probe", _fail_probe)
            failed_validate = client.post("/api/source-connections/validate?graph_id=g1", json={"source_node_id": "DS-ERP"})
            assert failed_validate.status_code == 422
            failed_body = failed_validate.json()["detail"]
            assert failed_body["error_code"] == "validation_failed"
            assert failed_body["retryable"] is True
            assert "raw-spreadsheet-id" not in failed_validate.text
            assert "topete_final" not in failed_validate.text
            assert "private_key" not in failed_validate.text

            monkeypatch.setattr(
                google_sheets_provider.GoogleSheetsJsonAdapter,
                "probe",
                lambda _self, _handle, _metadata: {"spreadsheet_id": "raw-spreadsheet-id"},
            )
            validate_resp = client.post("/api/source-connections/validate?graph_id=g1", json={"source_node_id": "DS-ERP"})
            assert validate_resp.status_code == 200, validate_resp.text
            assert validate_resp.json()["binding"]["validation_status"] == "valid"

            status_resp = client.get("/api/source-connections/status?graph_id=g1&source_node_id=DS-ERP")
            assert status_resp.status_code == 200
            assert status_resp.json()["binding"]["validation_status"] == "valid"

            unbind_resp = client.post("/api/source-connections/unbind?graph_id=g1", json={"source_node_id": "DS-ERP"})
            assert unbind_resp.status_code == 200
            assert unbind_resp.json()["binding"] == {
                "validation_status": "unbound",
                "documentation_status": "not_started",
                "writeback_status": "idle",
                "requires_binding": True,
            }
            assert SecretBindingStore(tmp_path).get("g1", "DS-ERP") is None
        finally:
            store.close()

    def test_api_secret_first_candidates_authorization_and_invalid_provider_input(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            _seed_google_sheets_secret(tmp_path)
            store.upsert_node(
                "g1",
                {"id": "DS-ERP", "label": "ERP 2025", "type": "Data Source", "details": {"source_kind": "google-sheets"}},
            )
            admin = _api_client(store, tmp_path)
            secret_ref = admin.get("/api/source-connections/candidates?graph_id=g1&source_node_id=DS-ERP").json()["secrets"][0]["secret_ref"]

            denied = _non_admin_api_client(store, tmp_path).post(
                "/api/source-connections/bind?graph_id=g1",
                json={"source_node_id": "DS-ERP", "secret_ref": secret_ref, "provider_inputs": {"spreadsheet_ref": "erp-2025"}},
            )
            assert denied.status_code == 403
            assert denied.json()["error_code"] == "unauthorized"
            assert "topete_final" not in denied.text

            invalid = admin.post(
                "/api/source-connections/bind?graph_id=g1",
                json={"source_node_id": "DS-ERP", "secret_ref": secret_ref, "provider_inputs": {"spreadsheet_ref": ""}},
            )
            assert invalid.status_code == 422
            assert invalid.json()["detail"]["error_code"] == "invalid_provider_input"
            assert "raw-spreadsheet-id" not in invalid.text

            sources = admin.get(f"/api/source-connections/candidates?graph_id=g1&secret_ref={secret_ref}")
            assert sources.status_code == 200
            assert sources.json()["sources"] == [
                {"graph_id": "g1", "node_id": "DS-ERP", "label": "ERP 2025", "provider_kind": "google-sheets-json", "validation_status": "unbound"}
            ]
            assert "topete_final" not in sources.text
        finally:
            store.close()

    def test_api_redacts_not_allowlisted_missing_mapping_and_revalidation_required(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            _seed_google_sheets_secret(tmp_path)
            admin = _api_client(store, tmp_path)
            store.upsert_node(
                "g1",
                {
                    "id": "DS-ERP",
                    "label": "ERP 2025 raw-spreadsheet-id topete_final",
                    "type": "Data Source",
                    "details": {"source_kind": "google-sheets"},
                },
            )
            allowed_secret_ref = admin.get("/api/source-connections/candidates?graph_id=g1&source_node_id=DS-ERP").json()["secrets"][0]["secret_ref"]
            store.upsert_node(
                "g1",
                {
                    "id": "DS-CSV",
                    "label": "CSV export raw-spreadsheet-id topete_final",
                    "type": "Data Source",
                    "details": {"source_kind": "csv"},
                },
            )
            secret_ref = admin.get("/api/source-connections/candidates?graph_id=g1&source_node_id=DS-CSV").json()["secrets"]
            assert secret_ref == []

            not_allowlisted = admin.post(
                "/api/source-connections/bind?graph_id=g1",
                json={
                    "source_node_id": "DS-CSV",
                    "secret_ref": allowed_secret_ref,
                    "provider_inputs": {"spreadsheet_ref": "erp-2025"},
                },
            )
            assert not_allowlisted.status_code == 404
            assert not_allowlisted.json()["detail"]["error_code"] == "not_allowlisted"
            assert "raw-spreadsheet-id" not in not_allowlisted.text
            assert "topete_final" not in not_allowlisted.text

            missing_mapping = admin.post("/api/source-connections/validate?graph_id=g1", json={"source_node_id": "DS-ERP"})
            assert missing_mapping.status_code == 409
            assert missing_mapping.json()["detail"]["error_code"] == "missing_private_mapping"
            assert "raw-spreadsheet-id" not in missing_mapping.text
            assert "topete_final" not in missing_mapping.text

            SecretBindingStore(tmp_path).upsert(
                SecretBindingRecord(
                    graph_id="g1",
                    source_node_id="DS-ERP",
                    secret_ref_alias="sec_orphaned_raw-spreadsheet-id_topete_final",
                    internal_secret_id="deleted_topete_final",
                    provider_kind="google-sheets-json",
                    provider_inputs={"spreadsheet_ref": "erp-2025"},
                )
            )
            revalidation_required = admin.post("/api/source-connections/validate?graph_id=g1", json={"source_node_id": "DS-ERP"})
            assert revalidation_required.status_code == 409
            assert revalidation_required.json()["detail"]["error_code"] == "revalidation_required"
            assert "deleted_topete_final" not in revalidation_required.text
            assert "raw-spreadsheet-id" not in revalidation_required.text
            assert "topete_final" not in revalidation_required.text
        finally:
            store.close()


class TestGoogleSheetsServiceAccountUpload:
    """Slice 1 — uploaded Google service-account JSON is stored only as a secret value."""

    def test_google_sheets_upload_returns_redacted_metadata_and_stores_raw_only_in_values(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from brain_ds.connectors.secrets.providers import google_sheets as google_sheets_provider

        captured_service_accounts: list[dict[str, object]] = []

        class SuccessfulSheetsService:
            def spreadsheets(self):
                return self

            def get(self, **_kwargs):
                return self

            def execute(self):
                return {"spreadsheetId": "1oVc-jvWV1s-0dW8YNK3nlK-vn3pLF5kInnHWqRWt5Ig", "properties": {"title": "Budget"}}

        store = _store_with_graph(tmp_path)
        try:
            monkeypatch.setattr(
                google_sheets_provider,
                "_build_sheets_service",
                lambda service_account: captured_service_accounts.append(service_account) or SuccessfulSheetsService(),
            )
            client = _api_client(store, tmp_path)

            resp = client.post(
                "/api/secrets?graph_id=g1&agent_scope=workspace_admin&probe=true",
                json={
                    "handle": "gsheets_budget",
                    "kind": "google-sheets-json",
                    "metadata": {"spreadsheet_url": _GSHEETS_URL, "sheet_range": "Sheet1!A1:Z"},
                    "raw_value": _service_account_json(),
                },
            )

            assert resp.status_code == 201, resp.text
            assert len(captured_service_accounts) == 1
            assert captured_service_accounts[0]["private_key"] == _GSHEETS_PRIVATE_KEY
            assert captured_service_accounts[0]["client_email"] == _GSHEETS_CLIENT_EMAIL
            serialized_response = resp.text
            assert _GSHEETS_PRIVATE_KEY not in serialized_response
            assert _GSHEETS_CLIENT_EMAIL not in serialized_response
            assert "private_key" not in serialized_response
            assert "client_email" not in serialized_response

            list_resp = client.get("/api/secrets?graph_id=g1&agent_scope=workspace_admin")
            assert list_resp.status_code == 200
            serialized_list = list_resp.text
            assert _GSHEETS_PRIVATE_KEY not in serialized_list
            assert _GSHEETS_CLIENT_EMAIL not in serialized_list
            assert "private_key" not in serialized_list
            assert "client_email" not in serialized_list

            manifest_text = (tmp_path / ".brain_ds" / "secrets.json").read_text(encoding="utf-8")
            assert _GSHEETS_PRIVATE_KEY not in manifest_text
            assert _GSHEETS_CLIENT_EMAIL not in manifest_text
            assert "client_email" not in manifest_text

            values_text = (tmp_path / ".brain_ds" / "secrets.values.json").read_text(encoding="utf-8")
            assert "API_SENTINEL_PRIVATE_KEY" in values_text
            assert _GSHEETS_CLIENT_EMAIL in values_text
        finally:
            store.close()

    def test_query_param_workspace_admin_cannot_escalate_secret_access(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            client = _non_admin_api_client(store, tmp_path)

            resp = client.get("/api/secrets?graph_id=g1&agent_scope=workspace_admin")

            assert resp.status_code == 403
            body = resp.json()
            assert body["status"] == "permission_denied"
            assert "handles" not in body
        finally:
            store.close()

    def test_google_sheets_upload_rejects_user_oauth_payload_without_creating_handle(
        self, tmp_path: Path
    ) -> None:
        store = _store_with_graph(tmp_path)
        try:
            client = _api_client(store, tmp_path)
            credential = json.loads(_service_account_json())
            credential["type"] = "authorized_user"

            resp = client.post(
                "/api/secrets?graph_id=g1&agent_scope=workspace_admin",
                json={
                    "handle": "gsheets_bad",
                    "kind": "google-sheets-json",
                    "metadata": {"spreadsheet_url": _GSHEETS_URL, "sheet_range": "Sheet1!A1:Z"},
                    "raw_value": json.dumps(credential),
                },
            )

            assert resp.status_code == 422
            assert "type" in resp.text
            assert _GSHEETS_PRIVATE_KEY not in resp.text
            assert _GSHEETS_CLIENT_EMAIL not in resp.text
            list_resp = client.get("/api/secrets?graph_id=g1&agent_scope=workspace_admin")
            assert list_resp.json()["handles"] == []
        finally:
            store.close()

    def test_google_sheets_upload_rejects_bad_spreadsheet_url_without_leaking_secret(
        self, tmp_path: Path
    ) -> None:
        store = _store_with_graph(tmp_path)
        try:
            client = _api_client(store, tmp_path)

            resp = client.post(
                "/api/secrets?graph_id=g1&agent_scope=workspace_admin&probe=true",
                json={
                    "handle": "gsheets_bad_url",
                    "kind": "google-sheets-json",
                    "metadata": {
                        "spreadsheet_url": "https://docs.google.com/document/d/not-a-sheet/edit",
                        "sheet_range": "Sheet1!A1:Z",
                    },
                    "raw_value": _service_account_json(),
                },
            )

            assert resp.status_code == 422
            assert "spreadsheet_url" in resp.text
            assert _GSHEETS_PRIVATE_KEY not in resp.text
            assert _GSHEETS_CLIENT_EMAIL not in resp.text
            assert "private_key" not in resp.text
            assert "client_email" not in resp.text

            list_resp = client.get("/api/secrets?graph_id=g1&agent_scope=workspace_admin")
            assert list_resp.status_code == 200
            assert list_resp.json()["handles"] == []
        finally:
            store.close()

    def test_google_sheets_probe_failure_returns_safe_error_without_leaking_secret(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from brain_ds.connectors.secrets.providers import google_sheets as google_sheets_provider

        class FailingSheetsService:
            def spreadsheets(self):
                return self

            def get(self, **_kwargs):
                return self

            def execute(self):
                raise RuntimeError(
                    f"permission denied for {_GSHEETS_PRIVATE_KEY} {_GSHEETS_CLIENT_EMAIL} private_key client_email"
                )

        store = _store_with_graph(tmp_path)
        try:
            monkeypatch.setattr(
                google_sheets_provider,
                "_build_sheets_service",
                lambda _service_account: FailingSheetsService(),
            )
            client = _api_client(store, tmp_path)

            resp = client.post(
                "/api/secrets?graph_id=g1&agent_scope=workspace_admin&probe=true",
                json={
                    "handle": "gsheets_denied",
                    "kind": "google-sheets-json",
                    "metadata": {"spreadsheet_url": _GSHEETS_URL, "sheet_range": "Sheet1!A1:Z"},
                    "raw_value": _service_account_json(),
                },
            )

            assert resp.status_code == 422, resp.text
            assert "Google Sheets probe failed" in resp.text

            serialized_response = resp.text
            assert _GSHEETS_PRIVATE_KEY not in serialized_response
            assert _GSHEETS_CLIENT_EMAIL not in serialized_response
            assert "private_key" not in serialized_response
            assert "client_email" not in serialized_response

            list_resp = client.get("/api/secrets?graph_id=g1")
            assert list_resp.status_code == 200
            assert list_resp.json()["handles"] == []
            assert not (tmp_path / ".brain_ds" / "secrets.values.json").exists()
        finally:
            store.close()

    def test_google_sheets_permission_probe_failure_returns_fix_forward_message(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from brain_ds.connectors.secrets.providers import google_sheets as google_sheets_provider

        class PermissionDenied(Exception):
            status_code = 403

        class FailingSheetsService:
            def spreadsheets(self):
                return self

            def get(self, **_kwargs):
                return self

            def execute(self):
                raise PermissionDenied("PERMISSION_DENIED private_key client_email")

        store = _store_with_graph(tmp_path)
        try:
            monkeypatch.setattr(
                google_sheets_provider,
                "_build_sheets_service",
                lambda _service_account: FailingSheetsService(),
            )
            client = _api_client(store, tmp_path)

            resp = client.post(
                "/api/secrets?graph_id=g1&probe=true",
                json={
                    "handle": "gsheets_permission_denied",
                    "kind": "google-sheets-json",
                    "metadata": {"spreadsheet_url": _GSHEETS_URL, "sheet_range": "Sheet1!A1:Z"},
                    "raw_value": _service_account_json(),
                },
            )

            assert resp.status_code == 422, resp.text
            assert "share the spreadsheet" in resp.text
            assert "retry later" not in resp.text.lower()
            assert _GSHEETS_PRIVATE_KEY not in resp.text
            assert "private_key" not in resp.text
        finally:
            store.close()

    def test_google_sheets_raw_upload_cannot_use_legacy_service_account_ref_bypass(
        self, tmp_path: Path
    ) -> None:
        store = _store_with_graph(tmp_path)
        try:
            client = _api_client(store, tmp_path)

            resp = client.post(
                "/api/secrets?graph_id=g1",
                json={
                    "handle": "gsheets_legacy_bypass",
                    "kind": "google-sheets-json",
                    "metadata": {
                        "spreadsheet_url": _GSHEETS_URL,
                        "spreadsheet_id": "1oVc-jvWV1s-0dW8YNK3nlK-vn3pLF5kInnHWqRWt5Ig",
                        "sheet_range": "Sheet1!A1:Z",
                        "service_account_ref": "BRAINDS_LEGACY_GOOGLE_SA",
                    },
                    "raw_value": _service_account_json(),
                },
            )

            assert resp.status_code == 422
            assert "service_account_ref" in resp.text
            assert _GSHEETS_PRIVATE_KEY not in resp.text
            assert _GSHEETS_CLIENT_EMAIL not in resp.text

            list_resp = client.get("/api/secrets?graph_id=g1")
            assert list_resp.status_code == 200
            assert list_resp.json()["handles"] == []
        finally:
            store.close()


class TestSecretAdminGateAndValidationStatus:
    """PR1 — secret API exposes explicit admin/empty/validation states."""

    def _audit_count(self, store: GraphStore) -> int:
        row = store.conn.execute("SELECT COUNT(*) FROM tools_audit").fetchone()
        return int(row[0])

    def test_list_secrets_requires_workspace_admin_scope(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            client = _non_admin_api_client(store, tmp_path)
            before = self._audit_count(store)

            resp = client.get("/api/secrets?graph_id=g1")

            assert resp.status_code == 403
            body = resp.json()
            assert body["status"] == "permission_denied"
            assert "workspace_admin" in body["detail"]
            assert "handles" not in body
            row = store.conn.execute(
                "SELECT tool_name, result_status, input_hash FROM tools_audit ORDER BY id DESC LIMIT 1"
            ).fetchone()
            assert self._audit_count(store) == before + 1
            assert tuple(row[:2]) == ("api_list_secrets", "error")
            assert _AWS_META["secret_id"] not in json.dumps(tuple(row))
        finally:
            store.close()

    def test_non_admin_cannot_probe_even_with_workspace_admin_query_param(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            client = _non_admin_api_client(store, tmp_path)
            before = self._audit_count(store)

            resp = client.post(
                "/api/secrets/validate?graph_id=g1&handle=warehouse_ro&agent_scope=workspace_admin"
            )

            assert resp.status_code == 403
            body = resp.json()
            assert body["status"] == "permission_denied"
            assert "handle" not in body
            row = store.conn.execute(
                "SELECT tool_name, result_status, input_hash FROM tools_audit ORDER BY id DESC LIMIT 1"
            ).fetchone()
            assert self._audit_count(store) == before + 1
            assert tuple(row[:2]) == ("api_validate_secret", "error")
        finally:
            store.close()

    def test_non_admin_cannot_create_even_with_workspace_admin_query_param(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            client = _non_admin_api_client(store, tmp_path)
            before = self._audit_count(store)

            resp = client.post(
                "/api/secrets?graph_id=g1&agent_scope=workspace_admin",
                json={"handle": "aws_denied", "kind": "aws-secrets", "metadata": _AWS_META},
            )

            assert resp.status_code == 403
            assert resp.json()["status"] == "permission_denied"
            assert not (tmp_path / ".brain_ds" / "secrets.json").exists()
            row = store.conn.execute(
                "SELECT tool_name, result_status, input_hash FROM tools_audit ORDER BY id DESC LIMIT 1"
            ).fetchone()
            assert self._audit_count(store) == before + 1
            assert tuple(row[:2]) == ("api_create_secret", "error")
            assert _AWS_META["secret_id"] not in json.dumps(tuple(row))
        finally:
            store.close()

    def test_non_admin_cannot_delete_even_with_workspace_admin_query_param(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            admin = _api_client(store, tmp_path)
            create_resp = admin.post(
                "/api/secrets?graph_id=g1",
                json={"handle": "aws_delete_guard", "kind": "aws-secrets", "metadata": _AWS_META},
            )
            assert create_resp.status_code == 201, create_resp.text
            client = _non_admin_api_client(store, tmp_path)
            before = self._audit_count(store)

            resp = client.delete(
                "/api/secrets/aws_delete_guard?graph_id=g1&agent_scope=workspace_admin"
            )

            assert resp.status_code == 403
            assert resp.json()["status"] == "permission_denied"
            list_resp = admin.get("/api/secrets?graph_id=g1")
            assert {item["handle"] for item in list_resp.json()["handles"]} == {"aws_delete_guard"}
            row = store.conn.execute(
                "SELECT tool_name, result_status, input_hash FROM tools_audit ORDER BY id DESC LIMIT 1"
            ).fetchone()
            assert self._audit_count(store) == before + 1
            assert tuple(row[:2]) == ("api_delete_secret", "error")
        finally:
            store.close()

    def test_retryable_google_probe_failure_returns_safe_machine_reason(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from brain_ds.connectors.secrets.providers import google_sheets as google_sheets_provider

        class RateLimited(Exception):
            status_code = 429

        class FailingSheetsService:
            def spreadsheets(self):
                return self

            def get(self, **_kwargs):
                return self

            def execute(self):
                raise RateLimited("quota exhausted private_key client_email")

        store = _store_with_graph(tmp_path)
        try:
            monkeypatch.setattr(
                google_sheets_provider,
                "_build_sheets_service",
                lambda _service_account: FailingSheetsService(),
            )
            client = _api_client(store, tmp_path)

            resp = client.post(
                "/api/secrets?graph_id=g1&probe=true",
                json={
                    "handle": "gsheets_retryable",
                    "kind": "google-sheets-json",
                    "metadata": {"spreadsheet_url": _GSHEETS_URL, "sheet_range": "Sheet1!A1:Z"},
                    "raw_value": _service_account_json(),
                },
            )

            assert resp.status_code == 422, resp.text
            body = resp.json()
            assert body["detail"]["reason"] == "retryable_provider_error"
            assert "retry later" in body["detail"]["message"].lower()
            assert _GSHEETS_PRIVATE_KEY not in resp.text
            assert "private_key" not in resp.text
        finally:
            store.close()

    def test_list_secrets_admin_empty_state_is_not_permission_denied(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            client = _api_client(store, tmp_path)

            resp = client.get("/api/secrets?graph_id=g1&agent_scope=workspace_admin")

            assert resp.status_code == 200
            assert resp.json() == {
                "graph_id": "g1",
                "status": "empty",
                "handles": [],
                "message": "No hay secretos configurados en este workspace.",
            }
        finally:
            store.close()

    def test_add_secret_returns_safe_probe_status_without_echoing_handle_or_secret_id(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = _store_with_graph(tmp_path)
        try:
            calls: list[tuple[str, dict[str, object]]] = []
            monkeypatch.setattr(
                AwsSecretsAdapter,
                "probe",
                lambda _self, handle, metadata: calls.append((handle, metadata)) or None,
            )
            client = _api_client(store, tmp_path)

            resp = client.post(
                "/api/secrets?graph_id=g1&agent_scope=workspace_admin&probe=true",
                json={
                    "handle": "aws_probe",
                    "kind": "aws-secrets",
                    "metadata": _AWS_META,
                },
            )

            assert resp.status_code == 201, resp.text
            body = resp.json()
            assert body["validation"] == {
                "status": "ok",
                "connection": "probed",
                "message": "Validación segura OK; la conexión respondió correctamente.",
            }
            assert calls == [("aws_probe", _AWS_META)]
            assert "aws_probe" not in body["validation"]["message"]
            assert _AWS_META["secret_id"] not in resp.text
        finally:
            store.close()

    def test_secret_create_and_delete_emit_secret_safe_audit_rows(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = _store_with_graph(tmp_path)
        try:
            monkeypatch.setattr(
                AwsSecretsAdapter,
                "probe",
                lambda _self, handle, metadata: None,
            )
            client = _api_client(store, tmp_path)
            before = self._audit_count(store)

            create_resp = client.post(
                "/api/secrets?graph_id=g1&probe=true",
                json={"handle": "aws_audited", "kind": "aws-secrets", "metadata": _AWS_META},
            )
            delete_resp = client.delete("/api/secrets/aws_audited?graph_id=g1")

            assert create_resp.status_code == 201, create_resp.text
            assert delete_resp.status_code == 204
            rows = store.conn.execute(
                "SELECT tool_name, result_status, input_hash FROM tools_audit ORDER BY id DESC LIMIT 2"
            ).fetchall()
            assert self._audit_count(store) == before + 2
            assert [(row[0], row[1]) for row in rows] == [
                ("api_delete_secret", "ok"),
                ("api_create_secret", "ok"),
            ]
            serialized_rows = json.dumps([tuple(row) for row in rows])
            assert _AWS_META["secret_id"] not in serialized_rows
        finally:
            store.close()

    def test_secret_create_validation_failure_emits_secret_safe_audit_row(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            client = _api_client(store, tmp_path)
            before = self._audit_count(store)

            resp = client.post(
                "/api/secrets?graph_id=g1",
                json={
                    "handle": "gsheets_bad_payload",
                    "kind": "google-sheets-json",
                    "metadata": {"spreadsheet_url": _GSHEETS_URL, "sheet_range": "Sheet1!A1:Z"},
                    "raw_value": json.dumps({"type": "authorized_user", "private_key": _GSHEETS_PRIVATE_KEY}),
                },
            )

            assert resp.status_code == 422
            row = store.conn.execute(
                "SELECT tool_name, result_status, input_hash FROM tools_audit ORDER BY id DESC LIMIT 1"
            ).fetchone()
            assert self._audit_count(store) == before + 1
            assert tuple(row[:2]) == ("api_create_secret", "error")
            serialized_row = json.dumps(tuple(row))
            assert _GSHEETS_PRIVATE_KEY not in serialized_row
            assert "private_key" not in serialized_row
        finally:
            store.close()

    def test_secret_probe_endpoint_emits_secret_safe_audit_row(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = _store_with_graph(tmp_path)
        try:
            monkeypatch.setattr(
                AwsSecretsAdapter,
                "probe",
                lambda _self, handle, metadata: None,
            )
            client = _api_client(store, tmp_path)
            client.post(
                "/api/secrets?graph_id=g1",
                json={"handle": "aws_probe_audited", "kind": "aws-secrets", "metadata": _AWS_META},
            )
            before = self._audit_count(store)

            resp = client.post("/api/secrets/validate?graph_id=g1&handle=aws_probe_audited")

            assert resp.status_code == 200, resp.text
            row = store.conn.execute(
                "SELECT tool_name, result_status, input_hash FROM tools_audit ORDER BY id DESC LIMIT 1"
            ).fetchone()
            assert self._audit_count(store) == before + 1
            assert tuple(row[:2]) == ("api_validate_secret", "ok")
            assert _AWS_META["secret_id"] not in json.dumps(tuple(row))
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
                "/api/secrets?graph_id=g1&agent_scope=workspace_admin",
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
