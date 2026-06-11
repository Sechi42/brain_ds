---
description: Guide the full brain_ds elicitation-to-BRD pipeline
agent: brain-ds-orchestrator
subtask: false
---

Start the brain_ds orchestration pipeline.

1. Resolve the active organization graph through the brain_ds MCP (do NOT read from Engram for domain entities).
2. If no context exists, ask the user to run `/elicit-context` first.
3. If context exists but no map, guide the user to run `/map-connections`.
4. If map exists, guide the user to run `/generate-brd`.
5. After each step, validate state via the MCP (not Engram) and suggest the next command.

Never auto-delegate as sub-agents; keep the flow interactive and explicit.
