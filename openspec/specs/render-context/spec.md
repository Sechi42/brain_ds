# Spec: backend-ui-contract

**Date**: 2026-05-20
**Change**: backend-ui-contract
**Phase**: spec
**Roadmap**: backend-migration-to-new-ui — Phase A · #1 (observation #875)
**Proposal**: `openspec/changes/backend-ui-contract/proposal.md` (engram #879)
**Exploration**: `openspec/changes/backend-ui-contract/exploration.md` (engram #878)
**Artifact store**: hybrid (file + engram topic_key `sdd/backend-ui-contract/spec`)
**Test runner**: `uv run python -m unittest discover -s tests`

---

## Open Questions Resolved

| OQ | Decision |
|----|----------|
| **OQ-A** | `updated_at` format is **LOCKED** as `YYYY-MM-DDTHH:MM:SSZ` (UTC, second precision, `Z` suffix). No milliseconds. No `+00:00`. Regex: `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`. |
| **OQ-B** | `node.score` is **full float precision** at the contract boundary. No rounding in Python. The UI rounds to 2 decimal places at display time. |

OQ-C (workspace derivation fallback), OQ-D (onAiAction payload), OQ-E (TS constants module) — design-phase territory; not addressed here.

---

## Delta for backend-ui-contract

### ADDED Requirements

---

### Requirement R01 — contract_version at RENDER_CONTEXT root

`RENDER_CONTEXT` MUST include a `contract_version` field at the root level.

- **Type**: JSON string.
- **Value**: exactly `"1.0.0"`.
- **Format**: semver `MAJOR.MINOR.PATCH` — three dot-separated non-negative integers.
- **Semver policy**:
  - PATCH (`1.0.x`): documentation-only changes, no shape change.
  - MINOR (`1.x.0`): new optional fields added anywhere. Clients that ignore unknown fields MUST keep working.
  - MAJOR (`x.0.0`): any rename, retype, removal, semantic change, or optional → required promotion.
- Clients SHOULD warn when the MAJOR digit differs from what they were built against. Clients MUST NOT crash on higher MINOR or PATCH.

**Test name**: `test_contract_version_is_one_zero_zero`

#### Scenario R01-A: contract_version equals the string "1.0.0"
- GIVEN a `RENDER_CONTEXT` built from any valid graph via `build_render_context`
- WHEN the consumer reads `context["contract_version"]`
- THEN the value MUST equal the string `"1.0.0"` exactly

#### Scenario R01-B: contract_version is present at the root level
- GIVEN a `RENDER_CONTEXT` built from any valid graph
- WHEN the context is serialized to JSON
- THEN `"contract_version"` MUST appear as a top-level key (not nested under any sub-object)

#### Scenario R01-C: contract_version is pinned by a literal regression test
- GIVEN the existing test suite in `tests/`
- WHEN `uv run python -m unittest discover -s tests` runs
- THEN at least one test MUST assert `context["contract_version"] == "1.0.0"` as a literal string comparison (not a pattern match)

---

### Requirement R02 — meta.workspace object

`RENDER_CONTEXT.meta` MUST include a `workspace` sub-object with exactly four keys: `root`, `displayPath`, `project`, and `graph`.

All four keys are **required** and MUST be non-empty strings.

**Sub-field specifications**:

| Key | Type | Derivation |
|-----|------|------------|
| `root` | string (absolute path) | Workspace root: CLI cwd or `--root` flag value |
| `displayPath` | string (POSIX-style relative) | Relative path from `root` to the graph JSON file, using forward slashes only |
| `project` | string | Depth-1 path segment under `root`; falls back to `basename(root)` when the graph JSON is at depth 0 (directly inside `root`) |
| `graph` | string | Filename stem of the graph JSON (without the `.json` extension) |

**Cross-platform rule**: `root` MAY contain native OS path separators (backslashes on Windows). `displayPath` MUST use forward slashes (`/`) regardless of the host platform.

**Test name**: `test_meta_workspace_present_and_well_formed`

#### Scenario R02-A: typical nested workspace
- GIVEN a workspace with `root = "/workspace"` and graph JSON at `"/workspace/acme-corp/billing/v2-graph.json"`
- WHEN `build_render_context` is called
- THEN `context["meta"]["workspace"]["root"]` MUST be `"/workspace"` (or its OS-native equivalent)
- AND `context["meta"]["workspace"]["displayPath"]` MUST be `"acme-corp/billing/v2-graph.json"` (forward slashes)
- AND `context["meta"]["workspace"]["project"]` MUST be `"acme-corp"` (depth-1 segment)
- AND `context["meta"]["workspace"]["graph"]` MUST be `"v2-graph"`

#### Scenario R02-B: depth-0 graph (JSON at root — fallback)
- GIVEN a workspace with `root = "/workspace"` and graph JSON at `"/workspace/my-graph.json"`
- WHEN `build_render_context` is called
- THEN `context["meta"]["workspace"]["displayPath"]` MUST be `"my-graph.json"`
- AND `context["meta"]["workspace"]["project"]` MUST be `"workspace"` (basename of `root`)

#### Scenario R02-C: deeper nesting — only depth-1 counts as project
- GIVEN a workspace with `root = "/ws"` and graph JSON at `"/ws/acme-corp/billing/2026/v3-graph.json"`
- WHEN `build_render_context` is called
- THEN `context["meta"]["workspace"]["project"]` MUST be `"acme-corp"` (depth-1 only; deeper segments are NOT separate project entities)
- AND `context["meta"]["workspace"]["displayPath"]` MUST be `"acme-corp/billing/2026/v3-graph.json"` (forward slashes, full relative path)

#### Scenario R02-D: displayPath uses forward slashes on Windows
- GIVEN a Windows host where the resolved path uses backslashes
- WHEN `build_render_context` is called
- THEN `context["meta"]["workspace"]["displayPath"]` MUST contain only forward slashes (`/`)
- AND MUST NOT contain backslashes (`\`)

---

### Requirement R03 — node.score field

Every entry in `RENDER_CONTEXT.nodes` MUST include a `score` field.

- **Type**: JSON number (Python `float`).
- **Range**: `[0.0, 1.0]` inclusive.
- **Precision**: full float precision preserved in the JSON. No rounding at the contract boundary.
- **Formula**: `max(edge.score for edge in incident_edges(node))`.
- **Isolated node**: if a node has no incident edges, `score` MUST be `0.0`.
- **Source of truth**: `edge.score` is derived from `Edge.weight` as already computed by `brain_ds/scoring/scoring_engine.py`.

**Test names**: `test_every_node_has_score`, `test_node_score_is_max_of_incident_edge_scores`, `test_isolated_node_score_is_zero`

#### Scenario R03-A: node with multiple incident edges — score is maximum
- GIVEN a graph with node `A` having two incident edges with scores `0.3` and `0.75`
- WHEN `build_render_context` is called
- THEN `context["nodes"][A]["score"]` MUST equal `0.75`
- AND MUST NOT equal `0.3` or any other value

#### Scenario R03-B: isolated node — score is 0.0
- GIVEN a graph containing node `X` with no incident edges
- WHEN `build_render_context` is called
- THEN `context["nodes"][X]["score"]` MUST equal `0.0`

#### Scenario R03-C: node with exactly one incident edge
- GIVEN a graph with node `B` having exactly one incident edge with score `0.6`
- WHEN `build_render_context` is called
- THEN `context["nodes"][B]["score"]` MUST equal `0.6`

#### Scenario R03-D: score field is never undefined (popover.ts live bug closure)
- GIVEN any graph loaded via `build_render_context`
- WHEN the consumer reads `node["score"]` for every node in `context["nodes"]`
- THEN every value MUST be a number (not `None`, not absent, not `"undefined"`)
- Note: this closes the live bug where `popover.ts:77` reads `node.score` and gets `undefined` today

#### Scenario R03-E: full float precision preserved — no rounding at contract boundary
- GIVEN a graph with an edge whose `weight` is `0.123456789`
- WHEN `build_render_context` is called
- THEN `context["nodes"][incident_node]["score"]` MUST equal `0.123456789` (full precision, not `0.12`)

---

### Requirement R04 — node.updated_at field

Every entry in `RENDER_CONTEXT.nodes` MUST include an `updated_at` field.

- **Type**: JSON string.
- **Format**: **LOCKED** — `YYYY-MM-DDTHH:MM:SSZ` (UTC, second precision, `Z` suffix, no milliseconds, no `+00:00` variant).
- **Regex**: `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`.
- **Formula**: `max(evidence.timestamp for evidence in incident_evidence(node))`.
  - "incident evidence" means all `EvidenceRecord` objects whose IDs appear in `detail_index[node.id].evidence`.
- **Fallback**: when a node has zero incident evidence, `updated_at` MUST equal `meta.generated_at`.

**Test names**: `test_every_node_has_updated_at`, `test_node_updated_at_is_max_incident_evidence_timestamp`, `test_isolated_node_updated_at_falls_back_to_meta_generated_at`

#### Scenario R04-A: node with multiple evidence records — latest timestamp wins
- GIVEN a graph with node `N` linked to evidence records with timestamps `"2026-01-01T10:00:00Z"` and `"2026-05-14T12:30:00Z"`
- WHEN `build_render_context` is called
- THEN `context["nodes"][N]["updated_at"]` MUST equal `"2026-05-14T12:30:00Z"`

#### Scenario R04-B: node with no incident evidence — fallback to meta.generated_at
- GIVEN a graph where `meta.generated_at = "2026-03-01T08:00:00Z"` and node `M` has no linked evidence
- WHEN `build_render_context` is called
- THEN `context["nodes"][M]["updated_at"]` MUST equal `"2026-03-01T08:00:00Z"`

#### Scenario R04-C: format strictly matches locked pattern
- GIVEN any graph with at least one node
- WHEN `build_render_context` is called
- THEN every `node["updated_at"]` value MUST match the regex `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`
- AND MUST NOT contain milliseconds (e.g., `.000`)
- AND MUST NOT use `+00:00` in place of `Z`

---

### Requirement R05 — node.neighbor_count field

Every entry in `RENDER_CONTEXT.nodes` MUST include a `neighbor_count` field.

- **Type**: JSON integer (Python `int`).
- **Range**: `>= 0`.
- **Formula**: `len(RENDER_CONTEXT.adjacency[node.id])`.
- Counts distinct neighbors. An isolated node (absent from adjacency or with an empty adjacency list) has `neighbor_count = 0`.

**Test names**: `test_every_node_has_neighbor_count`, `test_neighbor_count_isolated_is_zero`, `test_neighbor_count_matches_adjacency`

#### Scenario R05-A: isolated node — neighbor_count is 0
- GIVEN a graph containing node `Z` with no incident edges
- WHEN `build_render_context` is called
- THEN `context["nodes"][Z]["neighbor_count"]` MUST equal `0`

#### Scenario R05-B: connected node — neighbor_count equals adjacency list length
- GIVEN a graph with node `C` that has 3 distinct neighbors in `RENDER_CONTEXT.adjacency["C"]`
- WHEN `build_render_context` is called
- THEN `context["nodes"][C]["neighbor_count"]` MUST equal `3`

#### Scenario R05-C: neighbor_count is integer, not float
- GIVEN any graph
- WHEN `build_render_context` is called
- THEN every `node["neighbor_count"]` value MUST be of Python type `int` (not `float`, not `str`)

---

### Requirement R06 — Backwards compatibility: existing fields MUST remain unchanged

All existing fields in `RENDER_CONTEXT` MUST remain unchanged in name, type, and semantics. The additions in R01–R05 are purely additive — nothing is renamed, retyped, removed, or made optional where previously required.

**Existing fields protected by this requirement** (non-exhaustive — any current key is protected):
- `meta`: `org`, `generated_at`, `node_count`, `edge_count`
- `nodes[*]`: `id`, `label`, `type`, `supertype`, `color`, `title`, `parent_id`, `depth`, `component_id`
- `edges[*]`: `from`, `to`, `label`, `title`, `width`, `score`
- `type_groups`, `adjacency`, `detail_index`, `evidence_records`, `ui_defaults`

**Test name**: `test_edge_score_assertion_preserved` (existing test — MUST stay green)

#### Scenario R06-A: edge.score assertion preserved verbatim
- GIVEN a graph with one edge whose `weight = 0.75`
- WHEN `build_render_context` is called
- THEN `context["edges"][0]["score"]` MUST equal `float(edge.weight)` — i.e., `0.75`
- Note: This assertion already exists in `tests/test_viewer.py` (`TestSlice5ScoreThresholdFilter.test_render_context_emits_edge_score`) and MUST remain passing without modification

#### Scenario R06-B: existing v1/v2 graph JSON parses without shape change
- GIVEN any graph JSON in a format already consumed by the existing test suite (v1 or v2 shape)
- WHEN parsed by `Graph.from_v1` and passed to `build_render_context`
- THEN the function MUST not raise any error
- AND all previously present fields MUST remain present with the same values
- AND the input JSON file MUST require no modification

#### Scenario R06-C: test_graph_contract.py stays green without changes
- GIVEN `tests/test_graph_contract.py` with its current assertions on `Node`/`Edge` roundtrip
- WHEN `uv run python -m unittest discover -s tests` runs after this change is applied
- THEN all tests in `test_graph_contract.py` MUST pass
- AND no existing assertion in that file MUST be deleted or modified

---

### Requirement R07 — Golden fixtures per entity supertype

At least one minimal golden `RENDER_CONTEXT` JSON fixture MUST exist for each of the 7 entity supertypes: `actor`, `data`, `process`, `problem`, `risk`, `metric`, `solution`.

- Each fixture MUST contain between 2 and 4 nodes inclusive.
- Each fixture MUST be the minimal valid graph for its supertype (only the nodes and edges necessary to exercise the supertype's contract fields).
- `build_render_context(load_fixture_graph)` MUST produce output that deep-equals the golden JSON when keys are sorted.
- Fixtures MUST be updated only via an explicit update mechanism (e.g., an `update_golden=True` flag in the test helper). Accidental drift MUST cause a test failure, not a silent update.

**Test names**: `test_golden_fixture_actor`, `test_golden_fixture_data`, `test_golden_fixture_process`, `test_golden_fixture_problem`, `test_golden_fixture_risk`, `test_golden_fixture_metric`, `test_golden_fixture_solution`

#### Scenario R07-A: build_render_context matches golden for each supertype
- GIVEN the minimal fixture graph for supertype `S` (2 to 4 nodes)
- WHEN `build_render_context(fixture_graph)` is called
- THEN the result MUST deep-equal the corresponding golden JSON file (sorted keys)
- AND the comparison MUST cover all keys including the new R01–R05 additions

#### Scenario R07-B: golden fixture reflects locked field values for new fields
- GIVEN any golden fixture
- THEN it MUST include `contract_version`, `meta.workspace`, and per-node `score`, `updated_at`, `neighbor_count`
- AND those values MUST be consistent with the fixture's input data (correct formula outputs, not placeholders)

---

### Requirement R08 — Tab persistence schema

The localStorage key `brain_ds.workspace.tabs.v1` MUST hold a JSON array of `TabModel` objects.

**TabModel schema** (locked):

```
TabModel {
  id:         string      — unique tab identifier (e.g., UUID or stable hash)
  label:      string      — display name for the tab (typically the graph filename stem)
  graphPath:  string      — POSIX-style relative path to the graph JSON
  active:     boolean     — true if this tab is currently active
  closeable:  boolean     — true if the user can close this tab
  openedAt:   string      — ISO-8601 UTC, format YYYY-MM-DDTHH:MM:SSZ (same locked format as node.updated_at)
}
```

The localStorage key `brain_ds.workspace.history.v1` MUST hold a JSON array of strings (POSIX-style graph paths), ordered last-active-first, with a maximum length of 50 entries.

**Scope note**: this requirement specifies the schema only. The runtime TypeScript code that reads/writes these keys is out of scope for this change.

**Test name**: `test_tab_model_schema_fields_documented` (schema documentation / static assertion)

#### Scenario R08-A: TabModel has all six required fields
- GIVEN the locked `TabModel` schema defined in this spec
- THEN the schema MUST declare exactly these six keys: `id`, `label`, `graphPath`, `active`, `closeable`, `openedAt`
- AND `openedAt` MUST use the same format as `node.updated_at` (`YYYY-MM-DDTHH:MM:SSZ`)

#### Scenario R08-B: history array is bounded
- GIVEN the locked `brain_ds.workspace.history.v1` schema
- THEN the array MUST have a maximum length of 50 entries
- AND entries MUST be strings (POSIX path strings)

#### Scenario R08-C: localStorage recovery contract
- GIVEN that a `brain_ds.workspace.tabs.v1` entry cannot be parsed (malformed JSON or wrong type)
- THEN the consumer MUST reset the key to an empty array and log the error
- AND MUST NOT crash or leave the tab strip in a broken state

---

## PRESERVED Requirements (must stay green — no changes permitted)

These requirements already exist in the codebase and MUST remain fully satisfied after this change.

### Requirement P01 — edge.score is float(edge.weight)
- `RENDER_CONTEXT.edges[*].score` MUST equal `float(edge.weight)` for every edge.
- Pinned by `TestSlice5ScoreThresholdFilter.test_render_context_emits_edge_score` in `tests/test_viewer.py`.

### Requirement P02 — Node/Edge domain roundtrip
- `Graph.from_v1` → `to_dict` → `Graph.from_v1` roundtrip MUST preserve all node and edge fields.
- Pinned by `TestGraphContract.test_to_dict_roundtrip_preserves_v2_fields_and_derives_supertype` in `tests/test_graph_contract.py`.
- Note: `score`, `updated_at`, `neighbor_count` are render-time derived by `build_render_context` and are NOT new fields on the `Node` dataclass. `test_graph_contract.py` MUST require zero changes.

### Requirement P03 — Existing viewer tests
- All tests in `tests/test_viewer.py` MUST remain passing.
- No existing assertion in that file MUST be deleted or weakened.

---

## New Test Files Required (apply-phase reference)

| File | Purpose |
|------|---------|
| `tests/test_render_context_contract.py` | New — covers R01 through R05 with the test names listed per requirement |
| `tests/test_render_context_golden.py` | New — covers R07, one test method per supertype |

---

## Explicit Test Name Registry

For strict TDD compliance, the apply-phase MUST write failing tests with these names before modifying `build_render_context`:

| Test name | Requirement | Scenario |
|-----------|-------------|----------|
| `test_contract_version_is_one_zero_zero` | R01 | R01-A, R01-B, R01-C |
| `test_meta_workspace_present_and_well_formed` | R02 | R02-A |
| `test_meta_workspace_depth_zero_fallback` | R02 | R02-B |
| `test_meta_workspace_depth_one_project_only` | R02 | R02-C |
| `test_meta_workspace_display_path_uses_posix_slashes` | R02 | R02-D |
| `test_every_node_has_score` | R03 | R03-A, R03-C |
| `test_node_score_is_max_of_incident_edge_scores` | R03 | R03-A |
| `test_isolated_node_score_is_zero` | R03 | R03-B |
| `test_node_score_full_float_precision` | R03 | R03-E |
| `test_node_score_never_undefined` | R03 | R03-D |
| `test_every_node_has_updated_at` | R04 | R04-C |
| `test_node_updated_at_is_max_incident_evidence_timestamp` | R04 | R04-A |
| `test_isolated_node_updated_at_falls_back_to_meta_generated_at` | R04 | R04-B |
| `test_updated_at_format_matches_locked_pattern` | R04 | R04-C |
| `test_every_node_has_neighbor_count` | R05 | R05-B, R05-C |
| `test_neighbor_count_isolated_is_zero` | R05 | R05-A |
| `test_neighbor_count_matches_adjacency` | R05 | R05-B |
| `test_golden_fixture_actor` | R07 | R07-A, R07-B |
| `test_golden_fixture_data` | R07 | R07-A, R07-B |
| `test_golden_fixture_process` | R07 | R07-A, R07-B |
| `test_golden_fixture_problem` | R07 | R07-A, R07-B |
| `test_golden_fixture_risk` | R07 | R07-A, R07-B |
| `test_golden_fixture_metric` | R07 | R07-A, R07-B |
| `test_golden_fixture_solution` | R07 | R07-A, R07-B |
| `test_tab_model_schema_fields_documented` | R08 | R08-A |

---

## Acceptance Signals

This change is done when ALL of the following are true:

1. `uv run python -m unittest discover -s tests` is green, including all new tests in `tests/test_render_context_contract.py` and `tests/test_render_context_golden.py`.
2. `tests/test_viewer.py` and `tests/test_graph_contract.py` remain unchanged or have only additive updates — no existing assertion deleted or weakened.
3. `RENDER_CONTEXT.contract_version` is present and equals `"1.0.0"`, pinned by a literal test.
4. `RENDER_CONTEXT.meta.workspace` is present with all four sub-fields populated for any CLI invocation.
5. Every node in `RENDER_CONTEXT.nodes` has `score` (float, non-null), `updated_at` (locked ISO format), and `neighbor_count` (int).
6. The hover popover for any existing graph shows a real numeric score — `popover.ts:77` no longer reads `undefined`.
7. Downstream changes (`workspace-shell-layout-migration`, `sqlite-graph-store`) can start against `contract_version 1.0.0` without further contract evolution.

---

## Engram trail

- Exploration: engram #878 / `openspec/changes/backend-ui-contract/exploration.md`
- Proposal: engram #879 / `openspec/changes/backend-ui-contract/proposal.md`
- Spec: this file + engram topic_key `sdd/backend-ui-contract/spec`
- Next phases: `sdd-design` (parallel) → `sdd-tasks`
