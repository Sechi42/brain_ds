# UI Chrome Consistency and Hierarchy — Final Review Checkpoint

## What to review
- Top toolbar at wide and narrow widths: visible navigation and view identity, secondary-action overflow, keyboard focus, and disabled controls.
- Left rail destinations: Projects, Search, Filters, Hierarchy, and Layout; confirm selected state, collapse/reopen behavior, sliders, segments, scrolling, and filter/legend synchronization.
- Right rail destinations: Inspector, AI Actions, Pipeline, Reader, BRD, and Settings; confirm exclusive panels, empty/loading/error states, form controls, and readable clipping boundaries.
- Canvas legend: Spanish labels and tooltips, keyboard expansion, selected/hidden type state, dark/light colors, and synchronization with filters.
- Hierarchy map: selected branch, breadcrumb/back, Escape, focus loop, narrow horizontal scroll, and return to the main graph.
- Dark and light themes, reduced-motion rules, overflow menu, tab navigation, and console-error-free Slice 1–3 audit paths.

## Live viewer
```powershell
uv run brain_ds ui .\tmp_sample_graph.json --output .\tmp\ui-chrome-consistency-hierarchy-final.html
```

## Static preview
- The generated live viewer above is the review surface; it includes the reviewed bundle and icon sprite.

## Section reference
- `ui-workspace-shell.md`, `section-1-left-shell.html`, `section-2-right-shell.html`, and `section-4-center-canvas.html`.

## Out of scope
- Existing physics bundle-revision expectations, secret-admin authorization fixtures, password-input contract, and historical rail spacing assertions are not chrome changes in this slice.
- No ontology, backend, source-connection, or graph feature work is included.
