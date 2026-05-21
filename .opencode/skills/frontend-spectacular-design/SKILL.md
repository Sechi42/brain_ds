---
name: frontend-spectacular-design
description: Build chrome/UI for brain_ds graph_viewer at the fidelity of brain_ds/ui/design/sections/* — token-disciplined, WCAG-compliant, icon-rich, with mandatory reviewable HTML checkpoints after each PR. Trigger when modifying graph_viewer.html, brain_ds/ui/templates/*, brain_ds/ui/src/**, or any workspace-shell/center-canvas/rail/panel work.
---

# Frontend Spectacular Design — brain_ds

The shipped design references in `brain_ds/ui/design/sections/` are the GROUND TRUTH for visual fidelity. Production templates (`brain_ds/ui/templates/graph_viewer.html`) MUST match the corresponding section in chrome quality, not just structure.

## When to invoke

- Editing `brain_ds/ui/templates/graph_viewer.html`
- Editing anything under `brain_ds/ui/src/` (renderer, panels, interactions)
- Implementing any slice of `workspace-shell-layout-migration` or successor changes
- Any PR that changes user-visible chrome (tab strip, toolbar, rails, panels, canvas)

## Design references — read BEFORE writing code

| Region | Reference file |
|---|---|
| Workspace shell + grid | `brain_ds/ui/design/sections/ui-workspace-shell.md` |
| Tokens (source of truth: `theme.py`) | `brain_ds/ui/design/sections/_tokens.css` |
| Shared component CSS | `brain_ds/ui/design/sections/_shared.css` |
| Left rail + L-panel | `section-1-left-shell.html` |
| Right rail + R-panel | `section-2-right-shell.html` |
| Button catalog | `section-3-button-catalog.html` |
| **Center canvas (tabs + toolbar + canvas)** | `section-4-center-canvas.html` |
| Node interactions | `section-5-node-interactions.html` |

If you are editing a region, OPEN the matching section file first and copy its component-level CSS verbatim where possible, only diverging when the live template needs runtime behavior the static reference cannot express.

## Non-negotiables

### 1. Token discipline
- **Never** hardcode hex colors in templates. Use `var(--*)` from `_tokens.css`.
- The runtime source of truth lives in `brain_ds/ui/theme.py` `THEME_TOKENS`; `_tokens.css` mirrors it.
- If a new token is needed, add it to `theme.py` first, then mirror to `_tokens.css`.

### 2. Hit targets (WCAG 2.5.5)
- Primary interactive controls: **44×44 minimum** (ADR-001, locked by spec-amendment-dr5).
- Tab strip rows: **36px** allowed (ADR-009 — tablist semantics exemption).
- File-tree rows: **28px** allowed (ADR-004 — dense data tree exemption).
- Anything else under 44px → reject.

### 3. Toolbar zones contract
The top toolbar MUST expose four `data-toolbar-zone` slots:
- `nav` — back/forward (left)
- `view` — view metadata label (flex 1, ellipsis on overflow)
- `overflow` — kebab/more-actions (right)
- `system-chrome` — RESERVED for native window controls, **do not paint**

### 4. Tab strip contract (ADR-008/009)
- `role="tablist"` on container, `role="tab"` on buttons
- Active tab: 2px `var(--accent-mora)` underline via `box-shadow: inset 0 -2px 0`, bg blending with canvas
- Close button: hover-reveal on inactive tabs (`opacity: 0` → `opacity: 1` on `.tab-item:hover`), always visible on active tab
- Max-width 180px with ellipsis on labels
- Separate 44×36 new-tab `+` button

### 5. Icons
- Use **Lucide** icons (already licensed in `_shared.css` header).
- Inline SVG with `aria-hidden="true"` for decorative, `aria-label` on the button.
- Stroke: `currentColor`, `stroke-width: 2` (use `2.5` only for small `x` close icons).

### 6. State model — every interactive control needs ALL of:
- default
- `:hover` (background lift to `var(--bg-panel-hover)`, color to `var(--text-normal)`)
- `:focus-visible` (2px `var(--accent-mora)` outline, 2px offset — global rule)
- `[disabled]` (`opacity: 0.45; cursor: not-allowed`)
- pressed/selected where applicable (`aria-pressed='true'` or `aria-selected='true'` → accent color)

### 7. Motion
- All `transition`/`animation` MUST be silenced under `@media (prefers-reduced-motion: reduce)`.
- Default transition: `200ms ease` for color/background/border/transform/opacity.

### 8. Theme parity
- Both `[data-theme='dark']` (default) and `[data-theme='light']` MUST render correctly.
- No theme-conditional hex — only token overrides on the `[data-theme='light']` selector.

## MANDATORY: post-PR review checkpoint

**After every PR that ships user-visible chrome, you MUST emit ONE of:**

1. A static HTML preview at `openspec/changes/<change-name>/review/<pr-slug>-preview.html` that the user can open and inspect in isolation — pulling in `_tokens.css` + `_shared.css` from the design references, NOT inlining tokens.
2. A PowerShell command to generate a live viewer from a sample graph (e.g. `uv run python -m brain_ds.cli view --input .\examples\sample_org\graph.json --output .\tmp\<pr-slug>.html`) AND a brief `review/<pr-slug>-review.md` explaining what to look at and what is out of scope.

**Both is preferred.** The review checkpoint is part of the deliverable, not an afterthought. No PR is complete without it.

Format of the review markdown:
```
# <PR title> Review Checkpoint

## What to review
- bullets describing the visual surface
- explicit out-of-scope items (so the user does not critique what is intentionally deferred)

## Live viewer
<powershell command>

## Static preview
- path to the preview HTML

## Section reference
- which section-N-*.html this PR matches against
```

## Anti-patterns — REJECT these on sight

- Hardcoded hex in `*.html` templates (use tokens)
- Plain `<button>` with text labels where the design reference uses icons
- `space-between` toolbars with no zone semantics
- Tabs without `role="tab"` / `aria-selected`
- Hit targets under 44px outside the documented exemptions
- New CSS variables without first adding them to `theme.py`
- Skipping the post-PR review HTML

## Tests
- `tests/test_viewer.py` — chrome and a11y assertions; run after every chrome change
- `tests/test_render_context_golden.py` — golden fixtures; if you break these, FIX the fixtures or your change — do NOT just rerun

## Self-check before declaring done

- [ ] Compared the rendered output side-by-side with the matching `section-N-*.html`
- [ ] No hardcoded hex in the template
- [ ] All controls meet the state model (default/hover/focus/disabled/pressed)
- [ ] Reduced-motion override in place
- [ ] Both themes render
- [ ] Post-PR review HTML written
- [ ] Viewer tests pass
