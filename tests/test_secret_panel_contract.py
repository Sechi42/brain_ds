from __future__ import annotations

from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
SECRET_PANEL = ROOT / "brain_ds" / "ui" / "src" / "panels" / "secret-panel.ts"
GRAPH_VIEWER = ROOT / "brain_ds" / "ui" / "templates" / "graph_viewer.html"
SECRET_SCHEMA = ROOT / "brain_ds" / "connectors" / "secrets" / "schema.json"
PLAYWRIGHT_CONFIG = ROOT / "brain_ds" / "ui" / "playwright.config.ts"


def _source() -> str:
    return SECRET_PANEL.read_text(encoding="utf-8")


def test_secret_panel_renders_permission_empty_and_ready_states_distinctly() -> None:
    source = _source()
    for token in ("permission_denied", "Permisos insuficientes", "_listStatus === 'empty'", "No hay secretos configurados en este workspace.", "_listStatus === 'ready'"):
        assert token in source


def test_secret_panel_omits_self_declared_admin_scope_and_shows_safe_probe_status() -> None:
    source = _source()
    for token in ("probe=true", "validation", "Validación segura OK", "data-secret-handle", "textContent = message"):
        assert token in source
    assert "agent_scope=workspace_admin" not in source
    assert "innerHTML = message" not in source


def test_secret_panel_add_secret_return_does_not_assign_undefined_optional_validation() -> None:
    source = _source()
    assert "const validation = data.validation;" in source
    assert "if (validation !== undefined)" in source
    assert "validation: data.validation" not in source


def test_secret_panel_surfaces_safe_backend_error_detail_without_html_injection() -> None:
    source = _source()
    for token in (
        "interface SecretErrorResponse",
        "_safeBackendMessage",
        "data.detail",
        "data.detail.message",
        "data.message",
        "result.errorMessage",
        "textContent = message",
    ):
        assert token in source
    assert "innerHTML = message" not in source


def test_secret_panel_bind_action_patches_data_source_connection_descriptor() -> None:
    source = _source()
    for token in (
        "dataSources?: SecretBindableDataSource[]",
        "_bindSecretToDataSource",
        "_apiUrl('/nodes/')",
        "method: 'PATCH'",
        "details: { connection: descriptor }",
        "secret_handle",
    ):
        assert token in source


def test_secret_panel_bind_ui_exposes_explicit_now_explorable_transition() -> None:
    source = _source()
    for token in (
        "data-bind-secret-handle",
        "data-bind-source-id",
        "now explorable",
        "aria-live=\"polite\"",
    ):
        assert token in source


def test_graph_viewer_passes_data_sources_to_secret_panel_mount() -> None:
    source = GRAPH_VIEWER.read_text(encoding="utf-8")
    for token in (
        "secretDataSources",
        "type === 'Data Source'",
        "dataSources: secretDataSources",
    ):
        assert token in source


def test_google_sheets_schema_asks_for_upload_friendly_sheet_url_not_aws_fields() -> None:
    schema = json.loads(SECRET_SCHEMA.read_text(encoding="utf-8"))
    contract = schema["provider_kinds"]["google-sheets-json"]

    assert contract["ui_fields"]["spreadsheet_url"] == "string"
    assert contract["ui_fields"] == {"spreadsheet_url": "string", "sheet_range": "string"}
    assert "secret_id" not in contract["types"]
    assert "region" not in contract["types"]
    assert "service_account_ref" not in contract["required"]
    assert "spreadsheet_id" in contract["required"]
    assert contract["raw_value_label"] == "Google service-account JSON"
    assert contract["raw_value_placeholder"].startswith('{"type":"service_account"')


def test_secret_panel_uploads_google_service_account_json_without_rendering_private_key() -> None:
    source = _source()

    for token in (
        "raw_value_label",
        "raw_value_placeholder",
        "textarea",
        "google-sheets-json",
        "_kindSupportsProbe(kind: string): boolean",
        "kind === 'google-sheets-json'",
    ):
        assert token in source

    assert "Valor de credencial" not in source
    assert "aws-google-sheets" not in source.split("function _kindSupportsProbe", maxsplit=1)[1].split("}", maxsplit=1)[0]
    assert "private_key" not in source


def test_secret_panel_does_not_interpolate_handle_into_inner_html_attributes() -> None:
    source = _source()
    render_list = source.split("function _renderList", maxsplit=1)[1].split("function _renderKindOptions", maxsplit=1)[0]

    assert "_safeDomIdToken(handle.handle)" in render_list
    assert "summary?.setAttribute('aria-label'" in render_list
    assert "detailBody.id = summaryId" in render_list
    assert "removeBtn?.setAttribute('aria-label'" in render_list
    assert "aria-label=\"Mostrar detalles de ${handle.handle}\"" not in render_list
    assert "id=\"${summaryId}\"" not in render_list


def test_secret_panel_escapes_array_metadata_before_inner_html_rendering() -> None:
    source = _source()
    render_meta = source.split("function _renderMeta", maxsplit=1)[1].split("// ── API", maxsplit=1)[0]

    assert "Array.isArray(value)" in render_meta
    assert "value.map((item) => _escapeHtml(item)).join(', ')" in render_meta
    assert "value.join(', ')" not in render_meta


def test_google_sheets_schema_marks_spreadsheet_id_as_derived_from_url() -> None:
    schema = json.loads(SECRET_SCHEMA.read_text(encoding="utf-8"))
    contract = schema["provider_kinds"]["google-sheets-json"]

    assert contract["metadata_derivations"] == {"spreadsheet_id": "spreadsheet_url"}
    assert "parsed from spreadsheet_url" in contract["descriptions"]["spreadsheet_id"]


def test_playwright_config_forbids_committed_only_tests_in_ci() -> None:
    source = PLAYWRIGHT_CONFIG.read_text(encoding="utf-8")

    assert "forbidOnly: !!process.env.CI" in source
