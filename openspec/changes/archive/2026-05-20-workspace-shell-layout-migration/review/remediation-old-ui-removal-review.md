# Remediation — Old UI Removal Review Checkpoint

## What to review
- Full 5-column workspace shell composition (left rail + L-panel + center chrome + inspector + right rail).
- Center column matches PR1.5 quality: tab strip semantics, 44px toolbar zones, realistic canvas placeholder, token-only styling.
- Left side uses Section-1 card language (`.panel-card`, `.command-search`, `.filter-chip`, `.score-control`, `.visual-key`, `.tree-row`, `.toggle-card`) and removes old legacy visuals.
- Right side uses Section-2/5 inspector accordion patterns, restrained `.empty-state`, and gear-only right rail.
- Optional theme toggle demo (`#theme-toggle`) flips `data-theme` dark/light for parity checks.

## Live viewer
`uv run python -m brain_ds.cli view --input .\examples\sample_org\graph.json --output .\tmp\workspace-shell-remediation.html`

## Static preview
- `openspec/changes/workspace-shell-layout-migration/review/remediation-old-ui-removal-preview.html`

## Section reference
- `brain_ds/ui/design/sections/section-1-left-shell.html`
- `brain_ds/ui/design/sections/section-2-right-shell.html`
- `brain_ds/ui/design/sections/section-4-center-canvas.html`
- `brain_ds/ui/design/sections/section-5-node-interactions.html`
