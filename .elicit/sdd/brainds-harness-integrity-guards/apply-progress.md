# Apply Progress — brainds-harness-integrity-guards

**Change**: brainds-harness-integrity-guards
**Mode**: Strict TDD (RED → GREEN per task group)
**Batch**: 1 of 1 — ALL tasks complete
**Status**: Ready for sdd-verify

---

## TDD Cycle Evidence

| Task | RED | GREEN | Notes |
|------|-----|-------|-------|
| B-1 | Test written; `confidence` column error (schema uses `weight`) | Fixed schema ref → PASS | upsert_node IS COALESCE-isolated; no escalation needed |
| B-2 | Wrote test first, immediately GREEN | PASS | Write took effect correctly |
| A-1..A-7 | ImportError on `check_agent_files` | PASS after implementation | 7 AgentFileCheckTests all green |
| A-8 | Implemented constants + check function | All 7 tests PASS | Registered in _run_all_checks |
| C-1 | Subdir path two-level; adjusted to single-level per `*/*.md` design | PASS | |
| C-2 | README in subdir silently ignored | PASS | PHASE_PATTERN.match(name) provides free scoping |
| C-3 | Phase-named broken artifact in subdir → CRITICAL | PASS after C-5 | |
| C-4 | Flat backward compat | PASS | additive union preserves flat level |
| C-5 | Glob union `*.md | */*.md` | All 4 C tests PASS | |
| C-6 | Removed local PHASE_PATTERN duplicates; import from canonical | PASS | Re-added `import re` for _artifact_payload |
| F-1 | Measured `brain_ds check` → 17 checks | Updated AGENT_FLOW.md: 12 → 17 | |
| F-2 | Full pytest: 1392 passed, 1 pre-existing installer FAIL | `brain_ds check` exits 0 | Gate passed |

---

## Completed Tasks

- [x] B-1: test_update_node_preserves_unrelated_node_and_edge
- [x] B-2: test_update_node_write_takes_effect
- [x] A-1..A-7: AgentFileCheckTests (7 tests RED then GREEN)
- [x] A-8: check_agent_files() implementation + registration
- [x] C-1: test_subdir_artifact_is_discovered
- [x] C-2: test_readme_in_subdir_is_ignored
- [x] C-3: test_broken_subdir_artifact_raises_critical
- [x] C-4: test_flat_artifact_backward_compat
- [x] C-5: Additive glob union in elicit_compliance.py
- [x] C-6: Removed PHASE_PATTERN duplicates; canonical import
- [x] F-1: Measured 17 checks; updated AGENT_FLOW.md
- [x] F-2: Full test suite + brain_ds check both pass

---

## Files Changed

| File | Action | What |
|------|--------|------|
| `tests/test_mcp_tools.py` | Modified | N-3 bystander + edge in setUp; B-1/B-2 tests; node count assertions updated; N-3→N-new in enqueues test |
| `tests/test_harness_check.py` | Modified | Added check_agent_files import; AgentFileCheckTests (7 tests); _write_passing_agent_files helper |
| `brain_ds/harness_check.py` | Modified | SUBAGENT_NAMES, CLAUDE_AGENT_FILES, REQUIRED_AGENT_GRANTS, _parse_agent_frontmatter, check_agent_files, registered in _run_all_checks |
| `brain_ds/verify/elicit_compliance.py` | Modified | Additive glob union `sorted(set(*.md) | set(*/*.md))` |
| `tests/test_elicit_lifecycle.py` | Modified | Removed local ELICIT_NAME_PATTERN; imported PHASE_PATTERN; added C-1..C-4 tests |
| `tests/test_dryrun_elicit_compliance.py` | Modified | Removed local PHASE_PATTERN; imported from canonical; kept `import re` |
| `AGENT_FLOW.md` | Modified | "12 checks" → "17 checks" (measured) |

---

## Deviations from Design

1. `test_update_node_enqueues_node_created` used `N-3` as the "new" node; changed to `N-new` since N-3 is now seeded in setUp.
2. C test subdirs use single-level depth (not `changes/my-change/`) to match the `*/*.md` glob. The spec scenario at two-level depth was inconsistent with the design's stated `*/*.md` glob pattern.
3. `import re` was still needed in `test_dryrun_elicit_compliance.py` after removing PHASE_PATTERN (used by `_artifact_payload`).

```json
{
  "artifact_type": "apply-progress",
  "change": "brainds-harness-integrity-guards",
  "status": "complete",
  "tasks_done": 12,
  "tasks_total": 12,
  "test_result": "1392 passed, 1 pre-existing fail (installer/opencode), 3 skipped",
  "check_result": "17 checks: 16 PASS, 1 SKIP, 0 FAIL",
  "next_recommended": "sdd-verify"
}
```
