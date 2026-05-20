# Exploration: backend-ui-contract

**Date**: 2026-05-20
**Change**: backend-ui-contract
**Phase**: explore
**Engram ref**: observation #878
**Roadmap**: observation #875 (Phase A · #1)

---

## Q1 — Current Backend Surface

The entire current backend-to-UI contract is a single Python function:

```
brain_ds/ui/render_context.py → build_render_context(graph: Graph) → dict
```

This dict is JSON-serialized and injected as `window.RENDER_CONTEXT` in the HTML via a string-replacement template renderer (`template_renderer.py`). There is NO HTTP server, NO API, NO database — the pipeline is pure file-in / HTML-out.

**RENDER_CONTEXT shape** (as of 2026-05-20):

```jsonc
{
  "meta": { "org", "generated_at", "node_count", "edge_count" },
  "nodes": [{ "id", "label", "type", "supertype", "color", "title", "parent_id", "depth", "component_id" }],
  "edges": [{ "from", "to", "label", "title", "width", "score" }],
  "type_groups": [{ "supertype", "types": [{ "type", "color", "count" }] }],
  "adjacency": { "node_id": ["neighbor_ids"] },
  "detail_index": { "node_id": { "node", "sections", "evidence", "relationships", "editable_fields" } },
  "evidence_records": { "evidence_id": { "id", "type", "source", "content", "provenance", "timestamp" } },
  "ui_defaults": { "hierarchical": true, "physics": false }
}
```

Key facts:
- `score` lives on EDGES (float, 0.0–1.0, computed by ScoringEngine), NOT on nodes.
- `nodes` shape has NO `score`, NO `updated_at`, NO `neighbor_count`.
- Component IDs (WCC) are computed via networkx at render time — deterministic, not stored.
- The ontology has 13 EntityTypes and 14 RelationshipTypes.
- ScoringEngine uses 6 factors: token_overlap, relationship_base, directionality, evidence_count, process_cooccurrence, explicit_reference.
- Only runtime dependency: `networkx>=3.0`. Zero web framework dependencies. This is the strongest architectural constraint.

---

## Q2 — What the New UI Expects (Per Section)

**Section 1 — Left Shell**
- Left rail: 5 icon buttons (file-tree, search, filters, AI, status). Rail width: 48px.
- L-panel: collapsible file-tree, 220–300px.
- `TreeNode { id, displayPath, type: "project"|"graph", children? }` — two-level hierarchy: organization → project → graph.json files.
- Status chip reads from `RENDER_CONTEXT.meta.org`.
- **Backend has no multi-graph / project hierarchy concept today** — one JSON = one graph.

**Section 2 — Right Shell**
- Inspector panel (280–360px), right rail (48px, gear icon).
- Inspector accordion: Properties, Metadata, Related, AI Actions.
- Properties shows: entity type, name, **score** (e.g. "Score: 0.82" — node-level).
- Metadata shows: node id, **updated date**.
- Related shows: outgoing edges with labels + inline evidence.
- AI Actions: `onAiAction(actionId, nodeId): void` — MCP bridge placeholder, not wired.

**Section 3 — Button Catalog**
- Pure visual reference. No new data requirements.

**Section 4 — Center Canvas**
- Tab strip (36px, ADR-009). `TabModel { id, label, graphId?, closeable, active }`.
- 44px LOCKED top toolbar (ADR-001) zones: nav, view, overflow, system-chrome.
- View zone metadata sourced from `RENDER_CONTEXT.meta`.
- **Multi-tab state**: each tab references a graphId — multiple graphs open simultaneously.
- Navigation history (back/forward) — client-side history stack.

**Section 5 — Node Interactions**
- 9 states: default, hover, hover-popover (PROPOSED), selected, keyboard-focus, ego-dimming (hover SHIPPED / selection PROPOSED), marquee (SHIPPED), edge-states (SHIPPED), context-menu (SHIPPED).
- Hover popover (`popover.ts:77`) reads `node.score` from `RENDER_CONTEXT.nodes` → **undefined/null today**. Score row silently dropped.
- Hover popover also wants: `node.label`, `node.type`, `node.source` (present), plus `neighbor_count` (absent).
- Ego-dimming uses `adjacency` map (SHIPPED).

---

## Q3 — Gap Analysis

| Gap | Section | Severity |
|---|---|---|
| `node.score` absent from RENDER_CONTEXT.nodes | S2 inspector, S5 popover | **HIGH** — popover silently broken |
| `node.updated_at` absent | S2 Metadata | MEDIUM — UI shows placeholder |
| `node.neighbor_count` absent | S5 popover | MEDIUM — derivable from adjacency |
| No project/graph hierarchy (TreeNode) | S1 file tree | **HIGH** — new domain concept |
| No multi-tab state contract | S4 tab strip | **HIGH** — new client-side model |
| Navigation history (back/forward) | S4 toolbar | LOW — client-side only |
| 3-column `graph_viewer.html` vs 5-column workspace shell | S4 center canvas | **HIGH** — layout migration |

**Critical gap detail**: `node.score` requires a domain decision — does not exist on `Node`, only on `Edge.weight`. ScoringEngine scores relationships (edges), not nodes. Resolution: (a) derive at render time as aggregated incident edge scores (max/mean), or (b) add pre-computed score field to Node dataclass. This is a backend data-model change, not UI wiring.

---

## Q4 — Real-time / Sync Constraints (MCP Phase C)

Current architecture is stateless after HTML generation. `onAiAction(actionId, nodeId)` is a placeholder.

Options for live updates (later, in Phase C):
- postMessage from a local HTTP server
- WebSocket
- SSE
- Poll a JSON file the MCP server writes

Any of these requires a local HTTP server or in-process Python server (acceptable if kept optional/dev-only).

**Conclusion**: MCP real-time is **out of scope** for this initial contract spec. The contract MUST define the shape of `onAiAction` payload and the delta format so both sides can converge later without retrofit.

---

## Q5 — Storage Layering Implications

Current: single JSON file per graph, no persistence layer.
UI expects: project hierarchy, tab state, navigation history.

If SQLite is introduced (Phase A #2):
- JSON input stays as user-facing import format.
- `Graph.from_v1` stays as parsing boundary.
- Store layer sits between parse and render: `JSON → Graph → Store → RENDER_CONTEXT`.
- Enables multi-graph queries, project metadata, cross-graph evidence, computed node scores.
- Node score can be computed and stored at ingest time rather than render time.
- pyproject.toml has zero database deps — `sqlite3` is stdlib so it costs nothing.

---

## Q6 — Candidate Approaches

| Approach | Description | Pros | Cons | Effort |
|---|---|---|---|---|
| **A — Enriched Static RENDER_CONTEXT** | Extend current JSON blob with missing node fields (score, updated_at, neighbor_count). No server. | Zero new deps, no infra change, TDD-friendly, .exe compatible | No real-time, no multi-graph, no tab persistence | **Low** |
| B — Local HTTP + REST API | Add Flask/FastAPI behind `--serve` flag | Real-time capable, REST standard | Adds framework deps, breaks zero-dep principle for .exe target | High |
| C — Local JSON File Bus | Python writes delta JSON files; browser polls | No server, offline | Polling fragile, not real-time | Medium |
| D — Hybrid Static + WebSocket (opt-in) | Static by default; optional WebSocket via stdlib `http.server` + `websockets` | Real-time opt-in, low extra dep | Two modes to test | High |

---

## Recommendation

**Approach A — Enriched Static RENDER_CONTEXT**, scoped tightly to close the concrete shipped-UI gaps.

Rationale:
1. Packaging constraint (networkx-only, .exe target) eliminates B and makes D conditional.
2. MCP bridge is explicitly "not wired" — real-time is NOT a blocker for the initial contract.
3. The 3 highest-severity gaps (node score, project hierarchy, 5-column layout) can all be resolved with enriched static data + client-side state, no server.
4. `node.score` can be computed at render time as `max(incident_edge_scores)` or a weighted mean — no new storage required for phase 1.
5. `neighbor_count` is derivable from the existing `adjacency` map at render time.
6. Multi-tab state is entirely client-side; the contract just needs `RENDER_CONTEXT` to be loadable per-graph independently.

**Phase boundary**: Approach A closes the data contract for the shipped UI (sections 1–5). Approach D is the right next step AFTER the contract is stable, scoped to the MCP bridge work (Phase C).

---

## Q7 — TDD Implications

- `tests/test_viewer.py` has existing assertions on RENDER_CONTEXT shape — any new fields need parallel tests.
- Existing: `ctx["edges"][0]["score"] == float(edge.weight)` — confirms score lives on edges. New node-score assertion must NOT break this.
- Golden fixture approach (frozen RENDER_CONTEXT JSON per entity type) would let each section's expected data be tested independently. Currently no section-scoped golden fixtures.
- `tests/test_graph_contract.py` covers Node/Edge roundtrip — must pass after Node field changes.
- Strict TDD: write a failing test for `RENDER_CONTEXT.nodes[*].score`, `.neighbor_count`, `.updated_at` BEFORE modifying `build_render_context`.

---

## Q8 — Open Questions (resolve in sdd-propose)

1. **Node score formula**: max of incident edge weights, weighted mean, or a separate NodeScoringEngine? (Domain question.)
2. **Node `updated_at` source**: EvidenceRecord timestamps, JSON input metadata, or user-stamped? `Node` has no timestamp field today.
3. **Project hierarchy ownership**: new JSON schema field (org → projects → graphs) or derived from filesystem path? Section 1 mock uses `displayPath` (suggests path-rooted).
4. **Multi-tab client contract**: state persisted to localStorage, sidecar file, or ephemeral (reset on reload)?
5. **RENDER_CONTEXT versioning**: add `contract_version` field to catch mismatches between backend and cached HTML?
6. **Layout migration scope**: 3-col → 5-col `graph_viewer.html` in the same PR as the data contract, or separately? Risk: combined diff likely > 400-line budget.

---

## Live Bug Found (Not Future-Tense)

`brain_ds/ui/src/interactions/popover.ts:77` reads `node.score` from `RENDER_CONTEXT.nodes`. `build_render_context()` never sets `score` on nodes — only on edges. **The score row in the hover popover is silently broken today.** Decision needed in proposal: include the fix in this change's scope, or carve out a separate hotfix.

---

## Ready for Proposal

Yes. Sufficient to drive sdd-propose. Proposal should scope to Approach A and answer open questions 1–6 before spec and design phases begin.

---

### Key Files (for sdd-propose reference)

- `brain_ds/ui/render_context.py` — `build_render_context()`: the exact function whose return shape is the contract.
- `brain_ds/ontology/graph_model.py` — `Node`, `Edge`, `Graph` dataclasses.
- `brain_ds/ui/src/interactions/popover.ts:77` — live bug (`node.score` always undefined).
- `brain_ds/ui/design/sections/` — authoritative UI expectations (sections 1–5).
- `brain_ds/ui/design/sections/ui-workspace-shell.md` — TS interfaces (`TabModel`, `TreeNode`, `FileTreeProps`) + ADRs (001, 009).
- `tests/test_viewer.py` — existing RENDER_CONTEXT contract tests.
- `pyproject.toml` — zero web framework deps; hardest constraint on any server-side approach.
