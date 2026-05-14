---
description: Generate a 14-section BRD from mapped knowledge
agent: brain-ds-orchestrator
subtask: false
---

Run `/generate-brd` for the resolved organization.

1. Read full Engram observations (no previews).
2. Keep org scoping consistent (no mixed prefixes).
3. Return read-only BRD by default.
4. Persist only when user explicitly requests `--save`.
5. Keep exactly 14 sections in required order.

Use the `generate-brd` skill workflow.
