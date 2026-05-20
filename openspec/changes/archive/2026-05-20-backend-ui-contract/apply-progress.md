## Implementation Progress

**Change**: backend-ui-contract
**Mode**: Strict TDD
**Delivery**: chained PR slice (`feature-branch-chain`)
**Current work unit**: verification warning remediation — R08-A openedAt locked regex assertion

### Completed Tasks (cumulative)
- [x] 1.1 Add `WorkspaceContext` dataclass + `CONTRACT_VERSION` constant in `brain_ds/ui/render_context.py`
- [x] 1.2 Add TS mirror constant in `brain_ds/ui/src/contract_version.ts`
- [x] 1.3 Add CLI `--root` flag parsing scaffold in `brain_ds/ui/cli.py`
- [x] 2.1–2.6 RED contract tests for R01–R05 and cross-language sync
- [x] 3.1–3.7 GREEN implementation and workspace wiring
- [x] 4.1–4.4 Golden fixtures + golden tests
- [x] 5.1–5.2 Strict suite pass + acceptance checks
- [x] Remediation: R08-B bounded history evidence, R08-C malformed tabs recovery evidence, R08-A non-tautological schema evidence, R03-C dedicated single-edge assertion
- [x] Warning remediation: dedicated R08-A regression assertion for exact locked `TabModel.openedAt` regex via production `LOCKED_UTC_SECONDS_PATTERN`

### Files Changed (this remediation)
| File | Action | What Was Done |
|------|--------|---------------|
| `tests/test_render_context_golden.py` | Modified | Added dedicated R08-A regression test asserting exact locked `openedAt` regex using production `LOCKED_UTC_SECONDS_PATTERN` constant |

### TDD Cycle Evidence
| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| R08-A warning remediation | `tests/test_render_context_golden.py` | Unit | ✅ Baseline from prior apply (`31/31` targeted tests green) | ✅ Test written first (dedicated regression assertion) | ✅ `uv run python -m unittest tests.test_render_context_contract tests.test_render_context_golden` → `31 passed` | ➖ Structural constant lock assertion (single exact output) | ➖ None needed |

### Test Summary
- R08-related tests: `uv run python -m unittest tests.test_render_context_contract tests.test_render_context_golden` → **31 passed**
- Required targeted suite: `uv run python -m unittest tests.test_render_context_contract tests.test_render_context_golden` → **31 passed**
- Full strict command: `uv run python -m unittest discover -s tests` → **602 passed, 4 skipped**

### Deviations from Design
- None — implementation remains within R08-A verification warning scope only.

### Issues Found
- None.

### Remaining Tasks
- [x] All tasks in `openspec/changes/backend-ui-contract/tasks.md`
- [ ] Pending: rerun `sdd-verify` to confirm warning closure and clean PASS verdict

### Workload / PR Boundary
- Mode: chained PR slice (`feature-branch-chain`)
- Current work unit: warning-only verification hardening
- Boundary: starts at verify warning (missing dedicated `openedAt` locked regex assertion), ends at dedicated source-backed regression + full strict suite green
- Estimated review budget impact: tiny (single test file, one focused assertion)

### Status
22/22 tasks complete. Warning remediation complete; ready for `sdd-verify` rerun.
