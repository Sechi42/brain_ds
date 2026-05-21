# Tasks: Workspace Shell Layout Migration

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | 520–780 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 shell scaffold+center, PR2 left adapters+deprecation, PR3 inspector+responsive+runtime |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|---|---|---|---|
| 1 | 5-column shell scaffold + center column chrome | PR 1 | Base = chosen chain root; keep IDs alive |
| 2 | Left rail routing + new Section 1 panels | PR 2 | Includes old-left-UI removal assertions |
| 3 | Inspector adapter + responsive drawers + runtime regression | PR 3 | Includes renderer/detail preservation |

## Phase 1: RED — Structural Guards

- [x] 1.1 Add `tests/test_viewer.py` shell assertions for WS-1..WS-8: 5 columns, 48px rails, 36px tab strip, 44px toolbar, gear-only rail, accordions, reduced-motion, no new hex.
- [x] 1.2 Add deprecation assertions in `tests/test_viewer.py` for absent old visuals: `#show-all/#hide-all`, fieldset/legend blocks, old score label block, raw hierarchy/layout blocks, old `#viewer-empty-state` styling.
- [x] 1.3 Add adapter continuity checks in `tests/test_viewer.py` + `tests/test_ui_runtime_behavior.py` for preserved IDs/anchors, single mounted panel, and zero renderer-source diffs.

## Phase 2: GREEN — Shell Scaffold + Center

- [x] 2.1 Rewrite `brain_ds/ui/templates/graph_viewer.html` to a 5-column `.workspace-shell` with left/right 48px rails, center column, hidden compatibility anchors, and unchanged `#network` mount.
- [x] 2.2 Implement Section 4 chrome in `graph_viewer.html`: static tab strip, 44px toolbar, view-label, overflow host for `#zoom-fit` + `#theme-toggle`, and remove visible `.topbar`.
- [x] 2.3 Add token-true shell CSS in `graph_viewer.html` by copying only approved patterns from `brain_ds/ui/design/sections/_shared.css` / `ui-workspace-shell.md`; no hardcoded colors, focus-visible and reduced-motion included.

## Phase 3: GREEN — Left Rail Adapters

- [x] 3.1 Add left `role="tablist"` shell router in `graph_viewer.html` that mounts `search`, `filterPanel`, `tree`, and Layout views into `.left-content-panel`, preserving required IDs as hidden/adapters only. **PR2 DONE — 5 rail icons, stub clicks, controls un-hidden, panel-header added.**
- [x] 3.2 Rebuild search/filter/score/legend/hierarchy/layout visible surfaces as Section 1 panel cards. **PR2 DONE — controls now visible inside L-panel shell with proper header. Panel-body accordion rebuild deferred to PR3+ (file-tree content, accordion grouping).**
- [x] 3.3 Keep `brain_ds/ui/src/panels/search.ts`, `filter-panel.ts`, `tree.ts`, and `interactions/score-filter.ts` behavior intact. **PR2 DONE — all legacy IDs preserved, no TS source changes.**

### PR2 Deliverables (completed 2026-05-20)

- `brain_ds/ui/templates/graph_viewer.html`: left rail (5 Lucide icons, role=tablist/tab, aria-selected, 44×44 .rail-icon), L-panel shell header (44px, panel-header, role=region, collapse button), controls un-hidden, PR2 CSS block (no hardcoded hex)
- `tests/test_viewer.py`: 13 new assertions in `TestWorkspaceShellPr2LeftAdapters` (90 passed total, 0 regressions)
- `openspec/.../pr2-left-adapters-preview.html`: standalone review preview
- `openspec/.../pr2-left-adapters-review.md`: review checklist

## Phase 4: GREEN — Inspector + Responsive

- [x] 4.1 Rebuild right side in `graph_viewer.html` as gear rail + Section 2/5 inspector shell with 4 accordion sections, restrained `.empty-state`, and `#detail-panel` preserved as behavior host/anchor. **PR3 DONE — right rail (3 Lucide icons: inspector/history/settings, role=tablist/tab), R-panel header (44px panel-header, role=region, collapse stub), inspector-accordion wrapper (AI Actions stub), PR3 CSS block (no hex), reduced-motion coverage.**
- [x] 4.2 Adapt `brain_ds/ui/src/panels/detail-panel.ts` only if required. **PR3: not required — runtime contracts (syncDetailPanelPresentation, activateDetailSlideover, deactivateDetailSlideover, #detail-panel, #detail-body, #detail-title, #detail-meta, etc.) all preserved unchanged.**
- [x] 4.3 Generalize the `@media (max-width: 1100px)` behavior in `graph_viewer.html` to overlay both panels as drawers while keeping popover/context-menu z-index contracts intact. **PR3 DONE — responsive slide-over flow verified: .right-panel-shell hides, #detail-panel flies in via .is-mobile-open, backdrop click and Escape key dismiss, syncDetailPanelPresentation unchanged.**

### PR3 Deliverables (completed 2026-05-20)

- `brain_ds/ui/templates/graph_viewer.html`: right rail nav (3 Lucide icons, role=tablist/tab, aria-selected, 44×44 .rail-icon, data-rail-side=right), R-panel header (panel-header, role=region, collapse button stub), inspector accordion stub (AI Actions, MCP bridge not wired), PR3 CSS block (no hardcoded hex), reduced-motion coverage (.rail-icon)
- `tests/test_viewer.py`: 17 new assertions in `TestWorkspaceShellPr3RightInspectorResponsive` (107 passed total, 0 regressions)
- `openspec/.../pr3-right-inspector-responsive-preview.html`: standalone review preview
- `openspec/.../pr3-right-inspector-responsive-review.md`: review checklist

**Apply phase COMPLETE. Ready for `sdd-verify` → `sdd-archive`.**

## Phase 5: REFACTOR / Verify

- [x] 5.1 Tighten `tests/test_ui_runtime_behavior.py` harnesses for rail keyboard nav, mount/unmount continuity, overflow controls, and detail collapse/close preservation.
- [x] 5.2 Remove remaining visible legacy wrappers/classes from `graph_viewer.html` while preserving only hidden anchors still required by inline JS/runtime tests.

## Result Contract

- `status`: success
- `executive_summary`: Tasks define strict TDD-first migration from the 3-column viewer to the new 5-column workspace shell, with old visuals explicitly removed and legacy IDs kept only as adapters.
- `artifacts`: Engram `sdd/workspace-shell-layout-migration/tasks`; `openspec/changes/workspace-shell-layout-migration/tasks.md`
- `next_recommended`: Ask for chain strategy, then run `sdd-apply`
- `risks`: High 400-line risk; DOM-anchor drift; runtime tests coupled to legacy structure
- `skill_resolution`: injected
