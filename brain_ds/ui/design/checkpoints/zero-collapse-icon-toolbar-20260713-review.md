# Zero-Width Panel Collapse + Inspector Icon Toolbar (2026-07-13) Review Checkpoint

## What to review

- **Zero-width collapse (the "ugly rectangle" fix)**: collapsing either side panel
  now animates its grid track to 0px. The 48px residual strip with the floating
  chevron (visible between the rail and the framed center card whenever a panel
  was closed) is gone. Children freeze at the pre-collapse width during the
  200ms animation so text does not rewrap mid-flight; `visibility` flips after
  the fade so hidden controls leave the tab order.
- **Rails are the reopen affordance**: clicking any LEFT rail icon expands the
  panel to that section; re-clicking the ACTIVE icon collapses it (the right
  rail already worked this way — both sides now share the same toggle model).
  Collapsing clears the rail selection so no icon reads lit while its panel is
  hidden.
- **Inspector icon toolbar**: the framed 2-column grid of chunky labeled pills
  (Editar / Exportar JSON / Guardar / Colapsar / Cerrar) is now ONE row of 44px
  square icon buttons matching the rail/toolbar chrome. Labels stay in the DOM
  for screen readers (visually hidden); `title` tooltips carry the text. Cerrar
  sits apart on the right edge and turns danger (red tint) on hover; edit-mode
  ON reads as a pressed mora accent state.
- **Specificity bugfix**: the `#edit-toggle/#export-json/#detail-collapse/#detail-close`
  id-level color rules silently beat every scoped hover/pressed state — the
  danger hover and the pressed accent never painted before. Removed.
- **Header chevron parity**: left and right panel headers both use 16px chevrons.

Out of scope (intentionally deferred):

- The detail panel title arriving as English "Node details" from the bundle
  (template says "Detalles del nodo") — pre-existing bundle behavior.
- Canvas node/edge rendering and search-select not auto-rendering the detail
  body (pre-existing selection flow).
- BRD / secret / pipeline panel internals.

## Live viewer

```powershell
uv run brain_ds ui .\tmp_sample_graph.json --output .\tmp\panel-fix.html
# open tmp\panel-fix.html — collapse the left panel with the header chevron
# (it should disappear COMPLETELY, no leftover strip), reopen it from any left
# rail icon, re-click the active icon to close it again; open the Inspector
# from the right rail, select a node, hover Cerrar (danger tint) and toggle
# Editar (pressed accent); switch themes and repeat.
```

## Static preview

- Session screenshots (repo root): `repro-baseline-right-collapsed.png` /
  `repro-baseline-both-collapsed.png` (before — note the floating chevron strip)
  vs `fix-iter1-load.png`, `fix-iter1-left-collapsed.png`,
  `fix-iter1-rail-reopen.png`, `fix-iter2-icon-toolbar.png`,
  `fix-iter2-node-selected.png`, `fix-iter2-light.png` (after).

## Section reference

- `ui-workspace-shell.md` (shell grid + surfaces)
- `section-1-left-shell.html` (left rail + panel header)
- `section-2-right-shell.html` (right rail + inspector header)
- `section-3-button-catalog.html` (44px icon button language the toolbar adopts)
