# Apply Progress — brainds-live-agentic-cycle-validation

## Batch: PR-1 / Slice 1a + PR-2 / Slice 1b (doc mirrors) + PR-3 / Slice 2 (delegation seam)

**Mode**: Strict TDD (RED → GREEN → REFACTOR)
**Date**: 2026-06-14
**Status**: COMPLETE — 22/22 tasks done; 0 intentional REDs remaining; all 3 slices done, ready for verify

---

## TDD Cycle Evidence

### Slice 1a

| Task | RED evidence | GREEN evidence | Notes |
|---|---|---|---|
| T1a-1 | `AttributeError: module 'brain_ds.mcp.grounding' has no attribute 'PIPELINE_STAGES'` | `test_pipeline_stages_constant_shape_and_order` PASS | Confirmed RED before T1a-2 |
| T1a-2 | — | T1a-1 GREEN after inserting PIPELINE_STAGES constant | Implementation task |
| T1a-3 | `AssertionError: 'pipeline_stages' not found in {…elicit_context…}` | `test_pipeline_stages_in_all_three_grounding_payloads` PASS | Confirmed RED before T1a-4 |
| T1a-4 | — | T1a-3 GREEN after composer injection | Implementation task |
| T1a-5 | `AssertionError: 'pipeline_stages' not in SDD_FLOW.md` | GREEN via T1b-1 (docs/SDD_FLOW.md) | Cross-slice; intentional |
| T1a-6 | `` '`verify`' not found in README `` | GREEN after T1a-7 + README rows | Required ALLOWED_PHASES guard |
| T1a-7 | — | 3 PHASE_PATTERN copies byte-identical | Implementation task |
| T1a-8 | CRITICAL for clean verify artifact (naming mismatch) | `test_verify_artifact_clean_passes_compliance` PASS | Verify gate |
| T1a-9 | — | T1a-8 GREEN after PHASE_PATTERN admission of verify prefix | Implementation task |
| T1a-10 | `PIPELINE_STAGES not in discovered set` | `test_pipeline_stages_discovered_and_not_exempt` PASS | Drift guard |

### Slice 1b

| Task | RED evidence | GREEN evidence | Notes |
|---|---|---|---|
| T1b-1 | `AssertionError: 'pipeline_stages' not in docs/SDD_FLOW.md` (pre-existing from 1a) | `test_sdd_flow_doc_references_delegation_protocol_constants` PASS | Intentional RED |
| T1b-2 | — | AGENT_FLOW.md pipeline section added | Doc-only task |
| T1b-3 | — | prompts/brain-ds-orchestrator.md restructured | Doc-only task |
| T1b-4 | — | .claude/agents/brainds-orchestrator.md restructured | Doc-only task |
| T1b-5 | — | skills/elicit-context/SKILL.md + .opencode mirror byte-identical; `brain_ds check` 4 PASS | Harness check guard |

### Slice 2

| Task | RED evidence | GREEN evidence | Notes |
|---|---|---|---|
| T2-1 | `ModuleNotFoundError: No module named 'tests.fixtures.delegation'` | `DelegationCall` dataclass created | Confirmed RED before creating module |
| T2-2 | same import error | `LiveDelegationHarness` Protocol created | Part of same module |
| T2-3 | same import error | `FakeDelegator` created with `to_handoffs()` | Part of same module |
| T2-4 | 9 tests: 6 PASS + 3 FAIL (`delegation_calls` not in fixture) | All 9 PASS after conftest refactor | S3.1–S3.7 + 2 backward-compat |
| T2-5 | `AssertionError: dry_run_elicit_output must expose 'delegation_calls'` | conftest.py refactored; `delegation_calls` exposed | Seam injection |
| T2-6 | — | `test_sub_agent_writes_only_to_elicit` still PASS | `prompt` field preserved via `FakeDelegator` |
| T2-7 | — | 1340 passed, 0 intentional REDs; `brain_ds check` 4 PASS | Full suite gate |

---

## Completed Tasks

### Slice 1a — [x] ALL DONE
- [x] T1a-1: PIPELINE_STAGES constant defined in grounding.py
- [x] T1a-2: Implementation (PIPELINE_STAGES list with 6 stages)
- [x] T1a-3: pipeline_stages + intake_paths injected in all 3 payload composers
- [x] T1a-4: Implementation (elicit_context, map_connections_context, generate_brd_context)
- [x] T1a-5: SDD_FLOW.md doc guard (resolved via T1b-1)
- [x] T1a-6: .elicit/README.md verify + archive rows
- [x] T1a-7: 3 PHASE_PATTERN copies byte-identical (elicit_compliance.py, test_elicit_lifecycle.py, test_dryrun_elicit_compliance.py)
- [x] T1a-8: verify gate — check_elicit_compliance handles verify-*.md without CRITICAL
- [x] T1a-9: Implementation (_check_verify_payload in elicit_compliance.py)
- [x] T1a-10: drift guard — PIPELINE_STAGES auto-discovered, NOT in CATEGORY2_EXEMPT

### Slice 1b — [x] ALL DONE
- [x] T1b-1: docs/SDD_FLOW.md — pipeline_stages + intake_paths referenced; RED test GREEN
- [x] T1b-2: AGENT_FLOW.md — linear pipeline section + intake_paths branching diagram
- [x] T1b-3: prompts/brain-ds-orchestrator.md — 6-stage linear pipeline + verify gate
- [x] T1b-4: .claude/agents/brainds-orchestrator.md — 6-stage pipeline + verify/archive phases
- [x] T1b-5: skills/elicit-context/SKILL.md Pipeline Stages section + .opencode mirror byte-identical + SHARED_CONTEXT.md updated

### Slice 2 — [x] ALL DONE
- [x] T2-1: `DelegationCall` dataclass (agent, stage, refs, prompt) in `tests/fixtures/delegation.py`
- [x] T2-2: `LiveDelegationHarness` Protocol (runtime_checkable; `delegate()` + `calls` property)
- [x] T2-3: `FakeDelegator` class (synthetic_source_path stitched into prompt; `to_handoffs()` backward-compat helper)
- [x] T2-4: `tests/test_delegation_seam.py` — 9 tests all GREEN (S3.1–S3.7 + 2 backward-compat guards)
- [x] T2-5: `tests/conftest.py` refactored — `handoff(agent, stage, refs)` routes through `FakeDelegator`; `delegation_calls` exposed in return dict; backward-compat `handoffs` derived from `delegator.to_handoffs()`
- [x] T2-6: Backward-compat verified — `test_sub_agent_writes_only_to_elicit` PASS; `prompt` field preserved
- [x] T2-7: Full suite 1340 passed, 3 skipped, 1 pre-existing unrelated failure; `brain_ds check` 4 PASS 0 FAIL

---

## Files Changed

### Slice 1a
- `brain_ds/mcp/grounding.py` — PIPELINE_STAGES constant + 3-composer injection + DELEGATION_PROTOCOL.phases
- `brain_ds/verify/elicit_compliance.py` — PHASE_PATTERN extended + `_check_verify_payload` + completeness refactor
- `tests/test_elicit_lifecycle.py` — ALLOWED_PHASES, REQUIRED_PROTOCOL_KEYS, ELICIT_NAME_PATTERN + 4 new test methods
- `tests/test_dryrun_elicit_compliance.py` — local PHASE_PATTERN updated (byte-identical)
- `tests/test_grounding_drift_guard.py` — `test_pipeline_stages_discovered_and_not_exempt` added
- `tests/test_mcp_grounding.py` — 3 key-count tests updated (12→14, 10→12, 8→10)
- `.elicit/README.md` — verify + archive ownership rows added

### Slice 1b
- `docs/SDD_FLOW.md` — full rewrite with pipeline_stages table, intake_paths branching, all 8 protocol keys
- `AGENT_FLOW.md` — Pipeline lineal section + intake_paths branching + delegation diagram updated
- `prompts/brain-ds-orchestrator.md` — Pipeline stages table + intake_paths section + 6-step execution flow
- `.claude/agents/brainds-orchestrator.md` — Pipeline Stages section + intake branching + Phase 5/6 added
- `.elicit/README.md` — Quick path updated (verify/archive phases + gate requirement)
- `skills/elicit-context/SKILL.md` — Pipeline Stages (Mandatory) section added
- `.opencode/skills/elicit-context/SKILL.md` — byte-identical mirror
- `skills/SHARED_CONTEXT.md` — elicit-context summary updated; date bumped

### Slice 2
- `tests/fixtures/delegation.py` **(NEW)** — `DelegationCall` + `LiveDelegationHarness` + `FakeDelegator`
- `tests/test_delegation_seam.py` **(NEW)** — 9 prompt-shape / routing / backward-compat tests
- `tests/conftest.py` — `FakeDelegator` import; `handoff()` signature updated; `delegation_calls` exposed; backward-compat `handoffs` derived

---

## Final Test Run (Slice 2)

```
1340 passed, 3 skipped, 1 failed (pre-existing)
```

Pre-existing failure: `test_register_path_copies_wrapper_sh` — OpenCode CLI not installed; `dirname` command missing in POSIX shell on Windows. NOT part of this change.

## brain_ds check
```
4 PASS, 0 FAIL, 0 SKIP
```

## Next Step
`sdd-verify` — validate all 22 scenarios from the spec against the implementation.
