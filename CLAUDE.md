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
| `get_kpi_dossier` | data | Assemble a structured KPI dossier from graph lineage and limitations |
| `get_business_dossier` | data | Assemble a query-first business dossier; pending-question writes require `create_pending_questions=true` and never create edges |
| `search_graph` | data | Search nodes (FTS5 accent-insensitive + Python fallback) over label/type/details |
| `update_node` | data | Create/update node fields |
| `add_edge` | data | Create/update an edge between nodes |
| `delete_node` | data | Delete one node by id |
| `delete_edge` | data | Delete edges between source and target |
| `suggest_connections` | data | Rank compatible nodes for one node (connection RAG) |
| `assess_completeness` | data | Pre-mapping gate: missing/underspecified entity types + recommendation |
| `assess_currency` | data | Temporal currency coverage and criticality-ranked freshness gaps |
| `insert_pending_question` | data | Persist a deferred currency-elicitation question without resetting currency evidence |
| `get_weak_edges` | data | List edges with confidence below a cutoff (default 0.4) for audit |
| `snapshot_edges` | data | Read a bounded, retrieval-shaped edge snapshot for semantic verification |
| `list_source_connections` | connector | List Data Source nodes with explorable connection descriptors |
| `explore_source` | connector | Read-only exploration of a connected data source (describe/containers/tables/schema+preview) |
| `query_source` | connector | Execute a SELECT-only SQL query against an SQLite data source (capped at 200 rows) |
| `list_secret_handles` | secret | List workspace secret handles and redacted metadata (admin only) |
| `validate_secret_handle` | secret | Validate a workspace secret handle (dry-run by default; probe opt-in) |
| `list_workspaces` | workspace | List globally registered workspaces and mark the active one |
| `open_workspace` | workspace | Switch the active workspace to a registered project folder |
| `run_elicit` | grounding | Elicit grounding context + dual-persistence workflow |
| `map_connections` | grounding | Map grounding context + connection RAG workflow |
| `generate_brd` | grounding | BRD grounding context |
| `list_pending_confirmations` | data | List pending human-confirmation rows (latest per target, graph-wide) |
| `resolve_confirmation` | data | Resolve a pending confirmation by appending a human verdict row (append-only) |
| `retrieve_context` | data | Retrieve a reliability-annotated BFS subgraph centred on query anchors (FTS5 + optional cosine RRF + ledger join) |

For MCP server internals and archive details, see `sdd/mcp-server/archive-report`.

## Workspace scoping

- The MCP server resolves its project root with precedence `--project-root` → `BRAIN_DS_PROJECT_ROOT` → **session cwd**. The global OpenCode entry written by `install-opencode.ps1 -Global` pins nothing, so each session binds to the folder it was opened in.
- Every initialized workspace (via `brain_ds setup`, the desktop vault picker, or an MCP launch over an existing store) is registered in the global registry `~/.brain_ds/workspaces.json` (override dir with `BRAIN_DS_HOME`).
- Agents must follow `WORKSPACE_PROTOCOL` (attached to every grounding payload as `workspace`): operate only in the workspace matching the user's folder, switch with `open_workspace`, and ask the user when the target folder is not registered. `open_workspace` only accepts registered paths — that is the sandbox boundary for store switching.

## Setup

**Unified install guide: see `INSTALL.md`** (exe build, MCP config — interactive CLI wizard, one-shot command, or from the desktop vault picker — and harness verification).

Use `brain_ds setup`. It creates the local store if needed, writes absolute-root MCP configs, preserves unrelated config entries, and prints the next steps. Run it with no flags in a terminal for the interactive wizard. The desktop vault picker exposes the same engine via **Configurar MCP para este proyecto** (`POST /api/setup-mcp`).

### Quick path

1. Run setup once from the project root:

```bash
brain_ds setup --project-root . --agent both
```

2. Review the printed checklist:
   - rebuild/install the Windows exe
   - launch the exe and pick this folder
   - restart your agent client
   - approve `brain_ds` if prompted

3. In Claude Code, run `/mcp` and confirm `brain_ds` is connected with **33 tools**.

### What `brain_ds setup` guarantees

| Area | Behavior |
|---|---|
| Store alignment | Uses `Path.resolve()` so the desktop exe and external agent point at the same absolute project root |
| Store safety | Creates `.brain_ds/store.db` only when missing |
| Config safety | Backs up existing config before write and preserves unrelated MCP entries |
| Supported targets | Writes `.mcp.json`, `.opencode/opencode.json`, or both |
| Preview mode | `--dry-run` prints a diff preview and writes nothing |

### If you need a manual preview only

```bash
brain_ds setup --project-root . --agent both --dry-run
```

### Legacy low-level config output

`brain_ds mcp print-config` still exists for debugging or manual inspection.

```bash
brain_ds mcp print-config --project-root . --absolute
```

Example Claude output shape:

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

1. Run `brain_ds setup --project-root . --agent both`.
2. Open Claude Code at the project root.
3. Run `/mcp` and confirm `brain_ds` is connected.
4. Verify 33 tools appear.
5. Call `list_nodes` as a smoke check.
6. Live updates flow through the shared SQLite outbox path; MCP writes should reach the running UI without a manual config rewrite.

## Trade-offs

- `brain_ds setup` prefers absolute roots because the desktop exe canonicalizes the chosen folder before launching the UI.
- `brain_ds mcp print-config --project-root .` remains more portable, but it is easier to misalign with the desktop flow if launch cwd changes.

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

- **The UI BRD panel convention** (`brain_ds/ui/src/panels/brd-panel.ts` — node id
  `brd-{graphId}`, card_sections[0] `Contenido`): mirror any change in
  `BRD_GRAPH_PERSISTENCE_CONTRACT` (`grounding.py`), `skills/generate-brd/SKILL.md`
  (+ `.opencode` mirror), `.claude/agents/brainds-brd-writer.md`, and
  `prompts/brainds-brd-writer.md`. Guarded by
  `tests/test_mcp_grounding.py::test_brd_graph_persistence_contract_matches_ui_panel_convention`.
- **The delegation model** (orchestrator + sub-agents): `DELEGATION_PROTOCOL` in
  `grounding.py` is the cross-client source of truth; `.claude/agents/brainds-*.md`
  and `prompts/brainds-*.md` mirror it. Adding/renaming a sub-agent requires
  updating both installers (`install-opencode.ps1` / `.sh` task allowlist +
  subagent insertion), `brain_ds/harness_check.py` (`SUBAGENT_NAMES`,
  `CLAUDE_AGENT_FILES`), and `AGENT_FLOW.md`.

`tests/test_grounding_drift_guard.py` enforces the EntityType side of this: it
goes red if the ontology and `grounding.py` drift. Treat a red drift guard as
"the harness needs updating", not "the test is wrong".

`brain_ds check` verifies the installed harness (both clients, global + project)
stays aligned with the repo; `tests/test_harness_check.py` runs the repo-side
parity guards in CI.
