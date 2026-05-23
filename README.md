# Brain DS (Data & Knowledge Mapper)

![brain_ds_logo](assets/images/brain_ds_logo.png)

Enterprise Data & Knowledge Mapper: an organizational context brain for AI agents.

## What this is

`brain_ds` helps teams map how knowledge moves across an organization: people, departments, data sources, tacit know-how, problems/improvement areas, decisions, and outcomes.
It is designed so agents can reason with business context instead of isolated prompts.

![brain_ds_AQTT](assets/images/brain_ds_AQTT.png)

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
| `/brain-ds-pipeline` | Orchestrate full `/elicit-context` → `/map-connections` → `/generate-brd` flow |
| `/brain-ds-map` | Orchestrate mapping step with context checks |
| `/brain-ds-brd` | Orchestrate BRD step with map checks |

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

## Quick Start — From zero to first BRD

This section is a **literal walkthrough** — the order matters, and each step explains what's happening behind the scenes so you understand the system, not just the commands.

### Prerequisites

Before anything works, you need three things:

| What | Why you need it | Install link |
|------|----------------|--------------|
| **Git** | Clone the repo and manage changes | https://git-scm.com/downloads |
| **OpenCode** | The AI terminal where slash commands (`/elicit-context`, etc.) run. This is NOT a plugin — it's an AI coding terminal that supports agent skills and MCP tools. | https://opencode.ai |
| **Engram** (optional) | Persistent memory backend. brain_ds uses it for entity observations, session history, and knowledge recall across sessions. Without it, you lose cross-session memory — but the MCP graph store (SQLite) still works. **Install it if you want memory that persists across sessions.** | https://engram.shechi.com |
| **uv** (recommended) | Python package manager for the graph viewer (`/map-connections --graph-ui`). Optional but useful. | https://docs.astral.sh/uv/getting-started/installation/ |

### Step 1 — Clone and install project skills

```bash
git clone <repo-url>
cd brain_ds
```

Run the installer to wire up OpenCode skills:

- **PowerShell**: `./install-opencode.ps1 -Project -Agent`
- **Bash**: `./install-opencode.sh --project --agent`

This copies the project skills (`skills/elicit-context/`, `skills/map-connections/`, `skills/generate-brd/`) into `.opencode/skills/` so OpenCode can discover them. It also runs `uv sync` if `uv` is available.

### Step 2 — Configure the brain_ds MCP server

brain_ds has a Python MCP server that provides 6 data tools (`list_graphs`, `list_nodes`, `search_graph`, `get_node`, `update_node`, `add_edge`) plus 3 workflow stubs. OpenCode needs to know about it.

In your OpenCode configuration, add an MCP entry pointing to:

```json
{
  "mcpServers": {
    "brain_ds": {
      "command": "uv",
      "args": ["run", "python", "-m", "brain_ds.mcp.server"]
    }
  }
}
```

Without this, slash commands will look like they do nothing because the MCP tools powering them won't respond.

### Step 3 — Verify everything works

Open OpenCode inside the `brain_ds` directory and type:

```
/elicit-context
```

If the skills and MCP are wired correctly, you'll see me (the orchestrator) start an interactive interview — asking one question at a time about your organization.

If nothing happens or you get an error:
- Check that Engram is running (`engram doctor`)
- Check that the MCP server is listed in OpenCode's connected tools
- Run `uv sync` to make sure Python dependencies are installed

### Step 4 — How the pipeline actually works (the real flow)

This is the part that's **not obvious from reading the code**. The three commands MUST run in order, and each one is an interactive conversation with the orchestrator, not a silent batch job.

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  /elicit-context                                         │
│  ───────────────                                         │
│  I ask you questions about your organization,             │
│  one at a time, max 5 per session.                       │
│  You answer. I save structured observations to Engram.    │
│  Entity types captured: Department, Role, Data Source,    │
│  Heuristic, Tacit Knowledge, Problem/Improvement Area,   │
│  KPI, Solution, Decision, Organization.                  │
│                                                         │
│  When done, I call the MCP stub `run_elicit`             │
│  (this is just a hook — the real work is in Engram).    │
│                                                         │
│  ─────────────────────────────────────────────────       │
│                                                         │
│  /map-connections                                        │
│  ───────────────                                         │
│  I query Engram with 12 parallel searches.               │
│  I fetch EVERY full observation (no previews).           │
│  I tokenize and score connections by overlap rules.      │
│  I produce a report with:                                │
│    - Entity Table                                        │
│    - Information Flows (Role → Data Source)              │
│    - Overlaps (shared operational contexts)              │
│    - Broken Links (references to things not found)       │
│    - Missing Knowledge (entity types with no data)       │
│    - DS Intervention Opportunities                      │
│    - Provenance Table                                    │
│                                                         │
│  You can also use --graph (Mermaid) or --graph-json      │
│  (JSON data contract, feedable to the Python viewer).    │
│  --save persists the report to Engram.                   │
│                                                         │
│  I call the MCP stub `map_connections` at the end.       │
│                                                         │
│  ─────────────────────────────────────────────────       │
│                                                         │
│  /generate-brd                                           │
│  ───────────────                                         │
│  I retrieve everything from Engram again.                │
│  I build a 14-section Business Requirements Document:    │
│    1. Header          8. ADR Log                         │
│    2. Executive Summ  9. Data Provenance                 │
│    3. Current State   10. Risk Register                  │
│    4. Requirements    11. Cross-Dept Overlap Map         │
│    5. Data Sources    12. Project Portfolio              │
│    6. Stakeholder     13. KPI Dashboard                  │
│    7. Solution Opts   14. Improvement Roadmap            │
│                                                         │
│  The ADR is ALWAYS saved to Engram (architecture record).│
│  The BRD is only saved if you add --save.                │
│  I call the MCP stub `generate_brd` at the end.          │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Key insight**: The 3 MCP stubs (`run_elicit`, `map_connections`, `generate_brd`) are NOT entry points. They're **sentinel hooks** that I call at the end of each skill workflow. All the real work happens through:
- `mem_save` / `mem_search` / `mem_get_observation` (Engram tools)
- `brain_ds_list_nodes` / `brain_ds_update_node` / `brain_ds_add_edge` (MCP data tools)
- The orchestrator's multi-step workflows defined in the skill files

### Step 5 — Visualize your graph (optional)

After running `/map-connections --graph-json`, you'll get a `<org-name>-graph.json` file. To view it:

```bash
uv run brain_ds ui <org-name>-graph.json
```

This generates a standalone HTML file with an interactive node graph (search, filter, legend, neighborhood highlight, layout controls). No server needed — the HTML is fully offline.

You can also run the full pipeline in one go:
```bash
/map-connections --graph-ui
```
This generates the JSON, creates the HTML viewer, and opens it.

## Invoking brain_ds

You can keep using `uv run brain_ds ...`, or use repo-root wrappers:

- Bash: `./brain_ds.sh ui org-graph.json`
- CMD: `brain_ds.cmd ui org-graph.json`
- PowerShell: `./brain_ds.ps1 ui org-graph.json`

Optional PATH registration via installers:

- PowerShell: `./install-opencode.ps1 -RegisterPath`
- Bash: `./install-opencode.sh --register-path`

This copies wrapper scripts to `~/.config/opencode/bin/` so you can invoke them globally once that directory is on your `PATH`.

## Repository structure

| Path | Description |
|---|---|
| `skills/` | Project skills used by OpenCode workflows |
| `.atl/skill-registry.md` | Local skill registry and compact rules |
