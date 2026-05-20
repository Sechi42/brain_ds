# ui-workspace-shell — Design Reference

**Purpose**: This file is the verifiable design-spec artifact for the `ui-sections-redesign` SDD change.
It contains ASCII wireframes, component contracts, icon catalogs, token mappings, and the accessibility
contract for all 4 sections of the new Obsidian-like workspace shell.

**Amendment in effect**: spec-amendment-dr5 (#839) — top toolbar row is LOCKED at **44px**.
This supersedes any 36px implication from the original task brief.

**Out of scope for this change**:
- `renderer.ts` internals and all canvas slices (viewport pan/zoom, marquee, ego-network dimming,
  hover popover, context menu)
- Any production Python or TypeScript code
- Test file changes
- New CSS token families (only existing `--bg-*`, `--accent-mora`, `--border-*`, `--text-*`, `--radius-*` tokens are used)
- See "Node Interaction Visual Contracts" below for design-only mappings.

---

## Full Workspace Grid (X-1 Wireframe)

The workspace is one CSS Grid with 5 columns (left-to-right):

```
┌──┬────────────┬───────────────────────────────┬───────────┬──┐
│  │            │ [tab strip — 36px]             │           │  │
│  │            ├───────────────────────────────┤           │  │
│L │  L-panel   │ [top toolbar — 44px]           │  R-panel  │R │
│  │ 220–300px  │                               │  280–360px│  │
│  │            │ [canvas — flex 1]              │           │  │
│  │            │                               │           │  │
└──┴────────────┴───────────────────────────────┴───────────┴──┘
48px            ←────── minmax(0,1fr) ──────→              48px
```

**Grid column template**: `icon rail | panel | 1fr | panel | icon rail`

CSS declaration (`.workspace-shell`):
```css
grid-template-columns:
  var(--rail-w)          /* L-rail   — 48px        */
  minmax(220px, 300px)   /* L-panel  — collapsible */
  minmax(0, 1fr)         /* center   — flex        */
  minmax(280px, 360px)   /* R-panel  — collapsible */
  var(--rail-w);         /* R-rail   — 48px        */
```

Note: `--rail-w: 48px` is a local custom property scoped to `.workspace-shell`, NOT a global theme token.

**Responsive / mobile**: deferred to the design phase. Desktop layout (≥ 1100px) is the only contract here.
At ≤ 1100px, both panels collapse to overlay drawers; rails remain visible at 48px each.

---

## Section 4 — Center Canvas

### ASCII Wireframe (C-1)

```
┌──────────────────────────────────────────────────────────┐
│ ▼ Vista gráfica  •  │ alpha │ + │                        │ ← tab strip 36px
├──────────────────────────────────────────────────────────┤
│ ← →    Acme Co · 142 nodes · 318 edges · 2026-05-20   ⋯ │ ← toolbar 44px (LOCKED — DR-5)
├──────────────────────────────────────────────────────────┤
│                                                          │
│                                                          │
│                    [canvas area]                         │
│              (div#network — mount point)                 │
│                                                          │
│                                                          │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

The center column is a **nested flex container** (not additional grid rows):
- `.tab-strip` — `flex: 0 0 36px` (tablist semantics exemption, ADR-009)
- `.top-toolbar` — `flex: 0 0 44px` (LOCKED at 44px per spec-amendment-dr5 / ADR-001)
- `.canvas-area` — `flex: 1 1 auto; min-height: 0`

No bottom bar. The status chip is in the left rail, not a footer row.

### `TabModel` Interface (C-2)

```ts
interface TabModel {
  id: string;                                  // opaque tab identifier
  label: string;                               // display label in tab
  graphRef: { id: string; displayPath: string }; // graph reference
  isDirty: boolean;                            // adds • indicator before label
  isActive: boolean;                           // true for the active tab
}
```

Callbacks:
- `onTabSelect(tabId: string): void` — called when a tab is clicked
- `onTabClose(tabId: string): void` — called when tab close (×) is clicked
- `onNewTab(): void` — called when the + button is clicked

**Tab close affordance** (ADR-008, Q-NEW-5 resolved): the × close button is visible on the **active tab**
at all times, and on **any tab on hover**. Inactive tabs hide it by default via CSS
(`.tab:not([data-tab-active='true']) .tab-close { opacity: 0; } .tab:hover .tab-close { opacity: 1; }`).

### Top Toolbar Zones (C-3)

The toolbar is divided into 4 data zones via `data-toolbar-zone`:

| Zone | `data-toolbar-zone` | Content | Notes |
|------|---------------------|---------|-------|
| Navigation | `nav` | Back (arrow-left) + Forward (arrow-right) buttons | `aria-label` required; Forward disabled in demo |
| View label | `view` | Text label: org · node count · edge count · date | Reflects shipped `.topbar` info (ADR-002) |
| Overflow | `overflow` | ⋯ button (more-horizontal) | Opens dropdown with layout controls |
| System chrome | `system-chrome` | **Empty** — reserved for native window controls | MUST NOT be painted by CSS |

**Toolbar height**: **44px** (LOCKED per spec-amendment-dr5 / ADR-001).
Reasoning: WCAG 2.5.5 requires 44×44 minimum for primary CTAs (back, forward, overflow buttons).
A 36px toolbar cannot host 44px buttons without visual overflow.

**System-chrome region**: reserved for native desktop window controls (min/max/close). This region is
intentionally left empty — do NOT paint CSS backgrounds, icons, or buttons here.

### Canvas Region (C-4) — Out of Scope

The canvas mount point is `<div id="network" data-canvas-mount>`. No `<canvas>` element or renderer
instantiation appears in the reference HTML.

The following are **OUT OF SCOPE** for this design change:
- `renderer.ts` and all implementation slices (1a/1b pan+zoom, 3a marquee, 3b 2-hop, 4 hover popover,
  5 score filter, 6 context menu)
- Viewport pan/zoom, inertia
- Marquee multi-select
- Ego-network dimming
- Hover popover (350ms grace)
- Context menu
- W6 gap-slot dashed cards
- W7 RelType grouping (data-side)

These behaviors are preserved verbatim from the shipped `renderer.ts` and are NOT modified.

### Layout Control Migration (C-5) — RECOMMENDATION (not locked)

> **RECOMMENDATION** (not locked — final decision deferred to design phase / implementation):
>
> - **Zoom-fit** and **Theme-toggle** → migrate to top toolbar overflow menu (canvas-scoped, rare invocation)
> - **Hierarchical** and **Physics** → remain in L-rail Layout panel (graph-scoped exploration toggles)
>
> Rationale (ADR-003): Hierarchical/Physics are toggles users flip during graph exploration — burying
> them in overflow adds friction. Zoom-fit and theme are app-wide / canvas-wide single-purpose actions.
> Rejected alternative: move all 4 to toolbar (buries exploration toggles, increases overflow menu noise).

---

## Token Source Strategy (X-2)

**Strategy**: copy (not `@import`).

`_tokens.css` is a verbatim copy of the `:root{}` block from
`brain_ds/ui/templates/graph_viewer.html` (lines 21–63), plus an empty `[data-theme='light']` placeholder.

**Rationale** (ADR-010): `graph_viewer.html` is a Jinja2 template injected at runtime — static HTML
cannot `@import` it. Manual copy with a dated header comment is the interim strategy.

**Follow-up**: a future SDD change should extract tokens into a `tokens.css` build artifact consumed by
both the Jinja2 template and these design references. This eliminates drift risk.

**Required minimum tokens** (spec X-2 AC):
- `--bg-main` — main background
- `--bg-panel` — panel background
- `--accent-mora` — accent color (#a78bfa, 6.66:1 on #161616)
- `--text-normal` — body text
- `--border-subtle` — subtle border

---

## Prefers-Reduced-Motion (X-4)

All hover and transition animations must honor the `prefers-reduced-motion: reduce` user preference.

CSS pattern (placed in `_shared.css`):

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## WCAG AA Compliance (X-3)

### Contrast Ratios

| Token pair | Ratio | WCAG AA requirement | Pass? |
|------------|-------|---------------------|-------|
| `--accent-mora: #a78bfa` on `--bg-main: #161616` | **6.66:1** | ≥ 4.5:1 (normal text) / ≥ 3:1 (UI component) | **Pass** |
| `--text-normal: #dcddde` on `--bg-main: #161616` | **10.7:1** | ≥ 4.5:1 | **Pass** |
| `--text-muted: #848484` on `--bg-main: #161616` | **3.57:1** | ≥ 3:1 (UI component / large text) | **Pass** |
| `--text-bright: #f5f6f7` on `--bg-main: #161616` | **14.4:1** | ≥ 4.5:1 | **Pass** |

### Focus Ring

All interactive elements use `outline: 2px solid var(--accent-mora); outline-offset: 2px` on `:focus-visible`.
`--accent-mora: #a78bfa` achieves 6.66:1 contrast on `--bg-main: #161616` — exceeds WCAG AA (4.5:1).

### Touch Targets

- Rail icon buttons: **44×44 px** (`.rail-icon { width: 44px; height: 44px; }`) — spec X-3, B-4 compliant
- Toolbar buttons: **44×44 px** within the 44px toolbar row — compliant
- Tab strip row: **36px** — tablist semantics exemption (ADR-009). Tab buttons are grouped items in a
  horizontal tablist; WCAG 2.5.5 target-size applies to standalone pointer targets. Tabs in a horizontal
  tablist are categorized as "essential" UI components (compare VSCode, Chrome, Obsidian).
- File-tree rows: **28px visual height** — dense data tree exemption (ADR-004). Primary action (open graph)
  is also triggered via keyboard Enter, satisfying WCAG 2.1 alternative input path.

### ARIA Requirements per Element Type

| Element type | Required ARIA |
|---|---|
| Rail icon button (tab role) | `role="tab"`, `aria-selected="true/false"`, `aria-label`, `tabindex="0/-1"` |
| Toggle button (theme, physics, hierarchical) | `aria-pressed="true/false"`, `aria-label` |
| Accordion trigger (summary) | `aria-expanded` implicit via `<details open>` attribute |
| Tab item (in tab strip) | `data-tab-id`, `data-tab-active`, `role="tab"`, `aria-selected` |
| Icon-only button | `aria-label` (required), SVG has `aria-hidden="true"` |
| Status chip | `aria-label="Switch vault (current: XXXX)"`, `aria-haspopup="menu"` |

**Note**: `aria-selected` is used on rail icons because the rail is a
`role="tablist"` with `role="tab"` children. `aria-current` applies to navigation landmarks;
`aria-selected` is correct for tablist/tab semantics per WAI-ARIA 1.2 specification.

---

## Section 1 — Left Rail, Content Panel, Status Chip

### ASCII Wireframe (L-1)

```
┌──┬───────────────────────────────────┐
│Fi│ Files                         ⌃   │
│  │ ┌───────────────────────────────┐ │
│Se│ │ ▾ Acme Workspace              │ │
│  │ │   ▾ projects                  │ │
│Fl│ │     ▸ brain-ds                │ │
│  │ │     ▸ alpha                   │ │
│Hi│ │   ▸ archive                   │ │
│  │ │ ▸ Personal                    │ │
│Ly│ └───────────────────────────────┘ │
│  │                                   │
│  │                                   │
│  │                                   │
│YS│                                   │
└──┴───────────────────────────────────┘
 48px           220–300px (collapsible)
```

The left rail is a dedicated column and is marked with `data-rail-side="left"` in HTML.
Status chip placement is the last child inside the rail container (NOT a page footer).

### Left Rail Icon Catalog (L-2)

| id | label | aria-label | default-route | keyboard-shortcut |
|---|---|---|---|---|
| `file-tree` | Files | `Open file tree panel` | `file-tree` | `Mod+1` |
| `search` | Search | `Open search panel` | `search` | `Mod+2` |
| `filters` | Filters | `Open filters panel` | `filters` | `Mod+3` |
| `hierarchy` | Hierarchy | `Open hierarchy panel` | `hierarchy` | `Mod+4` |
| `layout` | Layout | `Open layout panel` | `layout` | `Mod+5` |

Optional (documented, not rendered in this reference HTML):
- `bookmarks` → bookmarks panel (TBD)
- `workspace` → workspace layout presets (TBD)

Active icon state is represented as `aria-selected="true"` on the active item.

### Left Panel Routing Contract (L-3)

The active left panel follows existing panel module lifecycle:
- `mount(root, deps)`
- `unmount()`

| icon-id | panel-module |
|---|---|
| `file-tree` | `file-tree` |
| `search` | `search` |
| `filters` | `filters` |
| `hierarchy` | `hierarchy` |
| `layout` | `layout` |

Default rendered module in `section-1-left-shell.html` is `file-tree`, with `data-panel-module="file-tree"`.
Inactive modules are absent from DOM in the static reference.

### File-Tree Component Contract (L-4)

```ts
interface TreeNode {
  id: string; // opaque ID (never filesystem path)
  displayPath: string;
  type: "project" | "graph";
  children?: TreeNode[];
}

interface FileTreeProps {
  data: TreeNode[];
  onProjectSelect(projectId: string): void;
  onGraphOpen(graphRef: { id: string; displayPath: string }): void;
}
```

Mock data rules in reference HTML:
- IDs are opaque (`prj_acme_01`, `grf_acme_01`, etc.), never paths.
- Includes at least 2 project nodes and 2 graph nodes.

### Accordion Contract (L-5)

File-tree groupings use accordion semantics via native `<details>`:

| Field | Contract |
|---|---|
| Section identifier | `data-accordion-section` |
| Open state | `data-accordion-open="true|false"` |
| Trigger ARIA | `aria-expanded="true|false"` on trigger button/summary semantics |
| Toggle behavior | Click trigger to open/close; keyboard Enter/Space supported |

### Status Chip Contract (L-6)

| Field | Contract |
|---|---|
| DOM placement | Last child inside `data-rail-side="left"` |
| Data source | `RENDER_CONTEXT.meta.org` or `projectContext` callback |
| Display format | max 4 uppercase chars |
| Attribute | `data-status-chip` |

Reference HTML mock uses `ACME` (4 chars).

### Token Mapping (L-7)

| Token | UI element |
|---|---|
| `--bg-panel` | content panel background |
| `--bg-panel-hover` | rail icon hover + tree row hover |
| `--bg-active` | active rail icon + selected tree row |
| `--border-subtle` | rail/panel separators |
| `--text-normal` | panel labels + tree text |
| `--accent-mora` | active icon indicator + focus ring |

Section 1 HTML and shared CSS must use `var(--*)` only for all color declarations.
Left panel width contract is `minmax(220px, 300px)`.

---

## Section 2 — Right Rail, Inspector Panel

### ASCII Wireframe (R-1)

```
┌──────────────────────────────┬──┐
│ [Company Name] Workspace  ⌃  │⚙ │
│ ──────────────────────────── │  │
│ ▾ Properties                 │  │
│ ▸ Metadata                   │  │
│ ▾ Related                    │  │
│   ▾ Evidence (inline)        │  │
│ ▸ AI Actions (placeholder)   │  │
└──────────────────────────────┴──┘
   280–360px (inspector)       48px
```

Right shell structure:
- Inspector panel width: `minmax(280px, 360px)`
- Right rail width: `48px`
- Rail element uses `data-rail-side="right"`

### Right Rail Icon Catalog (R-2)

| id | label | aria-label | route | state |
|---|---|---|---|---|
| `gear` | Settings | `Open settings panel` | `settings` | active by default |

Locked behavior:
- Exactly one rendered icon in PR-3: `data-rail-icon="gear"`
- `magic-wand` remains reserved and hidden until MCP bridge ships

### Settings Panel Contract (R-3)

Panel lifecycle follows existing module conventions:
- `mount(root, deps): void`
- `unmount(): void`

Default active module in `section-2-right-shell.html`:
- `data-panel-module="settings"`

Placeholder settings categories for design reference:
- Appearance
- Keybindings
- About

### Outer Accordion Contract (R-4, user-reviewed update)

Outer inspector accordions use native `<details>/<summary>` semantics.

| Section id | Default | Notes |
|---|---|---|
| `properties` | open | primary entity fields |
| `metadata` | collapsed | auxiliary identifiers/timestamps |
| `related` | open | related entities + inline evidence |
| `ai-actions` | collapsed | placeholder only |

Important boundary:
- **Evidence is inline inside `related`**, not a fifth outer accordion.
- Existing node-detail internals remain out of scope; this is shell-level organization only.

### AI Actions Placeholder (R-5)

Callback shape (contract only):

```ts
onAiAction(actionId: string, nodeId: string): void
```

Status:
- `MCP bridge — not wired`
- PR-3 includes disabled placeholder text only; no MCP integration or runtime behavior.

### Token Mapping (R-6)

| Token | Usage |
|---|---|
| `--bg-panel` | inspector + rail background |
| `--bg-panel-hover` | hover states on summaries/buttons |
| `--bg-active` | selected/active states |
| `--border-subtle` | panel/rail separators + accordion borders |
| `--text-normal` | body text |
| `--text-bright` | section headers |
| `--accent-mora` | active rail indicator + focus ring |

All Section 2 styles must use `var(--*)` token references only.

---

## Section 3 — Button / Icon Catalog

### Purpose

This section defines a single cross-cutting contract for every icon-only control used in:
- Left rail (Section 1)
- Right rail (Section 2)
- Tab strip and top toolbar (Section 4)

It exists so interaction, ARIA, shortcuts, and visual states stay consistent across the workspace shell.

### Master Icon-Button Catalog (B-1)

| id | glyph-source | label | aria-label | tooltip | keyboard-shortcut | default-state | active-state | disabled-state | focus-ring |
|---|---|---|---|---|---|---|---|---|---|
| `file-tree` | Lucide `folder-tree` | Files | `Open file tree panel` | `Files` | `Ctrl+1 / Cmd+1` | muted icon, transparent bg | `aria-selected="true"` + accent indicator | allowed when no projects loaded (demo) | `2px var(--accent-mora)` |
| `search` | Lucide `search` | Search | `Open search panel` | `Search` | `Ctrl+2 / Cmd+2` | muted icon, transparent bg | `aria-selected="true"` + accent indicator | not used by default | `2px var(--accent-mora)` |
| `filters` | Lucide `sliders-horizontal` | Filters | `Open filters panel` | `Filters` | `Ctrl+3 / Cmd+3` | muted icon, transparent bg | `aria-selected="true"` + accent indicator | not used by default | `2px var(--accent-mora)` |
| `hierarchy` | Lucide `network` | Hierarchy | `Open hierarchy panel` | `Hierarchy` | `Ctrl+4 / Cmd+4` | muted icon, transparent bg | `aria-selected="true"` + accent indicator | not used by default | `2px var(--accent-mora)` |
| `layout` | Lucide `layout-grid` | Layout | `Open layout panel` | `Layout` | `Ctrl+5 / Cmd+5` | muted icon, transparent bg | `aria-selected="true"` + accent indicator | not used by default | `2px var(--accent-mora)` |
| `gear` | Lucide `settings` | Settings | `Open settings panel` | `Settings` | `Ctrl+, / Cmd+,` | muted icon, transparent bg | `aria-selected="true"` + accent indicator | not used by default | `2px var(--accent-mora)` |
| `tab-new` | Lucide `plus` | New tab | `Open new tab` | `New tab` | `Ctrl+T / Cmd+T` | muted icon, transparent bg | n/a (instant action) | not used by default | `2px var(--accent-mora)` |
| `tab-close` | Lucide `x` | Close tab | `Close tab` | `Close tab` | `Ctrl+W / Cmd+W` | hidden on inactive tab | visible on active/hover | not used by default | `2px var(--accent-mora)` |
| `nav-back` | Lucide `arrow-left` | Back | `Back` | `Back` | `Alt+← / Option+←` | muted icon, transparent bg | pressed feedback only | disabled when no history | `2px var(--accent-mora)` |
| `nav-forward` | Lucide `arrow-right` | Forward | `Forward` | `Forward` | `Alt+→ / Option+→` | muted icon, transparent bg | pressed feedback only | disabled when no future history | `2px var(--accent-mora)` |
| `overflow` | Lucide `more-horizontal` | More actions | `Open more actions` | `More actions` | none | muted icon, transparent bg | active while menu is open | not used by default | `2px var(--accent-mora)` |
| `status-chip` | text chip (4-char) | Workspace code | `Switch workspace (current: ACME)` | `Switch workspace` | none | panel-hover surface | active while menu is open | not used by default | `2px var(--accent-mora)` |

Catalog identity contract:
- Every row `id` MUST appear in `section-3-button-catalog.html` as `data-catalog-id="..."`.
- Lucide SVGs are inline with `aria-hidden="true"`.
- Icon-only controls MUST include `aria-label` on the button itself.

### States Visual Contract (B-2)

| state | data attribute | token contract | meaning |
|---|---|---|---|
| default | `data-state="default"` | `color: var(--text-muted)`, `background: transparent` | Resting state |
| hover | `data-state="hover"` | `background: var(--bg-panel-hover)`, `color: var(--text-normal)` | Pointer hover preview |
| active | `data-state="active"` | `background: var(--bg-active)`, `color: var(--accent-mora)` | Selected / pressed / opened state |
| focus | `data-state="focus"` | `outline: 2px solid var(--accent-mora); outline-offset: 2px` | Keyboard focus visible |
| disabled | `data-state="disabled"` | `opacity: 0.45`, `cursor: not-allowed` | Temporarily unavailable |

Purple discipline for enterprise tone:
- `--accent-mora` is used only for active/focus/indicator semantics.
- No broad purple/lavender surfaces are used in this catalog.

### Keyboard Shortcut Map (B-3)

| Scope | Action | Windows/Linux | macOS |
|---|---|---|---|
| Left rail | Files/Search/Filters/Hierarchy/Layout | `Ctrl+1..5` | `Cmd+1..5` |
| Right rail | Settings | `Ctrl+,` | `Cmd+,` |
| Tabs | New tab | `Ctrl+T` | `Cmd+T` |
| Tabs | Close active tab | `Ctrl+W` | `Cmd+W` |
| Tabs | Next/Previous tab | `Ctrl+Tab` / `Ctrl+Shift+Tab` | `Cmd+Option+→` / `Cmd+Option+←` |
| Toolbar | Back / Forward | `Alt+←` / `Alt+→` | `Option+←` / `Option+→` |
| Toolbar | Zoom fit | `Ctrl+0` | `Cmd+0` |
| Layout | Toggle Hierarchical / Physics | `Ctrl+6` / `Ctrl+7` | `Cmd+6` / `Cmd+7` |

Reference HTML requirement:
- Each catalog row/cell must surface shortcut text visibly (not only in title tooltip).

### Accessibility Contract (B-4)

| Element type | Required attributes / behavior |
|---|---|
| Rail icon (`role="tab"`) | `aria-label`, `aria-selected`, keyboard reachable, 44×44 hit target |
| Icon action button | `aria-label`, 44×44 hit target, visible focus ring |
| Toggle button | `aria-label`, `aria-pressed="true/false"` |
| Active rail item | `aria-selected="true"` |
| SVG icon | `aria-hidden="true"` |

Mandatory accessibility notes:
- Focus ring color uses `--accent-mora: #a78bfa` on `--bg-main: #161616` (**6.66:1**, WCAG AA pass).
- `prefers-reduced-motion: reduce` is honored by `_shared.css` for hover/focus transitions.
- Dense rows (tab strip 36px, tree rows 28px) follow approved exemptions; primary icon buttons remain 44×44.

### Reference artifact requirement

`section-3-button-catalog.html` is the static, file://-friendly visual proof for this section.
It must show every catalog id above with visible shortcut text and explicit `data-state` demos.

---

## Node Interaction Visual Contracts

Section 5 (slice 2) extends the static reference file: `section-5-node-interactions.html`.
This reference artifact is design-only and never loaded by production runtime (`graph_viewer.html` + `renderer.ts`).

Token strategy for this slice:
- No new token families.
- Reuses existing `_tokens.css` variables (`--bg-*`, `--text-*`, `--accent-mora`, `--vis-*`, `--wcc-*`).
- Avoids `--vis-node-*`/`--vis-edge-*` additions in this design-only slice to prevent token-sync drift with `theme.py` and `graph_viewer.html`.

| State | CSS token path | Renderer reference | Status |
|---|---|---|---|
| default | `--wcc-c*` + `--vis-panel-border` | `renderer.ts:710` | SHIPPED |
| hover | `--vis-focus-ring` | `renderer.ts:752` | SHIPPED |
| selected | `--vis-focus-ring` + `--accent-mora-muted` | `renderer.ts:757` | SHIPPED |
| keyboard-focus | `--vis-focus-ring` | `renderer.ts:762` | SHIPPED |
| ego-dimming (hover) | `--accent-mora` + opacity tiers | `renderer.ts:716` | SHIPPED |
| ego-dimming (selection) | `--accent-mora` + opacity tiers | `renderer.ts:716` | PROPOSED |
| marquee + multi-select | `--vis-marquee-stroke` + `--vis-marquee-fill` | `renderer.ts:686` | SHIPPED |
| edge-states (default/related/dimmed) | `--border-strong` + `--accent-mora` + `--text-muted` | `renderer.ts:721` | SHIPPED |
| context menu + score-filter affordance | `--vis-panel-bg` + `--vis-panel-border` + `--vis-panel-text` | `context-menu.ts:1` | SHIPPED |
| hover-popover | `--vis-panel-bg` + `--vis-panel-border` + `--vis-popover-muted` + `--accent-mora-muted` | `renderer.ts:752` | PROPOSED |
