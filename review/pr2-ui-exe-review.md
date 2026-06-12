# PR#2 UI + EXE Review Checkpoint

## What to review
- Reader toolbar sticky behavior in the central markdown reader: the bar should stay flush to the top edge while scrolling, without the broken half-cut halo.
- Reader note editing: editing a note, changing selection, and blurring should still save to the node being edited.
- BRD side panel summary mode: metadata + short preview in the right rail, with the full BRD opening in the center reader.

## Live viewer
`uv run python -m brain_ds ui serve --project-root .`

## Static preview
- Not generated in this slice. Use the live viewer command above.

## Section reference
- `brain_ds/ui/design/sections/section-4-center-canvas.html`

## Out of scope
- Full EXE/NSIS packaging output review.
- Non-reader inspector or rail redesign beyond the BRD summary slice.
