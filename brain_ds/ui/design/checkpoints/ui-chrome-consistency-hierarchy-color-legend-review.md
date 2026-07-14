# UI Chrome Consistency — Color Legend Review Checkpoint

## What to review
- Compact canvas legend remains visible at narrow widths and expands with type names and counts.
- Legend, filter chips, tree chips, inspector dots, and canvas nodes use the same theme-aware type colors.
- Toggling a filter updates the canvas legend state; legend rows can toggle the same filter.
- Dark and light themes preserve labelled, distinguishable type swatches.

## Out of scope
- Hierarchy branch navigation and final cross-panel polish are deferred to later slices.

## Live viewer
`uv run brain_ds ui .\tests\fixtures\graph_inputs\actor.json --output .\tmp\ui-chrome-consistency-color-legend.html`

## Section reference
- `brain_ds/ui/design/sections/section-4-center-canvas.html`
