## Exploration: workspace-shell-layout-migration

### Current State

**3-column flat grid** in `brain_ds/ui/templates/graph_viewer.html` (line 73):
```
grid-template-columns: minmax(260px,320px) 1fr minmax(280px,360px)
```

The three columns are:
| Column | Element | Content |
|--------|---------|---------|
| Left | `<aside class="controls">` | Search, type filters, legend, hierarchy tree, layout buttons (hierarchical, physics, zoom-fit, theme) |
| Center | `<div id="center-split">` | Canvas control row (show-more, hide-markdown), `#network` mount point, `#markdown-reader` |
| Right | `<aside id="detail-panel">` | Node detail body with cards, evidence, relationships; multi-select tiered panel |

The `.topbar` header (48px) sits above the grid with org name, node/edge count, timestamp. No tab strip exists. The detail panel has mobile breakpoint overlay at ≤1100px.

**JS wiring**: All panel modules mount via `window.brainDsUI.*` (detailPanel, search, filterPanel, tree, scoreFilter, contextMenu, popover). Inline JS in `graph_viewer.html` directly references DOM elements by ID for layout controls (`#toggle-hierarchical`, `#toggle-physics`, `#zoom-fit`, `#theme-toggle`, `#node-search`, `#type-filters`, `#legend`, `#tree-panel`, `#score-threshold-slider`, etc.).

**CSS token situation**: Two parallel systems coexist:
1. Inline `:root {}` in `graph_viewer.html` (lines 21-63) — defines `--bg-*`, `--accent-mora`, `--border-*`, `--text-*`, `--radius-*`, `--vis-*`, `--wcc-*` tokens
2. `theme.py` → `theme_tokens_css()` → `__BRAIN_DS_THEME_TOKENS__` — produces `--theme-*` prefixed tokens (injected at line 17 before the inline `:root {}`)

The design reference files (`_tokens.css`, `_shared.css`, `section-*.html`) use the `--bg-*` etc tokens, NOT `--theme-*`. The `_tokens.css` is a manual copy of `graph_viewer.html`'s `:root{}` block.

### Target State

**5-column workspace shell** per `_shared.css` (line 14-25):
```
grid-template-columns: 48px | minmax(220px,300px) | minmax(0,1fr) | minmax(280px,360px) | 48px
     L-rail         L-panel              center          R-panel         R-rail
```

The center column is a nested flex container:
- `.tab-strip` — 36px (tablist semantics exemption ADR-009)
- `.top-toolbar` — 44px (LOCKED per spec-amendment-dr5 / ADR-001)
- `.canvas-area` — flex 1 with `#network` mount point

Design reference HTML files exist in `brain_ds/ui/design/sections/`:
- `section-1-left-shell.html` — left rail (48px) + left content panel (220-300px) with file-tree module, 5 routeable panels (Files/Search/Filters/Hierarchy/Layout), status chip
- `section-2-right-shell.html` — inspector panel (280-360px) with properties/metadata/related/ai-actions accordions + right rail (48px) with settings icon
- `section-3-button-catalog.html` — master icon catalog with all states (default/hover/active/focus/disabled)
- `section-4-center-canvas.html` — tab strip (36px) + toolbar (44px) + canvas (flex 1), toolbar divided into 4 zones (nav/view/overflow/system-chrome)
- `section-5-node-interactions.html` — static design reference for node visual states (out of scope for this change)

Panel routing uses `mount(root, deps)` / `unmount()` lifecycle. Default left module is `file-tree`, right module is `settings`.

### Affected Files and Contract Points

| File | Role | Impact |
|------|------|--------|
| `brain_ds/ui/templates/graph_viewer.html` | Production template | **Primary target**. Swap 3-col grid → 5-col shell. Migrate all content into the new structure. |
| `brain_ds/ui/template_renderer.py` | Template engine | Minor: no structural change needed; token injection stays same. |
| `brain_ds/ui/src/main.ts` | JS bundle entry | May need to register new panel modules (file-tree, settings panel) if they don't exist. |
| `brain_ds/ui/src/main.css` | CSS entry | Currently imports vis-network CSS. May add shell CSS import. |
| `brain_ds/ui/src/panels/tree.ts` | Tree panel | Currently mounts to `#tree-panel`. Needs routing via shell lifecycle. |
| `brain_ds/ui/src/panels/search.ts` | Search panel | Currently mounts to `.search-group`. Needs routing. |
| `brain_ds/ui/src/panels/filter-panel.ts` | Filter panel | Currently mounts to `#type-filters`. Needs routing to L-panel "Filters" module. |
| `brain_ds/ui/src/panels/detail-panel.ts` | Detail panel | Currently mounts to `#detail-panel`. Stays in R-panel area but under inspector shell. |
| `brain_ds/ui/src/interactions/score-filter.ts` | Score filter | Currently mounts to `#score-threshold-slider`. Affected if slider moves. |
| `brain_ds/ui/theme.py` | Token source | `theme_tokens_css()` outputs `--theme-*` tokens. Token drift with `:root{}` exists. |
| `brain_ds/ui/design/sections/_tokens.css` | Design ref token copy | Must be kept in sync. |
| `brain_ds/ui/design/sections/_shared.css` | Design ref shared CSS | Defines `.workspace-shell`, `.center-column`, `.rail-icon`, `.status-chip`, etc. **This is the CSS contract to implement**. |
| `brain_ds/ui/design/sections/section-1-left-shell.html` | Design ref | Left rail + panel routing + file-tree contract |
| `brain_ds/ui/design/sections/section-2-right-shell.html` | Design ref | Inspector panel + right rail contract |
| `brain_ds/ui/design/sections/section-3-button-catalog.html` | Design ref | Icon catalog contract (states, ARIA, shortcuts) |
| `brain_ds/ui/design/sections/section-4-center-canvas.html` | Design ref | Tab strip + toolbar + canvas contract |
| `brain_ds/ui/workspace_storage_contract.py` | Tab persistence | R08 TabModel contract (from backend-ui-contract). Used by tab strip. |
| `brain_ds/ui/src/contract_version.ts` | Version sync | Already exists from backend-ui-contract. |
| `tests/test_ui_section1_left_shell_reference.py` | Test | Validates design ref HTML — should pass unchanged. |
| `tests/test_ui_section2_right_shell_reference.py` | Test | Validates design ref HTML — should pass unchanged. |
| `tests/test_viewer.py` | Test | 1094 lines. Validates render output. PINS HTML STRUCTURE — likely to break. |
| `tests/test_render_context_contract.py` | Test | Validates data contract — should pass unchanged. |
| `tests/test_contract_version_sync.py` | Test | Version sync — should pass unchanged. |

### Gap Analysis: Current 3-column → Target 5-column

| Concern | Current (3-col) | Target (5-col) | Gap | Severity |
|---------|----------------|----------------|-----|----------|
| **Grid** | Flat 3-col: `260-320px / 1fr / 280-360px` | 5-col: `48px / 220-300px / 1fr / 280-360px / 48px` | Rails missing; left panel shrinks from 260-320 to 220-300 | **Structural** |
| **Left panel content** | Single `.controls` panel with search, filters, legend, tree, layout buttons | Left rail (icons for file-tree/search/filters/hierarchy/layout) + routed L-panel | Current is monolithic; target needs rail + routing + module lifecycle | **Major** |
| **Right panel content** | Detail panel with node details, evidence, relationships, multi-select | Inspector panel with accordions (properties/metadata/related/ai-actions) + right rail (settings icon) | Detail content must be embedded inside inspector; rail icon toggles panels | **Major** |
| **Tab strip** | None. Simple `.topbar` header with org name. | 36px tab strip with TabModel, close buttons, new-tab button | Entirely new component | **Moderate** |
| **Top toolbar** | `.topbar` at 48px with org meta + theme toggle | 44px toolbar with 4 zones: nav, view, overflow, system-chrome | Different height (48→44px), different content layout | **Moderate** |
| **Layout controls** | In left panel: hierarchical, physics, zoom-fit, theme toggle | C-5 recommendation: zoom-fit + theme → toolbar overflow; hierarchical + physics → L-panel Layout module | Controls redistributed across zones | **Moderate** |
| **CSS tokens** | Two parallel systems (`:root{}` inline + `--theme-*` from theme.py)  | Design ref uses `--bg-*` etc from `:root{}` | Token drift risk. Both systems co-exist. | **Low-Medium** |
| **JS DOM bindings** | Inline JS references IDs directly (`#toggle-hierarchical`, `#type-filters`, `#tree-panel`, etc.) | IDs move to new DOM locations | All direct references break. Must update template JS or use data attributes. | **Major** |
| **Test assertions** | `test_viewer.py` likely pins HTML structure | New HTML structure | Tests that check specific HTML fragments will break | **High** |
| **Responsive breakpoint** | 1100px breakpoint collapses 3-col to single-file stack | Target: rails stay 48px, panels collapse to overlay drawers | Different responsive contract | **Moderate** |
| **Module wiring** | Modules mount to specific DOM element IDs | Modules mount via shell routing (`mount`/`unmount` lifecycle) | All `.mount()` calls in template must switch to routed lifecycle | **Major** |
| **Detail panel behavior** | Has `is-empty`, `is-collapsed`, `is-mobile-open` states, focus trap, backdrop | Detail content embedded in inspector accordion. Multi-select panel still needed. | States need to work within new shell structure | **Moderate** |
| **Panel widths** | Left minmax 260-320px, Right minmax 280-360px | Left minmax 220-300px (narrower), Right minmax 280-360px (same) | Left panel minimum shrinks by 40px | **Low** |

### CSS Token Drift Detail

`theme.py`'s `theme_tokens_css()` generates `--theme-*` variables. `graph_viewer.html`'s inline `:root{}` generates `--bg-*`, `--accent-mora`, etc. The design refs use the latter. The template currently has both.

**This is a risk for the shell migration**: if the new shell CSS (`_shared.css` patterns) uses `--bg-*` tokens, and those tokens somehow drift from `--theme-*` equivalents, visual inconsistency results. The fix (extracting tokens into a shared build artifact) is out of scope for this change per the roadmap — **recommend adding a non-blocking acceptance criterion**: all CSS in the migrated template must reference `var(--bg-*)` tokens only, matching the design ref contract, and no new hardcoded hex values.

### Existing Relevant Tests

| Test file | What it tests | Impact |
|-----------|--------------|--------|
| `tests/test_ui_section1_left_shell_reference.py` | Design ref HTML: left rail semantics, file-tree contract, accordion, status chip, token mapping | **Should pass unchanged** (tests static HTML, not template) |
| `tests/test_ui_section2_right_shell_reference.py` | Design ref HTML: right rail semantics, accordion sections, token-only usage | **Should pass unchanged** (tests static HTML) |
| `tests/test_viewer.py` | Full render pipeline: validation, render_interactive_html output, contract validation | **WILL BREAK** if it asserts specific HTML structure. Likely uses string `in` checks that match old layout. |
| `tests/test_render_context_contract.py` | RENDER_CONTEXT data shape | **Should pass unchanged** (data not affected by layout) |
| `tests/test_contract_version_sync.py` | TS/Python version sync | **Should pass unchanged** |

Likely `test_viewer.py` test names that would break:
- Any test checking `"layout"` grid-template CSS
- Any test checking element IDs that move
- Any test checking org-meta/topbar content location

### Risks

1. **CSS systemic token drift**: Two parallel token systems (`--theme-*` vs `--bg-*`). If migration introduces `--theme-*` tokens from `theme.py` output, it drifts from design ref contract. The inline `:root{}` block in the template is the actual source of truth for the design reference tokens.

2. **JS wiring breakage**: Approximately 20+ direct DOM ID references in the inline `<script>` block of `graph_viewer.html`. Every one that refers to elements that move or get restructured needs to be updated.

3. **Responsive breakpoint rework**: The current mobile breakpoint (1100px) is tightly coupled to the 3-column structure. The target responsive behavior (rails persistent, panels as overlay drawers) is a different contract that must be implemented.

4. **Multi-select detail panel**: The `renderSelectionPanel` function (lines 687-851) directly manipulates `#detail-panel`, `#detail-title`, `#detail-meta`, `#detail-body`. In the new shell, this content lives inside the inspector panel's accordion structure.

5. **Test baseline disruption**: `test_viewer.py` (1094 lines) will likely fail on HTML structure assertions. Need to review which tests pin layout structure vs. which test data/logic.

6. **Design ref vs. production drift**: The section HTML files are static, `file://`-friendly references. The production template is Jinja2 with injected tokens. Any CSS class or structure decision must be implemented in the template, not copied from the ref HTML directly.

### Non-Goals (explicitly out of scope)

- SQLite persistence (Phase A #3)
- Desktop shell (Phase B)
- MCP server (Phase C)
- Contract evolution (contract 1.0.0 consumed as-is)
- New CSS token families (use only existing `--bg-*`, `--accent-mora`, `--border-*`, `--text-*`, `--radius-*`, `--vis-*` tokens)
- renderer.ts internals (viewport, marquee, popover, context menu, etc. remain untouched)
- Light theme token population in `_tokens.css` (the `:root{}` block already has placeholders)

### Recommended Approach

**Progressive rewrites within the single template file**, keeping all existing JS bindings working through each step:

**Step 1 — CSS grid swap only**: Replace the 3-column grid with the 5-column grid. Add rail columns as empty containers. Keep all existing panel content in the L-panel and R-panel slots. No functional change. This validates the grid layout works.

**Step 2 — Center column (tab strip + toolbar)**: Extract the `.topbar` into the new tab-strip + top-toolbar structure per `section-4-center-canvas.html`. Migrate zoom-fit and theme-toggle to the toolbar overflow zone. Keep nav buttons as static (disabled forward).

**Step 3 — Left rail + panel routing**: Create left rail icons as `role="tablist"`. Implement panel routing (`mount`/`unmount` lifecycle) for search, filters, hierarchy, layout panels. Default to open file-tree equivalent (the existing tree panel). Status chip at bottom of left rail.

**Step 4 — Right rail + inspector shell**: Create right rail with settings icon. Wrap existing detail panel content inside the inspector accordion structure (properties/metadata/related/ai-actions). Keep multi-select rendering working.

**Step 5 — Responsive breakpoint**: Update the ≤1100px breakpoint to match the target contract (rails persistent at 48px, panels as overlay drawers).

**Step 6 — Test updates**: Update `test_viewer.py` assertions to match new HTML structure. Design ref tests should pass unchanged.

### Key Decisions Pending for Proposal Phase

1. **Tab strip implementation**: Should it be static HTML with JS wiring (like design ref) or a new `window.brainDsUI.tabStrip` module? Design ref uses direct DOM manipulation.

2. **Panel routing**: Should the L-panel routing use existing `window.brainDsUI` modules or new dedicated modules? The current modules (search, filterPanel, tree) already have `.mount()` signatures.

3. **Layout control placement**: The C-5 recommendation is not locked — confirm hierarchical/physics stay in L-panel Layout module vs. toolbar overflow.

4. **Token de-duplication**: Should we invest in de-duplicating `--theme-*` vs `--bg-*` tokens as part of this change, or leave it for a follow-up? The roadmap says "no contract evolution" — suggest deferring.

5. **Detail panel in inspector shell**: Should the existing detail panel module be refactored to render inside the inspector accordion, or should the accordion wrap it?

### Testing Implications

- `test_viewer.py` tests that assert on HTML structure **will need updating**. The exact scope depends on which assertions exist — review before spec phase.
- Design ref tests (`test_ui_section*`) should pass unchanged since they test static reference HTML files.
- New tests needed for:
  - Shell grid structure: `test_shell_5_column_grid_structure` — validates grid-template-columns
  - Tab strip rendering: `test_tab_strip_renders` — validates TabModel contract
  - Left rail semantics: `test_left_rail_tablist_semantics` — validates role, aria-selected, keyboard navigation
  - Right rail semantics: `test_right_rail_settings_icon` — validates gear icon presence
  - Panel routing: `test_l_panel_module_lifecycle` — validates mount/unmount
  - Responsive breakpoint: `test_mobile_breakpoint_rails_persist` — validates rails stay 48px on small screens
  - Existing JS bindings: `test_layout_controls_still_work` — validates hierarchical/physics/zoom-fit/theme buttons remain functional

### Delivery Strategy Recommendation

**Single PR candidate** (not chained), because:
- All changes touch one file (`graph_viewer.html`) plus CSS/JS assets
- The design refs already provide the exact target
- Estimated changes: 300-500 lines (swap grid, add shell structure, relocate panel content, update responsive rules, move JS bindings to data-attribute selectors)

**If >400 lines**, split into:
1. PR 1: Grid swap + center column (Steps 1-2) ~200 lines
2. PR 2: Left rail + panel routing (Step 3) ~150 lines
3. PR 3: Right rail + inspector + responsive + tests (Steps 4-6) ~200 lines

### Result Contract

| Field | Value |
|-------|-------|
| **status** | `ready` |
| **executive_summary** | The 3-column flat grid in `graph_viewer.html` must become a 5-column workspace shell matching the shipped design references. 7 gaps identified: grid structure, left panel routing, right panel inspector, missing tab strip, toolbar migration, JS DOM binding relocations, and responsive breakpoint rework. All JS panel modules already exist in `window.brainDsUI` — the migration wires them into the shell lifecycle. CSS token drift between theme.py (`--theme-*`) and inline `:root{}` (`--bg-*`) is a known risk but out of scope for this change. Recommended approach: 6-step progressive rewrite of `graph_viewer.html` as a single PR (or 3 if >400 lines). |
| **artifacts** | `openspec/changes/workspace-shell-layout-migration/exploration.md` (this file); Engram observation topic_key `sdd/workspace-shell-layout-migration/explore` |
| **next_recommended** | Proposal phase — confirm the 5 pending decisions (tab strip module, panel routing, layout control placement, token de-duplication scope, detail panel integration approach) before spec writing. |
| **risks** | CSS token drift (two parallel systems), 20+ JS DOM ID bindings that break, responsive breakpoint rewrite, test_viewer.py assertion failures, multi-select panel integration with inspector shell |
| **skill_resolution** | Load `cognitive-doc-design` for proposal articulation; `work-unit-commits` for commit structure; `mermaid-diagrams` for any architecture diagrams in design phase |
