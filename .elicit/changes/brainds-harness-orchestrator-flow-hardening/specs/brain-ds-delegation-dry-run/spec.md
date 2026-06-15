# Delta for brain-ds-delegation-dry-run

> Slice 4 of `brainds-harness-orchestrator-flow-hardening`. Proves the
> harness end-to-end with a context-isolated multi-agent dry-run validated
> by sdd-verify.

## ADDED Requirements

### Requirement: context-isolated multi-agent dry-run

The brainds-orchestrator SHALL be able to launch the brain_ds sub-agents
(`brainds-source-explorer`, `brainds-graph-mapper`,
`brainds-connection-mapper`, `brainds-brd-writer`,
`brainds-query-consultant`) against a synthetic data source. Each
sub-agent MUST receive ONLY:

- A reference (path or topic key) to the artifacts it should produce.
- The path to the synthetic data source.

Each sub-agent MUST NOT receive: graph history, Engram domain data, or
unrelated files. Each sub-agent MUST write its outputs ONLY to `.elicit/`.

#### Scenario: a sub-agent receives no other context

- GIVEN the orchestrator is configured to launch `brainds-source-explorer`
  against a synthetic SQLite source
- WHEN the orchestrator hands off to the sub-agent
- THEN the sub-agent's prompt contains only: artifact references + the
  synthetic source path
- AND the sub-agent's prompt does NOT contain any other org graph history,
  Engram domain observation, or unrelated file content

#### Scenario: a sub-agent writes only to .elicit/

- GIVEN a sub-agent completes its run
- WHEN its run output is inspected for filesystem writes
- THEN every written file path is under `.elicit/`
- AND no file is written under any other directory (e.g. `brain_ds/`,
  `tests/`, repo root)

### Requirement: dry-run exercises the full cycle

The dry-run SHALL exercise, in order:

1. `list_source_connections` (against the synthetic source).
2. `explore_source` magnitude scan.
3. Sectioned documentation (hierarchy_template).
4. Map-connections (two-phase).
5. `generate-brd` where applicable.

The cycle MUST run on a synthetic SQLite fixture at
`tests/fixtures/synthetic_source.db` (or a builder-comparable path).

#### Scenario: a complete dry-run produces all expected .elicit/ files

- GIVEN the synthetic fixture exists and the orchestrator launches the
  full cycle
- WHEN the cycle completes
- THEN the `.elicit/` tree contains at least one file per phase:
  `elicit-*.md`, `source-exploration-*.md`, `source-docs-*.md`,
  `map-*.md`, and `brd-*.md`
- AND each file name matches the
  `<phase>-<org-slug>-<ISO-date>.md` pattern

### Requirement: sdd-verify validates .elicit/ output against harness specs

sdd-verify MUST inspect the `.elicit/` files produced by the dry-run and
assert that they comply with:

- (a) `brainds-docs` documentation format for the `source-docs` and `map`
  files (card_sections shape, icon presence, order discipline with BRD
  carve-out applied).
- (b) The completeness gate recommendation produced by
  `assess_completeness` (every dry-run cycle is followed by a recorded
  recommendation).
- (c) The BRD persistence contract (`order: 0`, `icon: ""`,
  `node_id = brd-<graph-id>`, `type = "Unknown"`) wherever a BRD is
  produced.
- (d) The `.elicit/` structure and naming from the lifecycle spec.

Any non-compliance SHALL be reported as a CRITICAL verify finding.

#### Scenario: a documented node passes brainds-docs format check

- GIVEN a `.elicit/source-docs-acme-2026-06-14.md` file in the dry-run
  output
- WHEN sdd-verify inspects it
- THEN every documented node has a `card_sections` array whose every
  entry has non-empty `title`, non-empty `content`, an `order` ≥ 1 (or the
  BRD carve-out applies), and an `icon` from the documented icon list (or
  `""` for BRD nodes)

#### Scenario: a non-compliant node is reported CRITICAL

- GIVEN a `.elicit/source-docs-acme-2026-06-14.md` file with a documented
  node whose `card_sections[0].order` is `0` and whose `type` is NOT
  `Unknown` (i.e. neither the BRD carve-out nor the generic rule
  applies)
- WHEN sdd-verify inspects the file
- THEN the verify report records a CRITICAL finding that names the file
  and the offending node

#### Scenario: BRD persistence contract is asserted when a BRD is produced

- GIVEN the dry-run produced a `.elicit/brd-acme-2026-06-14.md` file AND
  an associated `brd-<graph-id>` node
- WHEN sdd-verify inspects them
- THEN it asserts the node satisfies
  `node_id = "brd-<graph-id>"`, `label = "BRD"`, `type = "Unknown"`,
  `card_sections[0].order = 0`, and `card_sections[0].icon = ""`
- AND it asserts the BRD markdown contains wikilinks for every mentioned
  entity

#### Scenario: completeness gate is recorded

- GIVEN the dry-run cycle calls `assess_completeness` against the
  synthetic source's populated nodes
- WHEN sdd-verify inspects the dry-run output
- THEN it finds a recorded `assess_completeness` recommendation per cycle
  AND asserts the recommendation is one of `elicit`, `document`, or
  `proceed_with_gaps`
