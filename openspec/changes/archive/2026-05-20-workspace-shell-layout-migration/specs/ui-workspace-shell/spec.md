# Delta for ui-workspace-shell

## ADDED Requirements

### Requirement WS-1: 5-Column Workspace Grid

The `.workspace-shell` grid MUST use `grid-template-columns: 48px minmax(220px,300px) minmax(0,1fr) minmax(280px,360px) 48px` matching `_shared.css`. Rails MUST remain 48px at all viewport widths.

#### Scenario WS-1-A: desktop grid renders all 5 columns

- GIVEN viewport ≥1101px
- WHEN `graph_viewer.html` loads
- THEN the document MUST contain `.workspace-shell` with 5 grid-column tracks
- AND L-rail width = 48px, R-rail width = 48px

#### Scenario WS-1-B: grid track IDs match CSS contract

- GIVEN any rendered view
- THEN grid track minima are: L-rail 48px, L-panel 220px, center 0px, R-panel 280px, R-rail 48px
- AND grid track maxima are: L-panel 300px, R-panel 360px

---

### Requirement WS-2: Tab Strip

Center column MUST contain a `.tab-strip` with `flex: 0 0 36px`, 1 static tab (`data-tab-active="true"`), and a new-tab button. TabModel schema (R08) consumed as-is — no contract evolution.

#### Scenario WS-2-A: one static tab renders

- GIVEN any valid `RENDER_CONTEXT`
- WHEN `graph_viewer.html` loads
- THEN exactly 1 `.tab-item` with `data-tab-active="true"` exists
- AND a new-tab button with `aria-label="New tab"` is present

#### Scenario WS-2-B: tab strip height locked at 36px

- GIVEN any viewport
- THEN tab-strip computed height = 36px (ADR-009 tablist exemption)

---

### Requirement WS-3: Toolbar

Center column MUST contain a `.top-toolbar` with `flex: 0 0 44px`, `data-toolbar-zone` elements (view, overflow, system-chrome), and view-label showing org/node/edge counts. Layout controls: zoom-fit + theme-toggle in overflow zone; hierarchical + physics in L-panel Layout module.

#### Scenario WS-3-A: toolbar displays view-label

- GIVEN `RENDER_CONTEXT.meta` with `org="Acme"`, `node_count=5`, `edge_count=3`
- WHEN template renders
- THEN `.top-toolbar` view-label innerText contains "Acme", "5 nodes", "3 edges"

#### Scenario WS-3-B: zoom-fit and theme-toggle in overflow

- GIVEN toolbar is rendered
- THEN `data-toolbar-zone="overflow"` contains `#zoom-fit` button
- AND contains `#theme-toggle` button

#### Scenario WS-3-C: system-chrome zone is empty

- GIVEN toolbar is rendered
- THEN `data-toolbar-zone="system-chrome"` is empty — reserved for native window controls (ADR-002)

---

### Requirement WS-4: Left Rail + Panel Routing

Left rail MUST be a `data-rail-side="left"` container with exactly 5 `.rail-icon` buttons (search, filters, tree, hierarchy, layout), `role="tablist"`, `aria-selected` on active, ArrowUp/Down keyboard nav. Click MUST call existing `window.brainDsUI.*.mount()` / `.unmount()`.

Panels mount into new-shell `.left-content-panel` containers using Section 1 visual language (compact cards, accordions, token-true surfaces). Old sidebar `<div>` wrappers (`.sidebar-left`, old search block, old filter block) MUST NOT be present as visible containers. Old module behavior is accessed via adapters; visible UI uses new components only.

#### Scenario WS-4-A: left rail icon catalog

- GIVEN template renders
- THEN exactly 5 `.rail-icon` buttons exist with `data-rail-icon` values: "search", "filters", "tree", "hierarchy", "layout"
- AND each has `aria-label` and `role="tab"`

#### Scenario WS-4-B: active icon carries aria-selected

- GIVEN the search icon is active (default)
- THEN `.rail-icon[data-rail-icon="search"][aria-selected="true"]` exists
- AND all other rail icons have `aria-selected="false"`

#### Scenario WS-4-C: keyboard navigation

- GIVEN left rail has focus
- WHEN ArrowDown key is pressed
- THEN the next rail icon becomes `aria-selected="true"`
- AND the previous icon becomes `aria-selected="false"`

#### Scenario WS-4-D: status chip anchored at bottom

- GIVEN template renders with `meta.org="YSGA"`
- THEN `[data-status-chip]` is the last child of `[data-rail-side="left"]`
- AND its textContent is ≤4 uppercase characters

#### Scenario WS-4-E: old sidebar wrappers not in visible DOM

- GIVEN template renders
- THEN no `.sidebar-left` container exists as visible UI
- AND old search block, old filter block, old legend block are not present as visible containers
- AND panel content renders inside new-shell `.panel-card` / `[data-accordion-section]` wrappers

---

### Requirement WS-5: Right Rail + Inspector

Right rail MUST be `data-rail-side="right"` with exactly 1 icon: gear (`data-rail-icon="gear"`). Inspector panel MUST adopt Section 2/5 visual language: accordion `<details>` sections with `--bg-panel` compact card surfaces, restrained empty state, token-true metadata/preview treatment. Old `#detail-panel` visual markup is replaced by new inspector shell; `#detail-panel` ID is preserved as a mount anchor only if needed by existing JS.

#### Scenario WS-5-A: right rail single icon

- GIVEN template renders
- THEN exactly 1 rendered `.rail-icon` with `data-rail-icon="gear"` exists
- AND no element with `data-rail-icon="magic-wand"` exists in DOM

#### Scenario WS-5-B: inspector accordion wrapping

- GIVEN template renders
- THEN 4 `<details>` elements exist with `data-accordion-section` values: "properties", "metadata", "related", "ai-actions"
- AND the Properties `<details>` is open by default (`data-accordion-open="true"`)

#### Scenario WS-5-C: detail content preserved inside accordion

- GIVEN a node selection triggers `renderDetailPanel`
- THEN the rendered detail content appears inside `.inspector-body` of the open accordion section
- AND `renderSelectionPanel`, `renderEvidence`, `renderRelationships` callers are unchanged

#### Scenario WS-5-D: inspector uses Section 2/5 visual style

- GIVEN a node is selected and detail renders
- THEN card_sections render with `--bg-panel` compact card surfaces and `--border-subtle` separators
- AND empty state (no selection) uses restrained `.empty-state` with token-true muted text, not old `#viewer-empty-state` block with full instructional message

---

### Requirement WS-6: Responsive Breakpoint

At ≤1100px, rails MUST persist at 48px; L-panel and R-panel MUST become overlay drawers (ADR-012) with `z-index: 1000`. Center column MUST remain visible.

#### Scenario WS-6-A: panel overlay at breakpoint

- GIVEN viewport width 1099px
- THEN `[data-rail-side="left"]` and `[data-rail-side="right"]` computed width = 48px
- AND L-panel has `position: fixed` with left offset matching design
- AND R-panel has `position: fixed` with right offset matching design

#### Scenario WS-6-B: rails persist at any width

- GIVEN viewport width 600px
- THEN both rails' computed width = 48px

---

### Requirement WS-7: Token and Accessibility Discipline

ALL new CSS MUST use `var(--bg-*)`, `var(--border-*)`, `var(--text-*)`, or `var(--accent-*)` tokens. Zero new hardcoded hex colors. Rail icons MUST have 44×44px touch targets. Focus-visible MUST use `--accent-mora` outline. `prefers-reduced-motion` MUST disable transitions.

#### Scenario WS-7-A: no new hardcoded hex colors

- GIVEN any new style block in graph_viewer.html
- THEN every color value uses a `var(--*)` custom property
- AND zero lines contain bare hex color literals (e.g., `#1e1e1e`) not already present in pre-migration template

#### Scenario WS-7-B: rail icon touch targets

- GIVEN any rendered rail icon
- THEN computed min-height ≥44px AND min-width ≥44px

#### Scenario WS-7-C: reduced motion contract

- GIVEN `prefers-reduced-motion: reduce` is active
- THEN all transition/animation durations in shell styles are 0ms or none

---

### Requirement WS-8: Structural Test Assertions

Python test suite in `tests/test_viewer.py` MUST include new assertions:
1. `.workspace-shell` grid template-columns = 5 tracks
2. L-rail and R-rail width = 48px
3. Tab strip height = 36px, toolbar height = 44px
4. 5 left rail icons present with role="tablist"
5. Right rail has exactly 1 gear icon
6. 4 inspector accordion sections present
7. Responsive breakpoint at 1100px present in CSS
8. Zero new hardcoded hex colors in added styles
9. Reduced-motion media query present in added styles
10. Existing test assertions (all 602+) remain green
11. Old visual labels/classes absent from visible DOM: `#show-all`, `#hide-all`, old `<fieldset>` groups, old `<legend>`, old score-threshold `<label>` block, old hierarchy/layout raw `<div>` blocks, old `#viewer-empty-state` block
12. New shell classes present: `.panel-card`, `[data-accordion-section]` wrappers on panel content, `.toggle-card` on layout controls, `.empty-state` with token-restrained styling
13. Legacy IDs preserved as hidden/anchor/adapters where JS requires them, but NOT rendered as visible old-style UI

#### Scenario WS-8-A: shell structure tests pass

- GIVEN migration is applied
- WHEN `uv run python -m unittest discover -s tests` runs
- THEN 602+ tests pass (no regression)
- AND new shell-structure assertions pass with no failures

#### Scenario WS-8-B: old visual classes absent

- GIVEN migrated template renders
- THEN no `#show-all` or `#hide-all` element is visible
- AND no `<fieldset>` with old filter/legend classes exists in visible DOM
- AND no `<label>` block for old score-threshold slider style remains visible

#### Scenario WS-8-C: new shell classes and attributes present

- GIVEN migrated template renders
- THEN L-panel content uses `[data-accordion-section]` wrappers
- AND layout controls use `.toggle-card` with `aria-pressed`
- AND right panel empty state uses `.empty-state` with `var(--text-muted)`

---

### Requirement WS-9: Old Sidebar Visual Deprecation

The following old sidebar visual sections MUST NOT render in their pre-migration visual form in the live viewer: old search input + results block, old Filters fieldset/checkbox groups, "Show all" / "Hide all" buttons, old category type groups (`<fieldset>` / `<legend>` style), old score-threshold slider with raw label+input block, old Legend list with raw `<ul>` styling, old Hierarchy raw block, old Layout controls raw block.

Existing module behavior (search query, filter toggling, score threshold filtering, legend display, hierarchy navigation, layout control) MAY be reused only behind new shell components/adapters. Visible UI MUST use new components exclusively.

IDs from these sections MAY be preserved as hidden/anchor/adapters if needed by existing JS. Visible markup MUST use new-shell classes and data attributes only.

#### Scenario WS-9-A: old fieldset/legend classes absent from visible DOM

- GIVEN migrated template renders
- THEN no `<fieldset>` with old filter/legend CSS classes remains in visible DOM
- AND no `#show-all` or `#hide-all` renders as a visible link/button element

#### Scenario WS-9-B: old search block visual replaced by panel-card

- GIVEN search panel is mounted
- THEN search input renders inside a new-shell `.panel-card` with `data-accordion-section` wrapper
- NOT the old `.search-block` / `.search-results` div layout with pre-migration styling

#### Scenario WS-9-C: old score-threshold label/input block absent

- GIVEN score threshold control is rendered
- THEN no old `<label>Score threshold</label> <input type="range">` block with raw inline styling exists
- AND score threshold control uses a new-shell component (slider chip or compact card) with token styling

---

### Requirement WS-10: Left Panel Section 1 Visual Rebuild

All left panel content modules (search, filters, file-tree, hierarchy, layout) MUST render using Section 1 visual patterns: compact cards with `--bg-panel` surfaces and `--border-subtle` borders; `data-accordion-section` wrappers for collapsible groups; token-true search bars (`--bg-main` input background, `--accent-mora` focus ring); token-true filter toggle chips and category cards (no old `<fieldset>` / `<legend>` blocks); token-true tree rows at 28px height with indent-per-depth; token-true layout toggle cards.

No old label/input block styling, no old list-style `<ul>` for legend, no old fieldset-group borders.

#### Scenario WS-10-A: filter panel uses new-shell toggle chips

- GIVEN filters panel mounted
- THEN type filters render as toggle chips with `--bg-panel-hover` hover and `--accent-mora-muted` active state
- AND no old checkbox+fieldset group with pre-migration fieldset/legend styling exists

#### Scenario WS-10-B: hierarchy tree uses Section 1 tree-row pattern

- GIVEN hierarchy panel mounted
- THEN tree nodes render as `.tree-row` elements with 28px height, indent-per-depth, and expand/collapse chevrons
- AND no old raw `<ul>` hierarchy block with pre-migration styling exists

---

### Requirement WS-11: Layout Controls as New-Shell Panel Toggles

Hierarchical toggle and Physics toggle MUST render inside L-panel Layout module as new-style `.toggle-card` elements with `--bg-panel` surface, `--bg-panel-hover` hover, `aria-pressed` state, and `--accent-mora` active indicator. Old raw `<button>` / `<div>` layout blocks with pre-migration styling MUST NOT render.

#### Scenario WS-11-A: layout toggles are new-style toggle cards

- GIVEN Layout panel is mounted
- THEN `#toggle-hierarchical` and `#toggle-physics` render inside `.toggle-card` elements with `aria-pressed` state
- AND `.toggle-card` uses `--bg-panel` background with `--accent-mora` active indicator
- AND no old raw layout control block with pre-migration styling exists

---

### Requirement WS-12: Right Panel Section 2/5 Visual Style

Right detail panel MUST adopt Section 2/5 visual language:
- Empty state (no node selected): restrained `.empty-state` with token-true muted text (`--text-muted`), NOT old `#viewer-empty-state` block with full instructional message and pre-migration styling
- Selected-node state: inspector accordion `<details>` with compact card surfaces (`--bg-panel`), metadata/preview treatment per Section 2 reference
- Card sections: `--bg-panel` surfaces, `--border-subtle` separators, `--accent-mora-muted` highlights
- Collapse/Close: integrated into inspector header using new-shell `.rail-icon`-style buttons

Internal DOM construction of card_sections, W6/W7 relationships, and evidence rendering MUST NOT change structurally — only visual wrappers and tokens change.

#### Scenario WS-12-A: empty state uses restrained token styling

- GIVEN no node is selected in the viewer
- THEN right panel shows `.empty-state` with `color: var(--text-muted)` and restrained layout
- AND old `#viewer-empty-state` block with full instructional message and legacy classes is not present as visible UI

#### Scenario WS-12-B: detail card uses Section 2/5 compact card surfaces

- GIVEN a node with card_sections is selected
- THEN card_sections render inside `.inspector-body` with `--bg-panel` compact card styling
- AND separators use `--border-subtle`
- AND active/highlighted sections use `--accent-mora-muted`
- AND collapse/close controls are new-shell `.rail-icon`-style buttons in the inspector header

---

## Non-Goals

- SQLite persistence, multi-vault data, tab real population
- `renderer.ts` internals (viewport, marquee, popover, context menu)
- Backend contract evolution (v1.0.0 consumed as-is)
- CSS token de-duplication (`--theme-*` vs `--bg-*`) — deferred
- AI Actions wiring (placeholder accordion stub only)

## Test Name Registry

| Test | Requirement | Scenario |
|------|-------------|----------|
| `test_workspace_shell_grid_has_5_columns` | WS-1 | WS-1-A, WS-1-B |
| `test_rail_widths_locked_at_48px` | WS-1 | WS-1-A, WS-6-B |
| `test_tab_strip_has_one_static_tab_and_new_button` | WS-2 | WS-2-A |
| `test_tab_strip_height_36px` | WS-2 | WS-2-B |
| `test_toolbar_view_label_shows_counts` | WS-3 | WS-3-A |
| `test_toolbar_overflow_has_zoom_fit_and_theme` | WS-3 | WS-3-B |
| `test_toolbar_system_chrome_zone_empty` | WS-3 | WS-3-C |
| `test_left_rail_has_5_icons_with_aria_labels` | WS-4 | WS-4-A |
| `test_left_rail_active_icon_aria_selected` | WS-4 | WS-4-B |
| `test_left_rail_keyboard_nav_arrow_keys` | WS-4 | WS-4-C |
| `test_status_chip_at_bottom_of_left_rail` | WS-4 | WS-4-D |
| `test_old_sidebar_wrappers_not_in_visible_dom` | WS-4 | WS-4-E |
| `test_right_rail_single_gear_icon_no_magic_wand` | WS-5 | WS-5-A |
| `test_inspector_4_accordion_sections` | WS-5 | WS-5-B |
| `test_inspector_uses_section2_5_visual_style` | WS-5 | WS-5-D |
| `test_responsive_breakpoint_1100px_overlay_panels` | WS-6 | WS-6-A |
| `test_rails_persist_at_48px_any_viewport` | WS-6 | WS-6-B |
| `test_no_new_hardcoded_hex_colors` | WS-7 | WS-7-A |
| `test_rail_icons_min_44px_touch_target` | WS-7 | WS-7-B |
| `test_reduced_motion_disables_shell_transitions` | WS-7 | WS-7-C |
| `test_old_visual_classes_absent_new_shell_present` | WS-8 | WS-8-B, WS-8-C |
| `test_old_fieldset_legend_classes_absent` | WS-9 | WS-9-A |
| `test_old_search_block_replaced_by_panel_card` | WS-9 | WS-9-B |
| `test_old_score_threshold_label_block_absent` | WS-9 | WS-9-C |
| `test_filter_panel_uses_new_shell_toggle_chips` | WS-10 | WS-10-A |
| `test_hierarchy_tree_uses_section1_tree_row_pattern` | WS-10 | WS-10-B |
| `test_layout_toggles_are_new_style_toggle_cards` | WS-11 | WS-11-A |
| `test_empty_state_uses_restrained_token_styling` | WS-12 | WS-12-A |
| `test_detail_card_uses_section2_5_compact_surfaces` | WS-12 | WS-12-B |
