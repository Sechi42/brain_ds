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
