# SQLite Graph Store Specification

## Purpose
Define the schema, data access, and migration rules for the `brain_ds/store` SQLite-backed persistence layer.

## Out of Scope
- No MCP server integration.
- No HTTP/CLI changes.
- No SQLAlchemy/Alembic (stdlib `sqlite3` only).
- No render-derived fields persisted (`node.score`, `neighbor_count`, `component_id`).
- No changes to JSON v2.0.0 interchange format.

## Open Questions Resolved
- **OQ-1**: `nodes.parent_id` MUST be validated in Python logic, not a composite self-reference FK, avoiding SQLite quirks.
- **OQ-2**: `evidence.edge_ids`/`node_ids` MUST be back-pointers (JSON lists) on the evidence row for symmetric searching.
- **OQ-3**: `embeddings.target_type` MUST be a fixed enum (`CHECK(target_type IN ('node','edge','evidence','cluster'))`).
- **OQ-4**: `clusters.id` MUST be domain-supplied strings at insert, matching node/edge id conventions.
- **OQ-5**: `nodes.modified_at` MUST bump on explicit update AND when JSON details change on re-import.
- **OQ-6**: `GraphStore.close()` MUST explicitly checkpoint WAL (`PRAGMA wal_checkpoint(TRUNCATE)`).

## Requirements

### Requirement: Database Initialization & Migrations
The store MUST initialize the database, execute `PRAGMA` statements, and apply ordered migrations.

#### Scenario: First connection to new database
- GIVEN a non-existent database file or empty `:memory:` DB
- WHEN `GraphStore` is instantiated
- THEN WAL mode, foreign keys, and synchronous=NORMAL are enabled
- AND `migrate_to_1` applies all 8 tables and `store_meta`
- AND `schema_version` is set to `1`

#### Scenario: Existing database with older schema
- GIVEN a database with `store_meta.schema_version = N`
- WHEN `GraphStore` connects
- THEN all migrations `> N` apply transactionally
- AND `schema_version` is updated

#### Scenario: Closing connection
- GIVEN an active `GraphStore` connection
- WHEN `close()` or `__exit__()` is called
- THEN it executes `PRAGMA wal_checkpoint(TRUNCATE)` and closes `sqlite3.Connection`

### Requirement: JSON Import and Export
The store MUST losslessly import and export JSON `Graph` models (except render-derived fields).

#### Scenario: Import valid JSON
- GIVEN a JSON structure conforming to `v2.0.0`
- WHEN `import_json()` is called
- THEN a new `graphs` row is created, entities are inserted with a new `graph_id`, and `graph_id` is returned

#### Scenario: Export graph to JSON
- GIVEN a valid `graph_id` with existing rows
- WHEN `export_json(graph_id)` is called
- THEN the returned dictionary perfectly matches the `v2.0.0` shape (ignoring derived scores/components)

### Requirement: Entity Queries
The store MUST query nodes, edges, clusters, and evidence filtered by specific criteria.

#### Scenario: Query nodes by type and parent
- GIVEN multiple nodes in a graph
- WHEN `query_nodes(graph_id, type="Task", parent_id="Epic-1")` is called
- THEN only nodes matching the specific type and parent are returned

#### Scenario: Query edges by target
- GIVEN multiple edges in a graph
- WHEN `query_edges(graph_id, target="Node-A")` is called
- THEN all edges targeting "Node-A" are returned

### Requirement: Embeddings and Cosine Similarity
The store MUST persist packed float32 BLOB vectors and perform nearest-neighbor queries via Python cosine computation.

#### Scenario: Insert new embedding
- GIVEN `target_type`, `target_id`, `model`, and a `vector` sequence
- WHEN `upsert_embedding()` is called
- THEN vector is packed to `float32` BLOB and saved, updating `dimensions`

#### Scenario: Nearest embeddings query
- GIVEN a graph with 1,000 node embeddings
- WHEN `nearest_embeddings(graph_id, target_id, k=5)` is called
- THEN it retrieves the target vector, computes cosine similarity against all other vectors in-memory, and returns the top 5 `(target_id, score)` tuples

#### Scenario: Mixed dimensions
- GIVEN embeddings of dimension 384
- WHEN a cosine query or upsert is attempted with dimension 768
- THEN the store MUST raise a `ValueError` or `StoreError`