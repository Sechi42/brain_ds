# Tasks — brainds-live-agentic-cycle-validation

## Review Workload Forecast

| Slice | Sub-slice | Estimated changed lines | Files touched | 400-line budget risk |
|---|---|---|---|---|
| Slice 1a | Behavior (grounding + verify + tests) | ~240–300 | 5 | **Medium** |
| Slice 1b | Doc mirrors (prompts, skills, README, SDD_FLOW) | ~80–120 | 7–8 | Low |
| Slice 2 | Live delegation seam (new files + conftest refactor) | ~170–230 | 5 | Low |
| **Total** | | **~490–650** | **~17** | **High (full set)** |

- **Chained PRs recommended: Yes** — ship as 3 PRs: Slice 1a → Slice 1b → Slice 2.
- **Decision needed before apply: Yes** — ask maintainer to confirm the 1a/1b/2 PR chain before starting apply.
- Each PR is CI-green, independently rollback-safe, and fits inside ~60 min review scope.

---

## Slice 1a — Pipeline Constant + Verify Gate + Pattern Extensions (behavior)

**Goal**: make `PIPELINE_STAGES` exist, expose it in all 3 grounding payloads, extend `PHASE_PATTERN`/`ELICIT_NAME_PATTERN`/`ALLOWED_PHASES` to admit `verify` and `archive`, wire the verify Auto-run gate into `check_elicit_compliance`, and keep the drift guard clean.

### T1a-1 — RED test: `PIPELINE_STAGES` constant shape and order
- **File**: `tests/test_elicit_lifecycle.py`
- **Spec**: S1.1, S1.2
- **Action**: Add a test that imports `grounding.PIPELINE_STAGES`, asserts it is a `list[dict]` with exactly 6 elements in order `setup, intake, map, brd, verify, archive`, and that the `intake` stage dict carries keys `stage`, `description`, `agents`, and `intake_paths` (with sub-keys `datasource` and `human_org`).
- **Status**: [x] DONE — RED→GREEN

### T1a-2 — GREEN: add `PIPELINE_STAGES` to `grounding.py`
- **File**: `brain_ds/mcp/grounding.py`
- **Spec**: S1.1, S1.2, S1.3
- **Action**: Insert `PIPELINE_STAGES: list[dict[str, object]]` above `DELEGATION_PROTOCOL`. Six dicts in order; `intake` carries `intake_paths`. `CATEGORY2_EXEMPT` must NOT include it (already covered by design — list[dict] sweeps clean because all strings are lowercase prose or hyphenated agent names). Confirm via read of `CATEGORY2_EXEMPT` in drift guard — no edit needed there.
- **Status**: [x] DONE — Makes T1a-1 GREEN

### T1a-3 — RED test: `PIPELINE_STAGES` exposed in all 3 grounding payloads
- **File**: `tests/test_elicit_lifecycle.py`
- **Spec**: S1.4, S1.5, S1.6
- **Action**: Add assertions that `elicit_context()["pipeline_stages"]`, `map_connections_context()["pipeline_stages"]`, and `generate_brd_context()["pipeline_stages"]` all equal `grounding.PIPELINE_STAGES`. Also assert `elicit_context()["intake_paths"]` equals `PIPELINE_STAGES[1]["intake_paths"]`.
- **Status**: [x] DONE — RED→GREEN

### T1a-4 — GREEN: inject `pipeline_stages` and `intake_paths` into the 3 composers
- **File**: `brain_ds/mcp/grounding.py`
- **Spec**: S1.4, S1.5, S1.6
- **Action**: In `elicit_context()`, `map_connections_context()`, and `generate_brd_context()`, add `"pipeline_stages": PIPELINE_STAGES` and `"intake_paths": PIPELINE_STAGES[1]["intake_paths"]` to the returned dict. Update each function's docstring to list the new keys.
- **Status**: [x] DONE — Makes T1a-3 GREEN

### T1a-5 — RED test: `DELEGATION_PROTOCOL` carries `pipeline_stages` and `intake_paths` keys
- **File**: `tests/test_elicit_lifecycle.py`
- **Spec**: S5.3 (REQUIRED_PROTOCOL_KEYS extension)
- **Action**: Extend `REQUIRED_PROTOCOL_KEYS` in the test file to include `"pipeline_stages"` and `"intake_paths"`. This causes `test_sdd_flow_doc_references_delegation_protocol_constants` to go RED (docs not yet updated).
- **Status**: [x] DONE — test constant extended; test intentionally RED pending T1b-1
- **Note**: This task only edits the test constant; the doc update is T1b-1.

### T1a-6 — RED test: `PHASE_PATTERN` admits `verify` and `archive` prefixes
- **File**: `tests/test_dryrun_elicit_compliance.py` (local copy) AND `tests/test_elicit_lifecycle.py` (`ELICIT_NAME_PATTERN`)
- **Spec**: S2.1, S5.1
- **Action**:
  - In `test_dryrun_elicit_compliance.py`: update the local `PHASE_PATTERN` regex to admit `verify|archive` prefixes (byte-identical with the other copies).
  - In `test_elicit_lifecycle.py`: update `ELICIT_NAME_PATTERN` regex to admit `verify|archive` prefixes.
  - In `test_elicit_lifecycle.py`: add `"verify"` and `"archive"` to `ALLOWED_PHASES`.
  - Do NOT touch `brain_ds/verify/elicit_compliance.py` yet — that is T1a-7 making these RED tests green.
- **Status**: [x] DONE — RED→GREEN (via T1a-7 + README fix)

### T1a-7 — GREEN: extend `PHASE_PATTERN` in `elicit_compliance.py`
- **File**: `brain_ds/verify/elicit_compliance.py`
- **Spec**: S2.1, S5.1
- **Action**: Update `PHASE_PATTERN` regex to include `setup|intake|verify|archive` prefixes. Must be byte-identical with the two test copies updated in T1a-6.
- **Status**: [x] DONE — all 3 regex copies byte-identical

### T1a-8 — RED test: verify gate writes artifact and blocks archive on CRITICAL
- **File**: `tests/test_elicit_lifecycle.py` (new test method)
- **Spec**: S2.2, S2.3, S2.4, S2.5
- **Action**: Add a test that creates a temp `.elicit/` dir, writes a `verify-acme-2026-06-14.md` file with a valid fenced-JSON envelope (`{graph_id, stage: "verify", status, critical_count, findings, gate}`), and asserts `check_elicit_compliance` returns no CRITICAL for a clean verify artifact. Add a second variant with `gate: "BLOCKED"` / non-empty `findings` and assert CRITICAL appears. This test exercises the verify-stage behavior of `check_elicit_compliance`.
- **Status**: [x] DONE — RED→GREEN

### T1a-9 — GREEN: verify-stage branch in `check_elicit_compliance`
- **File**: `brain_ds/verify/elicit_compliance.py`
- **Spec**: S2.2, S2.3, S2.4, S2.5
- **Action**: Add a branch in `check_elicit_compliance`: when `path.name.startswith("verify-")`, call a new private `_check_verify_payload(path, payload)` that validates the JSON envelope keys (`graph_id`, `stage`, `status`, `critical_count`, `findings`, `gate`) and emits CRITICAL if `gate == "BLOCKED"` or `findings` is non-empty. Return no CRITICAL for a clean verify artifact (archive is allowed to proceed).
- **Status**: [x] DONE — Makes T1a-8 GREEN

### T1a-10 — RED test: drift guard sweep passes with `PIPELINE_STAGES` in scope
- **File**: `tests/test_grounding_drift_guard.py`
- **Spec**: S5.4
- **Action**: Add an assertion that `"PIPELINE_STAGES"` appears in the set returned by `_discover_category2_constants()` and is NOT in `CATEGORY2_EXEMPT`. Confirm existing `test_no_stale_entity_references_in_category2_constants` still passes (all PIPELINE_STAGES strings are lowercase prose / hyphenated — no CamelCase entity tokens).
- **Status**: [x] DONE — RED→GREEN (auto-green after T1a-2)

---

## Slice 1b — Cross-Client Doc Mirrors (sequential after 1a is GREEN)

**Goal**: update all doc/prompt/skill files so the drift guard's doc-sync tests pass, the `.elicit/README.md` ownership table is exact, and skills are byte-identical mirrors.

### T1b-1 — Update `docs/SDD_FLOW.md` to reference `pipeline_stages` and `intake_paths`
- **File**: `docs/SDD_FLOW.md`
- **Spec**: S4.3 (REQUIRED_PROTOCOL_KEYS doc-sync gate)
- **Action**: Add a table row for `pipeline_stages` and `intake_paths` in the protocol-key reference section. Ensure the words `pipeline_stages` and `intake_paths` appear literally (the guard checks `assertIn`).
- **Status**: Makes T1a-5 / `test_sdd_flow_doc_references_delegation_protocol_constants` GREEN.

### T1b-2 — Update `.elicit/README.md` to add `verify` and `archive` ownership rows
- **File**: `.elicit/README.md`
- **Spec**: S5.2
- **Action**: Add exactly two new rows to the "Phase ownership" table:
  - `| \`verify\` | \`brainds-orchestrator\` |`
  - `| \`archive\` | \`brainds-orchestrator\` |`
  - Update the "phases" list prose to enumerate all 7 phases (including `setup`, `intake` — these do not need lifecycle rows if they have no `.elicit` artifact file, but `verify` and `archive` do). The `test_lifecycle_doc_ownership_table_consistent` exact-set guard must pass: every phase in `ALLOWED_PHASES` must appear as a backtick-quoted entry in the table.
- **Status**: Makes `test_lifecycle_doc_ownership_table_consistent` GREEN.
- **Watch-out**: The test uses `re.findall(r"\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|")` for `phase_to_owner`. Both `verify` and `archive` rows must follow that exact markdown column format.

### T1b-3 — Update `AGENT_FLOW.md` to show 6-stage pipeline
- **File**: `AGENT_FLOW.md`
- **Spec**: S4.3
- **Action**: Add or update the pipeline sequence section to show `setup → intake → map → brd → verify → archive` and reference `PIPELINE_STAGES`. The `test_skill_registry_lists_all_6_brainds_agents` test checks AGENT_FLOW.md for all 6 known agents — confirm they remain present.
- **Status**: Makes S4.3 doc check GREEN; no new test — relies on existing assertion.

### T1b-4 — Update orchestrator prompts: `prompts/brain-ds-orchestrator.md` and `.claude/agents/brainds-orchestrator.md`
- **Files**: `prompts/brain-ds-orchestrator.md`, `.claude/agents/brainds-orchestrator.md`
- **Spec**: S4.1
- **Action**: Add `pipeline_stages` and `intake_paths` keys to the DELEGATION_PROTOCOL reference section. Add the 6-stage sequence (`setup → intake → map → brd → verify → archive`) to the orchestration flow description. Cross-client source of truth is `DELEGATION_PROTOCOL` in `grounding.py`; both files must match.
- **Status**: Completes S4.1.

### T1b-5 — Sync skills: `skills/*/SKILL.md` ↔ `.opencode/skills/*/SKILL.md` byte-identical
- **Files**: skills that reference the agentic cycle — at minimum `skills/elicit-context/SKILL.md`, `skills/map-connections/SKILL.md`, `skills/generate-brd/SKILL.md` and their `.opencode` mirrors
- **Spec**: S4.2
- **Action**: For any skill file that references the pipeline (stage names, handoff sequence, `intake_paths`), update the prose and then copy byte-identically to the `.opencode/skills/` mirror. Run `test_skill_registry_lists_all_6_brainds_agents` to confirm no agent names were dropped.
- **Status**: Completes S4.2.
- **Watch-out**: If no skill prose references the pipeline (the cycle stages are only in orchestrator prompts), this task may be a no-op except for confirming the mirror stays in sync. Document the decision either way.

---

## Slice 2 — Live Delegation Seam (parallel to 1b, depends on 1a being GREEN)

**Goal**: introduce `LiveDelegationHarness` Protocol + `FakeDelegator`, refactor `dry_run_elicit_output` to route handoffs through the delegator, add `verify`+`archive` steps to the fixture, and write prompt-shape assertions.

### T2-1 — RED test stubs: `tests/test_delegation_seam.py` (empty stubs for seam contract)
- **File**: `tests/test_delegation_seam.py` (NEW)
- **Spec**: S3.1
- **Action**: Create the test file with import stubs for `LiveDelegationHarness`, `FakeDelegator`, `DelegationCall` from `tests.fixtures.delegation`. Add two placeholder test functions that call `from tests.fixtures.delegation import FakeDelegator` and immediately `raise NotImplementedError`. This makes the import fail RED before the fixture file exists.
- **Status**: RED (import error) until T2-2.

### T2-2 — GREEN: create `tests/fixtures/delegation.py` with `LiveDelegationHarness` Protocol, `FakeDelegator`, `DelegationCall`
- **File**: `tests/fixtures/delegation.py` (NEW)
- **Spec**: S3.1, S3.2
- **Action**: Define:
  - `@dataclass DelegationCall(agent: str, stage: str, refs: list[str])`
  - `class LiveDelegationHarness(Protocol)`: method `handoff(agent: str, stage: str, refs: list[str]) -> None`
  - `class FakeDelegator`: implements `LiveDelegationHarness`; stores each call in `self.calls: list[DelegationCall]`; raises `ValueError` if `agent` is not in `KNOWN_AGENTS` from `test_elicit_lifecycle`.
- **Status**: Makes T2-1 import RED → GREEN (stubs now importable).

### T2-3 — RED test: `FakeDelegator.calls` records stage-aware handoffs in order
- **File**: `tests/test_delegation_seam.py`
- **Spec**: S3.2, S3.3
- **Action**: Replace placeholder tests with real assertions:
  - Create a `FakeDelegator`, call `.handoff("brainds-source-explorer", "intake", ["ref1"])`, assert `delegator.calls[0] == DelegationCall(agent="brainds-source-explorer", stage="intake", refs=["ref1"])`.
  - Assert calling `.handoff` with an unknown agent raises `ValueError`.
- **Status**: RED until T2-2 is complete (T2-2 makes this GREEN).

### T2-4 — RED test: prompt-shape assertions per pipeline stage
- **File**: `tests/test_delegation_seam.py`
- **Spec**: S3.5, S3.6
- **Action**: Add tests that verify, for each stage, the handoff `refs` list follows the expected shape:
  - `intake` (datasource path): `refs[0]` matches the source-exploration artifact path pattern.
  - `map`: `refs` contains the `source-docs-*.md` path.
  - `brd`: `refs` contains the `map-*.md` path.
  - `verify`: `refs` contains the `brd-*.md` path and the `map-*.md` path.
  - `archive`: `refs` contains the `verify-*.md` path.
  Use `FakeDelegator` throughout — no real agents invoked.
- **Status**: RED until T2-5 updates `conftest.py` to produce these shapes.

### T2-5 — GREEN: refactor `dry_run_elicit_output` to route through `FakeDelegator`
- **File**: `tests/conftest.py`
- **Spec**: S3.4, S3.5, S3.6, S3.7
- **Action**:
  - Import `FakeDelegator` and `DelegationCall` from `tests.fixtures.delegation`.
  - Replace the bare `handoff(agent, refs)` closure with `delegator = FakeDelegator()` and `delegator.handoff(agent, stage, refs)` calls.
  - Update the handoff call sites to be stage-aware: `("brainds-source-explorer", "intake", [...])`, `("brainds-graph-mapper", "map", [...])`, `("brainds-connection-mapper", "map", [...])`, `("brainds-brd-writer", "brd", [...])`.
  - Add verify step: call `check_elicit_compliance(elicit_dir)`, write `verify-{org_slug}-{iso_date}.md` with the gate envelope, call `delegator.handoff("brainds-orchestrator", "verify", [str(verify_path)])`.
  - Add archive step: call `delegator.handoff("brainds-orchestrator", "archive", [str(verify_path)])`.
  - Expose `delegation_calls` (list of `DelegationCall`) and `verify_status` in the returned dict.
  - Keep backward-compat: `handoffs` key still returns `list[dict[str, str]]` derived from `delegator.calls` so existing tests on `dry_run_elicit_output["handoffs"]` do not break.
- **Status**: Makes T2-4 GREEN.
- **Watch-out**: `test_sub_agent_writes_only_to_elicit` checks `prompt_records = dry_run_elicit_output["handoffs"]` and asserts `handoff["prompt"]` contains `synthetic_source_path` and `"artifact"`. Backward-compat wrapper must preserve the `prompt` field.

### T2-6 — RED test: verify path written in the fixture and compliant
- **File**: `tests/test_dryrun_elicit_compliance.py`
- **Spec**: S2.2, S3.7
- **Action**: Add a test that reads `dry_run_elicit_output["elicit_dir"]`, globs `verify-*.md`, and asserts at least one exists; then calls `check_elicit_compliance(elicit_dir)` and asserts zero CRITICAL findings in the result set (the fixture's verify artifact should pass the gate cleanly).
- **Status**: RED until T2-5 adds the verify write to the fixture.

### T2-7 — GREEN: verify artifact written by fixture passes compliance
- **Implicit**: Once T2-5 writes a clean `verify-*.md` with a valid envelope and `gate: "PASS"`, T2-6 goes GREEN automatically. No extra implementation file needed — T2-5 covers this.

---

## Cascade / Watch-out Tasks (included in the slices above — explicit callouts)

### CW-1 — THREE `PHASE_PATTERN` copies must be byte-identical (spans T1a-6 + T1a-7)
- Files: `brain_ds/verify/elicit_compliance.py`, `tests/test_elicit_lifecycle.py` (`ELICIT_NAME_PATTERN`), `tests/test_dryrun_elicit_compliance.py` (`PHASE_PATTERN`)
- Rule: commit T1a-6 and T1a-7 in the SAME commit. The regex after the change must read:
  `r"^(elicit|source-exploration|source-docs|map|brd|setup|intake|verify|archive)-[a-z0-9_-]+-\d{4}-\d{2}-\d{2}\.md$"`

### CW-2 — `.elicit/README.md` exact-set ownership table (T1b-2)
- The test uses `set(phase_to_owner.keys()) == set(ALLOWED_PHASES)`. After adding `verify` and `archive` to `ALLOWED_PHASES`, the README table must contain rows for EVERY phase in `ALLOWED_PHASES` — including existing ones. If `setup` or `intake` are in `ALLOWED_PHASES` but have no `.elicit` artifact convention, decide explicitly: either add them to `ALLOWED_PHASES` only after confirming a README row exists, or defer those two phases to a follow-up change. Default recommendation: add `verify` and `archive` only (to match spec scope); do NOT add `setup`/`intake` to `ALLOWED_PHASES` unless they have artifact files — the spec only requires `verify` and `archive` phase extensions.

### CW-3 — `skills/` ↔ `.opencode/skills/` byte-identical mirror (T1b-5)
- After any edit to a `skills/*/SKILL.md`, run a file-diff check to confirm the `.opencode/skills/*/SKILL.md` counterpart is byte-identical. If only orchestrator prompts change (not skills), this is a no-op.

### CW-4 — `DELEGATION_PROTOCOL.artifact_keys.phases` list update (T1a-4 cascade)
- `DELEGATION_PROTOCOL["artifact_keys"]["phases"]` currently lists `["elicit", "source-exploration", "source-docs", "map", "brd"]`. After this change it must include `"verify"` and `"archive"`. This is part of T1a-4 (same commit as the composer updates). The `test_sdd_flow_doc_references_delegation_protocol_constants` guard requires `docs/SDD_FLOW.md` to mention `pipeline_stages` and `intake_paths` — not the `phases` list itself — so this update is silent to that guard but is required for cross-client correctness.

---

## Execution Order

```
Slice 1a (sequential):
  T1a-1 (RED) → T1a-2 (GREEN)
  T1a-3 (RED) → T1a-4 (GREEN)
  T1a-5 (RED) [test constant edit only]
  T1a-6 (RED) → T1a-7 (GREEN) [same commit: all 3 regex copies]
  T1a-8 (RED) → T1a-9 (GREEN)
  T1a-10 (RED → auto-GREEN after T1a-2)

Slice 1b (sequential, after 1a is GREEN):
  T1b-1 → makes T1a-5 GREEN
  T1b-2 → makes T1a-6/ALLOWED_PHASES test GREEN
  T1b-3
  T1b-4
  T1b-5

Slice 2 (parallel to 1b, depends only on 1a):
  T2-1 (RED) → T2-2 (GREEN)
  T2-3 (RED → GREEN with T2-2)
  T2-4 (RED) → T2-5 (GREEN)
  T2-6 (RED) → T2-7 (implicit GREEN with T2-5)
```

## PR Plan

| PR | Slices | What ships | CI gate |
|---|---|---|---|
| PR-1 | 1a | `PIPELINE_STAGES`, verify gate, pattern extensions, drift guard | All tests GREEN |
| PR-2 | 1b | Doc mirrors, README ownership, SDD_FLOW, prompts, skills | Doc-sync tests GREEN |
| PR-3 | 2 | `delegation.py`, conftest refactor, delegation seam tests | All tests GREEN |

PR-2 and PR-3 can be opened in parallel after PR-1 merges (no overlap on files).
