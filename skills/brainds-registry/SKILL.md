---
name: brainds-registry
description: |
  Keep the MCP grounding harness, skills, agent definitions, and CLAUDE.md in sync after any ontology, tool, or skill change.
  Trigger: after adding/renaming entity types, relationship types, MCP tools, or editing any SKILL.md
license: MIT
disable-model-invocation: true
metadata:
  author: sechi42
  version: "1.0.0"
---

# brain_ds Registry Skill

## When to Use

- After adding or renaming an `EntityType` in `brain_ds/ontology/entity_types.py`.
- After adding or renaming a `RelationshipType` in `brain_ds/ontology/relationship_types.py`.
- After adding, renaming, or removing an MCP tool in `brain_ds/mcp/tools.py` `TOOL_REGISTRY`.
- After adding or modifying a scoring factor in `brain_ds/scoring/engine.py`.
- After editing any `skills/*/SKILL.md` or `.opencode/skills/*/SKILL.md`.
- After creating a new agent definition in `.claude/agents/`.

## Harness Maintenance Checklist (MANDATORY)

Run every check that applies to your change type. Never skip a check silently.

### EntityType added or renamed

- [ ] Add a `QUESTION_BANK` entry in `brain_ds/mcp/grounding.py` for each new type (or add to `ELICIT_EXEMPT_TYPES` if the type is not elicited via interview).
- [ ] Add the type to `ELICIT_EXEMPT_TYPES` in `tests/test_grounding_drift_guard.py` if it is exempt — the drift guard goes red otherwise.
- [ ] For Data Source-internal types (`DataContainer`, `DataField`), verify they stay exempt from elicitation and completeness, and document that they are scoped under a Data Source rather than standalone domain entities.
- [ ] Review `NODE_WRITE_TEMPLATES` and `COMPLETENESS_MATRIX_TEMPLATE["dataset_fingerprint_order"]` in `grounding.py` — both reference entity names by string value.
- [ ] Update the entity table in `skills/elicit-context/SKILL.md` and `.opencode/skills/elicit-context/SKILL.md`.
- [ ] Update the Entity-Type Section Map in `skills/brainds-docs/SKILL.md` if the new type needs canonical card_sections.
- [ ] Update the CLAUDE.md tool inventory table if entity types affect BRD output sections.

### RelationshipType added or renamed

- [ ] Category-1 relationship context in `grounding.py` is enum-derived — verify it picks up the new value automatically (no code edit needed if the enum is correctly declared).
- [ ] Review `CONNECTION_RULES` prose in `grounding.py` — add a rule entry for the new relationship type if it adds a new connection pattern.
- [ ] Update edge label tables in `skills/map-connections/SKILL.md` and `.opencode/skills/map-connections/SKILL.md`.

### Scoring factor added or modified

- [ ] Confirm `build_scoring_factors` map in `brain_ds/scoring/engine.py` still reads correctly.
- [ ] Verify the map_connections grounding context still describes the scoring accurately — update `grounding.py` Category-2 constants if the factor name or weight changed.

### MCP tool added, renamed, or removed

- [ ] Update `TOOL_REGISTRY` in `brain_ds/mcp/tools.py`.
- [ ] Update the tool count assertion in any test file that pins the count (search for `assert len(tools) ==`).
- [ ] Update the **Tool inventory** table in `CLAUDE.md` (root of repo).
- [ ] If the tool count changed, update the verification checklist in `CLAUDE.md`: "Verify 17 tools appear" → correct number.
- [ ] Update AGENTS.md if the new tool affects agent workflows.

### Skill prose edited (SKILL.md)

- [ ] Update the corresponding Category-2 constants in `brain_ds/mcp/grounding.py` that mirror skill prose for non-Claude clients.
- [ ] Keep `skills/*/SKILL.md` and `.opencode/skills/*/SKILL.md` byte-identical — mirror the change immediately.
- [ ] Run `/share-brainds` to regenerate `skills/SHARED_CONTEXT.md`.
- [ ] Update compact rules in `.atl/skill-registry.md` for the affected skill.

## Critical Patterns

| Pattern | Rule |
|---------|------|
| Drift guard is truth | A red `test_grounding_drift_guard.py` means the harness needs updating — never suppress the test. |
| Same-change rule | Harness updates go in the SAME commit as the ontology/tool/skill change — never deferred. |
| Mirror symmetry | `skills/*/SKILL.md` and `.opencode/skills/*/SKILL.md` must be byte-identical at all times. |
| Tool count pin | Update the count in CLAUDE.md AND in any test assertion that pins it. |
| Enum-derived vs string-valued | Category-1 (RelationshipType context) is enum-derived; Category-2 (entity names, section labels) are string-valued and MUST be updated manually. |

## Quick Audit Command

```bash
# Verify drift guard passes after your change
uv run pytest tests/test_grounding_drift_guard.py -v

# Count registered MCP tools
uv run python -c "from brain_ds.mcp.tools import TOOL_REGISTRY; print(len(TOOL_REGISTRY))"

# Check skills mirror consistency
diff -r skills/ .opencode/skills/ --include="SKILL.md"
```

## Files to Update by Change Type

| Changed in | Must also update |
|---|---|
| `entity_types.py` | `grounding.py` QUESTION_BANK, drift guard ELICIT_EXEMPT_TYPES, both SKILL.md mirrors, brainds-docs entity map |
| `relationship_types.py` | `grounding.py` CONNECTION_RULES, map-connections SKILL.md (both mirrors) |
| `tools.py` TOOL_REGISTRY | `CLAUDE.md` tool count + inventory, test count assertion |
| `scoring/engine.py` | `grounding.py` Category-2 scoring constants |
| Any `SKILL.md` | `.opencode/skills/` mirror, `grounding.py` Category-2 if skill prose mirrored, `.atl/skill-registry.md` compact rules, `skills/SHARED_CONTEXT.md` |
| `.claude/agents/*.md` | `AGENTS.md` agent table, `.atl/skill-registry.md` if agent uses skills |
