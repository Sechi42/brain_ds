# Design: backend-ui-contract

**Date**: 2026-05-20
**Change**: backend-ui-contract
**Phase**: design
**Roadmap**: backend-migration-to-new-ui — Phase A · #1 (observation #875)
**Proposal**: openspec/changes/backend-ui-contract/proposal.md (engram #879)
**Exploration**: openspec/changes/backend-ui-contract/exploration.md (engram #878)
**Artifact store**: hybrid (file + engram topic_key `sdd/backend-ui-contract/design`)

---

## Goals

1. Freeze `RENDER_CONTEXT` v1.0.0 as the first versioned data contract between `build_render_context` and the shipped workspace-shell UI (sections 1–5).
2. Make the three currently-absent node fields (`score`, `updated_at`, `neighbor_count`) deterministic, derived-at-render-time, and TDD-covered.
3. Surface filesystem-derived project hierarchy as `meta.workspace = { root, displayPath, project, graph }` without inventing a new JSON schema field.
4. Establish the cross-language sync mechanism for `contract_version` between Python (`render_context.py`) and TypeScript (`contract_version.ts`).
5. Preserve all existing `tests/test_viewer.py` and `tests/test_graph_contract.py` assertions — additive contract only.
6. Close the live popover.ts:77 bug as a free side-effect, with no TS edits.

## Non-Goals

- Layout migration 3-col → 5-col `graph_viewer.html` — owned by `workspace-shell-layout-migration` (roadmap #2). This design touches ZERO HTML/CSS/runtime-TS files. The only new TS file is a constants module (`contract_version.ts`), not a runtime/UI file.
- SQLite persistence layer — `sqlite-graph-store` (roadmap #3).
- MCP / WebSocket / SSE / real-time deltas — Phase C.
- Runtime wiring for tab strip, navigation history, or `onAiAction`. This design freezes their CONTRACT SHAPE only.
- Pre-computed node scores stored in the Graph JSON file format. Scores stay render-time-derived.
- New runtime dependencies. `networkx>=3.0` remains the only runtime dep.
- Multi-graph CLI mode (single `graph_json` arg preserved).

## Architecture Sketch

```
   ┌────────────────┐     ┌──────────────────────────────────┐
   │  graph JSON    │ ──▶ │  Graph.from_v1(payload)          │
   │  file / stdin  │     │  → brain_ds.ontology.Graph       │
   └────────────────┘     └──────────────────────────────────┘
                                          │
                                          ▼
   ┌────────────────────────────┐    ┌──────────────────────────────────────────┐
   │ cli.py                     │ ──▶│ build_render_context(graph, workspace?)  │
   │  • --root  (NEW)           │    │  • CONTRACT_VERSION = "1.0.0"            │
   │  • workspace = OQ-C        │    │  • meta.workspace = {root,displayPath,…} │
   │    fallback if missing     │    │  • per-node score / updated_at / nbr_cnt │
   └────────────────────────────┘    │  • all existing fields preserved         │
                                     └──────────────────────────────────────────┘
                                          │
                                          ▼
                              ┌──────────────────────────────┐
                              │ template_renderer.py         │
                              │  json.dumps(context) → str   │
                              │  → __BRAIN_DS_RENDER_CONTEXT__│
                              └──────────────────────────────┘
                                          │
                                          ▼
                              ┌──────────────────────────────┐
                              │ graph_viewer.html            │
                              │  window.RENDER_CONTEXT       │
                              │  • popover.ts reads .score   │
                              │  • contract_version.ts pins  │
                              │    "1.0.0" at compile-time   │
                              └──────────────────────────────┘
```

Data-flow stays purely additive: the same template-string replacement path ships, no new runtime dependency is introduced, and the contract surface is a single Python dict whose JSON serialization is the wire format.

## Module-level Changes

### `brain_ds/ui/render_context.py`

Additive surgery in one file:

- Add module-level constant: `CONTRACT_VERSION = "1.0.0"`.
- Add public dataclass: `WorkspaceContext(root: str, graph_path: str)`.
- Public signature evolves to:
  ```python
  def build_render_context(
      graph: Graph,
      workspace: WorkspaceContext | None = None,
  ) -> dict: ...
  ```
  When `workspace is None`, the function synthesizes the OQ-C fallback internally (`project="default"`, root=cwd, graph="(unknown)", displayPath=""), logs the stderr warning once per process, and proceeds. This preserves every existing call site in `tests/test_viewer.py` that invokes `build_render_context(Graph.from_v1(payload))` with a single positional arg. (See ADR-CV-002.)
- Add internal helpers (all pure, all deterministic):
  - `_compute_node_score(node_id, adjacency_or_incident_edges) -> float`
  - `_compute_node_updated_at(node, incident_evidence_ids, evidence_records, fallback: str) -> str`
  - `_compute_neighbor_count(node_id, adjacency) -> int`
  - `_compute_workspace_meta(workspace: WorkspaceContext | None) -> dict`
- Inject at root: `"contract_version": CONTRACT_VERSION`.
- Inject under `meta`: `"workspace": _compute_workspace_meta(workspace)`.
- Inject per node: `score`, `updated_at`, `neighbor_count`.
- Adjacency is already computed in this file; reuse it. Incident-edge enumeration must be done in a single O(E) pass and cached in a `defaultdict(list)` to avoid O(N*E) blow-up.

### `brain_ds/ui/cli.py`

- Add `--root <path>` optional flag to the `ui` subparser. Default: cwd.
- Resolve `WorkspaceContext`:
  ```python
  graph_path_resolved = json_path.resolve()
  root_resolved = Path(args.root).resolve() if args.root else Path.cwd().resolve()
  workspace = WorkspaceContext(root=str(root_resolved), graph_path=str(graph_path_resolved))
  ```
- Pass `workspace` through to `render_graph_file` (new kwarg) and onward to `build_render_context`.
- When stdin mode (`graph_json == "-"`) is active and `--root` is not passed, fall back to cwd. No special-casing — the OQ-C synthesizer inside `build_render_context` covers the case where derivation can't produce a meaningful `project`.

### `brain_ds/ui/viewer.py`

- `render_graph_file(...)` and `render_graph_data(...)` gain an optional `workspace: WorkspaceContext | None = None` kwarg.
- The kwarg is threaded into `build_render_context(graph, workspace=workspace)`.
- When the caller does not pass `workspace`, the call site passes `None` and lets `build_render_context` handle the OQ-C fallback. This keeps `viewer.py` ignorant of fallback policy — single owner of the rule.

### `brain_ds/ui/src/contract_version.ts` (NEW, 3–5 lines)

```ts
// Auto-mirrors brain_ds/ui/render_context.py::CONTRACT_VERSION.
// Drift is enforced by tests/test_contract_version_sync.py.
export const CONTRACT_VERSION = "1.0.0";
```

Not imported by any runtime file in this change. Phase B / C consumers will import this constant for compile-time guards.

### Tests — new

- `tests/test_render_context_contract.py` — field-presence + correctness + boundary tests (full list owned by spec phase).
- `tests/test_render_context_golden.py` — 7 frozen JSON goldens, one per entity supertype, ≤4 nodes each.
- `tests/fixtures/render_context/<supertype>.json` — golden RENDER_CONTEXT outputs.
- `tests/fixtures/graph_inputs/<supertype>.json` — minimal graph inputs that produce them.
- `tests/test_contract_version_sync.py` — reads both `brain_ds/ui/src/contract_version.ts` and `brain_ds.ui.render_context.CONTRACT_VERSION`; regex-extracts the TS literal (`/CONTRACT_VERSION\s*=\s*"([^"]+)"/`); asserts equality. No node toolchain, no TS parser — one regex on the text.

### Tests — existing (preserved)

- `tests/test_viewer.py` — every existing assertion stays green because:
  - Signature change is backwards-compatible (`workspace` defaults to `None`).
  - All new node fields are ADDED, no existing keys renamed/retyped/removed.
  - Existing assertions like `context["edges"][0]["score"] == float(edge.weight)` are untouched (edge-level score preserved).
  - The "exactly these keys" style is NOT used anywhere in `test_viewer.py` for nodes — current assertions check specific keys' presence/value, which are additive-safe.
  - One risk: existing tests trigger the `workspace is None` path → the stderr warning will fire during tests. Mitigation: warning is emitted via stdlib `logging.warning(...)` (NOT `print(..., file=sys.stderr)`) so test runs stay quiet by default and a test can `assertLogs(...)` when checking the fallback.
- `tests/test_graph_contract.py` — zero changes. New fields are render-time-derived; Node dataclass is unchanged.

## Key Algorithms

### Node score

```
def _compute_node_score(node_id, incident_edges_for_node) -> float:
    if not incident_edges_for_node:
        return 0.0
    return max(float(edge.weight or 0.0) for edge in incident_edges_for_node)
```

Edge cases:
- Isolated node (no incident edges) → `0.0`.
- Single incident edge with `weight=None` → `max(0.0)` = `0.0`.
- Multiple incident edges → max of all weights (None treated as 0.0).
- Self-loops (if they slip past validation) → contribute once.
- Source of truth: `brain_ds/scoring/engine.py` already computes `Edge.weight`. `node.score` is a derived VIEW over those weights, not a new domain concept. (Proposal said `scoring_engine.py`; actual path is `scoring/engine.py`.)

### Node updated_at

```
def _compute_node_updated_at(node, evidence_records, fallback: str) -> str:
    incident_timestamps = [
        evidence_records[eid]["timestamp"]
        for eid in (node.evidence_ids or [])
        if eid in evidence_records and evidence_records[eid].get("timestamp")
    ]
    if not incident_timestamps:
        return fallback  # caller supplies meta.generated_at; second-fallback resolved in spec
    return max(incident_timestamps)  # ISO-8601 strings sort lexicographically when canonical
```

Edge cases:
- Node with `evidence_ids=None` → fallback path.
- Node with `evidence_ids=[]` → fallback path.
- All referenced evidence entries have empty `timestamp` → fallback path.
- Mixed: some evidence with empty timestamp, some with valid → `max` of the non-empty subset.

**Spec-phase resolution required**: when `fallback` itself is the empty string (default for `Graph.generated_at`), the spec must lock the second-level fallback. Candidates: pass-through empty string, sentinel `"1970-01-01T00:00:00Z"`, or current-process time. Pseudocode accepts `fallback: str` as a parameter so the spec answer plugs in at the call site without touching this helper.

OQ-A (ISO-8601 precision) is also a spec-phase question; this helper is format-agnostic — it just compares strings.

### meta.workspace derivation

```
def _compute_workspace_meta(workspace: WorkspaceContext | None) -> dict:
    if workspace is None:
        # OQ-C unified fallback: library user called build_render_context directly,
        # OR CLI was invoked without --root in an unrecognizable cwd.
        logging.warning(
            "build_render_context: no WorkspaceContext supplied; "
            "synthesizing project='default' fallback."
        )
        return {
            "root": str(Path.cwd().resolve()),
            "displayPath": "",
            "project": "default",
            "graph": "(unknown)",
        }

    root = Path(workspace.root).resolve()
    graph_path = Path(workspace.graph_path).resolve()

    # displayPath: POSIX-style relative path from root to graph_path.
    try:
        rel = graph_path.relative_to(root)
        display_path = rel.as_posix()
    except ValueError:
        # graph_path lies outside root → degrade gracefully
        display_path = graph_path.as_posix()

    # project: depth-1 segment under root, or root.name if graph_path == root or depth 0.
    parts = display_path.split("/") if display_path else []
    if len(parts) >= 2:
        project = parts[0]
    else:
        project = root.name or "default"

    graph_stem = graph_path.stem or "(unknown)"

    return {
        "root": str(root),
        "displayPath": display_path,
        "project": project,
        "graph": graph_stem,
    }
```

Edge cases LOCKED:
- `graph_path == root/some.json` (depth 0) → `project = root.name`, `displayPath = "some.json"`.
- `graph_path == root/proj1/some.json` (depth 1) → `project = "proj1"`, `displayPath = "proj1/some.json"`.
- `graph_path == root/proj1/sub/some.json` (depth 2+) → `project = "proj1"` (depth-1 segment wins, deeper folders collapse).
- `graph_path` lies outside `root` → `displayPath` becomes absolute POSIX path, `project = root.name or "default"`.
- `workspace is None` → OQ-C fallback (above).

## Public API

### Python

```python
# brain_ds/ui/render_context.py
CONTRACT_VERSION: str = "1.0.0"

@dataclass
class WorkspaceContext:
    root: str        # absolute filesystem path to the workspace root
    graph_path: str  # absolute filesystem path to the graph JSON

def build_render_context(
    graph: Graph,
    workspace: WorkspaceContext | None = None,
) -> dict: ...
```

Return-dict surface deltas vs current shape (additive only):

```
{
  "contract_version": "1.0.0",                           # NEW (root)
  "meta": {
    "org": ...,                                          # existing
    "generated_at": ...,                                 # existing
    "node_count": ...,                                   # existing
    "edge_count": ...,                                   # existing
    "workspace": {                                       # NEW
      "root": "...",
      "displayPath": "...",
      "project": "...",
      "graph": "..."
    }
  },
  "nodes": [{
    "id": ..., "label": ..., "type": ..., "supertype": ...,
    "color": ..., "title": ..., "parent_id": ..., "depth": ..., "component_id": ...,
    "score": 0.82,                                       # NEW
    "updated_at": "2026-05-14T00:00:00Z",                # NEW
    "neighbor_count": 3                                  # NEW
  }],
  "edges": [...],            # unchanged (edge.score still present)
  "type_groups": [...],      # unchanged
  "adjacency": {...},        # unchanged
  "detail_index": {...},     # unchanged
  "evidence_records": {...}, # unchanged
  "ui_defaults": {...}       # unchanged
}
```

### TypeScript

```ts
// brain_ds/ui/src/contract_version.ts
export const CONTRACT_VERSION = "1.0.0";
```

Declared shapes (read-only consumers — Phase B/C will wire these):

```ts
// Already accessible via window.RENDER_CONTEXT
interface WorkspaceMeta {
  root: string;
  displayPath: string;
  project: string;
  graph: string;
}

interface NodeWithScore {
  // existing fields ...
  score: number;          // 0.0..1.0 inclusive
  updated_at: string;     // ISO-8601 string (precision locked in spec OQ-A)
  neighbor_count: number; // non-negative int
}

// Placeholder — Phase C will expand (OQ-D LOCKED below).
interface AiActionPayload {
  action_id: string;     // identifier from S2 inspector AI Actions accordion
  node_id: string;       // RENDER_CONTEXT.nodes[*].id of the focused node
  request_id: string;    // client-generated uuid for correlation across async MCP roundtrip
  payload: object;       // stub: empty object in v1.0.0; Phase C populates
}

// Placeholder signature — runtime wiring out of scope for this change.
type OnAiAction = (payload: AiActionPayload) => void;
```

## Locked Open Questions

### OQ-C (LOCKED) — Missing `--root` and unrecognizable cwd
When `--root` is not passed AND cwd has no recognizable project structure (no parent that matches a meaningful workspace heuristic), the synthesizer emits:
```
meta.workspace = { root: <cwd>, displayPath: "", project: "default", graph: "(unknown)" }
```
A single stderr warning is logged via stdlib `logging.warning(...)`. The same fallback is invoked when `build_render_context` is called WITHOUT a `WorkspaceContext` argument (library use). One mechanism, one warning, one fallback shape.

### OQ-D (LOCKED) — `onAiAction(actionId, nodeId)` placeholder shape
Minimum viable payload for v1.0.0:
```ts
{
  action_id: string,   // matches S2 AI-Actions accordion action ids
  node_id: string,     // RENDER_CONTEXT.nodes[*].id
  request_id: string,  // uuid v4, client-generated, used to correlate MCP responses
  payload: object      // stub — empty in v1.0.0
}
```
The runtime function signature stays `onAiAction(payload: AiActionPayload) => void`. The original two-arg shape (`actionId, nodeId`) is retained as a callable convenience for the S2 inspector mock today; the structured object is the wire shape. Phase C will MINOR-bump if it adds non-required fields to `payload`, or MAJOR-bump if `payload` becomes required-typed.

### OQ-E (LOCKED) — `contract_version` exposure to TS
A constants module lives at `brain_ds/ui/src/contract_version.ts` (3–5 lines, no imports, just `export const CONTRACT_VERSION = "1.0.0";`). Sync mechanism: `tests/test_contract_version_sync.py` reads the TS file as text, regex-extracts `/CONTRACT_VERSION\s*=\s*"([^"]+)"/`, and asserts equality with `brain_ds.ui.render_context.CONTRACT_VERSION`. No node toolchain. No TS parser. One regex, two file reads. Drift fails CI loudly.

OQ-A (ISO-8601 precision) and OQ-B (rounding boundary) are spec-phase territory and intentionally not resolved here.

## Trade-offs Considered

| Considered | Chosen | Why |
|------------|--------|-----|
| `WorkspaceContext` required vs optional | Optional (`None` triggers OQ-C fallback) | Preserves every existing `tests/test_viewer.py` call site; single owner of fallback policy; library users don't need to know about CLI concepts |
| `node.score` as Node dataclass field vs render-derived | Render-derived | Zero JSON schema churn; reversible; future NodeScoringEngine can replace the source behind same JSON key (PATCH bump) |
| `contract_version` as HTTP-style header vs JSON root field | Root field | No HTTP layer exists; root field is JSON-native; one less concept |
| `meta.workspace` as new JSON schema field vs filesystem-derived | Filesystem-derived | .exe target means "any project, anywhere"; zero JSON schema change; Section 1 mock already uses `displayPath` |
| Sync TS via codegen vs hand-mirrored + test | Hand-mirrored + regex test | 3-line file; no toolchain; identical maintenance cost; codegen would require node in the dev loop |
| Print warning to stderr directly vs stdlib logging | Stdlib logging | Tests can `assertLogs(...)`; library callers can configure handlers; CLI default behaviour unchanged |
| Per-node O(E) edge enumeration vs single-pass adjacency cache | Single-pass cache (`defaultdict(list)`) | Avoids O(N*E) cost on dense graphs; matches existing adjacency-build pattern in `render_context.py` |

## ADRs (lightweight)

### ADR-CV-001: `contract_version` is a JSON root field, not an HTTP header or sidecar
**Decision**: Inject `"contract_version": "1.0.0"` at the top of the returned dict.
**Why**: There is no HTTP layer. The contract surface IS the JSON dict. A root field is JSON-native, trivially inspected by both Python and TS, and survives file:// caching unchanged.
**Rejected**: An HTTP header (no server), a sidecar file (extra I/O, extra desync surface), a comment in `meta` (humans skip comments).

### ADR-CV-002: `WorkspaceContext` flows via optional constructor parameter, with `None` as the unified OQ-C fallback
**Decision**: `build_render_context(graph, workspace: WorkspaceContext | None = None) -> dict`. `None` triggers the OQ-C synthesizer internally.
**Why**: A required `workspace` parameter would break every existing `tests/test_viewer.py` call site (~10 invocations of `build_render_context(Graph.from_v1(payload))`). Module-level state (set-once-before-call) would be untestable and racy in parallel tests. The optional-with-fallback pattern preserves library ergonomics, lets the CLI supply the real workspace, and gives library callers a predictable degradation path.
**Rejected**: Module-level singleton (un-thread-safe, un-test-isolatable); required parameter (breaks acceptance signal #2 of the proposal); ContextVar (overkill, harder to discover).

### ADR-CV-003: `node.score` is a render-time-derived view, not a Node dataclass field
**Decision**: `node.score = max(incident_edge.weight)` computed inside `build_render_context`. Node dataclass remains unchanged.
**Why**: Zero churn to `brain_ds/ontology/graph_model.py` and zero churn to `tests/test_graph_contract.py`. Reversible. A future NodeScoringEngine can replace the source behind the same JSON key — clients see a PATCH bump, not a MAJOR one.
**Rejected**: Adding `score: float` to `Node` (forces JSON schema change, forces ingest-time computation, forces a domain decision before it's mature).

### ADR-CV-004: `contract_version` sync between Python and TS is enforced by a dedicated regex test, not by a build step
**Decision**: `tests/test_contract_version_sync.py` reads the TS file as text, regex-extracts the literal, asserts equality with the Python constant.
**Why**: One regex, two file reads, zero toolchain. Codegen or a node-based parser would add a build dependency to a repo that explicitly avoids them (.exe target, networkx-only constraint). The regex is tight (`/CONTRACT_VERSION\s*=\s*"([^"]+)"/`) and the TS file is human-owned and 3 lines long — drift surface is essentially zero.
**Rejected**: ts-morph parser (heavy), codegen script (adds dev-loop dependency), no enforcement (relies on memory).

### ADR-CV-005: `onAiAction` payload stays minimal in v1.0.0; Phase C may MAJOR-bump
**Decision**: v1.0.0 payload = `{ action_id, node_id, request_id, payload: {} }`. The runtime function signature is `onAiAction(payload: AiActionPayload) => void`.
**Why**: This change locks the contract shape so backend and UI can converge without retrofit. Phase C will know the full requirements (deltas, streaming, auth) and will be free to MAJOR-bump `contract_version` if needed. Today we pay for one extra field (`request_id`, `payload`) and gain a stable shape.
**Rejected**: Locking the full Phase C payload now (premature); leaving it un-typed (defeats the purpose of a contract).

## Risks specific to this design

1. **`logging.warning` noise in test runs.** Existing `tests/test_viewer.py` calls `build_render_context(Graph.from_v1(payload))` with no workspace ~10 times. Each call now triggers the OQ-C fallback warning. Mitigation: emit via stdlib `logging` (NOT print); test logging config does not promote WARNING to stderr by default; one explicit test asserts the warning fires when expected.
2. **OQ-A spec resolution interacts with `_compute_node_updated_at`.** The helper takes `fallback: str` as a parameter so the spec can plug in either pass-through empty string or a sentinel without touching this design. Flagged for spec phase.
3. **`graph_path.relative_to(root)` raises `ValueError` on Windows when paths are on different drives.** Caught explicitly; degraded path falls back to absolute POSIX form. Documented in pseudocode.
4. **`Path.cwd()` at OQ-C fallback time vs. CLI-resolution time.** The fallback uses `Path.cwd()` lazily inside `build_render_context`; if the CLI has already chdir'd, this could surprise. Mitigation: CLI resolves cwd ONCE in `cli.py` and passes an explicit `WorkspaceContext`. The lazy `cwd()` path is only for library users who didn't supply a workspace — they get whatever cwd happened to be.
5. **Single-pass incident-edge cache memory.** For graphs with N nodes and E edges, the cache is O(E). Acceptable — existing adjacency map is the same size and is already built.
6. **`max(incident_timestamps)` correctness depends on canonical ISO-8601.** OQ-A locks the format in spec phase. If timestamps in evidence are non-canonical (different precisions, mixed timezones), lexicographic max may not match chronological max. Mitigation: spec enforces canonical form, and existing fixtures already use `YYYY-MM-DDTHH:MM:SSZ` shape.

## Estimated changed lines (rough — sdd-tasks owns the forecast)

| File | Estimate (added) |
|------|-----:|
| `brain_ds/ui/render_context.py` | +60..90 |
| `brain_ds/ui/cli.py` | +25..40 |
| `brain_ds/ui/viewer.py` | +10..20 |
| `brain_ds/ui/src/contract_version.ts` (NEW) | +3..5 |
| `tests/test_render_context_contract.py` (NEW) | +120..180 |
| `tests/test_render_context_golden.py` (NEW) | +50..80 |
| `tests/test_contract_version_sync.py` (NEW) | +20..30 |
| `tests/fixtures/render_context/*.json` (7 NEW) | +80..120 |
| `tests/fixtures/graph_inputs/*.json` (7 NEW) | +40..70 |
| **TOTAL (rough)** | **~410..635** |

**Workload note**: total lands at or above the 400-line PR budget, but test files dominate (~310..480 of the total). Production code is ~98..155 lines. The Review Workload Forecast in `sdd-tasks` owns the chained-PR decision; flag if the orchestrator should consider `size:exception` or split tests into a follow-up PR.

## Engram trail

- Exploration: engram #878 / openspec/changes/backend-ui-contract/exploration.md
- Proposal: engram #879 / openspec/changes/backend-ui-contract/proposal.md
- Design: this file + engram topic_key `sdd/backend-ui-contract/design`
- Next phases: sdd-tasks (after spec also completes)
