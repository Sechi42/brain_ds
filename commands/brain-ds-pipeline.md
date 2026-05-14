---
description: Guide the full brain_ds elicitation-to-BRD pipeline
agent: brain-ds-orchestrator
subtask: false
---

Start the brain_ds orchestration pipeline.

1. Check Engram state for `org/*` context, map artifacts, and BRD readiness.
2. If no context exists, ask the user to run `/elicit-context` first.
3. If context exists but no map, guide the user to run `/map-connections`.
4. If map exists, guide the user to run `/generate-brd`.
5. After each step, validate state again and suggest the next command.

Never auto-delegate as sub-agents; keep the flow interactive and explicit.
