# UI Chrome Consistency — Slice 1 Review Checkpoint

## What to review
- At wide widths, the top toolbar shows its mode, zoom, preferences, and overflow controls without clipping.
- At narrow widths, only the essential organization navigation, graph metadata, and More actions control remain; the secondary controls are hidden without overlap.
- Switch the theme twice and confirm the toolbar, rails, focus ring, sliders, and collapsed rails remain readable in dark and light themes.
- Set a score threshold, switch graph tabs, then return to confirm the control state restores for that graph.
- Collapse each side panel and reopen it from its rail icon.

## Live viewer
```powershell
uv run brain_ds ui .\tmp_sample_graph.json --output .\tmp\ui-chrome-consistency-slice-1.html
```

## Static preview
- The Playwright checkpoint is `brain_ds/ui/e2e/chrome-consistency-slice-1.spec.ts`.

## Section reference
- `brain_ds/ui/design/sections/section-1-left-shell.html`
- `brain_ds/ui/design/sections/section-2-right-shell.html`
- `brain_ds/ui/design/sections/section-3-button-catalog.html`
- `brain_ds/ui/design/sections/section-4-center-canvas.html`

## Out of scope
- Node-color legend semantics and hierarchy navigation are separate slices.
