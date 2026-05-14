---
description: Build organization-scoped domain relationship map
agent: brain-ds-orchestrator
subtask: false
---

Run `/map-connections` for the resolved organization.

1. Read full Engram observations (no previews).
2. Keep records scoped to the resolved org.
3. Produce read-only inline report by default.
4. Persist only when user explicitly requests `--save`.

Use the `map-connections` skill workflow.
