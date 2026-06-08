# brain_ds MCP for Claude Code

## Overview

`brain_ds` ships an MCP stdio server for graph knowledge operations. Protocol version is pinned to `2024-11-05`.

## Tool inventory

| Tool | Type | Description |
|---|---|---|
| `list_graphs` | data | List available graph metadata |
| `create_graph` | data | Create an empty graph/vault (non-destructive) |
| `import_graph` | data | Import graph JSON from a project-local file |
| `list_nodes` | data | List graph nodes with optional filters |
| `list_data_sources` | data | List only Data Source nodes for a graph |
| `get_node` | data | Get one node by id |
| `search_graph` | data | Search nodes by substring over label/type/details |
| `update_node` | data | Create/update node fields |
| `add_edge` | data | Create/update an edge between nodes |
| `run_elicit` | agent stub | Requires AI agent workflow |
| `map_connections` | agent stub | Requires AI agent workflow |
| `generate_brd` | agent stub | Requires AI agent workflow |

For MCP server internals and archive details, see `sdd/mcp-server/archive-report`.

## Setup

1. Print config (portable default, relative root):

```bash
brain_ds mcp print-config --project-root .
```

2. Print config with absolute root (use when IDE launch cwd differs):

```bash
brain_ds mcp print-config --project-root . --absolute
```

3. Paste the emitted `mcpServers` JSON block into project-local `.claude/settings.json`.

### Windows path check (safer launch)

Use this when Claude Code may start from a different folder.

- [ ] Generate config with absolute root:

```bash
brain_ds mcp print-config --project-root . --absolute
```

- [ ] If output still shows `"command": ".\\brain_ds.CMD"`, resolve the installed executable and use that absolute path in `command`:

```powershell
where.exe brain_ds
```

- [ ] Keep absolute project-root values in config (`args[2]` and `env.BRAIN_DS_PROJECT_ROOT`) — this is expected and correct.

- [ ] In Claude Code, run `/mcp` and confirm `brain_ds` is connected with **12 tools**.

Example output shape:

```json
{
  "mcpServers": {
    "brain_ds": {
      "type": "stdio",
      "command": "...",
      "args": ["mcp", "--project-root", "."],
      "env": {
        "BRAIN_DS_PROJECT_ROOT": "."
      }
    }
  }
}
```

## Verification

1. Open Claude Code at the project root.
2. Run `/mcp` and confirm `brain_ds` is connected.
3. Verify 12 tools appear.
4. Call `list_nodes` as a smoke check.

## Trade-offs

- Relative `--project-root .` is portable across machines and repo clones.
- `--absolute` is machine-specific but resilient when launch cwd is not project root.

## Security boundary

- `print-config` writes JSON to stdout only.
- It does not write `.claude/settings.json`.
- MCP server sandboxing and store path enforcement remain in `resolve_store_path`.

## Harness maintenance (MANDATORY)

The MCP grounding harness (`brain_ds/mcp/grounding.py`) is what gives any MCP
client the ontology/schema/workflow context for `run_elicit`, `map_connections`,
and `generate_brd`. It must stay in sync with the ontology and the skills.

Whenever you add or rename any of the following, you MUST update the harness in
the same change:

- **An `EntityType`** (`brain_ds/ontology/entity_types.py`): add a `QUESTION_BANK`
  entry in `grounding.py` (or, if it is not elicited, add it to
  `ELICIT_EXEMPT_TYPES` in `tests/test_grounding_drift_guard.py`); review the
  Category-2 constants that reference entity names by value (`NODE_WRITE_TEMPLATES`,
  `COMPLETENESS_MATRIX_TEMPLATE["dataset_fingerprint_order"]`).
- **A `RelationshipType`** (`brain_ds/ontology/relationship_types.py`): Category-1
  relationship context is enum-derived (no edit needed), but check
  `CONNECTION_RULES` prose in `grounding.py`.
- **A scoring factor** (`brain_ds/scoring/engine.py`): exposed via
  `build_scoring_factors`; confirm the map context still reads correctly.
- **An MCP tool** (`brain_ds/mcp/tools.py` `TOOL_REGISTRY`): update the tool count
  assertions and `CLAUDE.md` tool inventory.
- **Skill prose** (`skills/*/SKILL.md`): the Category-2 constants in `grounding.py`
  mirror this prose for non-Claude clients — update both, and keep
  `skills/*/SKILL.md` and `.opencode/skills/*/SKILL.md` consistent.

`tests/test_grounding_drift_guard.py` enforces the EntityType side of this: it
goes red if the ontology and `grounding.py` drift. Treat a red drift guard as
"the harness needs updating", not "the test is wrong".
