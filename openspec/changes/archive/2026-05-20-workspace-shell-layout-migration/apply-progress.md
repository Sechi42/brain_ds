# Apply Progress — workspace-shell-layout-migration

**Mode**: Strict TDD  
**Delivery**: feature-branch-chain continuation

## Cumulative completed tasks

- [x] 1.1 Shell assertions baseline
- [x] 1.2 Deprecation assertions for old visible UI
- [x] 1.3 Adapter continuity checks (IDs/runtime hooks)
- [x] 2.1 5-column shell scaffold
- [x] 2.2 Center chrome
- [x] 2.3 Token-true shell CSS
- [x] 3.1 Left rail adapter shell
- [x] 3.2 Section-1 visible rebuild
- [x] 3.3 Module behavior continuity
- [x] 4.1 Inspector shell
- [x] 4.2 detail-panel contract preserved
- [x] 4.3 Responsive drawers
- [x] 5.1 Runtime harness tightening
- [x] 5.2 Legacy visible wrapper removal

## Remediation batch (warnings W1–W7)

### What changed
- Replaced old visible left controls with Section-1 style card surfaces (`.panel-card`, `data-accordion-section`, `.toggle-chip`, `.toggle-card`, `.tree-row`), while preserving required runtime IDs.
- Switched right rail to gear-only (`data-catalog-id="gear"`).
- Replaced old `#viewer-empty-state` surface with restrained `.empty-state` using new anchor `#viewer-empty`.
- Updated runtime harness IDs in `tests/test_ui_runtime_behavior.py` from `viewer-empty-state` to `viewer-empty`.
- Added remediation review checkpoint artifacts.

### TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 1.2 | `tests/test_viewer.py` | Unit | ✅ `uv run python -m unittest tests.test_viewer` (107/107) | ✅ Added `TestWorkspaceShellRemediationOldUiRemoval` first (5 failing) | ✅ Remediation class 6/6 passing | ✅ Covered absence + presence + 44px + gear-only + adapter IDs | ✅ Consolidated assertions to avoid trivial checks |
| 1.3 | `tests/test_viewer.py` | Unit | ✅ same baseline | ✅ Added adapter continuity assertions in remediation class | ✅ Passing in full viewer suite | ✅ IDs across left/center/right anchors asserted | ➖ None needed |
| 5.1 | `tests/test_ui_runtime_behavior.py` | Integration | ✅ Existing runtime test behavior known | ✅ Runtime harness updated to new empty-state anchor (`viewer-empty`) | ✅ `test_runtime_empty_state_filter_and_reset_flow` passing | ➖ Single targeted runtime flow | ✅ Minimal harness change only |
| 5.2 | `graph_viewer.html` + viewer tests | Unit+Integration | ✅ baseline + RED failures | ✅ Old visual blocks test failed before template edits | ✅ Viewer suite green (113/113) | ✅ Verified both removal and hidden-anchor preservation | ✅ Removed old visible wrappers, kept hidden anchors only |

## Tests run

1. `uv run python -m unittest tests.test_viewer.TestWorkspaceShellRemediationOldUiRemoval` → RED then GREEN (6/6)  
2. `uv run python -m unittest tests.test_viewer.TestWorkspaceShellPr3RightInspectorResponsive` → 17/17  
3. `uv run python -m unittest tests.test_viewer` → 113/113  
4. `uv run python -m unittest tests.test_ui_runtime_behavior.TestUiRuntimeBehavior.test_runtime_empty_state_filter_and_reset_flow` → 1/1  
5. `uv run python -m unittest discover -s tests` → 660 run, **8 failures** (7 pre-existing golden + 1 fixed runtime during batch; final known remaining: 7 pre-existing golden fixtures)

## Review checkpoint

- `openspec/changes/workspace-shell-layout-migration/review/remediation-old-ui-removal-preview.html`
- `openspec/changes/workspace-shell-layout-migration/review/remediation-old-ui-removal-review.md`

## Review artifact remediation (checkpoint retry)

- Replaced low-fidelity remediation preview with a polished single-page composition at PR1.5/PR2/PR3 quality level.
- Added complete 5-column shell, center chrome, left card system, right inspector accordions, gear-only right rail, and tasteful dark/light theme toggle demo.
- Removed inline style soup and standardized component classes for review readability (`.panel-card`, `.command-search`, `.filter-chip`, `.score-control`, `.visual-key`, `.tree-row`, `.toggle-card`, `.empty-state`, `.inspector-accordion`).
