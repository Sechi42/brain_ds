# Verify Report — brainds-harness-integrity-guards

**Change**: brainds-harness-integrity-guards
**Version**: spec #2188
**Mode**: Strict TDD
**Date**: 2026-06-15

---

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 12 |
| Tasks complete | 12 |
| Tasks incomplete | 0 |

All 12 tasks marked [x] in apply-progress. No incomplete tasks.

---

## Build & Tests Execution

**Build**: N/A (Python project, no compile step)

**Tests**: 1392 passed / 1 failed (pre-existing, installer/opencode CLI not installed on Windows) / 3 skipped

```
FAILED tests/test_installer.py::InstallerTests::test_register_path_copies_wrapper_sh
  AssertionError: 1 != 0 : OpenCode CLI not found. Install: https://opencode.ai/docs
  install-opencode.sh: line 4: dirname: command not found
```

Pre-existing failure: not caused by this change, confirmed in apply-progress as known non-blocker.

**brain_ds check**: 16 PASS, 0 FAIL, 1 SKIP — exits 0

**Coverage**: Not measured in this run (full suite ran; TDD coverage verified per task group at apply time)

---

## TDD Compliance (Strict TDD Mode)

| Task Group | TDD Cycle | Result |
|-----------|-----------|--------|
| B-1 (bystander test) | RED (schema ref error) → GREEN (fixed `weight`) | PASS |
| B-2 (write takes effect) | Immediate GREEN | PASS |
| A-1..A-7 (AgentFileCheckTests) | RED (ImportError) → GREEN after implementation | PASS |
| A-8 (implementation) | Implementation → all 7 tests GREEN | PASS |
| C-1..C-4 (subdir scoping) | RED → GREEN after glob union | PASS |
| C-5 (glob change) | Implemented; all 4 C tests PASS | PASS |
| C-6 (import canonical) | Removed duplicates; import verified | PASS |
| F-1 (measure + AGENT_FLOW) | Measured 17 checks; updated AGENT_FLOW.md | PASS |
| F-2 (gate) | 1392 passed; brain_ds check exits 0 | PASS |

---

## Spec Compliance Matrix

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R1: check_agent_files | all agents pass when correct | `test_harness_check.py::AgentFileCheckTests::test_all_agents_pass_when_correct` | COMPLIANT |
| R1: check_agent_files | missing required grant → FAIL | `test_harness_check.py::AgentFileCheckTests::test_missing_required_grant_fails` | COMPLIANT |
| R1: check_agent_files | agent file absent → FAIL | `test_harness_check.py::AgentFileCheckTests::test_missing_agent_file_fails` | COMPLIANT |
| R1: check_agent_files | name frontmatter mismatch → FAIL | `test_harness_check.py::AgentFileCheckTests::test_name_mismatch_fails` | COMPLIANT |
| R1: check_agent_files | query-consultant absent → SKIP not FAIL | `test_harness_check.py::AgentFileCheckTests::test_query_consultant_mirror_absent_is_skip_not_fail` | COMPLIANT |
| R1: check_agent_files | CRLF/BOM → PASS (robust parse) | `test_harness_check.py::AgentFileCheckTests::test_crlf_bom_frontmatter_parses_pass` | COMPLIANT |
| R1: check_agent_files | registered in _run_all_checks | `test_harness_check.py::AgentFileCheckTests::test_agent_check_registered_in_runner` | COMPLIANT |
| R1: AGENT_FLOW check count | must equal actual count (17) | AGENT_FLOW.md content + brain_ds check output | COMPLIANT |
| R2: bystander preservation | N-2 + N-2→N-3 edge survive update_node(N-1) | `test_mcp_tools.py::MCPToolsTests::test_update_node_preserves_unrelated_node_and_edge` | COMPLIANT |
| R2: write takes effect | updated node reflects new label | `test_mcp_tools.py::MCPToolsTests::test_update_node_write_takes_effect` | COMPLIANT |
| R3: subdir artifact discovered | brd in elicit_dir/subdir/ found | `test_elicit_lifecycle.py::TestElicitLifecycle::test_subdir_artifact_is_discovered` | COMPLIANT |
| R3: flat backward compat | flat elicit/*.md still found | `test_elicit_lifecycle.py::TestElicitLifecycle::test_flat_artifact_backward_compat` | COMPLIANT |
| R3: README ignored at subdir | README.md silently ignored | `test_elicit_lifecycle.py::TestElicitLifecycle::test_readme_in_subdir_is_ignored` | COMPLIANT |
| R3: broken subdir → CRITICAL | phase-named broken artifact in subdir | `test_elicit_lifecycle.py::TestElicitLifecycle::test_broken_subdir_artifact_raises_critical` | COMPLIANT |
| R3: PHASE_PATTERN canonical | imported from elicit_compliance, no duplicate | `test_elicit_lifecycle.py` module import + `test_dryrun_elicit_compliance.py` module import | COMPLIANT |

**Compliance summary**: 15/15 scenarios compliant

---

## Correctness (Static — Structural Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| `check_agent_files()` exists in harness_check.py | Implemented | Lines 185-270, `brain_ds/harness_check.py` |
| Registered in `_run_all_checks` | Implemented | Line 275: tuple includes `check_agent_files` |
| SUBAGENT_NAMES has exactly 4 slugs | Implemented | Lines 15-20: 4 slugs |
| CLAUDE_AGENT_FILES maps each slug | Implemented | Lines 22-24 |
| REQUIRED_AGENT_GRANTS matches spec | Implemented | Lines 28-33; graph-mapper has NO Write (absence encoding) |
| `_parse_agent_frontmatter` handles utf-8-sig + CRLF | Implemented | Lines 142-182 |
| bystander test asserts N-2 label/type/details/edge + node count | Implemented | Lines 122-145, test_mcp_tools.py |
| Glob union `*.md \| */*.md` in elicit_compliance | Implemented | Lines 137-138, elicit_compliance.py |
| PHASE_PATTERN.match(path.name) scopes both levels | Implemented | Line 145, elicit_compliance.py |
| PHASE_PATTERN imported canonically in both test files | Implemented | test_elicit_lifecycle.py:9, test_dryrun_elicit_compliance.py:10 |
| AGENT_FLOW.md updated 12→17 checks | Implemented | AGENT_FLOW.md contains "17 checks" |
| brain_ds check exits 0 with 17 results | Confirmed | `uv run brain_ds check` output: 16 PASS, 0 FAIL, 1 SKIP |

---

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| One CheckResult per agent (not aggregate) | Yes | `agent-file-{slug}`, `agent-name-{slug}`, `agent-tools-{slug}` per slug |
| Frontmatter parse: utf-8-sig + CRLF normalize + line-scan | Yes | `_parse_agent_frontmatter` implementation exact match |
| query-consultant → SKIP never FAIL | Yes | Lines 252-268, harness_check.py |
| graph-mapper Write absence encoded (no negative assertion) | Yes | `REQUIRED_AGENT_GRANTS` has no `Write` for graph-mapper; no negative test |
| R2 no prod change (Approach A test-only) | Yes | N-3 + edge seeded in setUp; no production code changed for R2 |
| R3 Approach A additive: glob union, PHASE_PATTERN scoping free | Yes | elicit_compliance.py line 137-138 |
| N-new used instead of N-3 in enqueues_node_created | Yes | Design deviation noted; avoids setUp conflict |
| AGENT_FLOW.md: measured value, not hardcoded | Yes | Measured 17 via harness_check_main, then written |
| source-explorer grants: spec value used (not design superset) | Yes | Spec is authoritative: `{"Write", "mcp__brain_ds__explore_source"}` |

---

## Issues Found

**CRITICAL** (must fix before archive):
None

**WARNING** (should fix):
None

**SUGGESTION** (nice to have):
- The design mentioned `list_source_connections` and `query_source` as part of source-explorer grants superset, but the spec only requires `{"Write", "mcp__brain_ds__explore_source"}`. Implementation correctly follows spec. Future spec update could expand grants if needed.

---

## Verdict

PASS

All 12 tasks complete. 15/15 spec scenarios compliant with passing tests. Full suite: 1392 passed, 1 pre-existing non-blocker (Windows installer opencode CLI), 3 skipped. `brain_ds check` exits 0 with 17 checks (16 PASS, 1 SKIP). Out-of-scope fence honored: no grounding.py edits, no ontology changes, no agent .md content edits, no save_graph/import_graph changes. Archive is allowed.
