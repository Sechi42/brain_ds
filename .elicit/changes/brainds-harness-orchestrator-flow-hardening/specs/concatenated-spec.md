# Spec: brain_ds Harness / Orchestrator Flow Hardening

> Hybrid store: this Engram topic + the 5 domain spec files under
> `.elicit/changes/brainds-harness-orchestrator-flow-hardening/specs/`.
> Reads proposal v2 (#2119) and design (#2120). Preserves the 4 reviewable
> slices and exposes them as 5 domain specs.

This artifact is the **concatenated mirror**. The 5 domain files are the
authoritative spec; this mirror exists for cross-session recovery.

---

## Domain 1 — `brd-persistence-contract` (Slice 1)

### Requirement: BRD Graph Persistence Contract

When the system persists a BRD to the graph (via `/generate-brd --save` or any
explicit user request to surface a BRD in the UI), the system MUST write ONE
graph node whose shape exactly matches
`BRD_GRAPH_PERSISTENCE_CONTRACT.update_node_template` in
`brain_ds/mcp/grounding.py`.

The persisted BRD node MUST satisfy, at minimum:

- `node_id` equals `brd-<graph-id>` (where `<graph-id>` is the org slug).
- `label` equals `BRD`.
- `type` equals `Unknown` (literal string).
- `card_sections` is a list whose element `[0]` has `title == "Contenido"`,
  `order == 0`, and `icon == ""`.
- Every mention of a graph entity inside `card_sections[0].content` is a
  wikilink using the `[[<node label>]]` or `[[<node label>|<display>]]` form.

#### Scenario: /generate-brd --save produces a compliant BRD node
- GIVEN an org graph with at least one typed node
- WHEN the user runs `/generate-brd --save` for that graph
- THEN the system creates or upserts exactly one node with `node_id =
  brd-<graph-id>`, `label = "BRD"`, `type = "Unknown"`, and
  `card_sections[0] = {title: "Contenido", order: 0, icon: ""}`
- AND the BRD markdown content contains wikilinks for every mentioned entity
  rather than plain-text references

#### Scenario: BRD save round-trips through the API
- GIVEN a BRD node already persisted with `card_sections[0].order == 0` and
  `icon == ""`
- WHEN the BRD panel issues a save (PATCH `/api/nodes/:id`) and the node is
  re-read
- THEN the re-read node's `card_sections[0]` still has `order == 0`, `icon ==
  ""`, and `title == "Contenido"`

### Requirement: brainds-docs carve-out for BRD/Unknown nodes
The `brainds-docs` skill MUST explicitly exempt BRD nodes (node_id `brd-*`,
type `Unknown`) from its generic card_sections ordering and icon rules. The
exemption MUST be recorded in BOTH `skills/brainds-docs/SKILL.md` and
`.opencode/skills/brainds-docs/SKILL.md`, and it MUST defer to
`BRD_GRAPH_PERSISTENCE_CONTRACT` as the single source of truth for the BRD
node's shape.

#### Scenario: brainds-docs carve-out is present in both skill mirrors
- GIVEN the project has two skill mirrors at `skills/brainds-docs/SKILL.md`
  and `.opencode/skills/brainds-docs/SKILL.md`
- WHEN either mirror is read
- THEN it contains an explicit carve-out clause stating that BRD nodes
  (`node_id` starting with `brd-`, `type` `Unknown`) are exempt from the
  generic order-≥-1 and non-empty-icon rules
- AND the carve-out clause references the BRD persistence contract values
  `order: 0` and `icon: ""`

### Requirement: BRD persistence contract recurrence guard
A test in `tests/test_mcp_grounding.py` MUST fail if the brainds-docs
carve-out text and the `BRD_GRAPH_PERSISTENCE_CONTRACT.update_node_template`
disagree on the BRD node's shape. The test MUST assert at minimum:
- The carve-out text references the values `order: 0` and `icon: ""`.
- Those values equal `BRD_GRAPH_PERSISTENCE_CONTRACT.update_node_template
  .card_sections[0].order` and `.icon` respectively.

#### Scenario: guard goes red on divergence
- GIVEN the recurrence guard is registered
- WHEN `BRD_GRAPH_PERSISTENCE_CONTRACT` is changed so that
  `card_sections[0].order` becomes any value other than `0` (or `.icon`
  becomes non-empty)
- THEN the guard test fails with a message that names both the contract and
  the brainds-docs carve-out

### Requirement: BRD render-contract end-to-end
A Playwright e2e test (`brain_ds/ui/e2e/brd-panel.spec.ts`) MUST cover the
BRD panel render contract end to end: wikilink resolution, freshness chip
rendering, and save round-trip.

#### Scenario: wikilinks resolve to navigable node links
- GIVEN a persisted BRD node whose content contains a wikilink to a known
  entity label
- WHEN the BRD panel renders the node
- THEN the rendered DOM contains an anchor element pointing to that
  entity's node id and does NOT show the raw `[[...]]` syntax

#### Scenario: freshness chip is visible
- GIVEN a persisted BRD node with a known `updated_at` value
- WHEN the BRD panel renders the node
- THEN the panel shows a freshness chip whose text matches the
  `updated_at` value (or a deterministic human-readable derivative of it)
  within the panel's metadata region

#### Scenario: save round-trip via PATCH /api/nodes/:id
- GIVEN a persisted BRD node opened in the BRD panel
- WHEN the user triggers a save through the panel UI
- THEN the panel issues PATCH `/api/nodes/:id`
- AND the re-fetched node's `card_sections[0]` still has `order == 0`,
  `icon == ""`, and `title == "Contenido"`
- AND the panel re-renders without a hard reload

---

## Domain 2 — `harness-drift-guard` (Slice 1)

### Requirement: Category-2 drift guard enumerates every constant
The drift guard in `tests/test_grounding_drift_guard.py` MUST classify every
Category-2 constant in `brain_ds/mcp/grounding.py` as either "swept" or
"explicitly exempt" via a discoverable registry. A meta-test MUST assert
that:
- Every module-level dict or list constant declared in `grounding.py` whose
  name matches the Category-2 pattern is either swept by the existing guard
  logic OR listed in a `CATEGORY2_EXEMPT` set with a one-line rationale
  comment.
- If a new constant is added that is neither swept nor exempt, the meta-test
  fails with a message naming the constant.

This converts the vague "all ~20 Category-2 constants" acceptance into a
precise, self-maintaining contract: any future constant fails the build
until consciously classified.

#### Scenario: a new Category-2 constant fails until classified
- GIVEN the drift guard is registered
- WHEN a new module-level dict constant (e.g. `NEW_CONSTANT_XYZ = {"a": 1}`)
  is added to `brain_ds/mcp/grounding.py` and is neither swept by the guard
  logic nor added to `CATEGORY2_EXEMPT`
- THEN the meta-test fails with a message that names `NEW_CONSTANT_XYZ` and
  instructs the author to add it to the swept set or to `CATEGORY2_EXEMPT`
  with a rationale

#### Scenario: a consciously-exempt constant passes
- GIVEN the drift guard is registered
- WHEN a new module-level dict constant is added to `grounding.py` and
  classified by adding it to `CATEGORY2_EXEMPT` with a one-line rationale
  comment
- THEN the meta-test passes

### Requirement: Sweep detects entity-name-shaped tokens
When the drift guard sweeps a Category-2 constant, the sweep MUST walk
nested `str`, `list`, and `dict` values, and MUST flag any token that
matches the entity-name shape used elsewhere in the harness (e.g. values
returned by the existing `_entity_values()` helper for `EntityType`) if that
token is not a real `EntityType.value`.

#### Scenario: stale entity name in a constant is caught
- GIVEN a Category-2 constant in `grounding.py` whose nested string value
  is the literal `"StaleEntity"` (or any token shaped like an entity name)
  AND `"StaleEntity"` is not a value of `EntityType`
- WHEN the drift guard sweeps that constant
- THEN the sweep reports a drift entry naming the constant, the path within
  it, and the stale token

### Requirement: Drift guard exits non-zero on any drift
The drift guard test file MUST exit with a non-zero status when any drift
is reported, so CI and `brain_ds check` reflect drift as a build failure
rather than a warning.

#### Scenario: drift guard failure is observable in CI
- GIVEN the drift guard is registered in the test suite
- WHEN the suite is invoked via `uv run pytest
  tests/test_grounding_drift_guard.py` against a working tree that
  introduces one drift
- THEN the process exits non-zero and the failure message names the
  offending constant and token

---

## Domain 3 — `elicit-artifact-lifecycle` (Slice 2)

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
`AGENT_FLOW.md` and with `DELEGATION_PROTOCOL.artifact_keys`. The mapping
SHALL be:

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

---

## Domain 4 — `datasource-readonly-secrets` (Slice 3)

### Requirement: read-only datasource access is the only path the harness exercises
When a connected data source is read by the harness, the connector MUST
open the source in read-only mode. For SQLite, this is the composition of
the read-only URI mode (`mode=ro`) and `PRAGMA query_only`, plus the
existing path sandbox. The read-only guarantee MUST hold for both
unauthenticated and authenticated sources.

#### Scenario: SQLite read-only enforcement with secret_ref
- GIVEN a SQLite data source descriptor with `kind: "sqlite"`, a sandboxed
  `path`, and an optional `secret_ref` naming a valid env var
- WHEN the connector opens the source
- THEN the URI includes `mode=ro` AND the connection issues
  `PRAGMA query_only` immediately after open
- AND any write attempt (INSERT, UPDATE, DELETE, CREATE, DROP) is rejected
  by the database engine, not just by the harness

#### Scenario: read-only holds for an unauthenticated SQLite source
- GIVEN a SQLite data source descriptor without `secret_ref`
- WHEN the connector opens the source and the harness runs a SELECT
- THEN the SELECT returns rows
- AND any write statement against the same connection fails with a
  read-only error

### Requirement: secret contract — referenced, never stored
A Data Source `details.connection` MAY include an OPTIONAL `secret_ref`
field whose value is the NAME of an environment variable (a string, not a
literal credential). The connector MUST resolve the credential value from
`os.environ` inside the open path. The raw credential value MUST NOT be
persisted to the store, to any card_sections, or to any `.elicit/`
artifact.

#### Scenario: secret_ref is stored as a name, not a value
- GIVEN a Data Source node whose `details.connection.secret_ref` is the
  string `BRAINDS_SRC_PWD`
- WHEN the node is serialized (e.g. to the store JSON or to disk)
- THEN the serialized payload contains the literal string `BRAINDS_SRC_PWD`
- AND the serialized payload does NOT contain the resolved value of
  `BRAINDS_SRC_PWD` from the environment

#### Scenario: anti-leak guard — resolved secret never reaches .elicit/
- GIVEN a Data Source node with `secret_ref = "BRAINDS_SRC_PWD"` and the
  env var `BRAINDS_SRC_PWD` is set to a sentinel value
  (e.g. `SENTINEL-LEAK-CANARY-12345`)
- WHEN a full explore + document + map + brd cycle runs against this
  source and writes all artifacts to `.elicit/`
- THEN no file under `.elicit/` (active cycle, archive, or any
  intermediate output) contains the literal string
  `SENTINEL-LEAK-CANARY-12345`

#### Scenario: missing env var fails closed, not open
- GIVEN a Data Source node with `secret_ref = "DOES_NOT_EXIST"` and the
  env var is unset
- WHEN the connector attempts to open the source
- THEN the open fails with a clear error that names the missing env var
- AND no default or placeholder credential is silently substituted

### Requirement: secret contract surfaced in the harness
`SOURCE_EXPLORATION_CONTRACT` in `brain_ds/mcp/grounding.py` MUST reference
the `secret_ref` mechanism (field name, source of resolution, and
no-persistence guarantee) so sub-agents can request / reference
credentials correctly. A guard test MUST assert that the contract text
mentions the string `secret_ref` and the no-persistence rule.

#### Scenario: SOURCE_EXPLORATION_CONTRACT mentions secret_ref
- GIVEN the harness is loaded
- WHEN `SOURCE_EXPLORATION_CONTRACT` is introspected
- THEN its serialized form contains the string `secret_ref` AND a clause
  stating the resolved value is not persisted

---

## Domain 5 — `brain-ds-delegation-dry-run` (Slice 4)

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
