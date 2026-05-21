# Proposal: Workspace Shell Layout Migration

## Intent

Replace the 3-column flat grid in `graph_viewer.html` with the 5-column workspace shell from the shipped design references (`ui-sections-redesign`). This is Phase A#2 — the first production-code change in the roadmap — consuming contract v1.0.0 without evolving it.

**Problem**: the live viewer has a flat `minmax(260px,320px) 1fr minmax(280px,360px)` grid with a monolithic left sidebar and no tab strip, rails, or inspector shell. Every downstream feature (multi-vault, tab persistence) needs the shell structure.

## Scope

### In Scope
- **Grid swap**: 3-column flat grid → 5-column `.workspace-shell` (`48px / 220-300px / 1fr / 280-360px / 48px`)
- **Center column**: tab strip (36px, 1 static tab) + toolbar (44px, view-label + overflow with zoom-fit/theme-toggle)
- **Left rail + panel routing**: 5 icon rail (`role="tablist"`) + status chip; existing search/filters/hierarchy/layout modules routed via `mount()`/`unmount()`
- **Right rail + inspector shell**: settings gear icon; existing detail panel content wrapped in 4 accordion `<details>` sections (Properties/Metadata/Related/AI-actions per ADR-005)
- **JS DOM binding migration**: ~20+ direct `#id` references relocated to new DOM positions or data-attribute selectors
- **[C-5] Layout control redistribution**: hierarchical+physics → L-panel Layout module; zoom-fit+theme → toolbar overflow
- **Responsive breakpoint**: ≤1100px — rails persist at 48px, panels become overlay drawers
- **Test updates**: `test_viewer.py` assertions updated for new HTML structure; new shell-structure tests added

### Out of Scope
- Tab persistence (Phase A#3 SQLite)
- Multi-tab real population (static 1-tab rendering only)
- File-tree real data (mock contract only — matches design ref)
- AI Actions wiring (placeholder accordion with disabled stubs)
- `renderer.ts` internals (viewport, marquee, popover, context menu untouched)
- `.topbar` org-meta removal — information redistributed to toolbar view-label and status chip (ADR-002)
- CSS token de-duplication (`--theme-*` vs `--bg-*`) — deferred to follow-up
- Contract evolution (v1.0.0 consumed as-is)

## Capabilities

### Modified Capabilities
- `render-context`: no spec-level change — template rendering path modified but contract output unchanged

### New Capabilities
None. This is a structural migration consuming existing contracts. No new data shapes, APIs, or spec-level behaviors.

## Approach

**Progressive rewrite of `graph_viewer.html`** in 6 steps matching the exploration recommendation, delivered as a single PR (estimated 300-500 changed lines) or 3-PR chain if >400:

1. **CSS grid swap only** — 5-column grid with empty rails, all content in place
2. **Center column** — tab strip + toolbar from `section-4-center-canvas.html`, zoom-fit/theme to overflow
3. **Left rail + routing** — 5-icon `role="tablist"`, panel router calls existing `.mount()`/`.unmount()`
4. **Right rail + inspector** — `<details>` accordion wrapper around existing detail panel content
5. **Responsive breakpoint** — overlay drawer pattern from `_shared.css` §2.5 (ADR-012)
6. **Test updates** — repair `test_viewer.py` assertions, add shell-structure tests

**Key decisions for the 5 exploration-deferred items**:
1. Tab strip: static HTML + inline JS (no new module; design ref pattern sufficient for v1)
2. Panel routing: reuse existing `window.brainDsUI.*` modules' `.mount()` — shell router in template inline script
3. Layout controls: confirm ADR-003 lock from design — hierarchical+physics in L-panel, zoom-fit+theme in toolbar
4. Token drift: defer de-duplication; non-blocking acceptance criterion — all CSS uses `var(--bg-*)` tokens, no new hardcoded hex
5. Detail panel: accordion wraps existing content as outer `<details>` — no internal refactoring of `renderDetailPanel`/`renderSelectionPanel`

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `brain_ds/ui/templates/graph_viewer.html` | **Modified** | Primary target — grid, shell structure, inline CSS, inline JS bindings |
| `brain_ds/ui/template_renderer.py` | Unchanged | Token injection stays same |
| `brain_ds/ui/src/main.ts` | Unchanged | Module registry unchanged |
| `brain_ds/ui/src/panels/*.ts` | Unchanged | Module internals untouched; mount targets change in template |
| `brain_ds/ui/src/interactions/*.ts` | Unchanged | Score filter, popover, context menu internals preserved |
| `brain_ds/ui/design/sections/_shared.css` | **Referenced** | CSS contract source — patterns copied into template |
| `tests/test_viewer.py` | **Modified** | HTML structure assertions updated; new shell tests added |
| `tests/test_ui_section*_reference.py` | Unchanged | Static design ref tests should pass |
| `tests/test_render_context_contract.py` | Unchanged | Data contract unchanged |
| `tests/test_contract_version_sync.py` | Unchanged | Version sync unchanged |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| 20+ JS DOM ID bindings break on element relocation | High | Audit all `getElementById` calls in inline script; migrate to `[data-layout-control]` attributes or relocate bindings alongside moved DOM |
| `test_viewer.py` HTML assertions fail (1094 lines) | High | Review assertions before spec phase; categorize as structural vs data/logic; update structural only |
| CSS token drift (`--theme-*` vs `--bg-*`) | Medium | Deferred — acceptance criterion enforces `--bg-*` token discipline; no new hardcoded hex |
| `renderSelectionPanel` integration with inspector accordion | Medium | Accordion wraps content as sibling structure; detail panel's `.mount()` target changes to accordion content slot; no internal refactoring |
| Responsive breakpoint interaction with hover popover (`z-index: 50`) | Low | Popover constrained to `canvas-area` bounds per shipped `popover.ts`; mobile overlay drawers use `z-index: 1000` as specified in design |
| Single PR exceeds 400-line budget | Medium | Fallback: 3-PR chain per exploration §Delivery Strategy (grid+center / left+routing / right+responsive+tests) |

## Rollback Plan

1. `git revert` the single migration commit (or the PR chain in reverse order)
2. The 3-column grid CSS, `.topbar` HTML, and inline JS bindings are preserved in the commit history
3. No database migration, no API change — pure template/CSS/JS rollback
4. Smoke check: `uv run pytest tests/test_viewer.py` must pass at reverted state

## Dependencies

- `backend-ui-contract` (Phase A#1, archived) — RENDER_CONTEXT v1.0.0 consumed
- `ui-sections-redesign` (archived design) — `_shared.css`, section-1/2/4 HTML as CSS contract source
- `center-node-interactions` (archived) — Section 5 popover/context-menu behavior preserved

## Success Criteria

- [ ] 5-column `.workspace-shell` renders at ≥1100px with correct grid track widths
- [ ] Left rail: 5 icons with `role="tablist"`, `aria-selected` switching, keyboard navigation (ArrowUp/Down)
- [ ] Right rail: gear icon only (magic-wand hidden per OQ-4 lock)
- [ ] Tab strip: 1 static tab rendered at 36px, new-tab button present
- [ ] Toolbar: 44px, view-label displays org/node/edge counts, overflow menu contains zoom-fit + theme toggle
- [ ] Layout controls: hierarchical+physics functional in L-panel Layout module; zoom-fit+theme functional in toolbar overflow
- [ ] Existing panel modules (search, filterPanel, tree, scoreFilter, detailPanel) mount and function correctly
- [ ] Detail panel content appears inside inspector accordion (4 sections per ADR-005)
- [ ] Hover popover and context menu (renderer-owned) remain functional
- [ ] Responsive: ≤1100px — rails persist at 48px, panels as overlay drawers
- [ ] All CSS uses `var(--bg-*)` tokens; zero new hardcoded hex values
- [ ] `test_viewer.py` updated; full test suite passes (602+)
- [ ] Design ref tests (`test_ui_section*_reference.py`) pass unchanged
- [ ] No regression in renderer.ts, vis-network, or contract version sync
