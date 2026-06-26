# AGENTS.md

Project: **brain_ds** — Enterprise Data & Knowledge Mapper.

## Quick Commands

| Command | Purpose |
|---|---|
| `/elicit-context` | Capture and structure missing organizational context |
| `source-docs dry-run` | Run the recon/plan dry-run recipe without graph writes |
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
| `brainds-source-explorer` | sonnet | Read-only source recon and sectioned documentation; emits the scoped 5-section pipeline artifact contract | [.claude/agents/brainds-source-explorer.md](.claude/agents/brainds-source-explorer.md) |
| `brainds-graph-mapper` | sonnet | Consolidates pipeline artifacts and pushes the documented source into the graph | [.claude/agents/brainds-graph-mapper.md](.claude/agents/brainds-graph-mapper.md) |
| `brainds-connection-mapper` | sonnet | Runs the connection-mapping pass with completeness gating and deferred weak links | [.claude/agents/brainds-connection-mapper.md](.claude/agents/brainds-connection-mapper.md) |
| `brainds-brd-writer` | sonnet | Builds the deterministic BRD and persists it to the graph and Engram | [.claude/agents/brainds-brd-writer.md](.claude/agents/brainds-brd-writer.md) |
| `brainds-currency-elicitor` | sonnet | Runs Brick-E currency elicitation from assess_currency/retrieve_context and defers stakeholder questions through insert_pending_question | [.claude/agents/brainds-currency-elicitor.md](.claude/agents/brainds-currency-elicitor.md) |
| `brainds-orchestrator` | opus | Coordinates elicit → source-docs → map → BRD and owns the dry-run recipe | [.claude/agents/brainds-orchestrator.md](.claude/agents/brainds-orchestrator.md) |

## Harness maintenance

The MCP grounding harness (`brain_ds/mcp/grounding.py`) must stay in sync with the
ontology and skills. When you add/rename an `EntityType`, `RelationshipType`,
scoring factor, MCP tool, or skill prose, update the harness in the same change.
`tests/test_grounding_drift_guard.py` enforces the EntityType side. See the
"Harness maintenance" section in `CLAUDE.md` for the full checklist.

Source-documentation pipeline artifacts use the scoped 5-section DELIVERABLE_CONTRACT, but BRD and map canonical outputs keep their own contracts.

Run `/brainds-registry` after any such change to get a targeted checklist of files to update.
