"""KPI composer prompt and curation-loop contract tests."""
from __future__ import annotations

from pathlib import Path

from brain_ds.mcp import grounding


REPO_ROOT = Path(__file__).resolve().parents[1]
CLAUDE_AGENT = REPO_ROOT / ".claude" / "agents" / "brainds-kpi-composer.md"
OPENCODE_PROMPT = REPO_ROOT / "prompts" / "brainds-kpi-composer.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_kpi_composer_is_standalone_registered_subagent_not_pipeline_stage() -> None:
    registered = grounding.DELEGATION_PROTOCOL["registered_subagents"]

    assert "brainds-kpi-composer" in registered
    assert registered["brainds-kpi-composer"]["tools"] == (
        "get_kpi_dossier",
        "suggest_connections",
        "insert_pending_question",
        "list_pending_confirmations",
        "resolve_confirmation",
        "add_edge",
    )
    pipeline_agents = {
        agent
        for stage in grounding.DELEGATION_PROTOCOL["pipeline_stages"]
        for agent in stage.get("agents", [])
    }
    assert "brainds-kpi-composer" not in pipeline_agents


def test_claude_agent_documents_human_confirmed_curation_round_trip() -> None:
    text = _read(CLAUDE_AGENT)

    for token in (
        "get_kpi_dossier",
        "suggest_connections",
        "insert_pending_question",
        "list_pending_confirmations",
        "resolve_confirmation",
        "add_edge",
        "measured-from",
        "depends-on",
    ):
        assert token in text

    assert "confirmed verdict" in text
    assert "rejected" in text
    assert "must not call `add_edge`" in text
    assert "DataField" in text
    assert "explicit human confirmation" in text


def test_opencode_prompt_mirrors_process_and_datafield_constraints() -> None:
    text = _read(OPENCODE_PROMPT)

    assert "Heuristic, Project, and Decision" in text
    assert "NOT a standalone Process" in text
    assert "DataContainer" in text
    assert "DataField" in text
    assert "explicit human confirmation" in text
    assert "confirmed verdict" in text
    assert "Rejected" in text
