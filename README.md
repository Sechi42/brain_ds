# brain_ds

Enterprise Data & Knowledge Mapper: an organizational context brain for AI agents.

## What this is

`brain_ds` helps teams map how knowledge moves across an organization: people, departments, data sources, tacit know-how, friction points, decisions, and outcomes.  
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
| `/generate-brd` | Generate a BRD from the mapped knowledge base |

## Organization scoping model

- Scope commands with `--org <name|slug>` when needed.
- Store and reason over artifacts with paths like:
  - `org/<slug>/domain/...`

This keeps multi-organization work clean and avoids context bleeding.

## Supported entity types (current)

- Organization
- Department
- Role
- Data Source
- Heuristic
- Tacit Knowledge
- UX Friction
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
4. Optional but recommended: install **Engram** for persistent memory/knowledge mapping (installer warns if missing and continues).
5. Start with:
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
- Later: **interactive UI** for exploration and graph navigation
