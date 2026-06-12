# AGENTS.md

Project: **brain_ds** — Enterprise Data & Knowledge Mapper.

## Quick Commands

| Command | Purpose |
|---|---|
| `/elicit-context` | Capture and structure missing organizational context |
| `/map-connections` | Build a cross-entity map from stored knowledge |
| `/generate-brd` | Generate a BRD from mapped organizational knowledge |
| `/share-brainds` | Regenerate `skills/SHARED_CONTEXT.md` skill index |
| `/brainds-docs` | Write or update node documentation and card_sections |
| `/brainds-registry` | Audit harness sync after ontology/tool/skill changes |

See `.atl/skill-registry.md` for compact rules and trigger resolution.

After `install-opencode.ps1` or `install-opencode.sh`, OpenCode auto-discovers project skills via `.opencode/skills/`.

## Skills

| Skill | Purpose | Path |
|---|---|---|
| `elicit-context` | Structured domain knowledge interview | [SKILL.md](skills/elicit-context/SKILL.md) |
| `generate-brd` | 14-section BRD from SQLite domain entities | [SKILL.md](skills/generate-brd/SKILL.md) |
| `map-connections` | Cross-entity relationship map and graph export | [SKILL.md](skills/map-connections/SKILL.md) |
| `share-brainds` | Regenerate SHARED_CONTEXT.md skill index | [SKILL.md](skills/share-brainds/SKILL.md) |
| `brainds-docs` | Node documentation and card_sections authoring | [SKILL.md](skills/brainds-docs/SKILL.md) |
| `brainds-registry` | Harness/ontology/tool sync audit checklist | [SKILL.md](skills/brainds-registry/SKILL.md) |

See `skills/SHARED_CONTEXT.md` for one-paragraph summaries of every skill.

## Agent Definitions

| Agent | Model | Purpose | Path |
|---|---|---|---|
| `brainds-query-consultant` | sonnet | Read-only graph Q&A — answers questions about nodes, data sources, owners | [.claude/agents/brainds-query-consultant.md](.claude/agents/brainds-query-consultant.md) |
| `brainds-source-explorer` | sonnet | Read-only external source exploration (Google Sheets, CSV, SQLite) | [.claude/agents/brainds-source-explorer.md](.claude/agents/brainds-source-explorer.md) |
| `brainds-orchestrator` | opus | Coordinates full elicit → map → BRD workflow; delegates to sub-agents | [.claude/agents/brainds-orchestrator.md](.claude/agents/brainds-orchestrator.md) |

## Harness maintenance

The MCP grounding harness (`brain_ds/mcp/grounding.py`) must stay in sync with the
ontology and skills. When you add/rename an `EntityType`, `RelationshipType`,
scoring factor, MCP tool, or skill prose, update the harness in the same change.
`tests/test_grounding_drift_guard.py` enforces the EntityType side. See the
"Harness maintenance" section in `CLAUDE.md` for the full checklist.

Run `/brainds-registry` after any such change to get a targeted checklist of files to update.
