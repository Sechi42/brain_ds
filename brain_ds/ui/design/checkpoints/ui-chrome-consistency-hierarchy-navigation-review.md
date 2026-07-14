# UI Chrome Consistency — Hierarchy Navigation Review Checkpoint

## What to review
- Opening the hierarchy map presents a clear full-context breadcrumb and disabled Back state.
- Selecting a chip isolates its ancestors and descendants; Back restores the complete map and prior scroll position.
- The scroll plane supports native overflow, Shift+wheel, pointer drag, keyboard Back, Escape, and dark/light themes.

## Out of scope
- Final cross-panel polish and global cleanup are deferred to Slice 4.

## Live viewer
`uv run brain_ds ui .\tests\fixtures\graph_inputs\actor.json --output .\tmp\ui-chrome-consistency-hierarchy.html`

## Section reference
- `brain_ds/ui/design/sections/section-4-center-canvas.html`
