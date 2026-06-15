# Spec: brainds-live-agentic-cycle-validation

Artifact store: brain_ds-hybrid.
Engram topic key: `sdd/brainds-live-agentic-cycle-validation/spec`.
Reads: `sdd/brainds-live-agentic-cycle-validation/proposal` (#2149).

---

## Overview

This spec describes WHAT must be true after the change is applied. It does not prescribe HOW
to implement it. Every scenario below must be expressible as a failing test BEFORE the
implementation exists (strict-TDD, Red-first).

The change has two delivery slices:

| Slice | Deliverable | Budget |
|-------|-------------|--------|
| 1 | Linear pipeline constant + verify/archive naming extension + cascade | ~250–350 lines across ~10 files |
| 2 | `LiveDelegationHarness` / `FakeDelegator` + prompt-shape + verify-gate tests | ~150–250 lines |

---

## Capability 1 — Pipeline Definition (`PIPELINE_STAGES`)

### What must be true

- `brain_ds/mcp/grounding.py` exports a module-level constant `PIPELINE_STAGES` that is a
  `list[dict[str, object]]` with **exactly 6 entries** in the order:
  `setup`, `intake`, `map`, `brd`, `verify`, `archive`.
- Each entry has at minimum the keys `stage` (string) and `description` (non-empty string)
  and `agents` (non-empty list of agent-name strings).
- The `intake` entry additionally carries an `intake_paths` key whose value is a `dict` with
  exactly two keys `datasource` and `human_org`, each mapping to a non-empty list of
  agent-name strings.
- All agent-name strings that appear in `PIPELINE_STAGES` and `intake_paths` are members of
  `KNOWN_AGENTS` (as defined in `tests/test_elicit_lifecycle.py`).
- `PIPELINE_STAGES` is NOT in `CATEGORY2_EXEMPT` (it is a swept constant).
- `PIPELINE_STAGES` contains no CamelCase EntityType literals — the drift sweep passes clean.
- The three grounding payloads (`run_elicit_context()`, `map_connections_context()`,
  `generate_brd_context()`) each contain a `pipeline_stages` key whose value equals
  `PIPELINE_STAGES`, and an `intake_paths` key equal to the `intake` stage's `intake_paths`.

### Scenarios

**S1.1 — Stage order invariant**

```
Given: PIPELINE_STAGES is imported from brain_ds.mcp.grounding
When:  [s["stage"] for s in PIPELINE_STAGES] is evaluated
Then:  the result equals exactly ["setup", "intake", "map", "brd", "verify", "archive"]
```

Test file: `tests/test_elicit_lifecycle.py` (new assertion in
`TestElicitLifecycle` or new `test_pipeline_stages_order` method).

**S1.2 — intake_paths branch structure**

```
Given: the "intake" stage dict from PIPELINE_STAGES
When:  its "intake_paths" key is inspected
Then:  keys == {"datasource", "human_org"}
       intake_paths["datasource"] is a non-empty list
       intake_paths["human_org"] is a non-empty list
       all agent strings appear in KNOWN_AGENTS
```

Test file: `tests/test_elicit_lifecycle.py`.

**S1.3 — All stage agents are in KNOWN_AGENTS**

```
Given: PIPELINE_STAGES
When:  all "agents" lists across all 6 stages are collected (flat)
Then:  every element is a member of KNOWN_AGENTS
```

Test file: `tests/test_elicit_lifecycle.py`.

**S1.4 — pipeline_stages in all three grounding payloads (cross-client)**

```
Given: run_elicit_context(), map_connections_context(), generate_brd_context()
       imported from brain_ds.mcp.grounding
When:  each payload dict is inspected
Then:  payload["pipeline_stages"] == PIPELINE_STAGES
       payload["intake_paths"] == PIPELINE_STAGES[1]["intake_paths"]
```

Test file: `tests/test_grounding_drift_guard.py` or a new
`tests/test_pipeline_grounding.py` (proposer's choice; must be covered).

**S1.5 — Drift sweep passes for PIPELINE_STAGES**

```
Given: PIPELINE_STAGES is a Category-2 constant (list, auto-discovered)
       and is NOT listed in CATEGORY2_EXEMPT
When:  test_swept_category2_constants_have_no_drift_tokens runs
Then:  no drift entries are reported for PIPELINE_STAGES
       (no CamelCase EntityType-like tokens in any string value)
```

Test file: `tests/test_grounding_drift_guard.py` (existing
`test_swept_category2_constants_have_no_drift_tokens` must stay green).

**S1.6 — test_every_category2_constant_is_classified passes**

```
Given: PIPELINE_STAGES is added to grounding.py
When:  test_every_category2_constant_is_classified runs
Then:  PIPELINE_STAGES appears in the swept set (not in missing)
       (no code change required in that test — auto-discovery handles it)
```

Test file: `tests/test_grounding_drift_guard.py` (existing test, must stay green).

---

## Capability 2 — Verify Gate

### What must be true

- The `verify` pipeline stage represents an **auto-run observable gate**: it calls
  `check_elicit_compliance(elicit_dir)` (re-using `brain_ds/verify/elicit_compliance.py`
  unchanged except for pattern extension), and the result determines whether `archive` may
  proceed.
- When the gate **passes** (zero findings), a file named
  `verify-<org-slug>-<date>.md` is written inside the `.elicit/<cycle>` directory.
- When the gate **fails** (one or more findings), the `archive` step is **blocked** — no
  archive artifact is written, and an error surface (exception, return value, or written
  report containing `FAIL`) makes the failure observable.
- The verify-artifact filename `verify-<org-slug>-<date>.md` must be **admitted** by
  `PHASE_PATTERN` in `brain_ds/verify/elicit_compliance.py` and `ELICIT_NAME_PATTERN` in
  `tests/test_elicit_lifecycle.py` and the `ALLOWED_PHASES` tuple in that same file.
  These patterns currently reject the `verify-` prefix — extending them is a deliberate
  RED-first step in Slice 1.

### Pattern extension contract

After the change, `ALLOWED_PHASES` must include at minimum:
`"elicit"`, `"source-exploration"`, `"source-docs"`, `"map"`, `"brd"`, **`"verify"`**.

The `ELICIT_NAME_PATTERN` regex must match filenames of the form:
`verify-<org-slug>-<date>.md` where slug is `[a-z0-9_-]+` and date is `\d{4}-\d{2}-\d{2}`.

`PHASE_PATTERN` in `elicit_compliance.py` must match the same form.

`setup`, `intake`, and `archive` prefixes MAY also be admitted (implementation choice); if
admitted they must be added to `ALLOWED_PHASES` and both patterns consistently.

### Scenarios

**S2.1 — PHASE_PATTERN admits verify-prefixed artifacts (RED-first)**

```
Given: PHASE_PATTERN from brain_ds.verify.elicit_compliance
When:  PHASE_PATTERN.match("verify-acme-2026-06-14.md") is evaluated
Then:  the match is not None
       (this FAILS before Slice 1 GREEN step)
```

Test file: `tests/test_elicit_lifecycle.py` (new test) or
`tests/test_dryrun_elicit_compliance.py`.

**S2.2 — ELICIT_NAME_PATTERN admits verify prefix (RED-first)**

```
Given: ELICIT_NAME_PATTERN from tests/test_elicit_lifecycle.py
When:  ELICIT_NAME_PATTERN.match("verify-acme-2026-06-14.md") is evaluated
Then:  the match is not None
```

Test file: `tests/test_elicit_lifecycle.py` (inline constant updated, existing
`test_elicit_naming_pattern` implicitly covers it).

**S2.3 — verify gate writes artifact on pass**

```
Given: an .elicit directory containing ONLY compliant artifacts
       (all pass check_elicit_compliance)
When:  the verify stage runs via FakeDelegator (Slice 2)
       or a direct invocation of the gate callable
Then:  a file "verify-<org-slug>-<date>.md" is written in that .elicit directory
       the file content contains a structured summary (no specific format required,
       but must include "PASS" or equivalent and the finding count = 0)
```

Test file: `tests/test_elicit_lifecycle.py` (new) or new
`tests/test_verify_gate.py`.

**S2.4 — verify gate blocks archive on fail**

```
Given: an .elicit directory containing at least one non-compliant artifact
       (check_elicit_compliance returns one or more Findings)
When:  the verify stage runs
Then:  no archive artifact is written
       the failure is surfaced (exception OR return value with "FAIL" OR written
       report containing "FAIL")
       the archive step is not invoked
```

Test file: `tests/test_verify_gate.py` (new) or `tests/test_elicit_lifecycle.py`.

**S2.5 — lifecycle README mentions verify and archive phases**

```
Given: .elicit/README.md
When:  its content is read
Then:  the string "`verify`" appears in the lifecycle table
       "brainds-orchestrator" is listed as owner for the verify phase
```

Test file: `tests/test_elicit_lifecycle.py`
(`test_lifecycle_doc_ownership_table_consistent` extended to include "verify").

---

## Capability 3 — Live Delegation Seam

### What must be true

- A `LiveDelegationHarness` **Protocol** (duck-typed interface) exists in the production
  code (or a shared test utility module) that defines a `handoff(agent: str, refs: list[str],
  stage: str) -> None` method signature (at minimum).
- A `FakeDelegator` test double exists that implements `LiveDelegationHarness`, records each
  call as `{"agent": str, "prompt": str, "stage": str}`, and optionally writes a stub
  artifact for any stage that requires one to continue the pipeline.
- The `dry_run_elicit_output` fixture in `tests/conftest.py` is refactored so that all
  `handoff(agent, refs)` calls route through a `FakeDelegator` instance, not the ad-hoc
  local closure.
- After the refactor, the fixture's observable contract (the `dict[str, object]` it returns)
  is unchanged: same keys (`graph_id`, `store_path`, `elicit_dir`, `synthetic_source_path`,
  `handoffs`, `written_files`, `entry_artifact`).
- Prompt shape for each stage satisfies the assertions below (Scenarios S3.2–S3.6).

### Scenarios

**S3.1 — FakeDelegator records every handoff**

```
Given: a FakeDelegator instance
When:  handoff("brainds-source-explorer", ["/some/path"], stage="intake") is called
Then:  delegator.calls == [{"agent": "brainds-source-explorer", "refs": ["/some/path"], "stage": "intake"}]
       (or equivalent structure)
```

Test file: `tests/test_dryrun_elicit_compliance.py` or new
`tests/test_live_delegation_harness.py`.

**S3.2 — source-explorer handoff prompt shape**

```
Given: FakeDelegator used in dry_run_elicit_output
When:  the handoff to "brainds-source-explorer" is inspected
Then:  prompt contains the synthetic_source_path
       prompt contains "artifact" (case-insensitive)
       prompt does NOT contain any of ("engram", "graph history", "Observation #",
       "unrelated file")
       stage == "intake"
```

Test file: `tests/test_dryrun_elicit_compliance.py` (`test_sub_agent_writes_only_to_elicit`
updated, or a new parallel test).

**S3.3 — graph-mapper handoff prompt shape**

```
Given: FakeDelegator used in dry_run_elicit_output
When:  the handoff to "brainds-graph-mapper" is inspected
Then:  prompt contains a reference to at least one .elicit artifact path
       stage == "intake" (datasource path) or "map"
       (both handoffs to graph-mapper must carry a stage field)
```

Test file: `tests/test_dryrun_elicit_compliance.py`.

**S3.4 — connection-mapper handoff prompt shape**

```
Given: FakeDelegator used in dry_run_elicit_output
When:  the handoff to "brainds-connection-mapper" is inspected
Then:  prompt contains a reference to the map artifact path
       stage == "map"
```

Test file: `tests/test_dryrun_elicit_compliance.py`.

**S3.5 — brd-writer handoff prompt shape**

```
Given: FakeDelegator used in dry_run_elicit_output
When:  the handoff to "brainds-brd-writer" is inspected
Then:  prompt contains the expected brd artifact path reference
       stage == "brd"
```

Test file: `tests/test_dryrun_elicit_compliance.py`.

**S3.6 — verify stage is invoked after brd, before archive**

```
Given: FakeDelegator used in the verify-gate path
When:  the full pipeline runs through FakeDelegator
Then:  delegator.calls contains a record with stage == "verify"
       that record appears AFTER any record with stage == "brd"
       and BEFORE any record with stage == "archive" (if archive is recorded)
```

Test file: `tests/test_verify_gate.py` or `tests/test_live_delegation_harness.py`.

**S3.7 — dry_run_elicit_output fixture contract is preserved after refactor**

```
Given: the conftest.py dry_run_elicit_output fixture is refactored to use FakeDelegator
When:  the fixture runs
Then:  the returned dict has exactly the keys:
       graph_id, store_path, elicit_dir, synthetic_source_path,
       handoffs, written_files, entry_artifact
       handoffs is a list of dicts each containing at minimum "agent" and "prompt"
       (existing tests depending on this contract must pass without modification)
```

Test file: all existing tests using `dry_run_elicit_output` must continue to pass
(`tests/test_dryrun_elicit_compliance.py`).

---

## Capability 4 — Cross-Client Parity

### What must be true

- `skills/*/SKILL.md` and `.opencode/skills/*/SKILL.md` are byte-identical for every skill
  file touched by this change. The existing `check_skills_mirror()` guard must stay green.
- The orchestrator prompts — `prompts/brain-ds-orchestrator.md` AND
  `.claude/agents/brainds-orchestrator.md` — both name the 6 pipeline stages in the same
  order and mention the verify gate behavior.
- `AGENT_FLOW.md` is updated to reflect the linear pipeline and intake branch model.
- `docs/SDD_FLOW.md` is updated to document the 6 stages including the verify gate.
- `.elicit/README.md` lifecycle table covers all phases including `verify` (and `archive`
  if that prefix is admitted).

### Scenarios

**S4.1 — Skills mirror byte identity**

```
Given: every skills/*/SKILL.md file modified by this change
When:  its byte content is compared to .opencode/skills/*/SKILL.md counterpart
Then:  content is identical (no encoding difference, no trailing newline delta)
```

Test file: existing skill mirror guard (harness_check / test_mcp_claude_config.py or
equivalent mirror assertion).

**S4.2 — Orchestrator prompts name 6 stages**

```
Given: prompts/brain-ds-orchestrator.md
       .claude/agents/brainds-orchestrator.md
When:  each file's content is searched for the pipeline stage names
Then:  all of ["setup", "intake", "map", "brd", "verify", "archive"] appear in each file
```

Test file: `tests/test_elicit_lifecycle.py` (new assertion or new test method).

**S4.3 — AGENT_FLOW.md names all pipeline stages**

```
Given: AGENT_FLOW.md at repo root
When:  its content is searched
Then:  all of ["setup", "intake", "map", "brd", "verify", "archive"] appear
       "datasource" and "human_org" (or equivalent branch labels) appear
```

Test file: `tests/test_elicit_lifecycle.py`.

**S4.4 — SDD_FLOW.md references verify gate**

```
Given: docs/SDD_FLOW.md
When:  its content is read
Then:  "verify" appears and is associated with "check_elicit_compliance"
       (or functionally equivalent prose describing the auto-run gate)
```

Test file: `tests/test_elicit_lifecycle.py`
(`test_sdd_flow_doc_references_delegation_protocol_constants` extended, or new test).

---

## Capability 5 — Drift / Lifecycle Guard Updates

### What must be true

These are RED-first steps in Slice 1 — tests must be written to go RED before any
implementation, then go GREEN when the implementation lands.

- `ALLOWED_PHASES` in `tests/test_elicit_lifecycle.py` is extended to include at minimum
  `"verify"` (and `"setup"`, `"intake"`, `"archive"` if those prefix filenames are admitted).
- `ELICIT_NAME_PATTERN` in `tests/test_elicit_lifecycle.py` is updated to match filenames
  with the `verify-` prefix (and others if admitted).
- `REQUIRED_PROTOCOL_KEYS` in `tests/test_elicit_lifecycle.py` is extended to include
  `"pipeline_stages"` and `"intake_paths"`, so `test_sdd_flow_doc_references_delegation_protocol_constants`
  fails until `docs/SDD_FLOW.md` documents these keys.
- `PHASE_PATTERN` in `brain_ds/verify/elicit_compliance.py` is extended to match `verify-`
  prefixed filenames, so `check_elicit_compliance` does not report a naming-contract
  violation for verify artifacts.

### Scenarios

**S5.1 — REQUIRED_PROTOCOL_KEYS includes pipeline_stages and intake_paths**

```
Given: REQUIRED_PROTOCOL_KEYS in tests/test_elicit_lifecycle.py
When:  test_sdd_flow_doc_references_delegation_protocol_constants runs
Then:  it checks that both "pipeline_stages" and "intake_paths" appear in
       docs/SDD_FLOW.md
       (test goes RED until SDD_FLOW.md is updated)
```

Test file: `tests/test_elicit_lifecycle.py`.

**S5.2 — verify filename passes existing naming test after ALLOWED_PHASES update**

```
Given: ALLOWED_PHASES now includes "verify"
       ELICIT_NAME_PATTERN updated to match "verify-<slug>-<date>.md"
When:  a file "verify-acme-2026-06-14.md" exists in .elicit
       and test_elicit_naming_pattern runs
Then:  the test passes (no assertion error for that filename)
```

Test file: `tests/test_elicit_lifecycle.py`.

**S5.3 — lifecycle README ownership table covers verify**

```
Given: .elicit/README.md updated to include verify row
When:  test_lifecycle_doc_ownership_table_consistent runs
Then:  "`verify`" appears in lifecycle_doc
       phase_to_owner["verify"] == "brainds-orchestrator"
       (or whatever agent is declared owner)
       the owner is in KNOWN_AGENTS
```

Test file: `tests/test_elicit_lifecycle.py`
(test already asserts `set(phase_to_owner.keys()) == set(ALLOWED_PHASES)` — extending
`ALLOWED_PHASES` automatically tightens this).

**S5.4 — PIPELINE_STAGES auto-discovered by drift sweep (no explicit classification needed)**

```
Given: PIPELINE_STAGES is a module-level list[dict] in grounding.py
       NOT listed in CATEGORY2_EXEMPT
When:  _discover_category2_constants() runs
Then:  "PIPELINE_STAGES" is in the discovered set
       test_every_category2_constant_is_classified passes without any new
       CATEGORY2_EXEMPT entry
       test_swept_category2_constants_have_no_drift_tokens passes (no EntityType tokens)
```

Test file: `tests/test_grounding_drift_guard.py` (existing tests, must stay green).

---

## Out-of-Scope Invariants (must NOT be violated)

| Invariant | Guard |
|-----------|-------|
| No subprocess or live-LLM calls in CI | Existing CI config; FakeDelegator never calls Task |
| No new sub-agents added | KNOWN_AGENTS stays at 6 members |
| `skills/*/SKILL.md` ↔ `.opencode/skills/*/SKILL.md` byte-identical | `check_skills_mirror()` |
| `check_elicit_compliance` logic unchanged (only pattern extended) | `tests/test_dryrun_elicit_compliance.py` existing tests |
| `dry_run_elicit_output` return dict contract unchanged | All existing `test_dryrun_elicit_compliance.py` tests pass |
| `SUBAGENT_NAMES` / `CLAUDE_AGENT_FILES` / `check_agent_files()` not introduced | Not in scope; deferred |

---

## Affected Files

| # | File | Capability | Slice |
|---|------|------------|-------|
| 1 | `brain_ds/mcp/grounding.py` | C1, C4 | 1 |
| 2 | `brain_ds/verify/elicit_compliance.py` | C2 | 1 |
| 3 | `tests/test_elicit_lifecycle.py` | C1, C2, C4, C5 | 1 |
| 4 | `tests/test_grounding_drift_guard.py` | C1, C5 | 1 (verify green) |
| 5 | `docs/SDD_FLOW.md` | C4 | 1 |
| 6 | `AGENT_FLOW.md` | C4 | 1 |
| 7 | `.elicit/README.md` | C2, C5 | 1 |
| 8 | `skills/*/SKILL.md` | C4 | 1 |
| 9 | `.opencode/skills/*/SKILL.md` | C4 | 1 (byte-identical mirror) |
| 10 | `prompts/brain-ds-orchestrator.md` + `.claude/agents/brainds-orchestrator.md` | C4 | 1 |
| 11 | `tests/conftest.py` | C3 | 2 |
| 12 | `brain_ds/verify/` (new file or extension) | C3 | 2 |
| 13 | `tests/test_verify_gate.py` (new) | C2, C3 | 2 |
| 14 | `tests/test_live_delegation_harness.py` (new, optional) | C3 | 2 |

---

## Assumptions / Risks Forced at Spec Level

| Risk | Assumption Made |
|------|-----------------|
| `setup`, `intake`, `archive` prefix filenames may or may not need to be admitted by PHASE_PATTERN | Spec requires `verify` admission as minimum; others are implementation choice, but must be consistent across PHASE_PATTERN, ELICIT_NAME_PATTERN, and ALLOWED_PHASES |
| `REQUIRED_PROTOCOL_KEYS` extension may break `test_sdd_flow_doc_references_delegation_protocol_constants` until docs are updated | Spec treats this as the intended RED-first behavior; both the test update and the docs update are in the same slice |
| `intake_paths` key placement (inside PIPELINE_STAGES vs. top-level in payload) | Spec follows proposal: nested inside the `intake` stage dict AND surfaced as a top-level `intake_paths` key in each grounding payload |
| `LiveDelegationHarness` Protocol location (production vs. test utility) | Spec requires it exist and be importable; exact module location is implementation choice |
| Verify artifact content format | Spec requires only that it contain "PASS" (or equivalent) and the finding count; no markdown schema is mandated |
