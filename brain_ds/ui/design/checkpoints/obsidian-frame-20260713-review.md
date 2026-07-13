# Obsidian Workspace Frame + Chrome Consistency (2026-07-13) Review Checkpoint

## What to review

- **Obsidian-style frame (encuadre)**: the center column (tab strip + toolbar + canvas)
  now floats as a rounded card (`--radius-workspace: 12px`, `--workspace-gap: 8px`,
  hairline `--border-subtle`, `--shadow-xs`) over a flat `--bg-main` shell. Rails and
  side panels sit flat on the base surface with no hard borders — separation comes
  from the frame gap, not lines.
- **Unified panel headers**: "Proyectos" (left) and "Inspector" (right) now share ONE
  `.panel-header` rule — 44px, 13px / semibold / `--text-normal`, `padding: 0 8px 0 16px`,
  accent-tinted title icon. Previously the right header was 0.85rem/650/`--text-bright`
  with different padding.
- **Unified rail selected states**: both rails use the same pattern (mora tint + edge
  indicator bar). The per-icon colored variants (inspector purple / AI-actions green
  with inset box-shadow ring) were removed.
- **Low-contrast cleanup**: the hardcoded `-10px 0 20px rgba(0,0,0,0.3)` drop shadow on
  the right shell is gone; panel bodies (`.controls`, `.detail-panel`) are transparent
  over the flat sidebar surface; inspector density tightened (16px padding/gap).
- **Overflow fixes**: `.panel-card` grid column is `minmax(0, 1fr)` and `.segment-btn`
  ellipsizes, so the "Tipo | Cluster | Data Source" segmented control no longer
  overflows the left panel edge.

Out of scope (intentionally deferred):

- Canvas node/edge rendering (untouched this pass).
- BRD / secret / pipeline panel internals (they inherit the flat shell only).
- Tauri window chrome and the `system-chrome` toolbar zone (still reserved, unpainted).

## Live viewer

```powershell
uv run brain_ds ui .\tmp_sample_graph.json --output .\tmp\obsidian-frame.html
# open tmp\obsidian-frame.html — toggle theme, open the Inspector rail icon,
# select the "Operations" node, collapse/expand both panels, resize the window
```

## Static preview

- Session screenshots (repo root): `ui-frame-baseline-dark.png` (before) vs
  `ui-frame-dark-inspector.png`, `ui-frame-dark-selected.png`, `ui-frame-light.png` (after).

## Section reference

- `ui-workspace-shell.md` (shell grid + surfaces)
- `section-1-left-shell.html` (left rail + panel header)
- `section-2-right-shell.html` (right rail + inspector header)

## Token changes (canonical `brain_ds/ui/static/tokens.css`)

- `--radius-workspace`: `0px` → `12px` (activates the frame)
- `--workspace-gap`: new, `8px` (frame gutter around the center card)
