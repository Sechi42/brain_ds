# Delta for ui-graph-viewer

## ADDED Requirements

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

## MODIFIED Requirements

### Requirement GV-3: Detail Panel in Inspector Accordion (Section 2/5 Visual Style)

`renderSelectionPanel` (line ~687) and `renderDetailPanel` MUST render content into the inspector accordion's open `<details>` body using Section 2/5 visual style. Empty state MUST use restrained token-true `.empty-state` with `var(--text-muted)` (not old `#viewer-empty-state` block with full instructional message and legacy classes). Selected-node detail card MUST use compact card surfaces with `--bg-panel`, `--border-subtle`, and `--accent-mora-muted` highlights. Internal DOM construction of card_sections, W6/W7 relationships, and evidence rendering MUST NOT change structurally — only outer visual wrappers and tokens change.

(Previously: Accordion wrapping is outer-shell only — detail content appeared in inspector accordion body without explicit Section 2/5 visual-style requirements. Empty state was not specified.)

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

### Requirement GV-4: Layout Control Redistribution (New-Shell Visuals)

Hierarchical toggle and Physics toggle MUST reside in L-panel Layout module rendered as new-style `.toggle-card` elements with `--bg-panel` surface, `--bg-panel-hover` hover, `aria-pressed` state, and `--accent-mora` active indicator. Zoom-fit and Theme-toggle MUST reside in toolbar overflow zone rendered as toolbar icon buttons. All four controls MUST retain existing click handler logic (`network.setOptions`, `network.fit`, theme switching) unchanged. Old raw `<button>` / `<div>` layout blocks with pre-migration styling MUST NOT render.

(Previously: Hierarchical toggle and Physics toggle in L-panel Layout module; Zoom-fit and Theme-toggle in toolbar overflow. Visual style and old-block deprecation were not specified.)

#### Scenario GV-4-A: hierarchical and physics in L-panel as toggle cards

- GIVEN the Layout rail icon is active
- WHEN the Layout panel module renders
- THEN `#toggle-hierarchical` and `#toggle-physics` render inside `.toggle-card` elements with `aria-pressed`
- AND `.toggle-card` uses `--bg-panel` background with `--accent-mora` active indicator
- AND no old raw layout control block with pre-migration styling exists
- AND clicking them calls the same `network.setOptions` calls as pre-migration

#### Scenario GV-4-B: zoom-fit and theme in toolbar overflow

- GIVEN toolbar overflow is rendered
- THEN `#zoom-fit` calls `network.fit({ animation: true })` on click
- AND `#theme-toggle` toggles `data-theme` attribute and persists to localStorage key `brain_ds.theme`

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
| `test_hierarchical_physics_in_l_panel_as_toggle_cards` | GV-4 | GV-4-A |
| `test_zoom_fit_theme_in_toolbar_overflow` | GV-4 | GV-4-B |
| `test_canvas_mount_network_element_in_center_column` | GV-5 | GV-5-A |
| `test_renderer_source_files_zero_diff` | GV-5 | GV-5-B |
| `test_hover_popover_context_menu_functional` | GV-5 | GV-5-C |

## Test Name Changes from Previous Revision

| Old Name | New Name | Reason |
|----------|----------|--------|
| `test_hierarchical_physics_in_l_panel` | `test_hierarchical_physics_in_l_panel_as_toggle_cards` | Visual-style assertion added (old raw blocks deprecated, `.toggle-card` required) |
| *(none)* | `test_empty_state_uses_restrained_token_styling` | New scenario GV-3-D added for restrained empty state |
