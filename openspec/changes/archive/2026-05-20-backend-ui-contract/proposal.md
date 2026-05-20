# Proposal: backend-ui-contract

**Date**: 2026-05-20
**Change**: backend-ui-contract
**Phase**: propose
**Roadmap**: backend-migration-to-new-ui — Phase A · #1 (observation #875)
**Exploration**: `openspec/changes/backend-ui-contract/exploration.md` (engram #878)
**Artifact store**: hybrid (file + engram topic `sdd/backend-ui-contract/proposal`)

---

## Intent

Freeze the **first versioned data contract** between the Python backend (`build_render_context`) and the shipped workspace-shell UI (sections 1–5). Approach is **Enriched Static RENDER_CONTEXT** — additive, no new dependencies, no server, no SQLite — so the contract can be specced, tested, and shipped without disturbing the .exe packaging target or the networkx-only constraint. This same change closes the live `node.score` popover bug as a natural consequence of decision 1.

## Problem

The backend and the UI archived in `brain_ds/ui/design/sections/` disagree on what data ships per node:

- **Live bug**: `brain_ds/ui/src/interactions/popover.ts:77` reads `node.score`, which `build_render_context` never sets — the popover's score row is silently broken on `main` today.
- **7 structural gaps** between backend and UI (3 HIGH severity): `node.score`, `node.updated_at`, `node.neighbor_count` absent; no project hierarchy; no multi-tab contract; no navigation history; layout-grid mismatch.
- **No versioned contract**: any backend change today can silently break cached HTML or downstream Phase B/C consumers (.exe distribution, MCP bridge) with zero detectable signal.
- **No project hierarchy on the backend**: Section 1's `TreeNode` model assumes organization → project → graph, but the backend treats one JSON = one graph.

Every downstream roadmap change (SQLite store, MCP delta wire, .exe distribution, Elicit/BRD generators) depends on this contract being explicit and stable.

## Scope (In)

- Add `score`, `updated_at`, `neighbor_count` to every entry in `RENDER_CONTEXT.nodes` (derivation rules in **Contract Surface**).
- Add `contract_version: "1.0.0"` at the root of RENDER_CONTEXT with explicit semver policy.
- Add `meta.workspace = { root, displayPath, project, graph }` so Section 1's file-tree has a concrete data source.
- Define the **shape** (not the runtime wiring) of:
  - `TabModel` persistence — localStorage key + JSON schema.
  - `onAiAction(actionId, nodeId)` payload — placeholder shape for Phase C MCP.
- Update the live bug at `popover.ts:77` from "always undefined" to "reads the new `node.score` field" — fixed by adding the field, not by editing TS in this change.
- Author golden fixtures (small, per-section) for `RENDER_CONTEXT` so future contract drift is detected immediately.
- All additions are **purely additive** — no existing field is renamed, retyped, or removed.

## Scope (Out)

- **Layout migration** (3-column → 5-column `graph_viewer.html`) — owned by downstream change **`workspace-shell-layout-migration`** (roadmap #2). Combining both would blow the 400-line PR budget and conflates contract shape with CSS/grid work.
- **SQLite persistence layer** — roadmap #3 `sqlite-graph-store`. Node score stays computed at render time, not stored.
- **MCP / WebSocket / real-time deltas** — Phase C. This proposal only nails down the *payload shape* of `onAiAction`, not the transport.
- **Tab strip / navigation history runtime wiring** — only the contract (localStorage key/shape, navigation stack shape) lives here; the actual TypeScript that reads/writes lives in a later UI change.
- **Multi-graph CLI mode** — single-graph CLI stays; multi-graph traversal arrives with the SQLite store (roadmap #3) and the workspace shell change (roadmap #2).
- **Existing OpenCode/Elicit/BRD workflows** (`/elicit-context`, `/map-connections`, `/generate-brd`, observation #538) — untouched.

## Approach

**Approach A from exploration Q6 — Enriched Static RENDER_CONTEXT.**

Why over B/C/D:
1. **Packaging constraint** (`pyproject.toml`: networkx-only; .exe target): any HTTP/WebSocket framework violates the strongest architectural invariant of the project.
2. **No MCP blocker**: real-time is explicitly Phase C; the contract just needs to declare *what* moves over the wire later, not *how*.
3. **TDD-friendly**: additive JSON shape is trivially testable with `unittest` (strict TDD is active, runner `uv run python -m unittest discover -s tests`).
4. **Reversible**: every addition is opt-in for clients that ignore unknown fields, so a future SQLite layer or WebSocket can replace the *source* of these fields without changing the *contract*.

Trade-off accepted: no real-time, no server-side state. Both are deferred deliberately to Phase C — they are NOT prerequisites for the UI sections already archived.

---

## Decisions

### Decision 1 — Node score formula

**Choice**: `node.score = max(edge.score for edge in incident_edges(node))`, computed at render time in `build_render_context`. If a node has no incident edges, `node.score = 0.0`.

**Why**: The user-facing copy in Section 2 inspector and Section 5 popover ("Score: 0.82") reads as "how strong is this node's strongest relationship in this graph?" — i.e., a *relevance* signal, not a centrality measure. Max-of-incident captures that directly. Weighted mean dilutes hub nodes (a node with one strong tie and many weak ones would score low, which contradicts inspector intent). A separate `NodeScoringEngine` adds a new domain class with its own factor weights — overkill for Phase A and a magnet for scope creep.

**Trade-off**: Max is sensitive to single high-weight outliers. Mitigation: pair `score` with `neighbor_count` in the popover so users see both "strongest tie" and "how connected" — the two signals together tell the real story. If, after shipping, we find users misreading the field, a NodeScoringEngine can be introduced behind the same JSON key without breaking the contract (PATCH bump).

**Source of truth**: `brain_ds/scoring/scoring_engine.py` already computes `Edge.weight`. `node.score` is a derived view, not a new domain entity.

---

### Decision 2 — Node `updated_at` source

**Choice**: Derived from `max(evidence.timestamp for evidence in incident_evidence(node))`, formatted ISO-8601 UTC. Fallback to `meta.generated_at` when a node has zero incident evidence.

**Why**:
- **TDD-able**: deterministic from existing `EvidenceRecord.timestamp` data already in RENDER_CONTEXT — no new schema field, no new clock dependency in tests.
- **JSON-import ergonomic**: users do not stamp nodes manually; they just provide evidence with timestamps (which they already do). Adding an explicit `Node.updated_at` field would require backfilling every existing JSON and would conflate "when was the node last touched" with "when was this graph generated."
- **Semantically honest**: a node IS its evidence; the last evidence update IS the last meaningful change to that node.

**Trade-off**: A node with no incident evidence has no real "updated_at" — falling back to `meta.generated_at` is a fiction but a safe, documented one. The alternative (returning `null`) would force the UI to render a placeholder, which Section 2's Metadata accordion already does poorly.

**Source of truth**: `RENDER_CONTEXT.evidence_records` (already shipped). `RENDER_CONTEXT.detail_index[node_id].evidence` (already shipped) gives the lookup path.

---

### Decision 3 — Project hierarchy ownership

**Choice**: **Filesystem-path-derived**, surfaced as `meta.workspace = { root: str, displayPath: str, project: str, graph: str }`. NO new JSON schema field on the graph input file.

Derivation (in `cli.py` / `viewer.py` before calling `build_render_context`):
- `root` — the workspace root directory the user invoked the CLI from (or passed via `--root`).
- `displayPath` — the relative path from `root` to the graph JSON file (e.g. `acme-corp/billing/v2-graph.json`).
- `project` — the first path segment under `root` (or the parent directory of the graph JSON if depth is 1).
- `graph` — the JSON filename stem.

**Why**:
- **Matches Section 1 mock data**: `TreeNode { id, displayPath, type: "project"|"graph", children? }` already uses `displayPath` — filesystem-rooted is the natural source.
- **Phase B compatibility**: the .exe target means "any project, anywhere on disk." Embedding hierarchy *into* the JSON would require every user to also be a schema author. Filesystem-derived means the user just points the .exe at a folder.
- **Zero JSON schema change**: the graph input file format stays exactly as it is today — no migration, no breaking change to existing fixtures.
- **Phase A scoping**: the file-tree only needs to *show* the hierarchy; it does not need to *persist* it.

**Trade-off**: Multi-project workspaces with non-flat directory structures (e.g. `acme-corp/billing/2026/v2-graph.json`) need a convention for what counts as `project` vs nested folders. Decision: depth-1 segment under `root` is `project`; deeper folders are *labels* on the tree but not separate entities. Phase B (or later) can introduce a `workspace.yaml` if the convention proves too rigid — but the contract field stays the same.

---

### Decision 4 — Multi-tab client contract

**Choice**: **localStorage**, keyed `brain_ds.workspace.tabs.v1`, holding a JSON array of `TabModel`. The contract declares the *key and the schema*; the *runtime read/write code* is out of scope for this change.

Schema (declared in the spec phase, not implemented in this change):

```jsonc
[
  { "id": "tab-uuid",
    "label": "v2-graph",
    "graphPath": "acme-corp/billing/v2-graph.json",
    "active": true,
    "closeable": true,
    "openedAt": "ISO-8601" }
]
```

Navigation history: `brain_ds.workspace.history.v1` — an ordered list of `graphPath` strings, max length 50, last-active-first.

**Why**:
- **Static HTML pipeline preserved**: no sidecar file means no Python write-back, no second source of truth, no race condition between backend regen and UI state.
- **Per-origin scoping** is exactly what we want: each workspace folder served via `file://` gets its own tab state; opening a different workspace gives a clean slate.
- **Phase C MCP** can read the same localStorage from a webview or via a postMessage bridge — the key is stable and versioned.
- **Ephemeral was rejected**: users expect tabs to survive reloads; resetting on every page-load is a known UX anti-pattern (Section 4 explicitly shows persistent tabs).

**Trade-off**: localStorage is per-origin and not portable across machines. Acceptable: this is a desktop tool, not a synced cloud app. If portability is later required, a sidecar `workspace.json` can mirror the localStorage schema verbatim — the same shape, just a different transport.

**Versioning note**: the `v1` suffix on the localStorage keys is independent of `contract_version` — it lets us migrate UI-side state without bumping the whole RENDER_CONTEXT contract.

---

### Decision 5 — RENDER_CONTEXT versioning

**Choice**: Add `contract_version: "1.0.0"` at the root of RENDER_CONTEXT.

**Policy** (semver, documented in spec):
- **PATCH** (`1.0.x`): documentation-only changes, comment additions, no shape change.
- **MINOR** (`1.x.0`): new *optional* fields anywhere in the tree. Clients that ignore unknown fields keep working.
- **MAJOR** (`x.0.0`): any of — renaming a field, changing a type, removing a field, changing semantics of an existing field, making a previously-optional field required.

Clients SHOULD log a warning when `contract_version` MAJOR differs from what they were built against. Clients MUST NOT crash on a higher MINOR or PATCH.

**Why**: without an explicit version, every backend change risks silently breaking cached HTML and downstream consumers (.exe distribution, MCP bridge, future SQLite-backed renderer). One string costs nothing and gives every future change a clean upgrade path.

**Trade-off**: developers must remember to bump. Mitigation: a single test (`test_contract_version_matches_spec`) reads the version from a constants module and from a spec markdown fixture and fails if they drift — this catches "forgot to bump" mechanically.

---

### Decision 6 — Layout migration scoping

**Choice**: **OUT of scope**. The 3-column → 5-column `graph_viewer.html` migration is owned by downstream change **`workspace-shell-layout-migration`** (roadmap entry #2).

**Why**: combining layout migration with contract additions in a single PR would:
- Almost certainly exceed the 400-line review budget (HTML grid + CSS variables + the contract additions together).
- Conflate two failure modes — "contract broke" and "layout broke" — in the same diff, making bisection slower.
- Block the contract addition (which is small, additive, and TDD-clean) on a much larger CSS rewrite.

This proposal does **not** touch `graph_viewer.html`, `renderer.ts`, `popover.ts`, or any other UI runtime file. The data contract is the *only* surface.

---

## Contract Surface (additions)

All additions are additive. No existing field is renamed, retyped, or removed.

### Root of RENDER_CONTEXT

| Field | Type | Required | Origin | Derivation |
|---|---|---|---|---|
| `contract_version` | string (semver) | required | constant | `"1.0.0"` in `brain_ds/ui/render_context.py` |

### `RENDER_CONTEXT.meta` (existing object, new sub-field)

| Field | Type | Required | Origin | Derivation |
|---|---|---|---|---|
| `meta.workspace` | object | required | computed | from CLI invocation context (see Decision 3) |
| `meta.workspace.root` | string (absolute path) | required | computed | CLI cwd or `--root` flag |
| `meta.workspace.displayPath` | string (POSIX-style relative) | required | computed | relative path from `root` to graph JSON |
| `meta.workspace.project` | string | required | computed | depth-1 segment under `root` |
| `meta.workspace.graph` | string | required | computed | JSON filename stem |

### `RENDER_CONTEXT.nodes[*]` (new fields per node)

| Field | Type | Required | Origin | Derivation |
|---|---|---|---|---|
| `score` | float (0.0–1.0) | required | computed | `max(edge.score for edge in incident_edges(node))`; `0.0` if no incident edges |
| `updated_at` | string (ISO-8601 UTC) | required | computed | `max(evidence.timestamp for evidence in incident_evidence(node))`; fallback to `meta.generated_at` |
| `neighbor_count` | int | required | computed | `len(RENDER_CONTEXT.adjacency[node.id])` |

### Out-of-band contracts (declared here, lived elsewhere)

| Surface | Where it lives | Shape locked in spec? |
|---|---|---|
| Tab persistence | `localStorage["brain_ds.workspace.tabs.v1"]` | yes — schema in spec phase |
| Nav history | `localStorage["brain_ds.workspace.history.v1"]` | yes — schema in spec phase |
| `onAiAction(actionId, nodeId)` payload | TS interface | placeholder only — full shape arrives with Phase C |

---

## Validation Strategy (TDD posture)

Strict TDD is active (runner: `uv run python -m unittest discover -s tests`). This proposal does **not** write tests — it declares what tests the spec phase MUST require.

Test additions the spec phase will require:

1. `tests/test_render_context_contract.py` (new file):
   - `test_contract_version_is_one_zero_zero` — root contains `contract_version == "1.0.0"`.
   - `test_every_node_has_score` — every entry in `nodes[]` has a `score` field of type float in `[0.0, 1.0]`.
   - `test_node_score_is_max_of_incident_edge_scores` — for a fixture with known edges, `node.score == max(...)`.
   - `test_isolated_node_score_is_zero` — node with no incident edges → `score == 0.0`.
   - `test_every_node_has_updated_at` — every node has a `updated_at` field, valid ISO-8601.
   - `test_node_updated_at_is_max_incident_evidence_timestamp` — fixture-based.
   - `test_isolated_node_updated_at_falls_back_to_meta_generated_at`.
   - `test_every_node_has_neighbor_count` — equals `len(adjacency[node.id])`.
   - `test_meta_workspace_present_and_well_formed` — keys `root`, `displayPath`, `project`, `graph` all present and non-empty strings.

2. `tests/test_render_context_golden.py` (new file):
   - One small frozen JSON fixture per entity type (actor, data, process, problem, risk, metric, solution — 7 supertypes; minimal 2–4-node graphs).
   - Assert `build_render_context(load_fixture)` equals the golden JSON exactly (sorted keys).
   - Keep fixtures small to avoid over-freezing.

3. `tests/test_viewer.py` (existing — must stay green):
   - `ctx["edges"][0]["score"] == float(edge.weight)` — edge.score assertion preserved verbatim.
   - All other existing assertions preserved.

4. `tests/test_graph_contract.py` (existing — must stay green):
   - Node/Edge roundtrip continues to pass. Since `score`, `updated_at`, `neighbor_count` are *render-time derived* and NOT new `Node` dataclass fields, this test should require zero changes. (If the design phase decides to add fields to `Node`, this test gets updated then — not here.)

**Strict TDD posture in spec phase**: every new contract field above gets a failing test written **before** any change to `build_render_context`.

---

## Live Bug Closure

`brain_ds/ui/src/interactions/popover.ts:77` reads `node.score` from `RENDER_CONTEXT.nodes`. Today that lookup returns `undefined` and the popover's score row drops silently.

**Closure**: Decision 1 adds `node.score` to RENDER_CONTEXT as a required field. The TS code at `popover.ts:77` already reads the correct path — *no TS edit is needed in this change*. The bug closes the moment `build_render_context` returns a score for every node. The spec phase will include a regression test that asserts `node.score` is present and numeric for every node in a fixture graph.

No hotfix carve-out is needed — the fix is the proposal.

---

## Risks

1. **Domain coupling (Decision 1)**: introducing `node.score` creates a derived quantity that readers may overload semantically (centrality? authority? PageRank?). Mitigation:
   - Inline docstring on `build_render_context` stating exactly: "max of incident edge scores, 0.0 if isolated."
   - The decision record above lives in this proposal AND will be copied verbatim into the spec phase's contract documentation.

2. **Backwards compatibility (Decision 5)**: clients that don't tolerate extra fields could break. Mitigation:
   - `contract_version` + additive-only policy makes the upgrade path explicit.
   - All current known consumers (the shipped TS in `brain_ds/ui/src/`) tolerate extra fields — they read specific keys, never iterate.
   - External consumers (Phase B .exe, Phase C MCP) don't exist yet and will be built against `1.0.0` from day one.

3. **Test surface (golden fixtures)**: golden fixtures can freeze too much and force noisy churn. Mitigation:
   - Keep fixtures *per entity type* and *minimal* (2–4 nodes each).
   - Section-scoped fixtures (one per UI section's data needs) rather than one mega-fixture.
   - Update golden files only via an explicit `update_golden=True` flag pattern in the test helper, so accidental updates fail loud.

4. **Workspace derivation edge cases (Decision 3)**: graph JSON files at the workspace root (depth 0) have no obvious `project`. Mitigation:
   - When the graph JSON is directly at `root`, `project` falls back to the basename of `root` itself. Spec phase will lock this convention.

5. **localStorage quota / cross-machine (Decision 4)**: localStorage is per-origin and ~5MB. For our tab/history sizes this is fine, but a corrupted/oversized entry could break the tab strip. Mitigation:
   - Spec phase requires a "if parse fails, reset to empty array and log" recovery path in the (later) TS code.
   - Tab schema is small (<200 bytes per tab); 50-entry history cap keeps total well under 1MB.

6. **Layout migration coupling pressure**: someone may push to bundle the 5-column migration into this PR because "the UI looks broken without it." Mitigation:
   - This proposal explicitly does NOT touch any HTML/CSS file. The new fields work in the current 3-column layout (just unused) and in the future 5-column layout identically.
   - The downstream change `workspace-shell-layout-migration` is already entered in the roadmap as #2.

---

## Open Questions Remaining (for spec / design phases)

- **OQ-A**: Exact ISO-8601 format for `updated_at` — with or without milliseconds? With or without timezone offset (`Z` vs `+00:00`)? **Tentative**: `YYYY-MM-DDTHH:MM:SSZ` (second precision, UTC `Z`). Spec to confirm.
- **OQ-B**: Should `node.score` round to 2 decimals at the contract boundary, or stay full-precision float? UI shows 2 decimals; backend could either round or let UI round. **Tentative**: full precision in JSON, UI rounds at display time. Spec to confirm.
- **OQ-C**: What happens when `--root` is not passed and cwd has no recognizable project structure? Error, warn, or synthesize a fallback workspace? **Tentative**: synthesize `meta.workspace.project = "default"` and warn. Spec to confirm.
- **OQ-D**: `onAiAction` payload shape — full design lives with Phase C, but the placeholder TS interface should still appear in design. Design phase to draft a minimal stub.
- **OQ-E**: Should `contract_version` be exposed in `window.RENDER_CONTEXT.contract_version` AND in a separate constants module the TS can import for compile-time checks? **Tentative**: yes — design phase will decide the module path.

---

## Acceptance Signals

This change has shipped correctly when **all** of these are true:

1. `uv run python -m unittest discover -s tests` is green, including new contract tests in `tests/test_render_context_contract.py`.
2. `tests/test_viewer.py` and `tests/test_graph_contract.py` are unchanged or only additively updated — no existing assertion deleted.
3. Opening any existing graph JSON in the viewer shows the score row in the hover popover with a real number (closing the live `popover.ts:77` bug) — no TS edit was required to achieve this.
4. `RENDER_CONTEXT.contract_version` is present, equals `"1.0.0"`, and a single test pins it.
5. `RENDER_CONTEXT.meta.workspace` is present with all four sub-fields populated for any CLI invocation.
6. The spec phase has a complete, testable specification of every field added above, including OQs A–C resolved.
7. The roadmap's downstream changes (`workspace-shell-layout-migration`, `sqlite-graph-store`) can begin without any further contract evolution — i.e., this is `contract_version 1.0.0` and the next change either consumes it unchanged or bumps the MINOR.

---

## Engram trail

- Exploration: engram #878 / `openspec/changes/backend-ui-contract/exploration.md`
- Proposal: this file + engram topic_key `sdd/backend-ui-contract/proposal`
- Next phases: `sdd-spec` and `sdd-design` (can run in parallel)
