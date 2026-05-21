# PR3 — Right Rail + Inspector + Responsive Review

**Change**: workspace-shell-layout-migration  
**Slice**: PR3 — right rail + inspector adapter + responsive behavior  
**Status**: Implementation complete — awaiting user visual review  

---

## What to inspect

Open `pr3-right-inspector-responsive-preview.html` in a browser (see command below).

### Right rail

- Three `.rail-icon` buttons (44×44 each) with Lucide icons:
  - `inspector` (panel-right icon) — **active by default**, `aria-selected="true"`
  - `history` (clock icon) — inactive stub
  - `settings` (gear icon) — inactive stub
- Active icon shows accent-mora highlight + **2px right inner-edge indicator** (via `_shared.css` `::before` pseudo on `[data-rail-side='right']` — the mirrored version places the indicator on the right inner edge, not the left)
- Inactive icons: muted color, hover shows `var(--bg-panel-hover)` background
- Focus ring: `2px var(--accent-mora)` outline on keyboard focus (`:focus-visible`)
- Rail icon clicks are **stubs only** — panel routing is a follow-up PR (HTML comment in template marks this)
- `role="tablist"` / `aria-orientation="vertical"` on the nav — semantically a vertical tablist

### R-panel header

- 44px header bar: "Inspector" title (left) + collapse chevron button (right)
- Collapse button is 44×44 (WCAG 2.5.5 compliant), `aria-label="Collapse right panel"`
- Header carries `role="region"` + `aria-label="Inspector panel"`
- **Collapse is a stub** — does not wire to `#detail-collapse` runtime; follow-up PR

### Inspector accordion sections

- Preview shows simulated node details (Properties, Metadata, Related) rendered using `.inspector-accordion` / `.inspector-summary` / `.inspector-body` classes from `_shared.css`
- Chevron rotates on open/close (CSS `details[open] .chevron` rule from `_shared.css`)
- AI Actions stub section present (MCP bridge — not wired)

### Responsive slide-over (CRITICAL — test this)

Resize browser below 1100px (or use DevTools mobile simulation):

1. `.right-panel-shell` hides (display: none in `@media (max-width: 1100px)`)
2. `#detail-panel` becomes a fixed slide-over when activated (`.is-mobile-open` class via JS)
3. `#detail-panel-backdrop` covers the canvas — click it to dismiss
4. Press `Escape` key to dismiss the slide-over
5. The responsive helpers `syncDetailPanelPresentation`, `activateDetailSlideover`, `deactivateDetailSlideover` remain unchanged — runtime behavior is preserved

The preview file does NOT include the full JS slide-over wiring (it's isolated). Test the responsive behavior by opening `brain_ds/ui/templates/graph_viewer.html` directly in a browser and resizing below 1100px.

---

## Out of scope for PR3

- **Rail-icon click BEHAVIOR** — clicking inspector/history/settings icons does not switch panel content; panel routing is a follow-up PR (HTML comments mark these stubs in the template)
- **L-panel content redesign** — tracked in `ui/l-panel-content-review` engram memory; out of scope for this chain
- **`tests/test_render_context_golden.py`** — pre-existing failures, not related to this PR
- **R-panel collapse wiring** — the header collapse button does not yet forward to `#detail-collapse`; it's a visual stub
- **MCP bridge / AI Actions** — stub only, not wired

---

## Live viewer PowerShell command

Open the preview in your default browser from the project root:

```powershell
Start-Process "openspec\changes\workspace-shell-layout-migration\review\pr3-right-inspector-responsive-preview.html"
```

Or navigate directly in the browser to:

```
C:\Users\evolu\Desktop\Master\brain_ds\openspec\changes\workspace-shell-layout-migration\review\pr3-right-inspector-responsive-preview.html
```

For full responsive slide-over testing, open the live template:

```powershell
Start-Process "brain_ds\ui\templates\graph_viewer.html"
```

---

## Responsive test instructions

1. Open `brain_ds/ui/templates/graph_viewer.html` in Chrome/Edge
2. Open DevTools → toggle device toolbar (Ctrl+Shift+M)
3. Set viewport width below 1100px (e.g. 768px)
4. Verify `.right-panel-shell` is hidden
5. Click a node — `#detail-panel` should slide in from the right as an overlay
6. Tap/click the `#detail-panel-backdrop` to close
7. Re-open and press `Escape` — panel should close
8. Return to > 1100px — inspector panel returns to its right-rail position inline

---

## Side-by-side comparison reference

Section-2 ground truth (right shell design reference):

```
C:\Users\evolu\Desktop\Master\brain_ds\brain_ds\ui\design\sections\section-2-right-shell.html
```

Open both files in browser tabs to compare:
- Right rail icon set and active indicator (right inner-edge mirror vs section-2's single gear icon)
- R-panel header "Inspector" title + collapse chevron
- Inspector accordion sections (Properties, Metadata, Related, AI Actions)

---

## Test results

- **107 passed** (90 PR1/PR1.5/PR2 baseline + 17 PR3 new assertions)
- 0 regressions in existing tests
- `tests/test_render_context_golden.py` — pre-existing failures (out of PR3 scope)

## Files changed

| File | Change |
|------|--------|
| `brain_ds/ui/templates/graph_viewer.html` | Right rail structure (section-2 icons), R-panel header, inspector accordion stubs, PR3 CSS block, reduced-motion coverage |
| `tests/test_viewer.py` | 17 new PR3 assertions (`TestWorkspaceShellPr3RightInspectorResponsive`) |
| `openspec/.../pr3-right-inspector-responsive-preview.html` | Standalone review preview |
| `openspec/.../pr3-right-inspector-responsive-review.md` | This file |
