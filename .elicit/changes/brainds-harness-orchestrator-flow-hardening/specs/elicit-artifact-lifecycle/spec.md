# Delta for elicit-artifact-lifecycle

> Slice 2 of `brainds-harness-orchestrator-flow-hardening`. Formalizes the
> `.elicit/` artifact store, the SDD flow document, and the agent-registry
> sync.

## ADDED Requirements

### Requirement: .elicit/ structure mirrors DELEGATION_PROTOCOL.artifact_keys

The `.elicit/` store MUST follow a layout whose phases and naming come
directly from `DELEGATION_PROTOCOL.artifact_keys`. The documented phases
SHALL be exactly: `elicit`, `source-exploration`, `source-docs`, `map`, and
`brd`. A `.elicit/` artifact file SHALL match the pattern
`.elicit/<phase>-<org-slug>-<ISO-date>.md` (active cycle) and SHALL move
under `.elicit/changes/<change-name>/` once its cycle is archived.

#### Scenario: an active-cycle artifact matches the naming pattern

- GIVEN a phase `source-exploration` runs for org slug `acme` on
  `2026-06-14`
- WHEN the artifact is written
- THEN the file path is `.elicit/source-exploration-acme-2026-06-14.md`
  (active cycle) OR
  `.elicit/changes/<change-name>/source-exploration-acme-2026-06-14.md`
  (archived cycle)

#### Scenario: an out-of-pattern filename is rejected by the lifecycle test

- GIVEN the `.elicit/` lifecycle test is registered
- WHEN a file is created under `.elicit/` whose name does not match
  `<phase>-<org-slug>-<ISO-date>.md` for an allowed phase
- THEN the lifecycle test fails and names the offending file

### Requirement: per-sub-agent write ownership

A documented table MUST map each `.elicit/` phase to the single brain_ds
sub-agent that writes it. The mapping MUST be consistent with
`AGENT_FLOW.md` and with `DELEGATION_PROTOCOL.artifact_keys`.

The mapping SHALL be:

| phase | owner sub-agent |
|---|---|
| `elicit` | `brainds-orchestrator` |
| `source-exploration` | `brainds-source-explorer` |
| `source-docs` | `brainds-source-explorer` |
| `map` | `brainds-connection-mapper` (with input from `brainds-graph-mapper`) |
| `brd` | `brainds-brd-writer` |

#### Scenario: ownership table is consistent with AGENT_FLOW.md

- GIVEN the lifecycle document exists
- WHEN it is parsed for the per-phase owner column
- THEN every owner is the name of a sub-agent documented in `AGENT_FLOW.md`
- AND no `.elicit/` phase is listed without an owner

### Requirement: archive lifecycle for completed cycles

A completed brain_ds cycle MUST be archived by moving its `.elicit/`
artifacts under `.elicit/changes/<change-name>/`. A documented procedure
SHALL specify the move operation and the conditions under which a cycle is
considered "completed" (BRD written OR explicit cycle-closure by the
orchestrator).

#### Scenario: archive move preserves the file name

- GIVEN an active cycle file `.elicit/elicit-acme-2026-06-14.md`
- WHEN the cycle is archived under change name `acme-onboard`
- THEN the file exists at
  `.elicit/changes/acme-onboard/elicit-acme-2026-06-14.md` with identical
  bytes
- AND the original path no longer contains the file

### Requirement: flow document grounded in DELEGATION_PROTOCOL

A flow document (proposed path `docs/SDD_FLOW.md`) MUST describe the SDD /
orchestration flow in human-readable form, grounded in and consistent with
the constants in `DELEGATION_PROTOCOL` (`role`, `session_setup`,
`artifact_keys`, `handoff_rule`, `source_exploration_flow`, `skill_scope`).
A guard test MUST assert that the document references each of those
constants by name.

#### Scenario: flow document references every required constant

- GIVEN the flow document exists
- WHEN it is scanned for the strings `role`, `session_setup`,
  `artifact_keys`, `handoff_rule`, `source_exploration_flow`, and
  `skill_scope`
- THEN each string appears at least once in the document

### Requirement: skill-registry lists all 6 brain_ds sub-agents

`.atl/skill-registry.md` MUST document all 6 brain_ds sub-agents:
`brainds-orchestrator`, `brainds-source-explorer`,
`brainds-query-consultant`, `brainds-graph-mapper`,
`brainds-connection-mapper`, and `brainds-brd-writer`. A guard test MUST
assert that each of these names appears in the registry.

#### Scenario: registry names match AGENT_FLOW.md

- GIVEN `.atl/skill-registry.md` and `AGENT_FLOW.md` exist
- WHEN both are scanned for the six required agent names
- THEN each of the six names appears in BOTH files
- AND the registry's Agent Definitions table has at least six rows
