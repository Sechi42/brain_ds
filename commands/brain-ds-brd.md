---
description: Guide BRD generation after mapping is complete
agent: brain-ds-orchestrator
subtask: false
---

Run BRD orchestration.

1. Verify that mapping outputs exist for the active org via the brain_ds MCP (not Engram).
2. If mapping is missing, ask the user to run `/map-connections` first.
3. If mapping is ready, instruct the user to run `/generate-brd`.
4. Confirm BRD completion and summarize any remaining gaps.

Keep the workflow interactive and manual.
