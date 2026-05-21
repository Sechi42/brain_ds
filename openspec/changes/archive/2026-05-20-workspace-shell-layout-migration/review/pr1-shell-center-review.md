# PR1 Review Checkpoint — Shell Scaffold + Center Chrome

## What to review

This slice only includes:
- 5-column workspace shell scaffold (`48px | 220-300 | 1fr | 280-360 | 48px`)
- Center tab strip (`36px`) and toolbar (`44px`)
- View-label + overflow controls (`#zoom-fit`, `#theme-toggle`)
- `#network` still mounted in center canvas
- Left/right are placeholders (full adapters and inspector work are PR2/PR3)

## Live viewer (production template path)

Generate a real viewer HTML from any graph JSON and open it:

```powershell
uv run python -m brain_ds.cli view --input .\examples\sample_org\graph.json --output .\tmp\pr1-shell-center.html
```

Then open `tmp\pr1-shell-center.html` in your browser.

## Static preview mirror (review-only)

If you want a deterministic visual-only checkpoint without Jinja/runtime dependencies, open:

- `openspec/changes/workspace-shell-layout-migration/review/pr1-shell-center-preview.html`

This is a non-production artifact for visual critique only.
