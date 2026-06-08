# PR2 — Design System Pass Review Checkpoint

## What to review
- **Rail + toolbar + gear icons**: were solid-black blobs (sprite symbols had no paint), now Lucide line glyphs painted with the current text color. Selected rail icon = `--text-normal`; idle = `--text-muted` (~3.75:1 on `--bg-panel`, passes WCAG 1.4.11 3:1).
- **Detail-panel action bar** (Editar / Exportar JSON / Guardar / Collapse / Cerrar): each button sizes to its label, never wraps text inside ("Exportar JSON" was breaking to two lines); buttons wrap as whole units. All 44px tall.
- **"Vista gráfica" tab focus**: replaced the UA default blue focus square with a `--accent-mora` token ring (`:focus-visible`, inset offset).
- **Graph edges**: new `--edge-stroke: #7c828c` token at 1.5px / 0.85 opacity (was faint `--border-strong` rgba(63,63,70,0.7) at 1px) — connections clearly visible on the dark canvas.

## Out of scope (deferred)
- **Gear de-orphan** (right rail only holds the settings gear): layout restructure deferred — low priority, subjective.
- **Light theme**: the chrome has no `[data-theme="light"]` token overrides today (pre-existing; viewer is effectively dark-only). Not introduced here.
- **Node-spread / physics layout**: nodes still cluster when all scores are 0 (edges are short but visible). Layout tuning is separate.

## Live viewer
```powershell
python -m brain_ds.ui ui serve --project-root . --port 8765
# then open http://127.0.0.1:8765/  (loads tmp_sample_graph.json — 9 nodes / 9 edges)
```

## Section reference
- Icons / rail: `brain_ds/ui/design/sections/section-1-left-shell.html` (inline SVGs use `fill="none" stroke="currentColor" stroke-width="2"`).
- Buttons: `section-3-button-catalog.html`.
- Tabs / toolbar: `section-4-center-canvas.html`.

## Files changed (PR2)
- `brain_ds/ui/templates/graph_viewer.html` — icon paint rule, tab `:focus-visible`, action-bar no-wrap, `.d4-edge` → `--edge-stroke`.
- `brain_ds/ui/static/tokens.css` — added `--edge-stroke`.

## Tests
- `test_tokens_css`, `test_obsidian_palette_contrast`, `test_viewer`, `test_ts_modules` — all green (264 tests).
