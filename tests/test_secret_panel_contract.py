from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SECRET_PANEL = ROOT / "brain_ds" / "ui" / "src" / "panels" / "secret-panel.ts"


def _source() -> str:
    return SECRET_PANEL.read_text(encoding="utf-8")


def test_secret_panel_renders_permission_empty_and_ready_states_distinctly() -> None:
    source = _source()
    for token in ("permission_denied", "Permisos insuficientes", "_listStatus === 'empty'", "No hay secretos configurados en este workspace.", "_listStatus === 'ready'"):
        assert token in source


def test_secret_panel_submits_admin_scope_and_safe_probe_status_without_secret_echo() -> None:
    source = _source()
    for token in ("agent_scope=workspace_admin", "probe=true", "validation", "Validación segura OK", "data-secret-handle", "textContent = message"):
        assert token in source
    assert "innerHTML = message" not in source


def test_secret_panel_add_secret_return_does_not_assign_undefined_optional_validation() -> None:
    source = _source()
    assert "const validation = data.validation;" in source
    assert "if (validation !== undefined)" in source
    assert "validation: data.validation" not in source
