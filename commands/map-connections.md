---
description: Build organization-scoped domain relationship map
agent: brain-ds-orchestrator
subtask: false
---

Run `/map-connections` for the resolved organization.

1. Resolve the organization graph, then read domain entities through brain_ds MCP (`list_nodes`, `search_graph`, and `suggest_connections`), not Engram.
2. Keep records scoped to the resolved org graph.
3. Produce read-only inline report by default.
4. Persist edges only when user explicitly requests `--save`.

Use the `map-connections` skill workflow.
