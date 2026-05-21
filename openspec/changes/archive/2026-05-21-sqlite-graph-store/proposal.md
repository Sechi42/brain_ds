# Proposal: sqlite-graph-store

**Date**: 2026-05-21
**Change**: `sqlite-graph-store`
**Phase**: propose
**Roadmap**: backend-migration-to-new-ui — Phase A · #3 (observation #875)
**Exploration**: engram #939 / `openspec/changes/sqlite-graph-store/exploration.md`
**Artifact store**: hybrid (file + engram `topic_key sdd/sqlite-graph-store/proposal`)

---

## Intent

Introduce SQLite as the canonical project-scoped persistence layer for `brain_ds`. Today the only durable representation of a graph is a single hand-edited JSON file; the runtime parses it, derives a render context, and emits HTML. This change adds `brain_ds/store/` — a thin, stdlib-only persistence package — that owns nodes, edges, evidence, clusters, embeddings, and per-graph metadata behind a versioned schema. The store unblocks Phase A · #4 `project-scoped-runtime` (single `uv run brain_ds ui` against a per-project DB), Phase B (`desktop-shell`, `.exe` installer carrying the same DB format), and Phase C (`mcp-server`, agent writes, embedding-based search). Doing it now — before #4 — is what lets the launcher import once, query incrementally, and stop treating the JSON file as the source of truth.

## Problem

- The JSON file is the only persistent representation of a graph (`brain_ds/ontology/graph_model.py`). There is no store, no cache, no per-project state.
- Phase A · #4 wants a single `uv run brain_ds ui` launcher pointed at a project directory. Without a store it has nowhere to read/write incremental state, no multi-graph workspace concept, and no way to isolate projects.
- Phase B (desktop / `.exe`) needs a bundle-friendly, file-local format. SQLite + `sqlite3` stdlib is the lowest-cost option and survives PyInstaller / Tauri sidecar packaging without extra DLLs.
- Phase C (MCP, agent edits, manual node editing) requires a write surface with ACID semantics. JSON file rewrites are not a viable write target for concurrent agents.
- Net-new concepts: **clusters and embeddings do not exist anywhere in the codebase today** (engram #940 — zero references in any Python, TypeScript, or HTML file). Postponing means designing them under pressure later, when MCP writes are already landing.
- Deferring is strictly worse: every later phase grows a JSON-only fallback path that we eventually rip out. Better to land the store first and let #4 build directly against it.

## Scope (In)

- New package `brain_ds/store/` with:
  - `__init__.py` — public re-exports (`GraphStore`, `StoreError`, `SchemaVersionMismatch`).
  - `schema.py` — DDL strings + index definitions, one source of truth.
  - `migrations.py` — ordered migration functions keyed by integer `schema_version`, applied on connect.
  - `graph_store.py` — `GraphStore` class wrapping a single `sqlite3.Connection`.
  - `repository.py` — per-entity query helpers (nodes / edges / evidence / clusters / embeddings) used by `GraphStore` and tests.
  - `models.py` — store-internal dataclasses or `TypedDict`s for rows (kept distinct from `ontology/graph_model.py` to avoid coupling).
- SQLite schema for 8 tables (full sketch below): `graphs`, `nodes`, `edges`, `evidence`, `clusters`, `cluster_members`, `embeddings`, `store_meta`.
- Versioned migrations: `store_meta(key, value)` row `schema_version=N`; migrations are an ordered list of `migrate_to_N(conn)` functions; on connect, the store applies every migration whose target version is strictly greater than the current `schema_version`. Initial version = 1.
- `GraphStore` lifecycle: one `sqlite3.Connection` per instance, opened with `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`, `PRAGMA synchronous=NORMAL`. Explicit `close()` and `__enter__` / `__exit__`.
- Core public methods:
  - `import_json(path: str | Path | dict) -> graph_id` — parse via `Graph.from_v1()`, write rows transactionally, return new `graph_id`.
  - `export_json(graph_id: str) -> dict` — reconstruct a v2.0.0-compatible dict from rows.
  - `save_graph(graph: Graph) -> graph_id` — upsert from an in-memory `Graph`.
  - `load_graph(graph_id: str) -> Graph` — hydrate the in-memory dataclass tree.
  - `query_nodes(graph_id, *, type=None, supertype=None, parent_id=None) -> list[NodeRow]`.
  - `query_edges(graph_id, *, source=None, target=None) -> list[EdgeRow]`.
  - `query_clusters(graph_id, *, parent_id=None) -> list[ClusterRow]`.
  - `search_evidence(graph_id, *, text: str | None=None, source: str | None=None) -> list[EvidenceRow]`.
  - `upsert_embedding(graph_id, target_type, target_id, model, vector: Sequence[float]) -> None`.
  - `nearest_embeddings(graph_id, target_id, k: int) -> list[tuple[str, float]]` — in-memory cosine over the full BLOB scan.
- JSON columns for nested fields: `nodes.details`, `nodes.card_sections`, `nodes.editable_fields`, `nodes.evidence_ids`, `edges.reasons`, `edges.evidence_ids`, `clusters.metadata`, `evidence.provenance`.
- Multi-graph isolation: every entity row carries a `graph_id` FK to `graphs(id)` with `ON DELETE CASCADE`.
- Embeddings: `BLOB` of packed `float32` + `dimensions: INTEGER`; cosine similarity computed in Python using `array.array("f")` or `struct.unpack`. No ANN index in this change.
- TDD-first (strict TDD active for this project, runner `uv run python -m unittest discover -s tests`):
  - In-memory SQLite (`:memory:`) fixtures per test for isolation.
  - Failing test BEFORE implementation for every public method on `GraphStore`.
  - CRUD coverage for all 8 tables.
  - Migration test: open a v0 DB (no `store_meta`), assert migrations apply in order, assert idempotency on second connect.
  - JSON round-trip: `import_json(fixture) → export_json(graph_id) == fixture` modulo documented derived fields.
  - Contract version mismatch detection: `graphs.contract_version` mismatch raises a typed error.

## Scope (Out / Non-Goals)

- **No MCP server surface.** Owned by Phase C · #7 `mcp-server`.
- **No HTTP server, no CLI changes, no launcher.** Owned by #4 `project-scoped-runtime`.
- **No layout, template, or UI changes.** `template_renderer.py`, `graph_viewer.html`, and `src/` TypeScript are untouched.
- **No SQLAlchemy, no Alembic, no third-party ORM.** Stdlib `sqlite3` only.
- **No vector index** (no FAISS, hnswlib, sqlite-vss, DuckDB). Full BLOB scan is acceptable below ~10k embeddings, which is the project-scale ceiling.
- **No multi-user / concurrent-writer hardening.** WAL gives us safe single-writer semantics for the desktop-app scope; multi-writer is a Phase C concern.
- **No `ScoringEngine` changes.** Factors and weights stay exactly as they are.
- **No persistence of render-derived fields.** `node.score`, `neighbor_count`, `component_id` are not stored — see ADR-1.
- **No change to the JSON interchange format.** The store consumes/produces v2.0.0 JSON; humans still edit JSON when they want to.
- **No change to `render_context.py` wiring.** If a follow-up wires the store into the render path, it lands in #4 behind a feature flag.

## Approach

Approach 1 from exploration #939 — **stdlib `sqlite3` + manual DDL + ordered Python migrations + JSON columns + float32 BLOB embeddings.** Rationale:

- Zero new dependencies: keeps the networkx-only constraint and the `.exe` packaging story intact (sqlite3 ships with embedded Python).
- The schema is small (8 tables, ~5 indices). An ORM is overkill and would obscure the migration logic that #4 and Phase B inherit.
- JSON columns keep the ontology flexible — `Node.details`, `Edge.reasons`, etc. evolve without DDL churn.
- BLOB embeddings keep the schema lean and avoid the ANN dependency surface. Cosine over <10k vectors is sub-millisecond in pure Python.
- `:memory:` SQLite makes the test suite genuinely fast and hermetic — strict TDD becomes practical, not aspirational.
- Clean handoff boundary for #4: the launcher gets `GraphStore(path)` and uses it; nothing leaks beyond the `store/` package.

## Architecture Decisions

### ADR-1 — Render-derived fields are NOT persisted

**Context**: `node.score`, `neighbor_count`, and `component_id` are derived at render time in `build_render_context()` (locked by change #1 `backend-ui-contract`). Tempting to denormalize them onto `nodes` to speed up the UI.

**Decision**: Do not persist them in this change. They are functions of edges/evidence and a network-wide WCC pass; they belong to the render layer.

**Consequences**:
- The store stays a pure data layer; no business logic leaks into rows.
- Render must recompute on every load — acceptable at project scale.
- If MCP writes in Phase C make caching worth the complexity, revisit with a materialized view or a `node_render_cache` table.

### ADR-2 — Migrations are ordered Python functions, not Alembic

**Context**: We need versioned schema evolution but cannot take a third-party dependency.

**Decision**: `migrations.py` exports `MIGRATIONS: list[Callable[[sqlite3.Connection], None]]` where index `i` migrates from version `i` to version `i+1`. `store_meta.schema_version` is the source of truth. On connect, apply every migration whose target version is strictly greater than the current value, inside a single transaction. Initial schema is `migrate_to_1`.

**Consequences**:
- Trivial to test (open `:memory:`, walk versions, assert end state).
- Reversibility is per-migration: irreversible migrations are explicitly documented; we do not promise a generic down path.
- Adding a migration is a code-review concern, not a config concern.

### ADR-3 — Embeddings are packed float32 BLOBs with in-Python cosine

**Context**: We need vector storage but cannot pull FAISS / hnswlib / sqlite-vss into the `.exe`.

**Decision**: `embeddings.vector` is `BLOB` of packed `float32`; `embeddings.dimensions` stores the length. `nearest_embeddings()` does a `SELECT ... WHERE graph_id=?` and computes cosine in Python.

**Consequences**:
- O(n) per query — fine at project scale (the design ceiling is ~10k embeddings).
- If Phase C needs ANN, we add a sibling `embeddings_index` table and a pluggable backend; the schema does not need to change.
- We pin `dimensions` per row, so mixed-dim queries fail loud, not silently.

### ADR-4 — One SQLite connection per `GraphStore`, explicit lifecycle, WAL on

**Context**: Multiple connections per process complicate WAL recovery and add surprise contention.

**Decision**: Each `GraphStore` instance owns exactly one `sqlite3.Connection`, opened with `journal_mode=WAL`, `foreign_keys=ON`, `synchronous=NORMAL`. The class is a context manager; `close()` is idempotent. Re-entrant writes are not supported — callers serialize.

**Consequences**:
- Single-writer model is explicit, not accidental.
- WAL files (`-wal`, `-shm`) appear next to the DB — documented for desktop packaging in #4 / Phase B.
- Process termination is safe; the WAL replays on next open.

### ADR-5 — JSON v2.0.0 remains the user-facing interchange

**Context**: The JSON file is what humans edit and what fixtures freeze. The store should not steal that role.

**Decision**: `import_json(path|dict)` and `export_json(graph_id)` are first-class methods. The store is NEVER the source of truth for hand-edited test fixtures. CI fixtures stay in JSON.

**Consequences**:
- Round-trip is a first-class test (`import → export ≡ input` modulo derived fields).
- Backwards path stays open for users without a desktop install.
- Schema evolution of the JSON format remains owned by `ontology/`, not `store/`.

### ADR-6 — Clusters are cross-cutting; membership is M:N with optional weight

**Context**: Net-new concept (engram #940). Clusters logically intersect ontology — any node can belong to multiple clusters regardless of its `EntityType`.

**Decision**: A node belongs to zero or more clusters via `cluster_members(cluster_id, node_id, weight)`. Membership is not coupled to `EntityType`. Clusters may nest via optional `clusters.parent_id`.

**Consequences**:
- Clusters can be used for tags, communities, topics, BRD groupings — no premature taxonomy.
- A node can be in disjoint clusters; UI consumers pick which projection to render.
- Migration cost to a stricter model later is a single backfill.

### ADR-7 — Every entity table carries `graph_id`

**Context**: Phase B is "any project, anywhere"; Phase C is multi-graph agent writes. We need isolation from day one.

**Decision**: `nodes`, `edges`, `evidence`, `clusters`, `cluster_members`, `embeddings` all carry `graph_id INTEGER NOT NULL REFERENCES graphs(id) ON DELETE CASCADE`. All indices that matter include `graph_id` as the leading column.

**Consequences**:
- Per-project / per-workspace isolation comes for free.
- Cross-graph queries are explicit (require a join through `graphs`).
- Deleting a graph is a single `DELETE FROM graphs WHERE id = ?` and cascades cleanly.

---

## Schema Sketch

> Final column nullability and exact types are finalized in `sdd-spec`. This is the architectural shape.

### `graphs` — one row per imported graph (workspace/project metadata)

| column | type | note |
|---|---|---|
| `id` | `INTEGER PRIMARY KEY` | autoincrement |
| `workspace_root` | `TEXT NOT NULL` | absolute path of the workspace root |
| `workspace_path` | `TEXT NOT NULL` | POSIX-style relative path of the source JSON |
| `project` | `TEXT NOT NULL` | depth-1 segment, matches contract #1 `meta.workspace.project` |
| `org` | `TEXT` | from `Graph.org` |
| `schema_version` | `TEXT NOT NULL` | JSON `Graph.schema_version`, e.g. `"2.0.0"` |
| `contract_version` | `TEXT NOT NULL` | render contract version (`"1.0.0"` from change #1) |
| `node_count` | `INTEGER NOT NULL DEFAULT 0` | denormalized cache |
| `edge_count` | `INTEGER NOT NULL DEFAULT 0` | denormalized cache |
| `imported_from` | `TEXT` | absolute path to source JSON, if any |
| `generated_at` | `TEXT` | original JSON `generated_at` |
| `created_at` | `TEXT NOT NULL` | ISO-8601 UTC |
| `updated_at` | `TEXT NOT NULL` | ISO-8601 UTC |

### `nodes`

| column | type | note |
|---|---|---|
| `id` | `TEXT NOT NULL` | domain id from JSON |
| `graph_id` | `INTEGER NOT NULL REFERENCES graphs(id) ON DELETE CASCADE` |
| `label` | `TEXT NOT NULL` |
| `type` | `TEXT NOT NULL` | one of 13 `EntityType` values |
| `supertype` | `TEXT NOT NULL` | one of 7 supertypes |
| `details` | `TEXT` | JSON |
| `card_sections` | `TEXT` | JSON list of `CardSection` |
| `editable_fields` | `TEXT` | JSON |
| `evidence_ids` | `TEXT` | JSON list |
| `layout_hint` | `TEXT` |
| `parent_id` | `TEXT` | nullable; spec phase pins FK behavior |
| `depth` | `INTEGER` |
| `created_at` | `TEXT NOT NULL` |
| `modified_at` | `TEXT NOT NULL` |
| PRIMARY KEY | `(graph_id, id)` |

### `edges`

| column | type | note |
|---|---|---|
| `edge_id` | `TEXT NOT NULL` |
| `graph_id` | `INTEGER NOT NULL REFERENCES graphs(id) ON DELETE CASCADE` |
| `source` | `TEXT NOT NULL` |
| `target` | `TEXT NOT NULL` |
| `label` | `TEXT NOT NULL` | one of 14 `RelationshipType` values |
| `weight` | `REAL NOT NULL` | 0.0–1.0 from `ScoringEngine` |
| `reasons` | `TEXT` | JSON list |
| `evidence_ids` | `TEXT` | JSON list |
| `created_at` | `TEXT NOT NULL` |
| PRIMARY KEY | `(graph_id, edge_id)` |

### `evidence`

| column | type | note |
|---|---|---|
| `id` | `TEXT NOT NULL` |
| `graph_id` | `INTEGER NOT NULL REFERENCES graphs(id) ON DELETE CASCADE` |
| `type` | `TEXT NOT NULL` |
| `source` | `TEXT NOT NULL` |
| `content` | `TEXT NOT NULL` | searchable body |
| `provenance` | `TEXT` | JSON |
| `timestamp` | `TEXT` | ISO-8601 UTC |
| PRIMARY KEY | `(graph_id, id)` |

### `clusters` (new)

| column | type | note |
|---|---|---|
| `id` | `TEXT NOT NULL` |
| `graph_id` | `INTEGER NOT NULL REFERENCES graphs(id) ON DELETE CASCADE` |
| `name` | `TEXT NOT NULL` |
| `description` | `TEXT` |
| `parent_id` | `TEXT` | nullable; self-reference within same graph |
| `metadata` | `TEXT` | JSON |
| `created_at` | `TEXT NOT NULL` |
| PRIMARY KEY | `(graph_id, id)` |

### `cluster_members` (new) — M:N

| column | type | note |
|---|---|---|
| `graph_id` | `INTEGER NOT NULL REFERENCES graphs(id) ON DELETE CASCADE` |
| `cluster_id` | `TEXT NOT NULL` |
| `node_id` | `TEXT NOT NULL` |
| `weight` | `REAL` | nullable; 0.0–1.0 if present |
| PRIMARY KEY | `(graph_id, cluster_id, node_id)` |

### `embeddings` (new)

| column | type | note |
|---|---|---|
| `id` | `INTEGER PRIMARY KEY` |
| `graph_id` | `INTEGER NOT NULL REFERENCES graphs(id) ON DELETE CASCADE` |
| `target_type` | `TEXT NOT NULL` | `"node"`, `"edge"`, `"evidence"`, `"cluster"` |
| `target_id` | `TEXT NOT NULL` |
| `model` | `TEXT NOT NULL` | embedding model identifier |
| `dimensions` | `INTEGER NOT NULL` |
| `vector` | `BLOB NOT NULL` | packed float32 |
| `created_at` | `TEXT NOT NULL` |
| UNIQUE | `(graph_id, target_type, target_id, model)` |

### `store_meta`

| column | type | note |
|---|---|---|
| `key` | `TEXT PRIMARY KEY` |
| `value` | `TEXT NOT NULL` |

Reserved keys: `schema_version` (integer-as-text), `created_at`, `last_migrated_at`.

### Required Indices

- `idx_nodes_graph` on `nodes(graph_id)`
- `idx_nodes_graph_type` on `nodes(graph_id, type)`
- `idx_nodes_graph_parent` on `nodes(graph_id, parent_id)`
- `idx_edges_graph_source` on `edges(graph_id, source)`
- `idx_edges_graph_target` on `edges(graph_id, target)`
- `idx_evidence_graph` on `evidence(graph_id)`
- `idx_evidence_graph_source` on `evidence(graph_id, source)`
- `idx_cluster_members_node` on `cluster_members(graph_id, node_id)`
- `idx_embeddings_target` on `embeddings(graph_id, target_type, target_id)`

---

## Risks & Mitigations

1. **Schema drift across phases.** Mitigation: `graphs.contract_version` per row + `store_meta.schema_version` global. `import_json` writes the current contract version; load raises `SchemaVersionMismatch` on incompatible majors. Tests pin both versions.
2. **JSON-to-store migration ambiguity.** Mitigation: `import_json` is the single ingress; round-trip test asserts lossless export for the fields the JSON owns. Render-derived fields are explicitly excluded from the round-trip oracle.
3. **Concurrent access surprises.** Mitigation: WAL + explicit single-writer contract per `GraphStore` instance, documented in the public docstring. Multi-writer is a Phase C concern.
4. **Embedding search scale.** Mitigation: full scan is fine below ~10k vectors per graph. ADR-3 leaves a clean upgrade path (sibling index table, pluggable backend).
5. **Cluster-ontology coupling pressure.** Mitigation: ADR-6 — `cluster_members` is M:N with no `EntityType` constraint. Reviewers reject any PR that adds such a constraint.
6. **Workspace metadata divergence from contract #1.** Mitigation: `graphs.workspace_root / workspace_path / project` mirror the field names from `RENDER_CONTEXT.meta.workspace`. Spec phase pins a 1:1 mapping test.
7. **Test isolation.** Mitigation: every store test opens a fresh `:memory:` DB. No shared state, no fixture files for the store layer.
8. **`.exe` bundling.** Mitigation: `sqlite3` is part of embedded Python; PyInstaller / Tauri sidecar carries no extra DLL. Verified by Phase B planning, not by this change.
9. **Render context regression** *(new risk)*. If a follow-up wires `render_context.py` to the store, the golden fixtures from change #1 may drift. Mitigation: keep the render path JSON-driven in #3; any store-backed render path lands in #4 behind a feature flag with the same golden fixtures asserted both ways.

---

## Review Workload Forecast (preliminary)

Rough line estimate for the apply phase:

| area | lines (estimate) |
|---|---|
| `brain_ds/store/__init__.py` | ~20 |
| `brain_ds/store/schema.py` | ~140 (DDL + indices for 8 tables) |
| `brain_ds/store/migrations.py` | ~80 (initial `migrate_to_1` + framework) |
| `brain_ds/store/models.py` | ~80 (row dataclasses / TypedDicts) |
| `brain_ds/store/repository.py` | ~180 (per-entity helpers) |
| `brain_ds/store/graph_store.py` | ~220 (public API + lifecycle + import/export) |
| `tests/test_graph_store.py` | ~250 (CRUD, round-trip, mismatch) |
| `tests/test_store_migrations.py` | ~80 (migration ordering + idempotency) |
| `tests/test_store_embeddings.py` | ~80 (BLOB pack/unpack + cosine) |

**Total estimate: ~1,130 changed lines.** This is well above the 400-line PR budget.

Cached delivery strategy is `ask-on-risk`. The `sdd-tasks` phase MUST surface `Chained PRs recommended: Yes` and `400-line budget risk: High`. The orchestrator will need to either chain PRs (recommended split below) or record a maintainer-approved `size:exception`.

Suggested chain (for `sdd-tasks` to confirm):
1. Schema + migrations + `store_meta` + tests for migration framework.
2. `graphs` + `nodes` + `edges` + `evidence` rows, repository + tests (no clusters, no embeddings).
3. Clusters + `cluster_members` + tests.
4. Embeddings (BLOB pack/unpack + cosine) + tests.
5. `import_json` / `export_json` round-trip + tests.

Each slice individually fits the 400-line budget.

---

## Open Questions for Spec Phase

- **OQ-1**: `nodes.parent_id` — declare as `REFERENCES nodes(graph_id, id)` with `ON DELETE SET NULL`, or leave un-enforced and validate in Python? FK self-reference plus composite PK has SQLite quirks worth pinning.
- **OQ-2**: `edges.evidence_ids` lives on edges today (JSON list). Should `evidence` rows carry a back-pointer (`evidence.edge_ids` / `evidence.node_ids`) or do we keep the relationship one-way via the JSON list? Affects `search_evidence` ergonomics.
- **OQ-3**: `embeddings.target_type` — fixed enum (`CHECK(target_type IN (...))`) or free text? Enum is safer; free text is friendlier to Phase C.
- **OQ-4**: `clusters.id` — domain-supplied string (matching node id style) or UUID generated at insert? Picks affect `import_json` ergonomics.
- **OQ-5**: `nodes.modified_at` — bumped only on explicit update via repository, or also when JSON details change on re-import? Affects how #4 surfaces "freshness" to the UI.
- **OQ-6**: Should `GraphStore.close()` checkpoint WAL (`PRAGMA wal_checkpoint(TRUNCATE)`) so the desktop installer never ships orphan `-wal` files? Pin behavior in spec.

---

## Acceptance Signals

Before `sdd-archive` closes this change and #4 `project-scoped-runtime` may start:

1. `uv run python -m unittest discover -s tests` is green; new store tests included.
2. Every public method on `GraphStore` has a failing test landed BEFORE the implementation commit (strict TDD signal, verifiable from git history).
3. `import_json(fixture) → export_json(graph_id)` round-trip is bit-exact on every JSON field the JSON contract owns (render-derived fields explicitly excluded by a documented diff oracle).
4. Migration test: opening a fresh `:memory:` DB applies `migrate_to_1`, sets `store_meta.schema_version = "1"`, and a second connect is a no-op.
5. Contract-version mismatch test: a graph row with a major-incompatible `contract_version` raises `SchemaVersionMismatch` on load.
6. Cosine similarity test: deterministic float32 vectors return the expected ordering; mixed-dimension query raises.
7. No new third-party dependency in `pyproject.toml` / `uv.lock`.
8. No edits outside `brain_ds/store/`, `tests/`, and minimal optional touches called out in spec (none required to pass #3).
9. `RENDER_CONTEXT` shape (change #1, contract_version `1.0.0`) is unchanged — verified by re-running existing render-context tests untouched.

---

## Engram Trail

- Exploration: engram #939 / `openspec/changes/sqlite-graph-store/exploration.md`
- Net-new concepts discovery: engram #940
- Roadmap anchor: engram #875 (Phase A · #3)
- Proposal: `openspec/changes/sqlite-graph-store/proposal.md` + engram `topic_key sdd/sqlite-graph-store/proposal`
- Next phases: `sdd-spec` and `sdd-design` (can run in parallel)
