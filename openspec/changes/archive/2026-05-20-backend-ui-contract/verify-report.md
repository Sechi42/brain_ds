## Verification Report

**Change**: backend-ui-contract
**Version**: 1.0.0
**Mode**: Strict TDD

---

### Completeness
| Metric | Value |
|--------|-------|
| Tasks total | 22 |
| Tasks complete | 22 |
| Tasks incomplete | 0 |

All checklist items in `openspec/changes/backend-ui-contract/tasks.md` are complete.

---

### Build & Tests Execution

**Build**: ➖ Skipped
```text
Skipped by project rule: never build after changes.
```

**Tests**: ✅ 602 passed / ❌ 0 failed / ⚠️ 4 skipped
```text
Focused warning-remediation suite:
uv run python -m unittest tests.test_render_context_golden
Result: 9 passed

Targeted verification suite:
uv run python -m unittest tests.test_render_context_contract tests.test_contract_version_sync tests.test_render_context_golden tests.test_cli tests.test_viewer
Result: 111 passed

Full strict suite:
uv run python -m unittest discover -s tests
Result: 602 passed, 4 skipped
```

**Coverage**: ➖ Not available

---

### TDD Compliance
| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | Found in apply-progress #888 |
| All remediation tasks have tests | ✅ | 1/1 remediation row is test-backed in `tests/test_render_context_golden.py` |
| RED confirmed (tests exist) | ✅ | The dedicated `openedAt` regex lock test exists in the modified test file |
| GREEN confirmed (tests pass) | ✅ | Focused, targeted, and full strict suites all pass |
| Triangulation adequate | ➖ | Single locked-regex assertion is appropriate for this narrow remediation |
| Safety Net for modified files | ✅ | Prior contract coverage remains green; preserved suites stayed green in targeted/full runs |

**TDD Compliance**: 6/6 checks passed

---

### Test Layer Distribution
| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit | 32 | 3 | `unittest` |
| Integration | 0 | 0 | not installed |
| E2E | 0 | 0 | not installed |
| **Total** | **32** | **3** | |

Contract coverage remains in `tests/test_render_context_contract.py`, `tests/test_render_context_golden.py`, and `tests/test_contract_version_sync.py`.

---

### Changed File Coverage
Coverage analysis skipped — no coverage tool detected.

---

### Assertion Quality
**Assertion quality**: ✅ All assertions verify real behavior

The new `openedAt` regression check is source-backed: it imports production-adjacent `LOCKED_UTC_SECONDS_PATTERN` and locks it to the exact UTC-second regex, so drift in the real contract constant fails the suite.

---

### Quality Metrics
**Linter**: ➖ Not available
**Type Checker**: ➖ Not available

### Spec Compliance Matrix

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R01 | R01-A contract_version literal | `tests/test_render_context_contract.py > test_contract_version_is_one_zero_zero` | ✅ COMPLIANT |
| R01 | R01-B contract_version at root | `tests/test_render_context_contract.py > test_contract_version_is_one_zero_zero` | ✅ COMPLIANT |
| R01 | R01-C literal regression test exists | `tests/test_render_context_contract.py > test_contract_version_is_one_zero_zero` | ✅ COMPLIANT |
| R02 | R02-A nested workspace derivation | `tests/test_render_context_contract.py > test_meta_workspace_present_and_well_formed` | ✅ COMPLIANT |
| R02 | R02-B depth-0 fallback | `tests/test_render_context_contract.py > test_meta_workspace_depth_zero_fallback` | ✅ COMPLIANT |
| R02 | R02-C depth-1 project only | `tests/test_render_context_contract.py > test_meta_workspace_depth_one_project_only` | ✅ COMPLIANT |
| R02 | R02-D POSIX displayPath on Windows | `tests/test_render_context_contract.py > test_meta_workspace_display_path_uses_posix_slashes` | ✅ COMPLIANT |
| R03 | R03-A max incident edge score | `tests/test_render_context_contract.py > test_node_score_is_max_of_incident_edge_scores` | ✅ COMPLIANT |
| R03 | R03-B isolated score is 0.0 | `tests/test_render_context_contract.py > test_isolated_node_score_is_zero` | ✅ COMPLIANT |
| R03 | R03-C single incident edge score | `tests/test_render_context_contract.py > test_node_score_with_single_incident_edge_matches_that_edge` | ✅ COMPLIANT |
| R03 | R03-D score never undefined | `tests/test_render_context_contract.py > test_node_score_never_undefined` | ✅ COMPLIANT |
| R03 | R03-E full float precision preserved | `tests/test_render_context_contract.py > test_node_score_full_float_precision` | ✅ COMPLIANT |
| R04 | R04-A latest evidence timestamp wins | `tests/test_render_context_contract.py > test_node_updated_at_is_max_incident_evidence_timestamp` | ✅ COMPLIANT |
| R04 | R04-B fallback to meta.generated_at | `tests/test_render_context_contract.py > test_isolated_node_updated_at_falls_back_to_meta_generated_at` | ✅ COMPLIANT |
| R04 | R04-C locked timestamp format | `tests/test_render_context_contract.py > test_updated_at_format_matches_locked_pattern` | ✅ COMPLIANT |
| R05 | R05-A isolated neighbor_count is 0 | `tests/test_render_context_contract.py > test_neighbor_count_isolated_is_zero` | ✅ COMPLIANT |
| R05 | R05-B neighbor_count matches adjacency | `tests/test_render_context_contract.py > test_neighbor_count_matches_adjacency` | ✅ COMPLIANT |
| R05 | R05-C neighbor_count is int | `tests/test_render_context_contract.py > test_every_node_has_neighbor_count` | ✅ COMPLIANT |
| R06 | R06-A edge.score preserved | `tests/test_viewer.py > TestSlice5ScoreThresholdFilter.test_render_context_emits_edge_score` | ✅ COMPLIANT |
| R06 | R06-B existing graph JSON parses without shape change | `tests/test_viewer.py`, `tests/test_graph_contract.py`, full strict suite | ✅ COMPLIANT |
| R06 | R06-C `test_graph_contract.py` stays green | `tests/test_graph_contract.py`, full strict suite | ✅ COMPLIANT |
| R07 | R07-A goldens match for all 7 supertypes | `tests/test_render_context_golden.py > test_golden_fixture_*` | ✅ COMPLIANT |
| R07 | R07-B goldens include locked new fields | `tests/test_render_context_golden.py > test_golden_fixture_*` | ✅ COMPLIANT |
| R08 | R08-A TabModel six fields + locked `openedAt` regex | `tests/test_render_context_golden.py > test_tab_model_schema_fields_documented`, `test_tab_model_opened_at_regex_is_locked_to_utc_seconds` | ✅ COMPLIANT |
| R08 | R08-B history array bounded to 50 strings | `tests/test_render_context_contract.py > test_history_payload_is_bounded_and_trims_overflow` | ✅ COMPLIANT |
| R08 | R08-C malformed localStorage recovery | `tests/test_render_context_contract.py > test_tabs_payload_malformed_json_recovers_to_default_and_logs`, `test_tabs_payload_wrong_type_recovers_to_default_and_logs`, `test_tabs_payload_valid_array_parses_without_reset` | ✅ COMPLIANT |

**Compliance summary**: 26/26 scenarios compliant

---

### Correctness (Static — Structural Evidence)
| Requirement | Status | Notes |
|------------|--------|-------|
| R01 | ✅ Implemented | `brain_ds/ui/render_context.py` emits root `contract_version` and `tests/test_contract_version_sync.py` locks Python↔TS parity |
| R02 | ✅ Implemented | `WorkspaceContext` is threaded through `cli.py` and `viewer.py`, and `meta.workspace` is derived in `render_context.py` |
| R03 | ✅ Implemented | Node `score` is render-derived from incident edges, including dedicated single-edge coverage for R03-C |
| R04 | ✅ Implemented | Node `updated_at` is derived from incident evidence with locked-format regression coverage |
| R05 | ✅ Implemented | Node `neighbor_count` is derived from adjacency size |
| R06 | ✅ Implemented | Existing edge-score and graph-roundtrip contracts remain green without weakening prior assertions |
| R07 | ✅ Implemented | 7 graph fixtures and 7 golden render-context fixtures exist and pass |
| R08 | ✅ Implemented | `brain_ds/ui/workspace_storage_contract.py` defines `TabModel`, storage keys, bounded history parsing, malformed recovery, and the locked `openedAt` regex constant |
| P01 | ✅ Preserved | Existing edge-score regression still passes |
| P02 | ✅ Preserved | Existing graph roundtrip contract still passes |
| P03 | ✅ Preserved | Existing viewer suite remains green |

---

### Coherence (Design)
| Decision | Followed? | Notes |
|----------|-----------|-------|
| ADR-CV-001 root `contract_version` | ✅ Yes | Implemented in `brain_ds/ui/render_context.py` |
| ADR-CV-002 optional `WorkspaceContext` fallback | ✅ Yes | Existing callers still work through `workspace=None` fallback |
| ADR-CV-003 node score is render-derived | ✅ Yes | `Node` dataclass stayed unchanged |
| ADR-CV-004 Python/TS sync via regex test | ✅ Yes | `tests/test_contract_version_sync.py` enforces literal parity |
| CLI/viewer workspace threading | ✅ Yes | `cli.py` resolves workspace and `viewer.py` forwards it |
| R08 contract-only scope | ✅ Yes | No runtime TS tab-strip wiring was introduced; verification stays at contract/helper level |

---

### Issues Found

**CRITICAL** (must fix before archive):
- None.

**WARNING** (should fix):
- None.

**SUGGESTION** (nice to have):
- None.

---

### Verdict
PASS

Clean pass: the prior final warning is CLOSED. `TabModel.openedAt` now has a dedicated source-backed regression test for the exact locked UTC-second regex, R08-A/B/C remain covered, R01–R07 remain compliant, preserved P01–P03 stay green, and archive is not blocked.
