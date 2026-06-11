---
description: Guide mapping step after context elicitation
agent: brain-ds-orchestrator
subtask: false
---

Run mapping orchestration.

1. Verify that elicited context exists in the active organization graph via the brain_ds MCP (`list_nodes`, `search_graph`).
2. If missing, stop and ask the user to run `/elicit-context`.
3. If present, instruct the user to run `/map-connections`.
4. Validate map outputs and provide the next recommended action.

Do not invoke skills as sub-agents.
