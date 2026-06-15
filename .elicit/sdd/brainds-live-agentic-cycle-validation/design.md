# Design: brainds-live-agentic-cycle-validation

Artifact store: brain_ds-hybrid. Engram topic key: `sdd/brainds-live-agentic-cycle-validation/design`.
Reads: `sdd/brainds-live-agentic-cycle-validation/proposal` (#2149).
Designs against: `brain_ds/mcp/grounding.py`, `brain_ds/verify/elicit_compliance.py`,
`tests/conftest.py`, `tests/test_elicit_lifecycle.py`, `tests/test_grounding_drift_guard.py`,
`tests/test_dryrun_elicit_compliance.py`.

## Executive summary

Encode the agentic cycle as ONE flat ordered `PIPELINE_STAGES` constant in `grounding.py`
(the cross-client source of truth, threaded into all three payload composers), make `verify`
an Auto-run gate that REUSES `check_elicit_compliance` and blocks `archive` on findings, and
introduce a `LiveDelegationHarness` Protocol + `FakeDelegator` at the artifact/prompt seam so
`dry_run_elicit_output` routes every handoff through a testable boundary. Two strict-TDD slices,
RED→GREEN, ask-on-risk delivery.

## Architecture approach

- **Pattern:** declarative pipeline constant + behavioral gate + dependency-inverted delegation seam.
- **Layering:** `grounding.py` is the *declaration* layer (what the pipeline IS). `elicit_compliance.py`
  is the *gate* layer (does an `.elicit/` dir pass). `conftest.py` + a new test seam module are the
  *exercise* layer (drive delegation deterministically, assert prompt shape + compliance).
- **Boundary discipline:** no subprocess, no live LLM, no parallel verifier. The seam stops at the
  artifact/prompt boundary; native `Task` has no Python hook, so the harness models it.
- **Cross-client invariant:** `grounding.py` constants are authoritative; skills/prompts/docs mirror
  them; `skills/` ↔ `.opencode/skills/` stay byte-identical.

---

## 1. `PIPELINE_STAGES` concrete definition

### Where it lives
New module-level constant in `brain_ds/mcp/grounding.py`, declared immediately ABOVE
`DELEGATION_PROTOCOL` (so the protocol can reference it). Annotated `list[dict[str, object]]`.

### Exact structure

```python
PIPELINE_STAGES: list[dict[str, object]] = [
    {
        "stage": "setup",
        "description": (
            "Resolve the active workspace, ask once how to store artifacts "
            "(engram / .elicit / both), and confirm the target graph."
        ),
        "agents": ["brainds-orchestrator"],
    },
    {
        "stage": "intake",
        "description": (
            "Branching stage. Two intake paths feed the same graph: a data-source "
            "path (explore + document a connected source) and a human/org path "
            "(interview the user). Either or both may run before mapping."
        ),
        "agents": ["brainds-orchestrator"],
        "intake_paths": {
            "datasource": ["brainds-source-explorer", "brainds-graph-mapper"],
            "human_org": ["brainds-orchestrator", "brainds-graph-mapper"],
        },
    },
    {
        "stage": "map",
        "description": (
            "Run the connection RAG over the populated graph, score candidate "
            "edges, and persist consolidated edges via add_edge."
        ),
        "agents": ["brainds-connection-mapper"],
    },
    {
        "stage": "brd",
        "description": (
            "Compose the BRD from the mapped graph and persist the brd-<graph> "
            "node with wikilinks per the BRD persistence contract."
        ),
        "agents": ["brainds-brd-writer"],
    },
    {
        "stage": "verify",
        "description": (
            "Auto-run gate: run check_elicit_compliance(.elicit/<cycle>); write "
            "verify-<org-slug>-<date>.md summarizing findings; block archive on any "
            "CRITICAL finding."
        ),
        "agents": ["brainds-orchestrator"],
    },
    {
        "stage": "archive",
        "description": (
            "Only after verify passes: persist final state and close the cycle in "
            "the active artifact store."
        ),
        "agents": ["brainds-orchestrator"],
    },
]
```

### Design rules baked in
- **Flat ordered list** → linear order is free; the lifecycle test asserts one strong invariant
  `[s["stage"] for s in PIPELINE_STAGES] == EXPECTED_ORDER`.
- **Prose + agent names only** → every `agents`/`intake_paths` value is an already-real string in
  `KNOWN_AGENTS`; NO graph-entity-type literals, so the Category-2 sweep stays clean (see §5).
- **`intake_paths` nested under the `intake` stage** → two named ordered lists (`datasource`,
  `human_org`); harness asserts *order within a branch*, not a richer schema.
- **`verify`/`archive` are explicit stages** → they are first-class, not implicit prose.

### Exposure in the three payload composers
Add `"pipeline_stages": PIPELINE_STAGES` to ALL THREE return dicts so every client (Claude + OpenCode)
sees the same pipeline regardless of which tool grounds it:

| Composer | Current keys | Change |
|---|---|---|
| `elicit_context()` | 12 keys | add `"pipeline_stages": PIPELINE_STAGES` → 13 keys; update docstring key list |
| `map_connections_context()` | 10 keys | add `"pipeline_stages": PIPELINE_STAGES`; update docstring |
| `generate_brd_context()` | 8 keys | add `"pipeline_stages": PIPELINE_STAGES`; update docstring |

Non-Claude (OpenCode) reads `pipeline_stages` straight from the JSON payload — a flat list of
`{stage, description, agents}` dicts is self-describing prose, no Claude-specific affordance needed.

---

## 2. `DELEGATION_PROTOCOL` changes

`DELEGATION_PROTOCOL` stays the cross-client orchestration contract. Two additions:

```python
DELEGATION_PROTOCOL: dict[str, object] = {
    "role": ...,                 # unchanged
    "session_setup": ...,        # unchanged
    "artifact_keys": {
        ...
        "phases": [              # EXTEND to the full linear pipeline
            "setup", "intake", "elicit", "source-exploration",
            "source-docs", "map", "brd", "verify", "archive",
        ],
    },
    "pipeline_stages": PIPELINE_STAGES,      # NEW — reference, single source
    "intake_paths": PIPELINE_STAGES[1]["intake_paths"],  # NEW — surfaced for convenience
    "handoff_rule": ...,         # unchanged
    "source_exploration_flow": ...,  # unchanged
    "skill_scope": ...,          # unchanged
}
```

Design note: `pipeline_stages` references the SAME list object (no copy) so there is exactly one
source of truth. `intake_paths` is surfaced as a top-level convenience key pointing at the same
nested dict.

### `REQUIRED_PROTOCOL_KEYS` (lifecycle test) update
`tests/test_elicit_lifecycle.py::REQUIRED_PROTOCOL_KEYS` currently lists 6 keys and
`test_sdd_flow_doc_references_delegation_protocol_constants` asserts each appears in
`docs/SDD_FLOW.md`. Add the two new keys:

```python
REQUIRED_PROTOCOL_KEYS = (
    "role", "session_setup", "artifact_keys", "handoff_rule",
    "source_exploration_flow", "skill_scope",
    "pipeline_stages",   # NEW
    "intake_paths",      # NEW
)
```

→ this forces `docs/SDD_FLOW.md` to document both new keys (RED until the doc is updated). This is
the cross-client doc-sync guard doing its job.

---

## 3. Verify gate mechanism

### How the orchestrator stage invokes the gate (modeled in the harness, §4)
The `verify` stage is "Auto-run minimalista": it calls the EXISTING
`check_elicit_compliance(elicit_dir) -> list[Finding]`. No new validation engine.

```
findings = check_elicit_compliance(elicit_dir)         # REUSE
write verify-<org-slug>-<date>.md  (summary of findings)
if any finding.severity == "CRITICAL":  BLOCK archive   # gate
else:  permit archive-<org-slug>-<date>.md
```

### `.elicit/verify-<org-slug>-<date>.md` artifact format
Same fenced-JSON envelope every other `.elicit` artifact uses (so it is itself parseable and
consistent), wrapped in the standard `# Title\n\n```json ... ```` body:

```json
{
  "graph_id": "<org-slug>",
  "stage": "verify",
  "checked_dir": ".elicit",
  "status": "pass",            // "pass" when no CRITICAL findings, else "fail"
  "critical_count": 0,
  "findings": [                // serialized Finding list (empty on pass)
    {"severity": "CRITICAL", "message": "...", "file": "..."}
  ],
  "gate": "archive-permitted"  // or "archive-blocked"
}
```

Design note: the verify artifact is itself a normal artifact, so it must pass `PHASE_PATTERN`
(below). It carries NO `documented_nodes` / `brd_node`, so `check_elicit_compliance` only applies
its naming + completeness checks to it — but to avoid the "no completeness recommendation" false
positive, the verify artifact is written AFTER a `map`/`brd` artifact already recorded a
recommendation, OR it echoes the recommendation. Simpler: verify is written into a fresh dir that
already contains the prior artifacts, so `completeness_recorded` is already true.

### Pattern changes so the verify (and archive) name validates

**`brain_ds/verify/elicit_compliance.py::PHASE_PATTERN`** — admit the new prefixes:

```python
PHASE_PATTERN = re.compile(
    r"^(setup|intake|elicit|source-exploration|source-docs|map|brd|verify|archive)"
    r"-[a-z0-9_-]+-\d{4}-\d{2}-\d{2}\.md$"
)
```

**`tests/test_elicit_lifecycle.py`** — keep `ELICIT_NAME_PATTERN` byte-identical to `PHASE_PATTERN`
(they intentionally mirror), and extend `ALLOWED_PHASES`:

```python
ALLOWED_PHASES = (
    "setup", "intake", "elicit", "source-exploration",
    "source-docs", "map", "brd", "verify", "archive",
)
ELICIT_NAME_PATTERN = re.compile(
    r"^(setup|intake|elicit|source-exploration|source-docs|map|brd|verify|archive)"
    r"-[a-z0-9_-]+-\d{4}-\d{2}-\d{2}\.md$"
)
```

**`tests/test_dryrun_elicit_compliance.py::PHASE_PATTERN`** — this is a THIRD copy of the same regex;
update it too (it is module-local). All three regexes MUST stay identical.

### Lifecycle doc-ownership guard impact (important gotcha)
`test_lifecycle_doc_ownership_table_consistent` parses `.elicit/README.md`'s `| phase | owner |`
table and asserts `set(phase_to_owner.keys()) == set(ALLOWED_PHASES)`. Adding `setup/intake/verify/
archive` to `ALLOWED_PHASES` means `.elicit/README.md` MUST add a row for each new phase, each owned
by a `KNOWN_AGENTS` member (all four owned by `brainds-orchestrator`). Cascade item, not optional.

---

## 4. `LiveDelegationHarness` / `FakeDelegator` design

### The seam (dependency inversion)
A `Protocol` at the artifact/prompt boundary. `dry_run_elicit_output` depends on the abstraction;
the test supplies a concrete `FakeDelegator`. This models delegation deterministically — it asserts
prompt SHAPE + artifact compliance, never LLM output.

### Location
New module `tests/fixtures/delegation.py` (test-only; lives beside `build_synthetic_source.py`).
Keeping it under `tests/fixtures` signals "test seam, not production code" and avoids importing test
doubles into `brain_ds/`.

### Python interface

```python
# tests/fixtures/delegation.py
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class DelegationCall:
    """One recorded handoff at the artifact/prompt boundary."""
    agent: str
    stage: str
    artifact_refs: tuple[str, ...]
    prompt: str


class LiveDelegationHarness(Protocol):
    """Seam standing in for the native Task delegation boundary.

    Implementations receive a fully-formed delegation request (agent, stage,
    artifact refs) and return the prompt that WOULD be sent. No LLM, no Task.
    """

    def delegate(self, agent: str, stage: str, artifact_refs: list[str]) -> str:
        """Build + record the handoff prompt; return it for shape assertions."""
        ...

    @property
    def calls(self) -> list[DelegationCall]:
        ...


@dataclass
class FakeDelegator:
    """Deterministic LiveDelegationHarness for tests.

    Builds the same prompt the real orchestrator would (agent + stage +
    artifact refs + source path), records every call, and returns the prompt.
    """
    source_path: Path
    _calls: list[DelegationCall] = field(default_factory=list)

    def delegate(self, agent: str, stage: str, artifact_refs: list[str]) -> str:
        prompt = (
            f"Stage: {stage}\n"
            f"Agent: {agent}\n"
            f"Artifact refs: {', '.join(artifact_refs)}\n"
            f"Synthetic source path: {self.source_path}\n"
        )
        self._calls.append(
            DelegationCall(agent=agent, stage=stage,
                           artifact_refs=tuple(artifact_refs), prompt=prompt)
        )
        return prompt

    @property
    def calls(self) -> list[DelegationCall]:
        return self._calls
```

### Refactor of `dry_run_elicit_output`
Today `handoff(agent, refs)` builds a `{"agent","prompt"}` dict and appends to a local list — there
is no `stage`. The refactor:

1. The fixture instantiates a `FakeDelegator(source_path=copied_db)` (or accepts an injected
   `LiveDelegationHarness` via an optional param defaulting to `FakeDelegator`).
2. `handoff(...)` becomes a thin wrapper that adds the `stage` and delegates:

```python
delegator: LiveDelegationHarness = FakeDelegator(source_path=copied_db)

def handoff(agent: str, stage: str, refs: list[str]) -> None:
    delegator.delegate(agent, stage, refs)
```

3. Each existing `handoff(...)` call site gains its `stage`:
   - `handoff("brainds-source-explorer", "intake", [...])`
   - `handoff("brainds-graph-mapper", "intake", [...])`
   - `handoff("brainds-connection-mapper", "map", [...])`
   - `handoff("brainds-brd-writer", "brd", [...])`
   - `handoff("brainds-query-consultant", "brd", [...])` (consult inside brd stage)
4. The fixture's returned dict exposes `"delegation_calls": [asdict-like view]` AND keeps
   `"handoffs"` (backward-compat: derive `{"agent","prompt"}` from `delegator.calls`) so existing
   `test_sub_agent_writes_only_to_elicit` keeps passing unchanged.
5. **Verify gate exercised in the fixture (Slice 2):** after the `brd` artifact is written, the
   fixture runs the verify step:

```python
findings = check_elicit_compliance(elicit_dir)
verify_payload = {
    "graph_id": org_slug, "stage": "verify", "checked_dir": ".elicit",
    "status": "fail" if findings else "pass",
    "critical_count": sum(f.severity == "CRITICAL" for f in findings),
    "findings": [{"severity": f.severity, "message": f.message,
                  "file": str(f.file)} for f in findings],
    "gate": "archive-blocked" if findings else "archive-permitted",
}
verify_path = write_artifact("verify", verify_payload)
if not findings:
    archive_path = write_artifact("archive", {"graph_id": org_slug,
        "stage": "archive", "verify_ref": str(verify_path)})
```

   The fixture returns `verify_status`, `verify_path`, and (when permitted) `archive_path`.

### Prompt-shape contract each delegated stage asserts
A delegation prompt is well-formed iff:
- contains `Stage: <stage>` where `<stage>` ∈ `{intake, map, brd}` (the delegated stages),
- contains `Agent: <agent>` where `<agent>` ∈ `KNOWN_AGENTS`,
- contains `Artifact refs:` with ≥1 ref, every ref ending `.md` and under `.elicit/`,
- contains the synthetic source path,
- contains NONE of the forbidden cross-store terms (`engram`, `graph history`, `Observation #`,
  `unrelated file`) — reuses the existing forbidden-term guard.

Tests assert against `delegator.calls` (structured `DelegationCall`s), not raw strings, so the shape
contract is explicit and non-brittle.

---

## 5. Drift-guard integration

- `PIPELINE_STAGES` is a module-level `list` constant named `[A-Z][A-Z0-9_]+` → auto-discovered by
  `_discover_category2_constants()`.
- It is **NOT** added to `CATEGORY2_EXEMPT` → it falls into the swept bucket automatically.
- `_sweep_constant` walks every string and flags `\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b` CamelCase tokens
  not in `_entity_values()` or `SAFE_ENTITYISH_TOKENS`. Our strings contain only:
  - prose (lowercase sentences), and
  - agent names like `brainds-source-explorer` (lowercase + hyphen → NOT CamelCase → not matched),
  - branch keys `datasource` / `human_org` (lowercase → not matched).
  → sweep passes clean. `test_swept_category2_constants_have_no_drift_tokens` stays green.
- `test_every_category2_constant_is_classified` auto-classifies it the moment it exists; no test edit
  required there. **Verification step in GREEN:** run the drift guard; if any description ever needs
  a CamelCase token, add it to `SAFE_ENTITYISH_TOKENS` (never to `CATEGORY2_EXEMPT`).

Gotcha: keep stage descriptions free of CamelCase product names (e.g. write "check_elicit_compliance"
lowercase-with-underscores, which it already is — `\b[A-Z]...` won't match).

---

## 6. Cross-client propagation plan

`grounding.py` is source of truth; everything below mirrors it. Concrete edits per file:

| # | File | Edit | Client |
|---|------|------|--------|
| 1 | `brain_ds/mcp/grounding.py` | add `PIPELINE_STAGES`; add `pipeline_stages`/`intake_paths` to `DELEGATION_PROTOCOL`; extend `artifact_keys.phases`; add `pipeline_stages` to 3 composers + docstrings | source |
| 2 | `brain_ds/verify/elicit_compliance.py` | extend `PHASE_PATTERN` | both |
| 3 | `tests/test_elicit_lifecycle.py` | `ALLOWED_PHASES`, `ELICIT_NAME_PATTERN`, `REQUIRED_PROTOCOL_KEYS`, new `PIPELINE_STAGES` order assertion | both |
| 4 | `tests/test_dryrun_elicit_compliance.py` | local `PHASE_PATTERN` copy | both |
| 5 | `.elicit/README.md` | add `setup/intake/verify/archive` rows to phase-owner table (owner `brainds-orchestrator`) + lifecycle prose | both |
| 6 | `docs/SDD_FLOW.md` | document the 6 linear stages, verify gate, AND mention `pipeline_stages`+`intake_paths` keys (satisfies `REQUIRED_PROTOCOL_KEYS` guard) | both |
| 7 | `AGENT_FLOW.md` | mirror linear pipeline + intake branches | both |
| 8 | `prompts/brain-ds-orchestrator.md` | name the 6 linear stages + verify gate | OpenCode |
| 9 | `.claude/agents/brainds-orchestrator.md` | name the 6 linear stages + verify gate | Claude |
| 10 | `skills/*/SKILL.md` (where pipeline prose is relevant: `generate-brd`, `map-connections`, `brainds-docs`) | mirror pipeline prose | both |
| 11 | `.opencode/skills/*/SKILL.md` | **byte-identical** copy of #10 | OpenCode |

Mirror discipline: edit `skills/<name>/SKILL.md` first, copy bytes verbatim to
`.opencode/skills/<name>/SKILL.md`. Run `/share-brainds` after skill edits. No agent roster change →
NO installer edits, NO `harness_check.py` `SUBAGENT_NAMES` edit (decision 6, deferred).

---

## 7. Slice boundaries + line estimates (delivery: ask-on-risk, 400-line budget)

### Slice 1 — Linear pipeline + verify/archive stages + cross-client cascade
**Scope:** `PIPELINE_STAGES` constant, `DELEGATION_PROTOCOL` keys, composer wiring, the three
`PHASE_PATTERN`/`ALLOWED_PHASES`/`ELICIT_NAME_PATTERN` extensions, `REQUIRED_PROTOCOL_KEYS`, the
lifecycle order assertion, and the FULL doc/prompt/skill cascade (items 5–11).

**Estimate:** ~280–360 changed lines, ~11 files (most of it doc/prompt/skill prose).
**Budget flag:** trips toward 400 because of the cascade. **Per ask-on-risk: surface to maintainer
before apply.** Recommended split if it exceeds budget — two stacked commits:
- 1a: constant + protocol + composers + pattern/test edits (`grounding.py`, `elicit_compliance.py`,
  3 test files) — the load-bearing behavior (~140–180 lines).
- 1b: docs/prompts/skill mirrors (items 5–11) — reviewable prose sub-unit (~140–180 lines).

The verify gate **definition** (stage semantics, artifact name, gate-blocks-archive rule) lands in
Slice 1 as part of `PIPELINE_STAGES`. Its **exercised behavior** lands in Slice 2.

### Slice 2 — LiveDelegationHarness/FakeDelegator + verify gate exercised
**Scope:** `tests/fixtures/delegation.py` (new), `conftest.py` `dry_run_elicit_output` refactor
(stage-aware `handoff`, delegator wiring, verify+archive steps, return-dict additions), new
prompt-shape + verify-gate tests.

**Estimate:** ~170–230 changed lines (new seam module + conftest refactor + new tests).
Comfortably under 400. No cross-client docs touched (seam is test-only).

**Recommendation:** two chained PRs (Slice 1 then Slice 2).

---

## 8. Test plan (RED first, per slice)

### Slice 1 RED tests
| Test | File | Asserts (fails until GREEN) |
|---|---|---|
| `test_pipeline_stages_linear_order` (new) | `tests/test_elicit_lifecycle.py` | `[s["stage"] for s in grounding.PIPELINE_STAGES] == ["setup","intake","map","brd","verify","archive"]` |
| `test_intake_paths_branches` (new) | `tests/test_elicit_lifecycle.py` | `intake` stage has `intake_paths` with `datasource` + `human_org` ordered agent lists, all in `KNOWN_AGENTS` |
| `test_pipeline_stages_in_all_composers` (new) | `tests/test_mcp_grounding.py` | each of the 3 composers returns `pipeline_stages` identical to `PIPELINE_STAGES` |
| `test_delegation_protocol_has_pipeline_keys` (new) | `tests/test_elicit_lifecycle.py` | `pipeline_stages` + `intake_paths` in `DELEGATION_PROTOCOL`; `REQUIRED_PROTOCOL_KEYS` extended |
| `test_verify_artifact_name_is_legal` (new) | `tests/test_elicit_lifecycle.py` / `test_dryrun_elicit_compliance.py` | `verify-acme-2026-06-14.md` and `archive-...` match `ELICIT_NAME_PATTERN`/`PHASE_PATTERN` |
| existing `test_every_category2_constant_is_classified` | `tests/test_grounding_drift_guard.py` | confirm `PIPELINE_STAGES` auto-classified, swept clean (no edit; verify green) |
| existing `test_lifecycle_doc_ownership_table_consistent` | `tests/test_elicit_lifecycle.py` | RED until `.elicit/README.md` adds the 4 new phase rows |
| existing `test_sdd_flow_doc_references_delegation_protocol_constants` | `tests/test_elicit_lifecycle.py` | RED until `docs/SDD_FLOW.md` mentions `pipeline_stages` + `intake_paths` |

### Slice 2 RED tests
| Test | File | Asserts (fails until GREEN) |
|---|---|---|
| `test_delegator_records_stage_aware_calls` (new) | `tests/test_delegation_seam.py` (new) | `FakeDelegator.delegate(...)` records a `DelegationCall` with agent/stage/refs/prompt |
| `test_delegation_prompt_shape_per_stage` (new) | `tests/test_delegation_seam.py` | every recorded call: `Stage:`/`Agent:` present, agent ∈ `KNOWN_AGENTS`, ≥1 `.md` ref under `.elicit/`, source path present, no forbidden terms |
| `test_dry_run_routes_handoffs_through_delegator` (new) | `tests/test_dryrun_elicit_compliance.py` | fixture exposes `delegation_calls`; stages cover `{intake, map, brd}` |
| `test_verify_stage_passes_on_compliant_cycle` (new) | `tests/test_dryrun_elicit_compliance.py` | compliant dry-run → `verify_status == "pass"`, `archive_path` present, verify artifact `gate == "archive-permitted"` |
| `test_verify_stage_blocks_archive_on_noncompliant` (new) | `tests/test_dryrun_elicit_compliance.py` | inject a noncompliant artifact → `check_elicit_compliance` returns CRITICAL → verify `status=="fail"`, `gate=="archive-blocked"`, NO archive artifact |
| existing `test_sub_agent_writes_only_to_elicit` | `tests/test_dryrun_elicit_compliance.py` | stays green via backward-compat `handoffs` derived from `delegator.calls` |

Test runner: `uv run pytest`. RED→GREEN per the project's strict-TDD mode.

---

## Risks / unresolved

| Risk | Mitigation / note |
|---|---|
| Three duplicated `PHASE_PATTERN` regexes drift | Update all three in the SAME Slice-1 commit; they MUST stay byte-identical |
| `verify` artifact trips `completeness_recorded` false-positive when alone in a dir | verify runs in a dir that already holds map/brd artifacts (recommendation already recorded); or echo the recommendation — confirm during apply |
| Slice 1 cascade exceeds 400 lines | ask-on-risk: surface to maintainer; stacked 1a/1b split ready |
| `.elicit/README.md` ownership-table guard is strict (exact set equality) | every new ALLOWED_PHASE needs exactly one owner row — easy to miss; called out as cascade item |
| Deferred `SUBAGENT_NAMES`/`check_agent_files()` leaves CLAUDE.md referencing unbuilt symbols | documented gap (decision 6); existing `KNOWN_AGENTS` roster guard covers the real invariant; clean follow-up slice |
| "Live" overclaim | seam is artifact/prompt-level by design; tests assert SHAPE + compliance, never LLM quality (decision 4) |
