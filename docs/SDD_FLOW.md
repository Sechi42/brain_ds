# brain_ds SDD orchestration flow

This is the human-readable flow for brain_ds. The orchestrator coordinates the cycle, sub-agents write phase artifacts into `.elicit/`, and the contract stays grounded in `DELEGATION_PROTOCOL`: `role`, `session_setup`, `artifact_keys`, `handoff_rule`, `source_exploration_flow`, `skill_scope`, `pipeline_stages`, and `intake_paths`.

## Quick path

1. Start with `session_setup` and choose the artifact store.
2. Follow `pipeline_stages` in order: **setup → intake → map → brd → verify → archive**.
3. At the `intake` stage, branch on `intake_paths`: `datasource` path uses `brainds-source-explorer` + `brainds-graph-mapper`; `human_org` path uses `brainds-orchestrator` + `brainds-graph-mapper`.
4. Run the sub-agent sequence using reference-only handoffs from `handoff_rule`.
5. Persist phase outputs using `artifact_keys`, run the `verify` gate, then archive when the gate passes.

## Pipeline stages (`pipeline_stages`)

The `pipeline_stages` key in `DELEGATION_PROTOCOL` is a flat ordered list of six stages:

| Stage | Agents | Notes |
|---|---|---|
| `setup` | `brainds-orchestrator` | Resolve org graph, artifact store, workspace. |
| `intake` | `brainds-source-explorer`, `brainds-graph-mapper` | Branches via `intake_paths`. |
| `map` | `brainds-connection-mapper` | Two-phase structural + cross-cutting. |
| `brd` | `brainds-brd-writer` | 14-section BRD; persist graph node + Engram. |
| `verify` | `brainds-orchestrator` | Compliance gate; writes `verify-<slug>-<date>.md`. |
| `archive` | `brainds-orchestrator` | Moves artifacts to `.elicit/changes/<change-name>/` only when `verify` passes. |

### Intake branching (`intake_paths`)

The `intake_paths` key describes two paths through the `intake` stage:

- **`datasource`**: a Data Source node exists and needs direct exploration → `brainds-source-explorer` (SCOPE + DOCUMENT) then `brainds-graph-mapper` (CONSOLIDATE + PUSH).
- **`human_org`**: knowledge comes from user interview rather than a live source → `brainds-orchestrator` (elicit interview) then `brainds-graph-mapper` (push to graph).

## Protocol key reference

| Protocol key | How the flow uses it |
|---|---|
| `role` | Keeps the orchestrator as coordinator and keeps execution work inside the named sub-agents. |
| `session_setup` | Resolves graph, organization, and artifact store before work starts. |
| `artifact_keys` | Defines the `.elicit/<phase>-<org-slug>-<ISO-date>.md` naming contract. |
| `handoff_rule` | Passes references to artifacts, never large copied content. |
| `source_exploration_flow` | Splits source work into scope, plan, document, and consolidate/push stages. |
| `skill_scope` | Restricts the flow to brain_ds domain skills and avoids unrelated global skills. |
| `pipeline_stages` | Ordered list of the six pipeline stages with agents and descriptions. |
| `intake_paths` | Two branching paths through the `intake` stage: `datasource` and `human_org`. |

## `.elicit/` phase ownership

| Phase | Owner sub-agent |
|---|---|
| `elicit` | `brainds-orchestrator` |
| `source-exploration` | `brainds-source-explorer` |
| `source-docs` | `brainds-source-explorer` |
| `map` | `brainds-connection-mapper` |
| `brd` | `brainds-brd-writer` |
| `verify` | `brainds-orchestrator` |
| `archive` | `brainds-orchestrator` |

## Sequence

```text
user
  -> brainds-orchestrator (`role`)
  -> session_setup: choose graph + artifact store
  -> [intake] branch on intake_paths:
       datasource path: brainds-source-explorer (SCOPE/DOCUMENT)
                        brainds-graph-mapper (CONSOLIDATE+PUSH)
       human_org path:  brainds-orchestrator (elicit interview)
                        brainds-graph-mapper (push to graph)
  -> brainds-connection-mapper (map stage: structural + cross-cutting)
  -> brainds-brd-writer (brd stage: 14-section BRD + persist)
  -> brainds-orchestrator (verify stage: compliance gate)
  -> brainds-orchestrator (archive stage: move artifacts if verify passes)
```

## Archive lifecycle

When the cycle ends, the `archive` stage moves all active-cycle files from `.elicit/` into `.elicit/changes/<change-name>/`. The move is byte-identical. Completion requires the `verify` gate to have passed — archive is blocked on a failing `verify`.

## Checklist

- [ ] The doc references `role`, `session_setup`, `artifact_keys`, `handoff_rule`, `source_exploration_flow`, `skill_scope`, `pipeline_stages`, and `intake_paths`.
- [ ] The phase-owner table matches `.elicit/README.md`.
- [ ] The archive lifecycle points to `.elicit/changes/<change-name>/`.
- [ ] The verify gate is shown as blocking the archive stage.

## Next step

Use `.elicit/README.md` when creating or archiving lifecycle artifacts.
