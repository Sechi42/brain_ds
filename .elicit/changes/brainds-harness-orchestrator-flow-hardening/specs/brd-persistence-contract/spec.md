# Delta for brd-persistence-contract

> Slice 1 of `brainds-harness-orchestrator-flow-hardening`. Resolves the
> brainds-docs / BRD persistence conflict and adds the BRD render-contract
> end-to-end check.

## ADDED Requirements

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

The `brainds-docs` skill MUST explicitly exempt BRD nodes (node_id
`brd-*`, type `Unknown`) from its generic card_sections ordering and icon
rules. The exemption MUST be recorded in BOTH `skills/brainds-docs/SKILL.md`
and `.opencode/skills/brainds-docs/SKILL.md`, and it MUST defer to
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
