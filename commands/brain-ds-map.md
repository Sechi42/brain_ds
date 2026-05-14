---
description: Guide mapping step after context elicitation
agent: brain-ds-orchestrator
subtask: false
---

Run mapping orchestration.

1. Verify that elicited context exists in Engram (`org/*/domain/...`).
2. If missing, stop and ask the user to run `/elicit-context`.
3. If present, instruct the user to run `/map-connections`.
4. Validate map outputs and provide the next recommended action.

Do not invoke skills as sub-agents.
