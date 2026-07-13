"""Tests for the LiveDelegationHarness / FakeDelegator seam.

The seam records every agent delegation at the artifact/prompt boundary,
enabling prompt-shape assertions without a live LLM or real Task invocation.

Scenarios covered (Spec C3, S3.1–S3.7):
- S3.1  FakeDelegator records DelegationCall with correct agent name
- S3.2  FakeDelegator records stage per call
- S3.3  Calls are recorded in pipeline order
- S3.4  Prompt includes all required artifact refs
- S3.5  intake datasource path routes to source-explorer then graph-mapper
- S3.6  intake human_org path routes to orchestrator then graph-mapper
- S3.7  dry_run_elicit_output fixture routes handoffs through FakeDelegator
"""

from __future__ import annotations

from tests.fixtures.delegation import FakeDelegator


# ---------------------------------------------------------------------------
# S3.1  FakeDelegator records DelegationCall with correct agent name
# ---------------------------------------------------------------------------

def test_fake_delegator_records_agent_name() -> None:
    delegator = FakeDelegator()
    delegator.delegate(agent="brainds-source-explorer", stage="intake", refs=["ref1.md"])
    assert len(delegator.calls) == 1
    assert delegator.calls[0].agent == "brainds-source-explorer"


# ---------------------------------------------------------------------------
# S3.2  FakeDelegator records stage per call
# ---------------------------------------------------------------------------

def test_fake_delegator_records_stage() -> None:
    delegator = FakeDelegator()
    delegator.delegate(agent="brainds-source-explorer", stage="intake", refs=["ref1.md"])
    assert delegator.calls[0].stage == "intake"


# ---------------------------------------------------------------------------
# S3.3  Calls are recorded in pipeline order
# ---------------------------------------------------------------------------

def test_fake_delegator_preserves_call_order() -> None:
    delegator = FakeDelegator()
    delegator.delegate(agent="brainds-source-explorer", stage="intake", refs=["a.md"])
    delegator.delegate(agent="brainds-graph-mapper", stage="intake", refs=["b.md"])
    delegator.delegate(agent="brainds-connection-mapper", stage="map", refs=["c.md"])
    delegator.delegate(agent="brainds-brd-writer", stage="brd", refs=["d.md"])

    assert [c.agent for c in delegator.calls] == [
        "brainds-source-explorer",
        "brainds-graph-mapper",
        "brainds-connection-mapper",
        "brainds-brd-writer",
    ]
    assert [c.stage for c in delegator.calls] == ["intake", "intake", "map", "brd"]


# ---------------------------------------------------------------------------
# S3.4  Prompt includes all required artifact refs
# ---------------------------------------------------------------------------

def test_delegation_call_prompt_contains_refs() -> None:
    delegator = FakeDelegator()
    delegator.delegate(
        agent="brainds-graph-mapper",
        stage="map",
        refs=["source-docs-acme-2026-06-14.md", "map-acme-2026-06-14.md"],
    )
    call = delegator.calls[0]
    assert "source-docs-acme-2026-06-14.md" in call.prompt
    assert "map-acme-2026-06-14.md" in call.prompt


# ---------------------------------------------------------------------------
# S3.5  intake datasource path — correct agent sequence
# ---------------------------------------------------------------------------

def test_intake_datasource_routing() -> None:
    """datasource intake must route through source-explorer then graph-mapper."""
    from brain_ds.mcp.grounding import PIPELINE_STAGES

    intake_stage = next(s for s in PIPELINE_STAGES if s["stage"] == "intake")
    datasource_agents = intake_stage["intake_paths"]["datasource"]  # type: ignore[index]

    delegator = FakeDelegator()
    for agent in datasource_agents:
        delegator.delegate(agent=agent, stage="intake", refs=["some-ref.md"])

    agents_called = [c.agent for c in delegator.calls]
    assert agents_called == list(datasource_agents), (
        f"datasource intake must call {list(datasource_agents)}, got {agents_called}"
    )


# ---------------------------------------------------------------------------
# S3.6  intake human_org path — correct agent sequence
# ---------------------------------------------------------------------------

def test_intake_human_org_routing() -> None:
    """human_org intake must route through orchestrator then graph-mapper."""
    from brain_ds.mcp.grounding import PIPELINE_STAGES

    intake_stage = next(s for s in PIPELINE_STAGES if s["stage"] == "intake")
    human_org_agents = intake_stage["intake_paths"]["human_org"]  # type: ignore[index]

    delegator = FakeDelegator()
    for agent in human_org_agents:
        delegator.delegate(agent=agent, stage="intake", refs=["some-ref.md"])

    agents_called = [c.agent for c in delegator.calls]
    assert agents_called == list(human_org_agents), (
        f"human_org intake must call {list(human_org_agents)}, got {agents_called}"
    )


# ---------------------------------------------------------------------------
# S3.7  dry_run_elicit_output routes handoffs through FakeDelegator
# ---------------------------------------------------------------------------

def test_dry_run_elicit_output_routes_through_delegator(
    dry_run_elicit_output: dict[str, object],
) -> None:
    """The fixture must expose delegation_calls recorded by FakeDelegator."""
    calls = dry_run_elicit_output.get("delegation_calls")
    assert calls is not None, "dry_run_elicit_output must expose 'delegation_calls'"
    assert isinstance(calls, list)
    assert len(calls) >= 4, f"Expected at least 4 delegation calls, got {len(calls)}"

    agent_names = [c.agent for c in calls]
    # source-explorer must appear before graph-mapper
    assert "brainds-source-explorer" in agent_names
    assert "brainds-graph-mapper" in agent_names
    se_idx = agent_names.index("brainds-source-explorer")
    gm_idx = agent_names.index("brainds-graph-mapper")
    assert se_idx < gm_idx, "source-explorer must be delegated before graph-mapper"


def test_dry_run_elicit_output_handoffs_backward_compat(
    dry_run_elicit_output: dict[str, object],
) -> None:
    """backward-compat: handoffs list must still have 'agent' and 'prompt' keys."""
    handoffs = dry_run_elicit_output.get("handoffs")
    assert handoffs is not None, "handoffs must still be present for backward-compat"
    assert isinstance(handoffs, list)
    assert len(handoffs) >= 4

    for h in handoffs:
        assert "agent" in h, f"handoff missing 'agent': {h}"
        assert "prompt" in h, f"handoff missing 'prompt': {h}"


def test_dry_run_prompt_contains_synthetic_source_path(
    dry_run_elicit_output: dict[str, object],
) -> None:
    """Every delegated prompt must contain synthetic_source_path (existing guard)."""
    synthetic_source_path = str(dry_run_elicit_output["synthetic_source_path"])
    handoffs = dry_run_elicit_output["handoffs"]
    for handoff in handoffs:  # type: ignore[union-attr]
        assert synthetic_source_path in handoff["prompt"], (
            f"Expected synthetic_source_path in prompt for agent={handoff['agent']}"
        )
