# Design: sqlite-graph-store

**Date**: 2026-05-21
**Change**: `sqlite-graph-store`
**Phase**: design
**Roadmap**: backend-migration-to-new-ui — Phase A · #3 (engram #875)
**Proposal**: engram #941 / `openspec/changes/sqlite-graph-store/proposal.md`
**Exploration**: engram #939 / `openspec/changes/sqlite-graph-store/exploration.md`
**Artifact store**: hybrid (file + engram topic_key `sdd/sqlite-graph-store/design`)

---

## 1. Goal

Stand up `brain_ds/store/` as the **only** ACID-backed persistence boundary for the brain_ds graph domain, owned by a single `GraphStore` class that wraps `sqlite3` (stdlib), exposes per-aggregate query methods, and lossly-round-trips a `Graph` dataclass via a versioned schema. Every load-bearing decision below is constrained by four invariants: (a) **stdlib only — no new deps**; (b) **`Graph` dataclass stays pristine** — store-only timestamps live in row models, never in the domain; (c) **strict TDD with `:memory:`** — every public method has a failing test before implementation; (d) **render-derived fields are NEVER persisted** — `node.score`, `neighbor_count`, `component_id`, `updated_at` are recomputed by `render_context.build_render_context`.

---

## 2. Module Layout

```
brain_ds/store/
├── __init__.py            # Public exports: GraphStore, StoreError + subclasses, row models
├── schema.py              # SQL DDL constants (CREATE TABLE / CREATE INDEX) + TABLES tuple
├── migrations.py          # MIGRATIONS list[Migration]; apply_pending(); IncompatibleStoreError gate
├── models.py              # Row models (dataclasses) — NodeRow, EdgeRow, EvidenceRow, ClusterRow,
│                          #   ClusterMemberRow, EmbeddingRow, GraphMeta, NearestHit. NOT a re-impl
│                          #   of graph_model.Graph; these carry persistence-only fields (timestamps).
├── graph_store.py         # GraphStore orchestrator — connection lifecycle, import/export, save/load,
│                          #   delegates aggregate I/O to repository.py.
├── repository.py          # NodeRepository, EdgeRepository, EvidenceRepository, ClusterRepository,
│                          #   EmbeddingRepository, GraphMetaRepository — single-aggregate SQL only.
├── serialization.py       # encode_json / decode_json (sort_keys, ensure_ascii=False);
│                          #   encode_vector / decode_vector (little-endian float32 via struct).
└── errors.py              # StoreError hierarchy.

tests/store/
├── __init__.py
├── test_schema.py            # DDL applies; all 8 tables and indices present.
├── test_migrations.py        # v0→v1 on connect; idempotent on second connect; forward-version raises.
├── test_serialization.py     # JSON determinism; vector round-trip; corrupt-vector raises.
├── test_graph_meta.py        # graphs CRUD; list_graphs ordering; delete cascades.
├── test_node_repository.py   # nodes CRUD; query by type/supertype; FK to graphs.
├── test_edge_repository.py   # edges CRUD; query by source/target; composite PK.
├── test_evidence_repository.py
├── test_cluster_repository.py
├── test_embedding_repository.py  # upsert idempotency; nearest cosine ordering; mixed-dim raises.
└── test_graph_store_roundtrip.py # import_json → export_json deep-equal; save_graph → load_graph deep-equal.
```

Responsibilities (one sentence each):

- **`__init__.py`** — re-exports the public surface and nothing else; consumers `from brain_ds.store import GraphStore, StoreError`.
- **`schema.py`** — DDL string constants only; no I/O.
- **`migrations.py`** — ordered registry + `apply_pending(conn)` + version gate.
- **`models.py`** — typed row containers for I/O between repositories and the orchestrator; pure data.
- **`graph_store.py`** — owns the `sqlite3.Connection`, applies PRAGMAs, runs migrations on connect, exposes the public API.
- **`repository.py`** — narrowly-scoped per-aggregate SQL; never touches the connection lifecycle.
- **`serialization.py`** — pure codec functions (deterministic JSON, packed float32); unit-testable in isolation.
- **`errors.py`** — single `StoreError` base + concrete subclasses raised by the surface above.

---

## 3. Public API Contract

```python
from collections.abc import Sequence
from pathlib import Path
from brain_ds.ontology.graph_model import Graph
from brain_ds.store.models import (
    NodeRow, EdgeRow, EvidenceRow, ClusterRow, EmbeddingRow,
    GraphMeta, NearestHit,
)

class GraphStore:
    def __init__(self, path: Path | str, *, read_only: bool = False) -> None: ...
    def __enter__(self) -> "GraphStore": ...
    def __exit__(self, *exc) -> None: ...
    def close(self) -> None: ...

    # Interchange
    def import_json(self, source: Path | dict, *, workspace_root: Path | None = None) -> str: ...
    def export_json(self, graph_id: str) -> dict: ...

    # Aggregate I/O
    def save_graph(self, graph: Graph, *, graph_id: str | None = None) -> str: ...
    def load_graph(self, graph_id: str) -> Graph: ...

    # Meta
    def list_graphs(self) -> list[GraphMeta]: ...
    def delete_graph(self, graph_id: str) -> None: ...

    # Per-aggregate queries
    def query_nodes(self, graph_id: str, *, type: str | None = None,
                    supertype: str | None = None) -> list[NodeRow]: ...
    def query_edges(self, graph_id: str, *, source: str | None = None,
                    target: str | None = None) -> list[EdgeRow]: ...
    def query_clusters(self, graph_id: str) -> list[ClusterRow]: ...
    def search_evidence(self, graph_id: str, *,
                        content_substr: str | None = None) -> list[EvidenceRow]: ...

    # Embeddings
    def upsert_embedding(self, graph_id: str, target_type: str, target_id: str,
                         model: str, vector: Sequence[float]) -> None: ...
    def nearest_embeddings(self, graph_id: str, target_id: str, *,
                           k: int = 10, model: str | None = None) -> list[NearestHit]: ...
```

### Method semantics

| Method | Purpose | Raises | R/W | Idempotency |
|--------|---------|--------|-----|-------------|
| `__init__` | Open/create DB at `path`, apply PRAGMAs, run pending migrations. `read_only=True` opens via `file:{path}?mode=ro` URI. | `IncompatibleStoreError`, `MigrationFailedError`, `sqlite3.OperationalError` | W (migrations) | Idempotent across processes for same DB. |
| `__enter__` / `__exit__` | Context-manager sugar; `__exit__` calls `close()`. | — | — | — |
| `close` | Commit pending tx, `PRAGMA wal_checkpoint(TRUNCATE)`, close connection. Safe to call twice. | — | W (checkpoint) | Idempotent. |
| `import_json` | Parse a graph JSON file or dict, build a `Graph` via `Graph.from_v1`, then `save_graph`. Returns `graph_id`. | `GraphNotFoundError` (source path missing), `DuplicateGraphError` (only when caller pins a colliding `graph_id` via the embedded `graph_id` key — see §6 OQ-1), `json.JSONDecodeError` | W | Idempotent on `(workspace_root, imported_from)` — re-importing the same file with the same workspace replaces the prior row (DELETE-then-INSERT under one tx). |
| `export_json` | Reconstruct the v2.0.0 dict from store rows. Mirrors `Graph.to_dict()` exactly. | `GraphNotFoundError` | R | Pure. |
| `save_graph` | Persist a `Graph` under a stable `graph_id` (caller-supplied or generated via `uuid.uuid4().hex`). Replaces existing graph atomically. | `DuplicateGraphError` *(only if caller passes an id already present AND `if_exists="raise"` — see ADR-D1)* | W | Idempotent on `graph_id`: a second call with same id replaces nodes/edges/evidence/clusters under one tx. |
| `load_graph` | Materialize a `Graph` from rows. Render-derived fields are NOT populated. | `GraphNotFoundError` | R | Pure. |
| `list_graphs` | Return all `GraphMeta` rows ordered by `updated_at DESC, id ASC`. | — | R | Pure. |
| `delete_graph` | `DELETE FROM graphs WHERE id = ?` — cascades to all child tables. | `GraphNotFoundError` | W | Idempotent: second delete raises `GraphNotFoundError`. |
| `query_nodes` | Filtered scan over `nodes` for `graph_id`. | `GraphNotFoundError` | R | Pure. |
| `query_edges` | Filtered scan over `edges`. | `GraphNotFoundError` | R | Pure. |
| `query_clusters` | All clusters for graph. | `GraphNotFoundError` | R | Pure. |
| `search_evidence` | `LIKE '%' || ? || '%'` on `evidence.content` when `content_substr` is set; otherwise full scan. | `GraphNotFoundError` | R | Pure. |
| `upsert_embedding` | `INSERT OR REPLACE` on UNIQUE `(graph_id, target_type, target_id, model)`. Validates `len(vector) == dimensions` against existing row when present. | `GraphNotFoundError`, `CorruptVectorError` (mixed dim against existing row) | W | Idempotent on the unique key tuple. |
| `nearest_embeddings` | Load the query vector for `target_id` (matching `model` if given), stream candidate rows of the same dimension, cosine via `math.fsum`, top-k via `heapq.nlargest`. | `GraphNotFoundError`, `CorruptVectorError` (query vector missing or stored dim mismatch) | R | Pure. |

ADR-D1: `save_graph` uses an implicit replace semantic (no `if_exists` flag in v1). Callers wanting collision detection can `list_graphs()` first. The flag is reserved for a future change.

---

## 4. Schema (final DDL sketch)

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

-- ===== store-level metadata =====
CREATE TABLE store_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- Reserved keys: schema_version, created_at, last_migrated_at.

-- ===== graph aggregate =====
CREATE TABLE graphs (
    id               TEXT PRIMARY KEY,                -- uuid4().hex
    workspace_root   TEXT,                            -- absolute fs path or NULL
    workspace_path   TEXT,                            -- display path under workspace_root
    project          TEXT,                            -- derived project bucket (matches RENDER_CONTEXT.meta.workspace.project)
    org              TEXT NOT NULL DEFAULT '',
    schema_version   TEXT NOT NULL DEFAULT '2.0.0',   -- Graph.schema_version (domain version)
    contract_version TEXT NOT NULL DEFAULT '1.0.0',   -- render-context CONTRACT_VERSION known at import time
    node_count       INTEGER NOT NULL DEFAULT 0,
    edge_count       INTEGER NOT NULL DEFAULT 0,
    imported_from    TEXT,                            -- source JSON path or NULL
    generated_at     TEXT NOT NULL DEFAULT '',        -- Graph.generated_at
    created_at       TEXT NOT NULL,                   -- ISO 8601, set by store
    updated_at       TEXT NOT NULL                    -- ISO 8601, refreshed on every save
);

CREATE INDEX idx_graphs_project ON graphs(project);

-- ===== nodes =====
CREATE TABLE nodes (
    graph_id        TEXT NOT NULL,
    id              TEXT NOT NULL,
    label           TEXT NOT NULL DEFAULT '',
    type            TEXT NOT NULL,                    -- EntityType.value
    supertype       TEXT,
    details         TEXT NOT NULL DEFAULT '{}',       -- JSON dict[str, str]
    card_sections   TEXT,                             -- JSON list[CardSection] or NULL
    evidence_ids    TEXT,                             -- JSON list[str]      or NULL
    editable_fields TEXT,                             -- JSON list[str]      or NULL
    layout_hint     TEXT,                             -- JSON dict           or NULL
    parent_id       TEXT,                             -- node id within same graph (Python-validated; see OQ-1)
    depth           INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    modified_at     TEXT NOT NULL,
    PRIMARY KEY (graph_id, id),
    FOREIGN KEY (graph_id) REFERENCES graphs(id) ON DELETE CASCADE
);

CREATE INDEX idx_nodes_graph_type      ON nodes(graph_id, type);
CREATE INDEX idx_nodes_graph_supertype ON nodes(graph_id, supertype);
CREATE INDEX idx_nodes_graph_parent    ON nodes(graph_id, parent_id);

-- ===== edges =====
CREATE TABLE edges (
    graph_id     TEXT NOT NULL,
    edge_id      TEXT NOT NULL,                       -- caller-supplied or generated f"{source}->{target}#{n}"
    source       TEXT NOT NULL,
    target       TEXT NOT NULL,
    label        TEXT NOT NULL,                       -- RelationshipType.value
    weight       REAL,                                -- nullable; 0.0..1.0 when present
    reasons      TEXT,                                -- JSON list[str] or NULL
    evidence_ids TEXT,                                -- JSON list[str] or NULL
    created_at   TEXT NOT NULL,
    PRIMARY KEY (graph_id, edge_id),
    FOREIGN KEY (graph_id) REFERENCES graphs(id) ON DELETE CASCADE
);

CREATE INDEX idx_edges_graph_source ON edges(graph_id, source);
CREATE INDEX idx_edges_graph_target ON edges(graph_id, target);

-- ===== evidence =====
CREATE TABLE evidence (
    graph_id   TEXT NOT NULL,
    id         TEXT NOT NULL,
    type       TEXT NOT NULL,
    source     TEXT NOT NULL,
    content    TEXT NOT NULL,
    provenance TEXT,                                  -- JSON dict[str, str] or NULL
    timestamp  TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (graph_id, id),
    FOREIGN KEY (graph_id) REFERENCES graphs(id) ON DELETE CASCADE
);

CREATE INDEX idx_evidence_graph_source ON evidence(graph_id, source);

-- ===== clusters (net-new domain) =====
CREATE TABLE clusters (
    graph_id    TEXT NOT NULL,
    id          TEXT NOT NULL,                        -- caller-supplied string (see OQ-4)
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    parent_id   TEXT,                                 -- self-ref within (graph_id, id); Python-validated
    metadata    TEXT,                                 -- JSON or NULL
    created_at  TEXT NOT NULL,
    PRIMARY KEY (graph_id, id),
    FOREIGN KEY (graph_id) REFERENCES graphs(id) ON DELETE CASCADE
);

CREATE TABLE cluster_members (
    graph_id   TEXT NOT NULL,
    cluster_id TEXT NOT NULL,
    node_id    TEXT NOT NULL,
    weight     REAL,                                  -- nullable
    PRIMARY KEY (graph_id, cluster_id, node_id),
    FOREIGN KEY (graph_id, cluster_id) REFERENCES clusters(graph_id, id) ON DELETE CASCADE,
    FOREIGN KEY (graph_id, node_id)    REFERENCES nodes(graph_id, id)    ON DELETE CASCADE
);

CREATE INDEX idx_cluster_members_node ON cluster_members(graph_id, node_id);

-- ===== embeddings (net-new) =====
CREATE TABLE embeddings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    graph_id    TEXT NOT NULL,
    target_type TEXT NOT NULL,                        -- 'node' | 'edge' | 'evidence' (Python-validated; see OQ-3)
    target_id   TEXT NOT NULL,
    model       TEXT NOT NULL,
    dimensions  INTEGER NOT NULL,
    vector      BLOB NOT NULL,                        -- packed little-endian float32, len = dimensions * 4
    created_at  TEXT NOT NULL,
    UNIQUE (graph_id, target_type, target_id, model),
    FOREIGN KEY (graph_id) REFERENCES graphs(id) ON DELETE CASCADE
);

CREATE INDEX idx_embeddings_target ON embeddings(graph_id, target_type, target_id);
```

Index inventory (matches §3 query methods):

| Index | Backs |
|-------|-------|
| `idx_graphs_project` | `list_graphs()` future project filters; `import_json` workspace dedup. |
| `idx_nodes_graph_type` | `query_nodes(graph_id, type=…)` |
| `idx_nodes_graph_supertype` | `query_nodes(graph_id, supertype=…)` |
| `idx_nodes_graph_parent` | hierarchy traversal during `load_graph` |
| `idx_edges_graph_source` | `query_edges(graph_id, source=…)` |
| `idx_edges_graph_target` | `query_edges(graph_id, target=…)` |
| `idx_evidence_graph_source` | `search_evidence(graph_id, …)` and provenance joins (future) |
| `idx_cluster_members_node` | reverse lookup “clusters containing node X” (Phase C) |
| `idx_embeddings_target` | `nearest_embeddings()` query-vector lookup |

---

## 5. Migration Model

- **Version key**: `store_meta.schema_version` (string of the integer index, default `'0'` when row missing).
- **Registry**: `migrations.MIGRATIONS: list[Migration]` where `Migration = Callable[[sqlite3.Connection], None]`. The list index PLUS ONE is the version after applying that migration (i.e., `MIGRATIONS[0]` upgrades 0 → 1).
- **Latest known version** = `len(MIGRATIONS)`.

**Apply algorithm** (in `migrations.apply_pending(conn)`):
1. Begin a single transaction.
2. `SELECT value FROM store_meta WHERE key='schema_version'`. If missing, treat as `0`.
3. If `current > latest_known`: raise `IncompatibleStoreError(f"store at version {current}, code knows {latest_known}")`.
4. For `i in range(current, latest_known)`: call `MIGRATIONS[i](conn)`. Any exception → wrap in `MigrationFailedError(i+1, original)` and let the outer transaction roll back.
5. `INSERT OR REPLACE INTO store_meta(key,value) VALUES('schema_version', ?)` with the new version.
6. `INSERT OR REPLACE` `last_migrated_at` with `datetime.now(UTC).isoformat()`.
7. Commit.

**v1 migration content** (`v1_initial_schema`): exactly the DDL block from §4, executed via `conn.executescript`. PRAGMAs `foreign_keys=ON`, `journal_mode=WAL`, `synchronous=NORMAL` are set on the connection BEFORE `apply_pending` (per-connection state, not persisted in the schema). `MIGRATIONS = [v1_initial_schema]` for this change. No down migrations.

---

## 6. Concurrency & Lifecycle

- **One connection per `GraphStore`** instance. The connection is opened in `__init__` and closed in `close()`. No pool, no thread-local handles.
- **PRAGMAs** set on connect (every connect, since they are session state except `journal_mode`):
  - `PRAGMA foreign_keys = ON;`
  - `PRAGMA journal_mode = WAL;` (persisted at DB level after first call — still safe to re-issue)
  - `PRAGMA synchronous = NORMAL;`
- **Read-only mode**: `__init__(path, read_only=True)` opens with `sqlite3.connect(f"file:{path}?mode=ro", uri=True)`. Migrations are NOT run in this mode; if the schema is out-of-date, raise `IncompatibleStoreError` immediately.
- **Checkpointing**: `close()` runs `PRAGMA wal_checkpoint(TRUNCATE)` before `conn.close()` to keep `.exe` installs free of orphan `-wal`/`-shm` sidecars (addresses OQ-6).
- **Single-writer contract**: documented in `GraphStore` docstring; no internal locking. The future Tauri/HTTP layer (change #4) chooses between a per-request `GraphStore` (with WAL serializing writers) or a single long-lived instance plus a `threading.Lock`. **That choice is explicitly deferred to change #4**.
- **Context manager**: `__enter__` returns `self`; `__exit__` always calls `close()`, swallowing no exceptions.

---

## 7. JSON & BLOB Serialization (`serialization.py`)

```python
import json, struct
from collections.abc import Sequence
from typing import Any
from brain_ds.store.errors import CorruptVectorError

def encode_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

def decode_json(raw: str | None) -> Any:
    if raw is None or raw == "":
        return None
    return json.loads(raw)

def encode_vector(vec: Sequence[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)

def decode_vector(buf: bytes, *, dimensions: int) -> list[float]:
    expected = dimensions * 4
    if len(buf) != expected:
        raise CorruptVectorError(
            f"expected {expected} bytes for {dimensions}-d vector, got {len(buf)}"
        )
    return list(struct.unpack(f"<{dimensions}f", buf))
```

Properties:

- **Determinism**: `encode_json` uses `sort_keys=True` and no extra whitespace so identical Python values produce byte-identical SQLite cells → enables idempotent re-import and clean diffs.
- **Round-trip**: `decode_json(encode_json(x)) == x` for any JSON-compatible `x` (verified by `test_serialization.py`).
- **No silent loss**: vector decoding validates byte length against `dimensions` (read from the row) and raises `CorruptVectorError` rather than returning a truncated list.
- **NULL passthrough**: `decode_json(None)` returns `None`, matching the dataclass defaults for `card_sections`, `evidence_ids`, `editable_fields`, `layout_hint`.

---

## 8. Embedding Similarity

`nearest_embeddings(graph_id, target_id, *, k=10, model=None)`:

1. Look up the query vector: `SELECT dimensions, vector, model FROM embeddings WHERE graph_id=? AND target_id=? AND (?='' OR model=?) LIMIT 1`. Raise `GraphNotFoundError` if the graph is absent; raise `CorruptVectorError` if no embedding exists for `target_id` under the requested `model`.
2. Decode via `decode_vector(buf, dimensions=dim)`. Normalize once: `q_norm = math.sqrt(math.fsum(x*x for x in q))`. If `q_norm == 0`, return `[]`.
3. Stream candidates: `SELECT id, target_type, target_id, model, dimensions, vector FROM embeddings WHERE graph_id=? AND dimensions=? AND id != ? AND (?='' OR model=?)` — same `graph_id`, same `dim`, excluding the query row.
4. For each candidate:
   - Decode via `decode_vector`.
   - Compute `dot = math.fsum(a*b for a, b in zip(q, c))`.
   - Compute `c_norm = math.sqrt(math.fsum(x*x for x in c))`; skip if `c_norm == 0`.
   - `score = dot / (q_norm * c_norm)`.
5. Top-k via `heapq.nlargest(k, candidates, key=lambda hit: hit.score)`.
6. Return `list[NearestHit]` (see `models.py`).

**Explicitly out of scope**: `numpy` fast-path, ANN indexes, FAISS/hnswlib/sqlite-vss. Stdlib only.

---

## 9. Domain → Store Mapping

| Domain field (`graph_model`) | Persists where | Notes |
|---|---|---|
| `Graph.schema_version` | `graphs.schema_version` | string, e.g. `"2.0.0"` |
| `Graph.org` | `graphs.org` | |
| `Graph.generated_at` | `graphs.generated_at` | ISO 8601 string, may be empty |
| `Graph.nodes` | one row per node in `nodes` | identity = `(graph_id, id)` |
| `Graph.edges` | one row per edge in `edges` | identity = `(graph_id, edge_id)`; `edge_id` synthesized when source `Edge.edge_id is None` (see OQ-2 below) |
| `Graph.evidence` | one row per record in `evidence` | identity = `(graph_id, id)` |
| `Node.id` | `nodes.id` | PK component |
| `Node.label` | `nodes.label` | |
| `Node.type` | `nodes.type` | `.value` of `EntityType` |
| `Node.details` | `nodes.details` JSON | `encode_json(node.details)` |
| `Node.supertype` | `nodes.supertype` | nullable |
| `Node.card_sections` | `nodes.card_sections` JSON | flattened list of `{title,content,icon,order}` dicts; NULL when domain value is None |
| `Node.evidence_ids` | `nodes.evidence_ids` JSON | list of evidence ids; NULL when None |
| `Node.editable_fields` | `nodes.editable_fields` JSON | NULL when None |
| `Node.layout_hint` | `nodes.layout_hint` JSON | NULL when None |
| `Node.parent_id` | `nodes.parent_id` | nullable; Python-validated against same-graph nodes |
| `Node.depth` | `nodes.depth` | INTEGER |
| `Edge.source` | `edges.source` | |
| `Edge.target` | `edges.target` | |
| `Edge.label` | `edges.label` | `.value` of `RelationshipType` |
| `Edge.weight` | `edges.weight` | REAL, nullable |
| `Edge.reasons` | `edges.reasons` JSON | NULL when None |
| `Edge.evidence_ids` | `edges.evidence_ids` JSON | NULL when None |
| `Edge.edge_id` | `edges.edge_id` | PK component; if domain value is None at save time, synthesize as `f"{source}->{target}#{n}"` where `n` is the index of the edge in `graph.edges` |
| `EvidenceRecord.id` | `evidence.id` | |
| `EvidenceRecord.type` | `evidence.type` | |
| `EvidenceRecord.source` | `evidence.source` | |
| `EvidenceRecord.content` | `evidence.content` | |
| `EvidenceRecord.provenance` | `evidence.provenance` JSON | NULL when None |
| `EvidenceRecord.timestamp` | `evidence.timestamp` | string, default `""` |
| **NOT persisted (render-derived)** | — | `Node.component_id`, render `node.score`, `node.neighbor_count`, `node.updated_at`. Recomputed every call to `build_render_context`. ADR-1 (proposal). |
| **NOT in domain — store-only** | — | `nodes.created_at`, `nodes.modified_at`, `edges.created_at`, `evidence.timestamp` semantics (re-import resets `modified_at`; see OQ-5), `graphs.created_at/updated_at/node_count/edge_count`, `clusters.*`, `cluster_members.*`, `embeddings.*`. These are PERSISTENCE-ONLY fields surfaced through row models (`NodeRow`, `EdgeRow`, etc.) and NEVER pushed back into `Graph`. |

`load_graph(graph_id)` reconstructs the `Graph` dataclass using ONLY the “Domain field” rows in the table above. Store-only columns are exposed via the `query_*` methods that return `*Row` types.

---

## 10. Error Hierarchy (`errors.py`)

```python
class StoreError(Exception):
    """Base for every error raised by brain_ds.store."""

class GraphNotFoundError(StoreError):
    """Raised when a graph_id has no row in graphs (or has been deleted)."""

class IncompatibleStoreError(StoreError):
    """Raised when the on-disk schema_version is higher than the code's latest migration."""

class DuplicateGraphError(StoreError):
    """Reserved: raised by save_graph when caller opts into collision detection (Phase C)."""

class CorruptVectorError(StoreError):
    """Raised when a stored vector's byte length does not match its dimensions column,
    or when a nearest_embeddings query targets a missing/mismatched vector."""

class MigrationFailedError(StoreError):
    """Wraps the original exception from a failed migration step.
    Attributes: target_version: int, original: BaseException."""
```

| Raised by | Errors |
|-----------|--------|
| `__init__` | `IncompatibleStoreError`, `MigrationFailedError`, `sqlite3.OperationalError` |
| `load_graph`, `export_json`, `delete_graph`, every `query_*`, `search_evidence`, `upsert_embedding`, `nearest_embeddings` | `GraphNotFoundError` |
| `upsert_embedding` | `CorruptVectorError` (mixed-dim re-upsert against existing row) |
| `nearest_embeddings` | `CorruptVectorError` (missing or dim-mismatched query vector) |
| `save_graph` (future) | `DuplicateGraphError` (gated behind ADR-D1) |

---

## 11. Test Design (TDD-first)

Every public method below MUST have its named failing test committed before the implementation. Test files live under `tests/store/`. Fixture pattern: `def _fresh_store() -> GraphStore: return GraphStore(":memory:")`.

### `tests/store/test_schema.py`
- `test_v1_creates_all_eight_tables` — assert `sqlite_master` contains `store_meta, graphs, nodes, edges, evidence, clusters, cluster_members, embeddings`.
- `test_v1_creates_all_indices` — assert every index in §4 is present.
- `test_pragmas_set_on_connect` — `PRAGMA foreign_keys` and `PRAGMA journal_mode` return `1` and `wal`.

### `tests/store/test_migrations.py`
- `test_fresh_store_reports_version_one` — covers `__init__`.
- `test_second_connect_is_noop` — open `:memory:` once… not possible across connections; use a temp file path; assert `last_migrated_at` does not change.
- `test_forward_version_raises_incompatible` — manually set `schema_version='99'` then reconnect → `IncompatibleStoreError`.
- `test_migration_failure_rolls_back` — inject a failing fake migration via monkeypatch; assert version unchanged and `MigrationFailedError` raised.

### `tests/store/test_serialization.py`
- `test_encode_json_is_sort_stable` — encoding two dicts with different insertion order returns identical strings.
- `test_decode_json_none_passthrough` — covers nullable JSON columns.
- `test_vector_roundtrip_float32` — encode→decode equals input to float32 precision (`pytest.approx`).
- `test_decode_vector_raises_on_wrong_length` — `CorruptVectorError`.

### `tests/store/test_graph_meta.py`
- `test_save_graph_creates_meta_row` — covers `save_graph` + `list_graphs`.
- `test_list_graphs_orders_by_updated_at_desc` — two saves, second one wins ordering.
- `test_delete_graph_cascades_to_children` — after delete, `query_nodes/edges/evidence` raise `GraphNotFoundError`.
- `test_delete_graph_twice_raises_not_found` — covers idempotency contract.

### `tests/store/test_node_repository.py`
- `test_save_then_query_nodes_by_type` — covers `query_nodes(type=…)`.
- `test_save_then_query_nodes_by_supertype` — covers `query_nodes(supertype=…)`.
- `test_node_modified_at_updates_on_resave` — covers OQ-5 (re-import bumps `modified_at`).
- `test_fk_violation_on_orphan_node` — INSERT a node with non-existent `graph_id` raises `sqlite3.IntegrityError`.

### `tests/store/test_edge_repository.py`
- `test_query_edges_by_source_and_target` — covers `query_edges(source=…)` and `target=…`.
- `test_edge_id_synthesized_when_missing` — `Edge.edge_id is None` round-trips to a stable synthesized id.
- `test_edge_weight_nullable` — `Edge.weight is None` survives round-trip.

### `tests/store/test_evidence_repository.py`
- `test_search_evidence_substring_match` — covers `search_evidence(content_substr=…)`.
- `test_search_evidence_no_filter_returns_all` — covers the no-filter branch.

### `tests/store/test_cluster_repository.py`
- `test_save_cluster_and_member` — covers `query_clusters`.
- `test_cluster_members_cascade_on_node_delete` — delete a node, member rows go.
- `test_cluster_parent_chain_python_validated` — invalid parent raises a clear ValueError (validated in `ClusterRepository`).

### `tests/store/test_embedding_repository.py`
- `test_upsert_embedding_is_idempotent` — second upsert with same key replaces vector.
- `test_upsert_embedding_mixed_dim_raises` — first upsert dim=8, second dim=16 → `CorruptVectorError`.
- `test_nearest_embeddings_orders_by_cosine` — vectors `q=[1,0,0]`, `a=[1,0,0]`, `b=[0,1,0]`, `c=[-1,0,0]` → ordering `[a, b, c]` with scores `[1.0, 0.0, -1.0]` (hand-computed).
- `test_nearest_embeddings_excludes_self` — query vector is not in result.
- `test_nearest_embeddings_filters_by_model` — vectors under different model names are not mixed.
- `test_nearest_embeddings_missing_target_raises` — `CorruptVectorError`.

### `tests/store/test_graph_store_roundtrip.py`
- `test_import_json_export_json_byte_equal_on_json_owned_fields` — load a fixture, import, export, assert deep-equal on every field EXCEPT render-derived (oracle documents the exclusion list).
- `test_save_graph_load_graph_dataclass_equal` — `Graph` → `save_graph` → `load_graph` returns an equivalent `Graph` (compare `to_dict()` outputs).
- `test_save_graph_is_idempotent_on_graph_id` — second save with same id replaces children atomically.
- `test_load_graph_unknown_id_raises` — `GraphNotFoundError`.
- `test_close_is_idempotent` — calling `close()` twice is safe.
- `test_context_manager_closes_on_exit` — `with GraphStore(...) as s: ...` leaves the file accessible afterwards.
- `test_read_only_mode_blocks_writes` — opening `read_only=True` then attempting `save_graph` raises `sqlite3.OperationalError`.

Total: **≥ 1 failing test per public method**, plus contract and integrity coverage.

---

## 12. Integration Seams (forward-looking)

- **Change #4 (`project-scoped-runtime`)** — `brain_ds/ui/render_context.py` gains a `RenderContextBuilder` (new symbol) that accepts `GraphStore | Graph` polymorphically. When given a `GraphStore`, it calls `store.load_graph(graph_id)` internally. **No code lands in this seam during change #3.** The hook point is the `build_render_context(graph: Graph, ...)` signature: change #4 wraps it; change #3 leaves it untouched.
- **Change #7 (`mcp-server`)** — MCP tools (`list_nodes`, `update_node`, `add_edge`, `search_graph`, `nearest_embeddings`) adapt to `GraphStore` directly. Do NOT introduce a separate adapter layer in this change; the public API in §3 is the adapter.
- **Change #9 (`manual-node-editing`)** — every write path on `GraphStore` (`save_graph`, `upsert_embedding`, future `update_node`) returns the row identifier so the UI cache layer in change #9 can invalidate by `(graph_id, node_id)`. For v1 this is implicit: `save_graph` returns `graph_id`, `upsert_embedding` returns `None` but the unique key is the caller’s input. The contract: **no write method MUST silently swallow the identity of what changed.**

---

## 13. Open Questions → Design Recommendations (spec must confirm)

- **OQ-1** — `nodes.parent_id` integrity. **Recommendation**: Python-validated in `NodeRepository.save_bulk()` (check `parent_id ∈ existing_node_ids ∪ batch_ids ∪ {None}`). NOT a composite FK because (a) self-referencing composite FKs in SQLite require deferred constraints which complicate the migration story, (b) Python validation gives a friendlier error than `IntegrityError`. `[spec must confirm]`
- **OQ-2** — Evidence back-pointers vs one-way JSON list. **Recommendation**: keep the one-way list on `nodes.evidence_ids` / `edges.evidence_ids` JSON columns. Adding a back-pointer table is a query optimization for Phase C and not justified at < 10k evidence. `[spec must confirm]`
- **OQ-3** — `embeddings.target_type` domain. **Recommendation**: free `TEXT` validated in Python against a `frozenset({'node', 'edge', 'evidence'})`. A SQL `CHECK` constraint locks future extensibility (e.g., `cluster`) behind a migration; Python validation does not. `[spec must confirm]`
- **OQ-4** — `clusters.id` domain. **Recommendation**: caller-supplied string. The store does NOT generate cluster ids. Rationale: clusters are an ontology concern (Phase C), the store stays a thin persistence layer. `[spec must confirm]`
- **OQ-5** — `nodes.modified_at` on re-import. **Recommendation**: `import_json` and `save_graph` always refresh `modified_at` for every node, even if `Node` content is unchanged. Cheaper than diffing and matches user expectation (“I re-imported, so the store is touched”). `[spec must confirm]`
- **OQ-6** — `close()` WAL checkpoint policy. **Recommendation**: `PRAGMA wal_checkpoint(TRUNCATE)` on every `close()` (already adopted in §6). Removes the `-wal` / `-shm` sidecars that confuse Windows installer cleanup. `[spec must confirm]`

---

## 14. Review Workload Re-Forecast

Refined from the proposal (delivery_strategy = `ask-on-risk`):

| Slice | Files | Est. lines | Tests | Notes |
|------|-------|-----------:|-------|-------|
| **S1 — schema + migrations** | `schema.py`, `migrations.py`, `errors.py`, `tests/store/test_schema.py`, `tests/store/test_migrations.py` | ~280 | 7 | Foundation; lands first; ends with a queryable empty DB. |
| **S2 — serialization** | `serialization.py`, `tests/store/test_serialization.py` | ~120 | 4 | Pure functions; unblocks every repository. |
| **S3 — repositories** | `models.py`, `repository.py`, `tests/store/test_graph_meta.py`, `test_node_repository.py`, `test_edge_repository.py`, `test_evidence_repository.py`, `test_cluster_repository.py` | ~520 | 18 | Largest slice; per-aggregate SQL + row models. |
| **S4 — graph_store orchestrator** | `graph_store.py`, `__init__.py`, `tests/store/test_graph_store_roundtrip.py` | ~280 | 7 | Lifecycle + import/export + save/load_graph round-trip. |
| **S5 — embeddings** | embeddings additions to `repository.py` + `graph_store.py`, `tests/store/test_embedding_repository.py` | ~200 | 6 | Cosine + heap top-k; lands last so it has stable row infrastructure to build on. |
| **Total** | | **~1,400** | **42** | Above 400-line budget. |

**Chained PRs recommended: Yes.** **400-line budget risk: High** (every slice except S2 exceeds it on its own). **Decision needed before apply: Yes.** Because cached `delivery_strategy = ask-on-risk`, the orchestrator MUST ask the user before `sdd-apply` whether to:

- (a) chain S1 → S2 → S3 → S4 → S5 as five PRs (recommended), or
- (b) merge as one PR under a maintainer-approved `size:exception` label.

Ordering rationale: TDD-friendly — each slice ends with green tests, no future slice rewrites a prior slice’s public API. S5 is intentionally last because it is the only slice that depends on stable row infrastructure from S3+S4.

---

## 15. Acceptance Signals (design phase)

The design is “done” when ALL of the following hold:

1. Every method in §3 has a one-line **purpose**, **error contract**, and **idempotency** entry in the table.
2. §4 DDL is complete: 8 tables + 9 indices + 3 PRAGMAs.
3. The mapping table in §9 covers every field of `Graph`, `Node`, `Edge`, `EvidenceRecord`, `CardSection`, including explicit “NOT persisted” rows for render-derived fields and explicit “store-only” rows for persistence-side timestamps.
4. §11 lists at least one **named failing test** per public method in §3.
5. §13 preserves all six open questions from the proposal and gives each a `[spec must confirm]` recommendation.
6. §14 produces a chained-PR ordering consistent with the cached `delivery_strategy`.
7. No production code is modified; no migration runs; no commits are made in this phase.

---

## Result Contract

- **status**: `done`
- **executive_summary**: Designed `brain_ds/store/` as a stdlib-only, single-`sqlite3.Connection` `GraphStore` over 8 tables with versioned Python migrations, JSON columns for nested ontology fields, float32 BLOB embeddings with stdlib cosine, per-aggregate repositories, a strict TDD test plan with ≥ 1 failing test per public method, and a 5-slice chained-PR review plan that flags 400-line budget risk = High.
- **artifacts**:
  - File: `brain_ds\openspec\changes\sqlite-graph-store\design.md`
  - Engram topic_key: `sdd/sqlite-graph-store/design`
- **next_recommended**: `sdd-spec` (spec phase has not run yet — design is the structural contract the spec will derive requirements from), then `sdd-tasks`.
- **risks**:
  - Six OQs remain routed to spec; spec MUST confirm before tasks lock the surface (OQ-1 parent_id integrity is the most likely re-litigation point).
  - Review workload re-forecast (~1,400 lines) exceeds the 400-line budget on four of five slices — orchestrator must apply `ask-on-risk` before `sdd-apply`.
  - `save_graph` collision semantics are deferred (ADR-D1) — if Phase C needs strict collision detection, a follow-up minor change is required.
  - Read-only mode raises `IncompatibleStoreError` when schema is out-of-date instead of silently using the older schema — confirm this is the desired UX for the `.exe` installer’s first launch on a stale DB.
- **skill_resolution**: `injected`
