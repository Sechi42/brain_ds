"""Semantic verifier prompt and grant contract tests."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = REPO_ROOT / "prompts" / "brainds-semantic-verifier.md"
AGENT_PATH = REPO_ROOT / ".claude" / "agents" / "brainds-semantic-verifier.md"


def _frontmatter_tools(agent_text: str) -> set[str]:
    tools: set[str] = set()
    in_tools = False
    for line in agent_text.splitlines():
        stripped = line.strip()
        if stripped == "---" and tools:
            break
        if stripped == "tools:":
            in_tools = True
            continue
        if in_tools and stripped.startswith("- "):
            tools.add(stripped[2:].strip())
            continue
        if in_tools and stripped and not stripped.startswith("-"):
            in_tools = False
    return tools


def test_semantic_verifier_prompt_grants_edge_snapshot_and_rubric() -> None:
    prompt = PROMPT_PATH.read_text(encoding="utf-8")

    assert "snapshot_edges(graph_id" in prompt
    assert "edge_id" in prompt
    assert "cited_evidence_ids" in prompt
    for verdict in ("supported", "unsupported", "contradicted", "insufficient_evidence"):
        assert verdict in prompt
    for dimension in ("edge_compatibility", "edge_semantics", "edge_evidence", "edge_calibration"):
        assert dimension in prompt


def test_semantic_verifier_agent_is_read_only_with_snapshot_edges() -> None:
    if not AGENT_PATH.exists():
        return

    agent = AGENT_PATH.read_text(encoding="utf-8")
    tools = _frontmatter_tools(agent)

    assert "mcp__brain_ds__snapshot_edges" in tools
    for mutation_tool in (
        "mcp__brain_ds__update_node",
        "mcp__brain_ds__add_edge",
        "mcp__brain_ds__delete_node",
        "mcp__brain_ds__delete_edge",
    ):
        assert mutation_tool not in tools
    assert "snapshot_edges(graph_id" in agent
    assert "Do NOT write to the graph" in agent
