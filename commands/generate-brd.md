---
description: Generate a 14-section BRD from mapped knowledge
agent: brain-ds-orchestrator
subtask: false
---

Run `/generate-brd` for the resolved organization.

1. Call the `generate_brd` MCP tool FIRST to load the grounding context (section order, rules, persistence contracts).
2. Resolve the organization graph, then read domain entities through brain_ds MCP typed retrieval (`list_nodes`), not Engram.
3. Keep org scoping consistent (no mixed graph IDs).
4. Return read-only BRD by default.
5. Persist only when user explicitly requests `--save` — then write BOTH stores: the graph node `brd-<slug>` via `update_node` (this is what makes the BRD visible in the brain_ds UI) AND the Engram mirror.
6. Keep exactly 14 sections in required order.

Use the `generate-brd` skill workflow.
