# Chrome Consistency + Color Legend + Hierarchy Map (2026-07-14) Review Checkpoint

## What to review

- **One selection language (mora)**: segmented controls (`Tipo/Cluster/Data Source`,
  `Jerárquico/Física`, label weights) now paint their active state with the same
  mora tint used by rail icons and toolbar `aria-pressed` — the white-fill outlier
  is gone. Sliders (umbral, grosor de aristas) are tokenized: mora thumb, quiet
  track, mono value badges (`.control-value-badge`) instead of inline styles.
- **Color legend fixed (root cause)**: `render_context` ships node colors as
  `{background, dark, light}`; `filter-panel.ts` still assigned that OBJECT to
  `style.background`, silently painting nothing. Swatches now resolve through the
  `--type-color-dark/light` custom-property pair (theme switches recolor via CSS,
  no re-render). LEYENDA rows show [dot] [type] [count] and dim when filtered out.
- **Canvas legend (identificador de colores)**: bottom-left `TIPOS` pill over the
  canvas expands a read-only list of every type with its color and count; rows dim
  while their type is hidden; state persists in localStorage; hidden in reader mode.
- **Mapa de jerarquía**: new toolbar button (list-tree icon, mode-switch group)
  opens a full-canvas tidy-tree overlay — depth columns N0..Nn with dashed guides,
  type-colored capsule chips, bezier connectors, meta line (raíces · niveles ·
  nodos · derivado de aristas). Prefers explicit `parent_id`; falls back to a BFS
  tree over directed edges (first parent wins, cycle-safe). Chip click selects the
  node in the canvas (inspector opens); ESC/X closes; reader mode auto-closes it.
- **Selection wipe bug (pre-existing) FIXED**: `selectAndReveal` queued a delayed
  null-render (deselect emission) that wiped the freshly rendered node detail —
  search/tree/projects selects showed the empty state. A generation token now
  invalidates stale delayed renders; `focusNode` bumps it.
- **Inspector color dot**: now resolves from the node's ontology color payload
  (was stuck on mora); theme-aware via the same `--type-color-*` pair.
- **Right panel normalization**: accordion summaries use the panel-card-title
  voice (11px uppercase muted); duplicated headings (`Acciones IA` ×3, Pipeline
  ×4) are sr-only'd; pipeline stage rows flattened (name + status chip, Spanish
  labels, `Solo lectura`); secret panel flattened (no floating card), lifecycle
  buttons in Spanish (`Validar vínculo` / `Desvincular fuente`); BRD `Crear BRD
  vacío` no longer stretches (pill-btn flex:1 pinned in column context).
- **Overflow menu**: icons (rotate-ccw / download / sun) + Spanish labels.
- **Proyectos / árbol**: type color dots on group summaries, member rows and tree
  rows; tree toggles use rotating Lucide chevrons instead of text arrows.

Out of scope (intentionally deferred):

- Ontology color VALUES (e.g. Organization #111827 near-invisible on dark canvas)
  — chips compensate with a hairline ring; changing entity colors is a data
  decision.
- Status vocabulary inside lifecycle badges (`binding state: unbound` …) — shared
  technical contract with the detail panel, kept in English in both.
- BRD/markdown reader internals.

## Live viewer

```powershell
uv run brain_ds ui .\tmp_sample_graph.json --output .\tmp\chrome-consistency.html
# open tmp\chrome-consistency.html —
#  1) check the TIPOS legend bottom-left (collapse/expand, colors match nodes);
#  2) open the hierarchy map from the toolbar (list-tree icon), click a chip,
#     confirm the node selects in the canvas with its type-colored dot in the
#     inspector title;
#  3) sweep the left rail sections: segmented actives are mora, sliders mora,
#     filters/leyenda/árbol/proyectos rows share the flat row + color dot DNA;
#  4) right rail: pipeline rows flat with Spanish chips, settings flat + Spanish;
#  5) toggle theme and repeat.
```

## Static preview

- Session screenshots (repo root): `audit-*.png` (before) vs `iter1-*.png`,
  `iter2-*.png`, `iter3-*.png` (after — dark/light, hierarchy map, legend,
  flattened right panels).

## Section reference

- `ui-workspace-shell.md` (flat shells + floating center card)
- `section-3-button-catalog.html` (mora pressed language, 44px targets)
- `section-1-left-shell.html` / `section-2-right-shell.html` (panel headers,
  section title voice)
