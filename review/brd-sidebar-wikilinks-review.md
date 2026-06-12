# BRD Sidebar Refresh + Obsidian Wikilinks — Review Checkpoint

## What to review

- **Wikilinks** (`.wikilink` in `graph_viewer.html`): internal links now render with an
  always-visible purple underline (`var(--accent-mora)`, 55% opacity) that strengthens to
  full color on hover with a soft purple background tint — Obsidian-style. Unresolved
  links keep their muted dashed style. Reduced-motion silences the transition.
- **BRD side panel freshness** (right rail, `data-rail-icon="brd"`):
  1. Re-activating the BRD rail icon now calls `refresh()` on the mounted panel, so a BRD
     pushed via MCP while the panel was hidden appears without reloading.
  2. While the page is open, live `node.created/updated/deleted` events for `brd-<graphId>`
     trigger an immediate panel refresh (wrapped `liveDataStore.applyEvent`).
  3. The panel mounts against the live data store (`getNodes()` / `getDetailIndex()`)
     instead of the page-load `RENDER_CONTEXT` snapshot.
- **Agent side**: the BRD writer contract now requires `[[wikilinks]]` for every graph
  entity mention (`BRD_GRAPH_PERSISTENCE_CONTRACT`, `skills/generate-brd/SKILL.md` + mirror,
  `.claude/agents/brainds-brd-writer.md`, `prompts/brainds-brd-writer.md`).

Out of scope (intentionally deferred): two-phase mapping UI, edge confidence display,
BRD `--strict` mode.

## Live viewer

```powershell
uv run python -m brain_ds ui tests\fixtures\graph_inputs\actor.json --output .\tmp\brd-sidebar-wikilinks-preview.html
```

To exercise the live-refresh path end to end: run the desktop UI over a workspace, then
`/generate-brd --save` from an MCP agent and watch the right-rail BRD panel update without
a reload.

## Static preview

- `tmp/brd-sidebar-wikilinks-preview.html` (already generated)

## Section reference

- `section-2-right-shell.html` (right rail + R-panel chrome)
