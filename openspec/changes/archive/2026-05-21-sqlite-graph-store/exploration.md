## Exploration: SQLite Graph Store

**Date**: 2026-05-21
**Change**: `sqlite-graph-store`
**Phase**: explore
**Roadmap**: backend-migration-to-new-ui — Phase A · #3 (observation #875)
**Predecessors**: backend-ui-contract ✅ archived, workspace-shell-layout-migration ✅ archived
**Artifact store**: hybrid (file + Engram topic_key `sdd/sqlite-graph-store/explore`)

---

### Current State

#### Data Flow (pre-SQLite)

```
   graph JSON file ──▶ Graph.from_v1() ──▶ build_render_context() ──▶ dict ──▶ HTML
                           │
                    Zero persistence layer
                    between parse and render
```

The graph JSON file is the **only** persistent representation. Everything else is ephemeral — rebuilt from scratch on every `brain_ds ui` invocation. There is no database, no cache, no store layer.

#### Graph Domain Model (brain_ds/ontology/graph_model.py)

| Dataclass | Fields | Notes |
|-----------|--------|-------|
| `Graph` | schema_version, org, generated_at, nodes, edges, evidence | Root container; schema_version="2.0.0" |
| `Node` | id, label, type, details, supertype, card_sections, evidence_ids, editable_fields, layout_hint, parent_id, depth, component_id | `component_id` is WCC computed at render time via networkx |
| `Edge` | source, target, label, weight, reasons, evidence_ids, edge_id | weight is float 0.0–1.0 from ScoringEngine |
| `EvidenceRecord` | id, type, source, content, provenance, timestamp | Provenance is optional dict |
| `CardSection` | title, content, icon, order | Display metadata for node detail |

13 EntityTypes (7 supertypes: actor/data/process/problem/risk/metric/solution).
14 RelationshipTypes with BASE_WEIGHTS as edge score priors.

The `Node` dataclass has **no** `score`, `updated_at`, `neighbor_count` fields. These are render-time-derived in `build_render_context()` via helper functions `_compute_node_score()`, `_compute_node_updated_at()`, `_compute_neighbor_count()`.

#### Clusters & Embeddings

**Do not exist** anywhere in the codebase. Zero references in any Python, TypeScript, or HTML file. These are entirely new domain concepts that need pure invention:
- **Cluster**: a named grouping of nodes (e.g., "Logistics Domain", "Engineering org"). May be hierarchical, overlapping, or flat.
- **Embedding**: a vector representation of a node or text chunk (float array, dim N). Used for semantic search. No existing vector storage or search capability.

#### Scoring Engine (brain_ds/scoring/)

- `ScoringEngine.score(ctx)` → `StrengthResult(weight, reasons, evidence_ids)`
- 6 configurable factors: token_overlap, relationship_base, directionality, evidence_count, process_cooccurrence, explicit_reference
- Factor weights configurable per engine instance (defaults via dict)
- Currently called during graph ingest (in `demo.py` or data pipeline), NOT at render time

---

### Affected Areas

#### New files to create

- `brain_ds/store/__init__.py` — GraphStore package
- `brain_ds/store/schema.py` — SQLite DDL (nodes, edges, evidence, clusters, embeddings, metadata)
- `brain_ds/store/migrations.py` — Schema migrations + version tracking
- `brain_ds/store/graph_store.py` — `GraphStore` class wrapping `sqlite3` connection
- `brain_ds/store/repository.py` — Repository methods: save_graph, load_graph, query_nodes, query_edges, search, etc.
- `brain_ds/store/models.py` — Store-specific dataclasses (e.g. StoredNode with stored scores)
- `tests/test_graph_store.py` — New test file for store operations
- `tests/fixtures/store/` — Test fixtures for SQLite

#### Existing files to modify

- `brain_ds/ontology/graph_model.py` — MAY add fields (node.score as stored?) — needs ADR
- `brain_ds/validation/_rules.py` — MAY validate store-backed data vs contract constraints
- `brain_ds/ui/render_context.py` — MAY add a `GraphStore` integration path (vs pure JSON ingest)
- `brain_ds/ui/cli.py` — MAY add `--serve` or project-scoped commands that auto-create SQLite store
- `brain_ds/ui/viewer.py` — MAY accept store instead of raw graph dict
- `pyproject.toml` — NO changes expected (sqlite3 is stdlib)

#### Files NOT affected

- `brain_ds/ui/template_renderer.py` — pure HTML rendering, no store awareness
- `brain_ds/ui/templates/graph_viewer.html` — UI template, no backend logic
- `brain_ds/ui/src/` — TypeScript files, no store awareness
- `brain_ds/scoring/` — scoring engine stays factor-based, just stores results differently
- `brain_ds/validation/_result.py` — result model unchanged

#### Tests affected

| Test file | Impact |
|-----------|--------|
| `tests/test_graph_contract.py` (8 tests) | If Node gains score field, roundtrip tests need additive assertions |
| `tests/test_viewer.py` (30+ tests) | No direct impact — store is a new layer below render |
| `tests/test_render_context_contract.py` (17 tests) | No direct impact — contract shape stays v1.0.0 |
| `tests/test_render_context_golden.py` (9 tests) | No direct impact — golden fixtures stay JSON-driven |
| `tests/test_scoring.py` (8 tests) | No direct impact — scoring is independent |
| `tests/test_cli.py` | May add store-aware CLI tests |
| `tests/*.py` (34 files total) | Minimally affected — store is additive |

---

### Schema Boundaries

#### Nodes Table (PROPOSED)

```sql
CREATE TABLE nodes (
    id          TEXT PRIMARY KEY,
    graph_id    TEXT NOT NULL,          -- FK to graphs table
    label       TEXT NOT NULL,
    type        TEXT NOT NULL,          -- EntityType value string
    supertype   TEXT NOT NULL,
    details     TEXT,                   -- JSON blob
    parent_id   TEXT,                   -- FK to nodes.id (optional)
    depth       INTEGER DEFAULT 0,
    score       REAL DEFAULT 0.0,       -- STORED (computed at ingest time vs render time — ADR needed)
    updated_at  TEXT,                   -- ISO-8601 UTC
    neighbor_count INTEGER DEFAULT 0,   -- cached at ingest
    component_id INTEGER,               -- WCC, computed at render OR stored
    created_at  TEXT NOT NULL,          -- store insert time
    modified_at TEXT NOT NULL           -- last update time
);
```

#### Edges Table (PROPOSED)

```sql
CREATE TABLE edges (
    id          TEXT PRIMARY KEY,       -- edge_id
    graph_id    TEXT NOT NULL,
    source      TEXT NOT NULL REFERENCES nodes(id),
    target      TEXT NOT NULL REFERENCES nodes(id),
    label       TEXT NOT NULL,          -- RelationshipType value
    weight      REAL,
    reasons     TEXT,                   -- JSON array of strings
    evidence_ids TEXT,                  -- JSON array of strings
    created_at  TEXT NOT NULL
);
```

#### Evidence Records Table (PROPOSED)

```sql
CREATE TABLE evidence (
    id          TEXT PRIMARY KEY,
    graph_id    TEXT NOT NULL,
    type        TEXT NOT NULL,
    source      TEXT NOT NULL,
    content     TEXT NOT NULL,
    provenance  TEXT,                   -- JSON blob
    timestamp   TEXT NOT NULL
);
```

#### Clusters Table (NEW — no existing model)

```sql
CREATE TABLE clusters (
    id          TEXT PRIMARY KEY,
    graph_id    TEXT NOT NULL,
    name        TEXT NOT NULL,
    description TEXT,
    parent_id   TEXT,                   -- hierarchical clustering
    metadata    TEXT,                   -- JSON blob
    created_at  TEXT NOT NULL
);

CREATE TABLE cluster_members (
    cluster_id  TEXT NOT NULL REFERENCES clusters(id),
    node_id     TEXT NOT NULL REFERENCES nodes(id),
    weight      REAL DEFAULT 1.0,       -- membership strength
    PRIMARY KEY (cluster_id, node_id)
);
```

#### Embeddings Table (NEW — no existing model)

```sql
CREATE TABLE embeddings (
    id          TEXT PRIMARY KEY,
    graph_id    TEXT NOT NULL,
    target_type TEXT NOT NULL,          -- "node" | "evidence" | "cluster"
    target_id   TEXT NOT NULL,          -- FK to the target (node/evidence/cluster id)
    model       TEXT NOT NULL,          -- embedding model identifier
    dimensions  INTEGER NOT NULL,
    vector      BLOB NOT NULL,          -- float32 array stored as bytes
    created_at  TEXT NOT NULL
);
```

#### Metadata & Migration Tracking

```sql
CREATE TABLE graphs (
    id              TEXT PRIMARY KEY,
    workspace_root  TEXT,
    workspace_path  TEXT,               -- relative displayPath
    project         TEXT,
    org             TEXT,
    schema_version  TEXT NOT NULL DEFAULT '2.0.0',
    contract_version TEXT NOT NULL DEFAULT '1.0.0',
    node_count      INTEGER DEFAULT 0,
    edge_count      INTEGER DEFAULT 0,
    imported_from   TEXT,               -- original JSON file path
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE store_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- Rows: schema_version (store schema, not graph schema), contract_version, created_at
```

---

### Approaches

#### 1. **SQLite stdlib with manual schema management**

Use Python's `sqlite3` module directly. Write DDL in a schema file, manage migrations with a version table. GraphStore class wraps connection with save/load/query methods.

| Aspect | Detail |
|--------|--------|
| **Pros** | Zero dependencies (stdlib), full control, TDD-friendly, works in .exe packaging, cross-platform |
| **Cons** | Manual migration logic, no ORM safety, JSON serialization for nested fields (details, reasons) |
| **Effort** | Medium |

#### 2. **SQLite via SQLAlchemy ORM**

Introduce SQLAlchemy as a dependency. Define declarative models, use Alembic for migrations.

| Aspect | Detail |
|--------|--------|
| **Pros** | ORM safety, auto-migrations, query builder, relationship loading |
| **Cons** | Breaks zero-dep constraint (networkx-only today), heavier .exe bundle, overkill for 5-6 tables |
| **Effort** | Medium-High |

#### 3. **JSON-file-based store (no SQLite)**

Keep current JSON file approach. Add sidecar index files (e.g., `.brain_ds/` directory with JSON-based indices).

| Aspect | Detail |
|--------|--------|
| **Pros** | Zero new dep, trivial implementation, human-readable files |
| **Cons** | No ACID, no concurrent reads/writes, no query capability, poor scaling for MCP Phase C writes, no vector storage |
| **Effort** | Low (but insufficient) |

#### 4. **DuckDB for analytical queries + SQLite for OLTP**

Two-database approach: SQLite for CRUD, DuckDB for analytical queries on embeddings and cross-graph metrics.

| Aspect | Detail |
|--------|--------|
| **Pros** | DuckDB has built-in vector similarity search, better for analytics, Parquet export |
| **Cons** | 2 dependencies (`duckdb` is not stdlib), more complex setup, heavier bundle, overkill for project-scoped runtime |
| **Effort** | High |

---

### Recommendation

**Approach 1 — SQLite stdlib with manual schema management.**

Rationale:
1. **Zero dependency cost**: `sqlite3` is part of Python stdlib since 2.5. The `pyproject.toml` currently lists only `networkx>=3.0`. SQLite adds **zero** new runtime deps — critical for the .exe packaging constraint.
2. **Simple schema**: We need 5-7 tables maximum. An ORM is overkill. Manual DDL with a versioned schema is clearer, faster, and easier to test.
3. **Vector storage**: Embeddings can be stored as BLOBs (float32 arrays). For Phase C (MCP search), implement in-memory cosine similarity — no vector extension needed for project-scale data (thousands of nodes, not millions).
4. **Migration**: A `store_meta` table with schema version + sequential migration functions (like Django's `--fake` pattern or Alembic's version model) is sufficient.
5. **JSON serialization**: Nested fields (details, reasons, evidence_ids) → JSON TEXT columns. Python's `json.dumps`/`json.loads` on read/write. `sqlite3` has no native JSON type but TEXT works fine.
6. **Multi-graph support**: The `graphs` table allows multi-graph in a single DB. The `graph_id` FK on every entity table enables scoped queries. This directly supports the multi-tab / project hierarchy the UI expects.
7. **Path forward to Phase C (MCP)**: A `GraphStore` class with `save_node()`, `update_node()`, `query()` methods gives a clean boundary for MCP tools without the MCP server needing to understand the ontology.

**Key Architectural Decision**: Should `node.score` be **stored** (computed at ingest time, cached) or **render-derived** (computed on every `build_render_context` call)?

The current contract (ADR-CV-003 from backend-ui-contract) says render-derived. Storing would change this. Two sub-options:
- **A**: Store raw edge weights only. Continue to derive node.score at render time. Pure additive change.
- **B**: Store pre-computed node.score. Changes ADR-CV-003 to reduce render-time computation. Better for MCP writes, worse for consistency.

Recommendation: **Option A for Phase A#3** — keep node.score render-derived. Option B belongs in Phase C when MCP writes make caching valuable. This keeps the change additive and minimizes domain model churn.

---

### Risks

1. **Schema drift**: If render_context.py evolves to v1.1.0 or v2.0.0 later, the store schema must evolve in lockstep. Mitigation: contract_version stored per-graph in the `graphs` table. The store layer can detect version mismatch and either migrate or refuse to serve.
2. **Migration path from JSON**: Existing users have `.json` graph files, not SQLite databases. The store must support importing from JSON (`GraphStore.import_json(path)`) and exporting to JSON for backward compat. The JSON format stays the user-facing interchange format.
3. **Concurrent access**: `sqlite3` supports WAL mode for concurrent readers, but single-writer. For Phase A (single-user project-scoped), this is fine. For Phase C (MCP server + UI), WAL mode + retry logic handles the load. For multi-user, SQLite is wrong — but Phase C should switch to a client-server DB if multi-user is needed.
4. **Embedding storage format**: Float32 BLOBs without indexing mean full-scan for similarity search. For <10k embeddings this is fast enough in Python with numpy. For larger datasets, consider FTS5 for text search + in-memory vector comparison. Full vector index (e.g., DuckDB, Chroma, pgvector) is out of scope for Phase A.
5. **Cluster concept intersects with ontology**: `EntityType` has no cluster affiliation. Clusters are a cross-cutting concern — any node can belong to multiple clusters. The store design must NOT couple cluster membership to entity type.
6. **WorkspaceShell PR1/PR1.5/PR2/PR3 assumptions**: The workspace shell expects `meta.workspace` with project/graph hierarchy. The SQLite store must produce equivalent or better workspace metadata. The `graphs` table captures this naturally — each row maps to one graph within a workspace.
7. **Test isolation**: SQLite `:memory:` databases give fast, isolated tests. Each test creates its own in-memory DB, runs migrations, and exercises the store. No fixture file management needed beyond the initial schema.
8. **.exe bundling**: `sqlite3` is part of embedded Python distribution. No extra DLLs needed. Confirmed safe for Tauri/PyInstaller bundling.

---

### Ready for Proposal

**Yes**. The exploration is sufficient to drive `sdd-propose`.

#### Recommended scope for proposal:

1. **Create** `brain_ds/store/` package with `GraphStore` class wrapping `sqlite3`
2. **Schema** for nodes, edges, evidence, graphs, clusters, cluster_members, embeddings, store_meta — as proposed above
3. **Default methods**: `import_json()`, `save_graph()`, `load_graph()`, `export_json()`, `query_nodes()`, `query_edges()`, `query_clusters()`, `search_evidence()`
4. **Migrations**: versioned schema with `store_meta` tracking, sequential migration functions, auto-migrate on connect
5. **ADR**: confirm node.score stays render-derived (not stored) for Phase A#3
6. **Tests**: in-memory SQLite test suite covering all CRUD operations, migration path, JSON import/export roundtrip
7. **Non-goals**: MCP integration, vector search at scale, multi-user concurrency, Alembic/SQLAlchemy

#### Open questions for proposal:

1. **Cluster definition source**: Are clusters derived automatically (e.g., from WCC component_id) or created manually by the user (via MCP/edit)? The store supports both, but the proposal should pick the primary use case.
2. **Embedding model**: Which embedding model will be used? The `embeddings.model` field is free-text, but the proposal should specify a default (e.g., sentence-transformers/all-MiniLM-L6-v2 or a no-model-hug tokenizer approach for offline).
3. **Import many graphs from a directory**: Does the CLI auto-discover `.json` files under a workspace root? Or is import explicit per file? This affects `CLI` tool UX.
4. **Workspace-level commands**: Should there be a `brain_ds store init` command that creates the SQLite DB and imports all discovered JSON? Or should the store be created lazily on first `brain_ds ui` call?
5. **GraphStore interface**: Should methods be async for future MCP server compatibility? (Python stdlib sqlite3 is sync — wrapping in `asyncio.to_thread` works but adds complexity.)
