---
name: spectacular-frontend-ui
description: Build spectacular, product-grade UI for brain_ds — an Obsidian-style knowledge-graph workspace. Token-driven, spatially locked, WCAG AA, with a mandatory section-by-section review loop. Refuses to ship production UI before design references are read and accepted.
---

# Spectacular Frontend UI — brain_ds

You are building UI for the **brain_ds workspace**: an Obsidian-flavored, dark-first, IDE-grade knowledge graph environment. The bar is the artifacts in `brain_ds/ui/design/sections/`. Every output must match that level of polish — or it does not ship.

## Design DNA (the aesthetic is decided)

This project is NOT a blank canvas. The aesthetic identity is **already chosen and committed** (see commits `94a0679 obsidian-workspace-ui`, `78a3acb graph-viewer-visual-polish`). Honor it. Do not "reinvent" the look.

- **Genre**: dark-first IDE / knowledge tool (Obsidian, VS Code, Linear lineage).
- **Voice**: quiet confidence. The canvas is the hero; chrome recedes.
- **Color economy**: a near-black canvas (`--bg-main: #161616`), a single sharp accent (`--accent-mora: #a78bfa`), and a 12-color WCC palette for graph nodes — used *only* where data demands color.
- **Density**: IDE-dense, not consumer-airy. 28px tree rows, 36px tab strip, 44px primary CTAs.
- **Motion**: restrained. Hover reveals, 100–150ms transitions, no decorative animation.
- **Typography**: native system stack. No web fonts. Weight and spacing do the work, not novelty fonts.

If a request pulls you toward marketing-site flavors (purple gradient washes, oversized hero type, decorative grain overlays, glassmorphism, neon glow), **push back**. That is not what this product is.

## Design Thinking — BEFORE writing code

For any non-trivial UI task, answer these out loud (in chat) before touching files:

1. **Purpose** — what problem does this section solve, for whom in the workspace?
2. **Spatial role** — where does it live in the 5-column grid? Rail, panel, center, or overlay?
3. **Spec contracts** — which ADR/spec locks apply (heights, ARIA, focus)?
4. **Differentiation** — what one detail will make this *feel* like brain_ds and not generic "AI dashboard"?
5. **Out of scope** — what will I deliberately NOT add?

Only after these are answered do you read references and write code.

## MANDATORY: Section-by-Section Review Loop

**Never build a full production UI in one shot.** The loop is non-negotiable:

1. Build ONE section (e.g. left rail, center canvas, right panel, a single accordion group).
2. Present it to the user — running HTML or visible diff.
3. Ask: *"Does this section look right? Anything to change before I move on?"*
4. **STOP. Wait for the user.** Do not continue to the next section, do not pre-emptively scaffold "what's next".
5. Iterate until accepted, then move on.

This loop applies to any format — static HTML reference, Jinja template, JS-rendered component.

### Stop conditions (refuse to continue)

- A locked design reference (`_tokens.css`, `_shared.css`, `ui-workspace-shell.md`) hasn't been read in this session.
- The user asks for "the whole UI in one shot" — explain the loop and propose the first section instead.
- A token is missing for what you need — propose adding it to `_tokens.css` first, do not hardcode.

## Pre-Build Reading Checklist (mechanical)

Before the first line of UI code, you have read:

- [ ] `brain_ds/ui/design/sections/_tokens.css` — current token set
- [ ] `brain_ds/ui/design/sections/_shared.css` — shared components (rail, grid, accordion, focus, status chip)
- [ ] `brain_ds/ui/design/sections/ui-workspace-shell.md` — workspace contract (wireframes, ARIA table, ADR table)
- [ ] The nearest existing reference section (`section-1-left-shell.html`, `section-4-center-canvas.html`, etc.)
- [ ] If touching the live viewer: `brain_ds/ui/templates/graph_viewer.html` `:root{}`

Skip this and the answer is wrong by construction.

## Design System Fundamentals

### Token Discipline (HARD RULE)

- **Source of truth**: `_tokens.css` (synced from `brain_ds/ui/theme.py` and `graph_viewer.html :root{}`).
- **No hardcoded hex values in CSS.** Every color is `var(--token-name)`.
- All tokens are family-prefixed: `--bg-*`, `--text-*`, `--border-*`, `--accent-*`, `--radius-*`, `--vis-*`, `--wcc-*`.
- Dark theme is the default. Light overrides go inside `[data-theme='light']`.
- **Minimum required tokens for any panel**: `--bg-main`, `--bg-panel`, `--accent-mora`, `--text-normal`, `--border-subtle`.
- **Need a new token?** Add it to `_tokens.css` AND `theme.py` AND `graph_viewer.html :root{}`. Note the sync in a comment. Don't fork.

### Spatial Hierarchy (LOCKED — DO NOT DEVIATE)

| Element             | Height            | Rule                                          |
| ------------------- | ----------------- | --------------------------------------------- |
| Rail icon buttons   | 44×44 px          | WCAG 2.5.5 touch target                       |
| Top toolbar row     | **44px LOCKED**   | ADR-001 / spec-amendment-dr5                  |
| Tab strip row       | **36px**          | ADR-009 tablist semantics exemption           |
| File-tree rows      | **28px visual**   | ADR-004 dense data tree exemption             |
| Canvas area         | `flex: 1`         | Fills remaining space                         |
| Status chip         | 40×44 px          | 44px hit target preserved                     |

If a design requirement seems to push against these, the answer is *not* to deviate — propose an ADR amendment.

### Composition Model

The workspace is a **CSS Grid with 5 columns**:

```
48px rail │ 220–300px panel │ minmax(0,1fr) center │ 280–360px panel │ 48px rail
```

The center column is a **nested flex**:

```
tab-strip (36px) → toolbar (44px) → canvas (flex 1)
```

Rails use `--rail-w: 48px` **scoped to `.workspace-shell`**, not a global token. The right-edge rail mirrors via `inset-inline-end` for the active indicator.

## Visual Hierarchy & Polish — what "spectacular" means here

- **Canvas is the hero.** Chrome surfaces (`--bg-panel: #1e1e1e`) sit on canvas (`--bg-main: #161616`) — a 2-step value gap, not a flat wall. Borders are barely-there (`rgba(255,255,255,0.06)`).
- **One accent, used sparingly.** `--accent-mora` marks *active state and only active state*. Selected rail icon, focus ring, marquee stroke, edge-primary in the graph. Not for hover, not for decoration.
- **Active-state has TWO signals.** Color shift + 2px `::before` edge indicator. Single-signal active states fail color-blind users.
- **Hover reveals secondary affordances.** Close buttons, action icons appear at hover only — `opacity 0 → 1` over `100ms`. They never *appear and disappear*; they pre-exist invisibly.
- **Status chip discipline.** 40×44, uppercase, `letter-spacing: 0.04em`, `font-weight: 600`. No icon-plus-label hybrids.
- **No bottom bar, no footer.** Status lives in the left rail. Reclaim that vertical space for canvas.
- **Density rewards proficiency.** This is a tool for repeat users — favor compact, scannable layouts over generous whitespace inside panels. Canvas gets the air.

## Motion & Micro-interactions

Motion is restrained on purpose. Use it where it carries meaning, not where it decorates.

| Where               | What                                    | Timing            |
| ------------------- | --------------------------------------- | ----------------- |
| Hover reveals       | opacity 0 → 1                           | 100ms ease        |
| Tab/rail selection  | color + indicator slide-in              | 150ms ease-out    |
| Accordion chevron   | rotate 0 → 90deg                        | 150ms ease        |
| Popovers (hover)    | delayed entry (350ms before fade-in)    | 150ms fade        |
| Marquee select      | accent stroke + muted fill              | instant           |

Forbidden: parallax, bounce, springy easing, decorative scroll animation, anything > 250ms on a chrome element.

**`prefers-reduced-motion: reduce`** collapses every transition/animation to `0.01ms`. This is already in `_shared.css` — do not re-implement it, do not bypass it.

## Anti-AI-Slop — patterns to refuse

These read as "AI-generated dashboard". The brain_ds aesthetic refuses them:

- Purple/pink gradient hero backgrounds. (We use one flat accent, not a wash.)
- Glassmorphism cards (`backdrop-filter: blur` over noisy surfaces).
- Generic web fonts hauled in for "personality" (Inter, Space Grotesk, Geist). Native stack only.
- Card-grid dashboards with rounded `border-radius: 16px+`. (Ours is `--radius-ui: 6px`.)
- Emoji used as icons. Lucide ISC SVGs only.
- "Floating" toolbars detached from the grid. The grid is the structure.
- Multiple accent colors competing in chrome. One accent. The WCC palette is data-only.
- Auto-generated marketing-site filler ("Get started in 3 steps", testimonial blocks, neon CTAs).
- Centered max-width content columns inside a workspace shell. The shell IS the layout.
- Box-shadows on panels for "depth". We use value-step backgrounds, not shadows.

If a stakeholder request maps to one of these, name the tradeoff and propose the brain_ds-native alternative.

## Accessibility (NON-NEGOTIABLE)

- **WCAG AA contrast** on every color pair. `--accent-mora: #a78bfa` achieves 6.66:1 on `--bg-main: #161616`. Run `brain_ds/ui/contrast-audit.json` checks for new pairs.
- **Global focus ring**: `outline: 2px solid var(--accent-mora); outline-offset: 2px` on `*:focus-visible`. Already in `_shared.css`.
- **Touch targets ≥ 44×44** for every primary interactive element (rails, toolbar buttons, status chip).
- **Semantic ARIA**:
  - `role="tablist"` / `role="tab"` + `aria-selected` for rails and tab strips.
  - `aria-pressed` for toggles (theme switch, panel collapse).
  - `aria-label` on every icon-only button (Lucide SVG gets `aria-hidden="true"`).
  - `aria-current="page"` for the active workspace tab.
- **`prefers-reduced-motion`** — honored globally via `_shared.css`.
- **Keyboard reachable** — every interactive element via Tab; activatable via Enter/Space. Arrow-key navigation within tablists.
- **`.visually-hidden`** utility for screen-reader-only labels.

## Design Reference Artifacts

| File                                                       | Purpose                                                    |
| ---------------------------------------------------------- | ---------------------------------------------------------- |
| `brain_ds/ui/design/sections/_tokens.css`                  | Token source of truth                                      |
| `brain_ds/ui/design/sections/_shared.css`                  | Shared components (rail, grid, focus, accordion, chip)     |
| `brain_ds/ui/design/sections/ui-workspace-shell.md`        | Full workspace spec — wireframes, contracts, ARIA, ADRs    |
| `brain_ds/ui/design/sections/section-1-left-shell.html`    | Reference: left rail + panel + file tree                   |
| `brain_ds/ui/design/sections/section-4-center-canvas.html` | Reference: tab strip + toolbar + canvas ("spectacular" bar)|
| `brain_ds/ui/design/sections/LICENSES`                     | Lucide ISC license                                         |
| `brain_ds/ui/theme.py`                                     | Python token source (must stay in sync)                    |
| `brain_ds/ui/templates/graph_viewer.html`                  | Live viewer — `:root{}` must mirror `_tokens.css`          |
| `brain_ds/ui/contrast-audit.json`                          | WCAG contrast audit data                                   |

## Implementation Rules

1. **Read design references first.** Not optional. See the Pre-Build Reading Checklist.
2. **Lucide icons only** (ISC license). `aria-hidden="true"` on the SVG, `aria-label` on the parent button.
3. **No inline styles.** All CSS goes in `<style>` blocks or linked `.css` files, using `var(--token)`.
4. **No emoji icons.** Ever. Lucide SVGs.
5. **System-chrome zone** (`data-toolbar-zone="system-chrome"`) **stays empty** — reserved for native window controls.
6. **Static design references are module-free.** No `import`s, no bundler — static HTML/CSS only (spec X-5).
7. **Font**: `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`. No external font loading.
8. **Box-sizing**: `border-box` on `*, *::before, *::after`.
9. **`min-height: 0`** on flex children that must shrink. This is the #1 bug in canvas layout.
10. **Token sync invariant**: changing `_tokens.css` requires the same change in `theme.py` and `graph_viewer.html :root{}`.

## Self-Check Before Declaring "Done"

Walk this list, in order. If any answer is "no" or "unsure", stop and fix it.

- [ ] I read the relevant design references this session.
- [ ] Every color is `var(--token)`. No hex literals in CSS.
- [ ] Heights honor the locked contracts (44/36/28/44).
- [ ] Every interactive element has its ARIA attributes + a 44×44 (or exempt) hit target.
- [ ] Focus ring visible on every interactive element via keyboard.
- [ ] `prefers-reduced-motion` honored (or already covered by `_shared.css`).
- [ ] No anti-AI-slop pattern slipped in.
- [ ] The change is one section, not three. The review loop is intact.
- [ ] If tokens were added: `_tokens.css`, `theme.py`, and `graph_viewer.html :root{}` all updated.

## When You Get Stuck

- **Token missing?** Propose adding it to `_tokens.css` + `theme.py` + `graph_viewer.html` in one PR. Do not hardcode.
- **Spec contradicts a request?** Surface the conflict. Cite the ADR/spec. Propose an amendment, do not silently deviate.
- **Reference doesn't cover the case?** Build the smallest possible reference HTML in `brain_ds/ui/design/sections/` FIRST, get it accepted, *then* port to the live template.
- **Stakeholder asks for something off-aesthetic?** Name it (e.g. "that's a glassmorphism pattern, which is on our anti-slop list because…") and offer the brain_ds-native alternative.
