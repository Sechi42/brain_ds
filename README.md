# brain_ds

Enterprise Data & Knowledge Mapper: an organizational context brain for AI agents.

## What this is

`brain_ds` helps teams map how knowledge moves across an organization: people, departments, data sources, tacit know-how, problems/improvement areas, decisions, and outcomes.
It is designed so agents can reason with business context instead of isolated prompts.

## Core brain storage

- **Engram** is used as the persistent storage brain.
- Knowledge is scoped by organization and domain paths so context stays separated and traceable.

## OpenCode commands and skills

Use these slash commands from OpenCode:

| Command | Purpose |
|---|---|
| `/elicit-context` | Capture and structure missing organizational context |
| `/map-connections` | Build a cross-entity map from stored organizational knowledge |
| `/map-connections --graph` | Same mapping flow, plus graph-oriented view/output |
| `/map-connections --graph-json` | Generate and save `<org>-graph.json` graph data contract |
| `/map-connections --graph-ui` | Generate graph JSON and auto-create interactive offline HTML viewer (default mode) |
| `/generate-brd` | Generate a BRD from the mapped knowledge base |

### Graph viewer quick start

- Default interactive offline viewer: `uv run brain_ds ui <org-graph.json>`
- Simple legacy fallback (PyVis): `uv run brain_ds ui <org-graph.json> --simple`
- Optional auto-open: `uv run brain_ds ui <org-graph.json> --open`
- Custom output path: `uv run brain_ds ui <org-graph.json> --output reports/viewer.html`
- Compatibility fallback still supported: `python -m brain_ds.ui <org-graph.json>`

#### Node detail cards (interactive viewer)

- The interactive panel is **read-only** and renders from `RENDER_CONTEXT.detail_index` (Python render-prep contract), not from browser-side derivation.
- Evidence appears as native `details/summary` blocks with provenance/source metadata when available.
- Relationship rationale is grouped by **incoming** and **outgoing** links and includes reasons/evidence IDs when present.
- Producer-first rule: generate structured `card_sections` + node `evidence_ids` + graph `evidence[]` during `/map-connections --graph-json` so the viewer can render complete node cards.

### Optional graph viewer dependency

- Interactive HTML generation is Python-only and offline by default (vendored local JS/CSS embedded into output HTML).
- `pyvis` is only required for `--simple` fallback mode.
- Install base project with: `uv sync`
- Enable `--simple` fallback dependency with: `uv sync --extra simple`
- If `pyvis` is unavailable, interactive default still works; only `--simple` fails with a dependency hint.

## Organization scoping model

- Scope commands with `--org <name|slug>` when needed.
- Store and reason over artifacts with paths like:
  - `org/<slug>/domain/...`

This keeps multi-organization work clean and avoids context bleeding.

## Supported entity types (current)

Source of truth: `brain_ds/ontology/entity_types.py` (`brain_ds.ontology.EntityType`).

- Organization
- Department
- Role
- Data Source
- Heuristic
- Tacit Knowledge
- Problem / Improvement Area
- Project
- Risk
- Decision
- KPI
- Solution

## Quick start (clone + one command install)

1. Clone this repository.
2. Install **OpenCode** (required) and **Git** (required).
3. Run one installer from repo root:
   - PowerShell: `./install-opencode.ps1`
   - Bash: `./install-opencode.sh`
4. Installer also runs `uv sync` automatically when `uv` is available to set up base Python deps.
5. If you plan to use `--simple`, run `uv sync --extra simple`.
6. If `uv` is missing, installer warns and continues. Install `uv`: https://docs.astral.sh/uv/getting-started/installation/
7. Optional but recommended: install **Engram** for persistent memory/knowledge mapping (installer warns if missing and continues).
8. Start with:
   - `/elicit-context`
   - `/map-connections`
   - `/generate-brd`

### Re-run behavior

- Safe to re-run anytime (idempotent).
- Generated bridge lives in `.opencode/skills/` (gitignored).
- Canonical source remains `skills/`; if you edit source skills, re-run installer to refresh bridge links/copies.

## Repository structure

| Path | Description |
|---|---|
| `skills/` | Project skills used by OpenCode workflows |
| `.atl/skill-registry.md` | Local skill registry and compact rules |

## Current status

- ✅ Core organizational mapping flow is in place
- ✅ BRD generation flow is available
- ✅ Engram-based persistent knowledge model is integrated

## Roadmap

- Next entity families: **Person**, **Event**, **Measurement**
- ✅ Interactive offline graph viewer (search, filter, legend, neighborhood highlight, layout controls)
