# Archive Report — brainds-harness-integrity-guards

**Change**: brainds-harness-integrity-guards
**Status**: ARCHIVED — SDD COMPLETE
**Date**: 2026-06-15
**Verdict**: PASS — 0 CRITICAL, 0 WARNING, 1 SUGGESTION (non-blocking)

---

## Executive Summary

Archived brainds-harness-integrity-guards: three ADD-only harness integrity guards deployed in a single PR (3 commit groups B→A→C, ~315 lines, under 400-line budget). Strict TDD: all 12 tasks GREEN. All tests PASS (1392 passed, 1 pre-existing Windows installer non-blocker, 3 skipped). brain_ds check: 16 PASS / 1 SKIP / 0 FAIL (17 total). Closes all three live follow-ups (#1 agent-definition drift guard / #2 graph-write isolation confirmed non-bug / #3 per-cycle subdir scoping).

---

## What Shipped

### R1 — Agent-Definition Guards (~200 lines)
- **check_agent_files()** function in brain_ds/harness_check.py
- **SUBAGENT_NAMES** enum: 4 registered slugs (brainds-brd-writer, brainds-connection-mapper, brainds-docs, brainds-query-consultant)
- **CLAUDE_AGENT_FILES** mapping: agent file paths (`.claude/agents/`, `.opencode/agents/`)
- **REQUIRED_AGENT_GRANTS** dict: per-agent required MCP tool grants (Write, Delegate, Read; query-consultant has no Write — absence encoding)
- **_parse_agent_frontmatter()**: UTF-8 BOM + CRLF-safe YAML parser (survives Windows .claude files)
- One CheckResult per agent (agent-file-{slug}, agent-name-{slug}, agent-tools-{slug})
- query-consultant mirror absence → SKIP not FAIL (future mirror tolerance)
- Registered in _run_all_checks tuple
- Would have caught the live connection-mapper Write scare (M3 undetected agent grant drift)

### R2 — Graph-Write Isolation Regression Test (~40 lines)
- **test_update_node_preserves_unrelated_node_and_edge()**: confirms upsert_node COALESCE isolation
  - Seeds N-2, N-3, B→C edge in setUp
  - Updates N-1 label
  - Asserts N-2 label/type/details + B→C edge survive update
  - Node count = 3 (no accidental deletes)
- **test_update_node_write_takes_effect()**: confirms updated label is returned
- Verdict: upsert is ISOLATED (live "Organization node loss" was a filtered-view misread, NOT a store bug)

### R3 — Per-Cycle Elicit Subdir Scoping (~75 lines)
- **Expanded glob** in assess_elicit_compliance: union of `*.md` + `*/*.md` (one level only)
- **PHASE_PATTERN** dedup: canonical import from brain_ds.verify.elicit_compliance (removed redundant local definitions in test_elicit_lifecycle.py and test_dryrun_elicit_compliance.py)
- Four new tests:
  - test_subdir_artifact_is_discovered
  - test_flat_artifact_backward_compat
  - test_readme_in_subdir_is_ignored
  - test_broken_subdir_artifact_raises_critical
- Supports `.elicit/sdd/*/` per-change artifact organization without breaking old flat `.elicit/*.md`

---

## Final State

| Metric | Value |
|--------|-------|
| Tasks total | 12 |
| Tasks complete | 12 |
| Tests passed | 1392 |
| Tests failed | 1 (pre-existing Windows installer non-blocker) |
| Tests skipped | 3 |
| brain_ds check PASS | 16 |
| brain_ds check SKIP | 1 |
| brain_ds check FAIL | 0 |
| Total checks | 17 (measured; stale "12 checks" in AGENT_FLOW.md corrected) |
| Commits | 3 groups (B→A→C) |
| Changed lines | ~315 (under 400 budget) |
| Delivery | Single PR |

---

## Spec Compliance (15/15 COMPLIANT)

All 15 spec scenarios (R1 7-part agent check, R2 2-part graph isolation, R3 4-part subdir scoping, R1.F check count verification) passed strict TDD RED→GREEN in verify-report #2193. No CRITICAL or WARNING findings.

---

## Out-of-Scope Fence (HONORED)

- ✓ No grounding.py ontology context edits
- ✓ No EntityType or RelationshipType changes
- ✓ No agent .md content edits (only guard logic)
- ✓ No save_graph/import_graph changes
- ✓ No skill prose updates

---

## Issues Closed

This SDD closes all three live follow-ups from M3:

1. **Agent-definition drift uncaught** (connection-mapper Write scare)
   - check_agent_files() + REQUIRED_AGENT_GRANTS now enforce agent-tool alignment
   - Would have caught the M3 agent grant gap

2. **Graph write isolation questioned** (Organization node loss panic)
   - test_update_node_preserves_unrelated_node_and_edge() confirms upsert COALESCE isolation
   - Verdict: store logic is sound; live issue was a filtered-view misread, NOT a bug

3. **Per-cycle subdir artifact scoping missing**
   - elicit_compliance glob expanded; PHASE_PATTERN centralized
   - `.elicit/sdd/{change-name}/*.md` now discoverable without breaking flat backward compat

---

## Artifact Index (Engram Topic Keys)

| Phase | ID | Topic Key |
|-------|----|-----------| 
| Explore | 2186 | sdd/brainds-harness-integrity-guards/explore |
| Proposal | 2187 | sdd/brainds-harness-integrity-guards/proposal |
| Spec | 2188 | sdd/brainds-harness-integrity-guards/spec |
| Design | 2189 | sdd/brainds-harness-integrity-guards/design |
| Tasks | 2190 | sdd/brainds-harness-integrity-guards/tasks |
| Apply-Progress | 2191 | sdd/brainds-harness-integrity-guards/apply-progress |
| Verify-Report | 2193 | sdd/brainds-harness-integrity-guards/verify-report |
| Archive-Report | 2194 | sdd/brainds-harness-integrity-guards/archive-report |

---

## Files Modified (Git)

Committed in three groups:
- **B**: tests/test_mcp_tools.py (2 new RED→GREEN tests)
- **A**: brain_ds/harness_check.py + tests/test_harness_check.py (R1 agent check implementation + 7 tests)
- **C**: brain_ds/verify/elicit_compliance.py + tests/test_elicit_lifecycle.py + tests/test_dryrun_elicit_compliance.py (R3 subdir glob + PHASE_PATTERN dedup + 4 tests)

Also updated: AGENT_FLOW.md (stale "12 checks" → measured 17).

---

## Recommendation

No follow-up needed. SDD is complete. All three harness gaps are closed. Ready to merge and ship.

---

Session: manual-brain_ds-2026-06-15-sdd-archive
Project: brain_ds
Scope: project
Topic: sdd/brainds-harness-integrity-guards/archive-report
