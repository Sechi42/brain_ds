# PR1.5 Review Checkpoint — Center Chrome Polish

## What to review

The center column chrome in `brain_ds/ui/templates/graph_viewer.html` is now at the fidelity of `brain_ds/ui/design/sections/section-4-center-canvas.html`.

Specifically:

- **Tab strip (36px, ADR-009)** — `role="tablist"`, `role="tab"`, active tab has 2px `var(--accent-mora)` underline via `box-shadow: inset 0 -2px 0`, close button hover-reveal on inactive / always-visible on active, max-width 180px with ellipsis, separate `tab-new` `+` button.
- **Top toolbar (44px, ADR-001)** — four zones: `data-toolbar-zone="nav|view|overflow|system-chrome"`. Back/forward Lucide arrows in `nav` (forward disabled). View-label slot renders `Org · N nodes · M edges · YYYY-MM-DD`. Overflow has the kebab/more-actions button, plus `#zoom-fit` and `#theme-toggle` (runtime IDs preserved for existing JS) as `toolbar-btn` icon buttons.
- **Iconography** — Lucide inline SVGs throughout (arrow-left, arrow-right, more-horizontal, x, plus). `aria-hidden="true"` on decorative SVGs, `aria-label` on buttons.
- **State model** — default / hover / `:focus-visible` (2px accent outline) / `[disabled]` / pressed-or-selected on every interactive control.
- **Token discipline** — zero hardcoded hex in the chrome CSS. Everything via `var(--*)`.
- **Reduced motion** — chrome transitions silenced under `@media (prefers-reduced-motion: reduce)`.
- **`#network` canvas mount preserved.**

## Out of scope (do NOT critique here — belongs to PR2/PR3)

- Left rail icons + L-panel adapters (PR2)
- Right rail icons + inspector adapter + responsive slide-over (PR3)
- Back/forward and overflow-kebab BEHAVIOR — they are stub buttons for chrome fidelity. Wiring belongs to later PRs.
- Light theme color overrides — `[data-theme='light']` still relies on `theme.py` runtime population.
- Golden fixture regen for `tests/test_render_context_golden.py` (pre-existing failures from PR1 era, not in PR1.5 scope).

## How to inspect

### Static preview (no runtime, deterministic)

Open in your browser:

```
openspec/changes/workspace-shell-layout-migration/review/pr1.5-chrome-polish-preview.html
```

This links to `brain_ds/ui/design/sections/_tokens.css` and `_shared.css` directly — what you see is what the live template should produce under default conditions.

### Live viewer (production template path)

Render the actual `graph_viewer.html` against a sample graph:

```powershell
uv run python -m brain_ds.cli view --input .\examples\sample_org\graph.json --output .\tmp\pr1.5-chrome-polish.html
```

Then open `tmp\pr1.5-chrome-polish.html`.

## Side-by-side reference

Compare both against the ground truth:

```
brain_ds/ui/design/sections/section-4-center-canvas.html
```

If anything in the center column chrome diverges from section-4 in ways NOT listed under "Out of scope", report it — that's a PR1.5 defect, not a deferred concern.

## Tests

- `tests/test_viewer.py` — 77 passing (62 from PR1 + 15 new PR1.5 chrome assertions: tablist semantics, close-button presence, all four toolbar zones, nav-back/forward catalog IDs, overflow `aria-haspopup="menu"`, no hardcoded hex in chrome regions, Lucide SVG presence, reduced-motion override).

## Next

User reviews this checkpoint. If approved → PR2 (left adapters). If defects → fix and re-emit a new review.
