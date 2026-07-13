"""Delegation seam for strict-TDD testing of the agentic pipeline.

The seam sits at the artifact/prompt boundary: wherever the orchestrator would
call a real Agent Task, the fixture calls ``delegator.delegate(...)`` instead.
``FakeDelegator`` records every call as a ``DelegationCall`` so tests can make
prompt-shape assertions without any LLM or subprocess.

Usage (in a fixture or test)::

    delegator = FakeDelegator()
    delegator.delegate(agent="brainds-source-explorer", stage="intake", refs=["ref.md"])
    assert delegator.calls[0].agent == "brainds-source-explorer"

The ``dry_run_elicit_output`` conftest fixture routes all handoffs through a
``FakeDelegator`` instance and exposes it as ``delegation_calls`` in the return
dict.  A derived ``handoffs`` list (``[{agent, prompt}, ...]``) is also kept for
backward-compat with ``test_sub_agent_writes_only_to_elicit``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence, runtime_checkable


@dataclass
class DelegationCall:
    """Immutable record of one agent delegation at the prompt boundary."""

    agent: str
    """Name of the agent being delegated to (e.g. 'brainds-source-explorer')."""

    stage: str
    """Pipeline stage this call belongs to (e.g. 'intake', 'map', 'brd')."""

    refs: list[str]
    """Artifact file-path references passed to the agent."""

    prompt: str
    """Deterministic prompt string built from agent, stage, and refs."""


@runtime_checkable
class LiveDelegationHarness(Protocol):
    """Protocol for objects that can delegate pipeline stages to agents.

    Any object that implements ``delegate`` and exposes ``calls`` satisfies
    this protocol — both ``FakeDelegator`` (for tests) and any future live
    implementation that wraps a real Task invocation.
    """

    @property
    def calls(self) -> list[DelegationCall]:
        """Ordered list of all delegation calls recorded so far."""
        ...

    def delegate(
        self,
        *,
        agent: str,
        stage: str,
        refs: Sequence[str],
    ) -> DelegationCall:
        """Record a delegation and return the call object."""
        ...


class FakeDelegator:
    """Deterministic delegation recorder — no real Task, no LLM.

    Implements ``LiveDelegationHarness``.  Every call to ``delegate`` builds a
    reproducible prompt string from its arguments and appends a
    ``DelegationCall`` to ``self.calls``.

    The ``synthetic_source_path`` attribute (optional) is stitched into every
    prompt so the existing ``test_sub_agent_writes_only_to_elicit`` guard still
    passes without modification.
    """

    def __init__(self, synthetic_source_path: str = "") -> None:
        self._calls: list[DelegationCall] = []
        self.synthetic_source_path = synthetic_source_path

    @property
    def calls(self) -> list[DelegationCall]:
        return list(self._calls)

    def delegate(
        self,
        *,
        agent: str,
        stage: str,
        refs: Sequence[str],
    ) -> DelegationCall:
        """Record the delegation and return its ``DelegationCall``."""
        prompt_lines = [
            f"Agent: {agent}",
            f"Stage: {stage}",
            f"Artifact refs: {', '.join(refs)}",
        ]
        if self.synthetic_source_path:
            prompt_lines.append(f"Synthetic source path: {self.synthetic_source_path}")
        prompt = "\n".join(prompt_lines) + "\n"
        call = DelegationCall(agent=agent, stage=stage, refs=list(refs), prompt=prompt)
        self._calls.append(call)
        return call

    # ------------------------------------------------------------------
    # Convenience: derive the backward-compat handoffs list from calls
    # ------------------------------------------------------------------

    def to_handoffs(self) -> list[dict[str, str]]:
        """Return ``[{agent, prompt}, ...]`` for backward-compat consumers."""
        return [{"agent": c.agent, "prompt": c.prompt} for c in self._calls]
