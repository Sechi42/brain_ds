# UI Polish Pass (2026-07-13) Review Checkpoint

## What to review

- **Canvas type-color identity**: every node now renders its ontology type color at rest
  (Data Source `#7c3aed`, DataContainer `#6d28d9`, DataField `#8b5cf6`, Unknown gray) with a
  soft glow; edges carry a faint tint of their source node. Selection/hover states glow in the
  node's own color instead of a generic blue. Theme toggle recolors nodes live.
- **Load framing**: the graph greets the user framed — early fit at 500 ms plus a re-fit when
  the physics simulation settles (skipped if the user already panned/zoomed).
- **Inspector auto-reveal**: clicking a node expands the collapsed right shell and routes it to
  the inspector section. Action buttons no longer clip; wide markdown tables scroll inside
  their card; card-section icon slugs (`database`, `columns`, `target`, `user`, `clock`,
  `alert-triangle`) render as Lucide sprite icons; duplicated sections dedupe in read mode.
- **Toolbar resilience**: tab labels ellipsize; when open panels squeeze the view zone the
  node/edge counters hide cleanly (container query) instead of crushing into "• : • 6".
- **Favicon**: inline SVG data-URI — no more `/favicon.ico` 404 console error.

Out of scope (intentionally deferred):

- Label overlap between nearby disconnected nodes (physics/label-policy tuning).
- Cluster/Data-Source organization view re-coloring semantics.
- Startup/vault-picker UX and Tauri shell work.

## Live viewer

```powershell
uv run python -m brain_ds.ui ui --project-root . --port 8801
# then open http://127.0.0.1:8801/ — click "Orders", toggle theme, resize the window
```

## Static preview

- Session screenshots (repo root): `ui-baseline-home.png` (before) vs `ui-iter1-dark-fitted.png`,
  `ui-iter2-icons.png`, `ui-iter3-final.png`, `ui-final-light.png` (after).

## Section reference

- `section-4-center-canvas.html` (tab strip + toolbar + canvas)
- `section-2-right-shell.html` (right rail + inspector panel)

## Verification

- `pytest`: 465 passed (viewer, server, canvas renderer, panels, render-context golden, theme, regression)
- `npm run ci` in `brain_ds/ui`: typecheck + build + bundle-size OK (raw 157006/163840, gz 45866/49152)
- `npm run bundle-freshness`: passed
- Playwright: dark/light parity, selection, auto-reveal, breadcrumb squeeze verified on live server
