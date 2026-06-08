# AGENTS.md

Project: **brain_ds** — Enterprise Data & Knowledge Mapper.

## Quick Commands

| Command | Purpose |
|---|---|
| `/elicit-context` | Capture and structure missing organizational context |
| `/map-connections` | Build a cross-entity map from stored knowledge |
| `/generate-brd` | Generate a BRD from mapped organizational knowledge |

See `.atl/skill-registry.md` for compact rules and trigger resolution.

After `install-opencode.ps1` or `install-opencode.sh`, OpenCode auto-discovers project skills via `.opencode/skills/`.

## Harness maintenance

The MCP grounding harness (`brain_ds/mcp/grounding.py`) must stay in sync with the
ontology and skills. When you add/rename an `EntityType`, `RelationshipType`,
scoring factor, MCP tool, or skill prose, update the harness in the same change.
`tests/test_grounding_drift_guard.py` enforces the EntityType side. See the
"Harness maintenance" section in `CLAUDE.md` for the full checklist.
