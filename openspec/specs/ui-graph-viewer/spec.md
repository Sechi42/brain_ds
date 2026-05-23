# Spec: ui-graph-viewer — Graph Viewer Integration

**Date**: 2026-05-20
**Change**: workspace-shell-layout-migration
**Roadmap**: backend-migration-to-new-ui — Phase A · #2
**Predecessor**: backend-ui-contract (Phase A · #1)
**Artifact store**: hybrid (file + engram topic_key `sdd/workspace-shell-layout-migration/spec`)

---

## Overview

This spec defines the graph viewer integration requirements for the workspace shell migration. It covers DOM binding continuity, panel module mount routing, detail panel integration with the inspector accordion, layout control redistribution, and renderer preservation.

---

## Domain: ui-graph-viewer

---

### Requirement GV-1: DOM Binding Continuity

All ~20 existing `document.getElementById()` calls in the inline `<script>` MUST continue to resolve valid DOM elements after grid migration. Elements relocated to new DOM positions MUST retain their `id` attributes or be referenced via `[data-layout-control]` selectors.

#### Scenario GV-1-A: all getElementById calls resolve

- GIVEN any valid `RENDER_CONTEXT` after grid migration
- WHEN the inline script executes `initApp()`
- THEN zero `getElementById` calls return null
- AND no `TypeError: .addEventListener of null` errors occur

#### Scenario GV-1-B: identifier contract preserved

- GIVEN the migrated template
- THEN the following IDs exist in DOM: `network`, `detail-panel`, `detail-body`, `detail-title`, `detail-meta`, `detail-close`, `detail-collapse`, `detail-panel-backdrop`, `theme-toggle`, `toggle-hierarchical`, `toggle-physics`, `zoom-fit`, `node-search`, `show-all`, `hide-all`, `type-filters`, `legend`, `tree-panel`, `tree-filter-chip`, `score-threshold-slider`, `score-badge`, `viewer-loading`, `viewer-empty-state`, `empty-reset-filters`, `viewer-live-region`, `export-json`, `edit-toggle`

---

### Requirement GV-2: Panel Module Mount Routing

Left-rail icon click MUST call `window.brainDsUI.search.mount()` / `.unmount()`, `window.brainDsUI.filterPanel.mount()` / `.unmount()`, `window.brainDsUI.tree.mount()` / `.unmount()`, `window.brainDsUI.scoreFilter.mount()` / `.unmount()` via shell router. Module source files (`panels/*.ts`) MUST remain unchanged.

#### Scenario GV-2-A: search module mounts on icon click

- GIVEN search rail icon is clicked
- WHEN the shell router dispatches
- THEN `window.brainDsUI.search.mount(panelRoot, deps)` is called with a DOM container inside `.left-content-panel`

#### Scenario GV-2-B: only one panel mounted at a time

- GIVEN search panel is mounted
- WHEN filters rail icon is clicked
- THEN search panel is unmounted before filter panel mounts

#### Scenario GV-2-C: panel module source files unchanged

- GIVEN the filesystem at `brain_ds/ui/src/panels/`
- THEN all `*.ts` files have zero diff from pre-migration state except mount target selectors
- AND `main.ts` module registry has zero diff

---

### Requirement GV-3: Detail Panel in Inspector Accordion (Section 2/5 Visual Style)

`renderSelectionPanel` (line ~687) and `renderDetailPanel` MUST render content into the inspector accordion's open `<details>` body using Section 2/5 visual style. Empty state MUST use restrained token-true `.empty-state` with `var(--text-muted)` (not old `#viewer-empty-state` block with full instructional message and legacy classes). Selected-node detail card MUST use compact card surfaces with `--bg-panel`, `--border-subtle`, and `--accent-mora-muted` highlights. Internal DOM construction of card_sections, W6/W7 relationships, and evidence rendering MUST NOT change structurally — only outer visual wrappers and tokens change.

#### Scenario GV-3-A: selection panel renders into inspector body

- GIVEN a node with `card_sections` is selected
- WHEN `renderSelectionPanel(panelData)` is called
- THEN rendered HTML appears inside `.inspector-body` of `[data-accordion-section="properties"]`
- AND `#detail-title` and `#detail-meta` show correct node label and type
- AND card surfaces use `--bg-panel` with `--border-subtle` separators

#### Scenario GV-3-B: accordion wrapper is structural only

- GIVEN a multi-select or single-node detail render
- THEN the inner DOM of `.detail-card`, `.detail-actions`, `.detail-header` matches pre-migration structure
- AND `renderEvidence`, `renderRelationships` output appears inside `[data-accordion-section="related"]` body
- AND outer wrappers use Section 2 `.inspector-accordion` / `.inspector-body` classes

#### Scenario GV-3-C: detail panel collapse/close work

- GIVEN detail panel is visible inside inspector
- WHEN `#detail-collapse` or `#detail-close` is clicked
- THEN panel collapses/hides with same behavior as pre-migration
- AND `detail-panel-backdrop` click behavior is preserved
- AND collapse/close controls are new-shell `.rail-icon`-style buttons in the inspector header

#### Scenario GV-3-D: empty state uses restrained token styling

- GIVEN no node is selected in the viewer
- THEN right panel shows `.empty-state` element with `color: var(--text-muted)` and restrained layout
- AND old `#viewer-empty-state` block with full instructional message and legacy classes is not present as visible UI
- AND `#viewer-empty-state` ID may be preserved as hidden/anchor for JS compatibility

---

### Requirement GV-4: Layout Control Redistribution (Segmented Control)

Hierarchical/Physics MUST render as `.segmented-control[role="radiogroup"][aria-label="View mode"]` > `.segment-btn[role="radio"]` with `aria-checked`. `.toggle-card` class, `aria-pressed` on these controls, and `◉` glyph MUST NOT exist. Active segment: `--accent-mora-muted` bg + `--text-bright` text. Inactive: transparent bg + `--text-muted`. Track: `--bg-active` bg + `--border-subtle` border + `--radius-md`. JS MUST enforce mutual exclusion via `aria-checked` on both buttons. Zoom-fit/Theme-toggle unchanged. Same `network.setOptions` calls preserved.
(Previously: `.toggle-card` elements with `aria-pressed` toggle and `◉` glyph indicator.)

#### Scenario GV-4-A: segmented control mutual exclusion

- GIVEN Layout panel visible
- THEN `#toggle-hierarchical` and `#toggle-physics` are `.segment-btn` children of `[role="radiogroup"]`
- AND each has `role="radio"` with mutually exclusive `aria-checked`
- AND click updates both `aria-checked` values and calls same `network.setOptions` logic

#### Scenario GV-4-B: zoom-fit and theme unchanged

- GIVEN toolbar overflow rendered
- THEN `#zoom-fit` calls `network.fit({animation:true})`; `#theme-toggle` persists theme to localStorage

---

### Requirement GV-5: Renderer and Behavior Preservation

`renderer.ts` internals (viewport pan/zoom, marquee multi-select, ego-network dimming, hover popover, context menu, score filter) MUST remain functional. `vis-network` canvas mount at `#network` MUST work identically to pre-migration.

#### Scenario GV-5-A: canvas mount unchanged

- GIVEN the migrated template
- THEN `#network` element is a descendant of `.center-column > .canvas-area`
- AND `new vis.Network(document.getElementById("network"), ...)` succeeds with no layout error

#### Scenario GV-5-B: renderer modules untouched

- GIVEN `brain_ds/ui/src/renderer.ts` and `brain_ds/ui/src/interactions/*.ts`
- THEN zero lines changed from pre-migration state

#### Scenario GV-5-C: hover popover and context menu functional

- GIVEN any node in the canvas
- WHEN the user hovers or right-clicks the node
- THEN popover tether and context menu appear identically to pre-migration
- AND popover `z-index: 50` does not conflict with drawer overlay `z-index: 1000`

---

### Requirement GV-14: Pill Filter Action Buttons

Show/Hide MUST render as `.pill-group` > `.pill-btn` / `.pill-btn--primary`. No `.toggle-chip` class or `aria-pressed`. `#show-all`: `.pill-btn--primary` (`--accent-mora-muted` bg, `--accent-mora` color/border). `#hide-all`: `.pill-btn` (`--bg-active` bg, `--text-muted` color, `--border-subtle` border). Min-height 44px, `--radius-md`. Clicks MUST call unchanged `onShowAll()`/`onHideAll()`.

#### Scenario GV-14-A: pill buttons trigger unchanged behavior

- GIVEN Filters panel visible
- WHEN `#show-all` or `#hide-all` clicked
- THEN `onShowAll()` / `onHideAll()` called (same as pre-D.2)
- AND neither button has `aria-pressed`

---

### Requirement GV-15: Control Accessibility

Segmented control: `role="radiogroup"` + `aria-label="View mode"`, buttons `role="radio"` + `aria-checked`. Arrow keys MUST navigate per WAI-ARIA radiogroup (Left/Up=prev, Right/Down=next). All interactive controls MUST show `:focus-visible` ring: 2px `var(--accent-mora)` outline, 2px offset. Active segment text MUST meet WCAG AA contrast against `--bg-canvas-deep`.

#### Scenario GV-15-A: ARIA semantics and keyboard

- GIVEN DOM rendered → `.segmented-control` has `role="radiogroup"` + `aria-label`
- AND `.segment-btn` children have `role="radio"` + `aria-checked` (exactly one true at load)
- WHEN ArrowRight on checked segment → focus and `aria-checked` move to next
- AND focused control shows 2px `var(--accent-mora)` outline via `:focus-visible`

---

### Requirement GV-16: Implementation Constraints

| Constraint | Rule |
|---|---|
| Tokens | Only D.1 `tokens.css`: `--bg-active`, `--border-subtle`, `--accent-mora`, `--accent-mora-muted`, `--text-muted`, `--text-bright`, `--radius-md`, `--duration-fast`, `--ease-standard`. Zero new custom properties. |
| Layout | 5-column grid, `.panel-card` sections, toolbar `data-toolbar-zone` slots unchanged. |
| Behavior | `network.setOptions`, `onShowAll`, `onHideAll`, renderer.ts, popover, context menu all unchanged. |
| Stack | No React, no Tailwind, no new TS component files. |
| IDs | `toggle-hierarchical`, `toggle-physics`, `show-all`, `hide-all` preserve exact `id` values. |
| Removals | `.toggle-card` and `.toggle-chip` classes removed; `aria-pressed` removed from these 4 controls. |

#### Scenario GV-16-A: all constraints met

- GIVEN D.2 rendered viewer
- THEN CSS uses only D.1 token references (zero new `:root` variables outside `tokens.css`)
- AND shell layout matches D.1 structure
- AND all 4 IDs exist with identical pre-D.2 values
- AND `.toggle-card`, `.toggle-chip` classes and `aria-pressed` on these controls are absent

---

### Requirement GV-17: Visual Checkpoint

`d2-viewer-sample.html` MUST be rendered from real `graph_viewer.html` template after D.2 changes, demonstrating: segmented control with token styling, pill primary/outline distinction, active/inactive states, and visible focus rings. Control CSS rules MUST use `var(--*)` tokens — no hardcoded hex values.

#### Scenario GV-17-A: checkpoint from real template

- GIVEN D.2 changes applied to `graph_viewer.html`
- WHEN `d2-viewer-sample.html` generated via template renderer
- THEN output contains `.segmented-control`, `.segment-btn`, `.pill-btn`, `.pill-btn--primary` elements
- AND control color rules use `var(--*)` only

---

## Preserved Behavior

| Component | Status |
|-----------|--------|
| `RENDER_CONTEXT` contract v1.0.0 | Consumed as-is |
| `build_render_context` output | Unchanged |
| `template_renderer.py` token injection | Unchanged |
| `renderer.ts` all slices (1–8) | Untouched |
| `vis-network` canvas constructor | Mount target only — same `#network` ID |
| `popover.ts`, `context-menu.ts`, `score-filter.ts` | Source unchanged |
| `main.ts` module registry | Zero diff |
| 602+ existing tests | Must stay green |

---

## Test Name Registry

| Test | Requirement | Scenario |
|------|-------------|----------|
| `test_all_getelementbyid_resolve_after_migration` | GV-1 | GV-1-A |
| `test_all_required_ids_present_in_migrated_dom` | GV-1 | GV-1-B |
| `test_search_module_mounts_on_rail_click` | GV-2 | GV-2-A |
| `test_only_one_panel_mounted_at_a_time` | GV-2 | GV-2-B |
| `test_panel_module_files_have_no_diff_except_mount_targets` | GV-2 | GV-2-C |
| `test_selection_panel_renders_into_inspector_accordion` | GV-3 | GV-3-A |
| `test_accordion_wrapper_preserves_inner_detail_structure` | GV-3 | GV-3-B |
| `test_detail_collapse_close_preserved` | GV-3 | GV-3-C |
| `test_empty_state_uses_restrained_token_styling` | GV-3 | GV-3-D |
| `test_d2_segmented_control_aria_structure` | GV-4 | GV-4-A |
| `test_runtime_segmented_control_mutual_exclusion` | GV-4 | GV-4-A |
| `test_zoom_fit_theme_in_toolbar_overflow` | GV-4 | GV-4-B |
| `test_canvas_mount_network_element_in_center_column` | GV-5 | GV-5-A |
| `test_renderer_source_files_zero_diff` | GV-5 | GV-5-B |
| `test_hover_popover_context_menu_functional` | GV-5 | GV-5-C |
| `test_d2_pill_buttons_structure` | GV-14 | GV-14-A |
| `test_d2_no_hidden_proxy_buttons` | GV-14 | GV-14-A |
| `test_d2_pill_buttons_have_min_height_css` | GV-14 | GV-14-A |
| `test_runtime_segmented_control_keyboard_navigation` | GV-15 | GV-15-A |
| `test_d2_segmented_buttons_have_ids_and_tabindex` | GV-16 | GV-16-A |
| `test_d2_segmented_and_pill_css_uses_only_tokens` | GV-16 | GV-16-A |
