# Tasks: sqlite-graph-store

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1,400 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Delivery strategy | ask-on-risk |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Work Units → PR Slices

| Slice | Est. lines | Tests | Scope |
|-------|-----------:|-------|-------|
| S1 | ~280 | 7 | schema.py, migrations.py, errors.py + tests |
| S2 | ~120 | 4 | serialization.py + tests |
| S3 | ~520 | 18 | models.py, repository.py + 5 test files |
| S4 | ~280 | 7 | graph_store.py, __init__.py + roundtrip tests |
| S5 | ~200 | 6 | embedding methods in repo+orchestrator + tests |

## Phase 1: Foundation

- [x] 1.1 RED: `tests/store/test_schema.py` — 8 tables, 9 indices, PRAGMAs.
- [x] 1.2 GREEN: `brain_ds/store/schema.py` — DDL for all tables+indices.
- [x] 1.3 RED: `tests/store/test_migrations.py` — v0→v1, re-connect no-op, forward→IncompatibleStoreError, rollback.
- [x] 1.4 GREEN: `brain_ds/store/migrations.py` — MIGRATIONS list, apply_pending(), v1_initial_schema via executescript.
- [x] 1.5 GREEN: `brain_ds/store/errors.py` — StoreError + 5 subclasses.
- [x] 1.6 RED: `tests/store/test_serialization.py` — JSON sort-stable, null passthrough, vector roundtrip, wrong-length raises.
- [x] 1.7 GREEN: `brain_ds/store/serialization.py` — encode/decode_json (sort_keys), encode/decode_vector (struct LE float32).

## Phase 2: Models + Repositories

- [x] 2.1 RED: `tests/store/test_graph_meta.py` — save→meta, list ordered, delete cascade, delete×2→GraphNotFoundError.
- [x] 2.2 RED: `tests/store/test_node_repository.py` — query by type/supertype, modified_at bumps, orphan FK.
- [x] 2.3 RED: `tests/store/test_edge_repository.py` — query source+target, synth edge_id, nullable weight.
- [x] 2.4 RED: `tests/store/test_evidence_repository.py` — substring match, no-filter.
- [x] 2.5 RED: `tests/store/test_cluster_repository.py` — save cluster+member, cascade delete, invalid parent→ValueError.
- [x] 2.6 GREEN: `brain_ds/store/models.py` — all 8 row dataclasses.
- [x] 2.7 GREEN: `brain_ds/store/repository.py` — GraphMetaRepository, NodeRepository (parent_id Python-validated).
- [x] 2.8 GREEN: `brain_ds/store/repository.py` — EdgeRepository, EvidenceRepository, ClusterRepository.

## Phase 3: Orchestrator

- [x] 3.1 RED: `tests/store/test_graph_store_roundtrip.py` — import→export eq, save→load eq, idempotent, close idempotent, context manager, read-only.
- [x] 3.2 GREEN: `brain_ds/store/graph_store.py` — GraphStore: connection lifecycle, PRAGMAs, WAL, migrations, close(wal_checkpoint TRUNCATE), import/export/save/load/delete, query_*, search_evidence.
- [x] 3.3 GREEN: `brain_ds/store/__init__.py` — public exports.

## Phase 4: Embeddings

- [x] 4.1 RED: `tests/store/test_embedding_repository.py` — idempotent, mixed-dim→CorruptVectorError, cosine ordering (q/a/b/c), self-exclude, model filter, missing→CorruptVectorError.
- [x] 4.2 GREEN: EmbeddingRepository in `repository.py`; upsert_embedding + nearest_embeddings in `graph_store.py` — BLOB float32, UNIQUE, cosine math.fsum, top-k heapq.

## Phase 5: Integration

- [x] 5.1 Run `uv run python -m unittest discover -s tests` — all green.
- [x] 5.2 Confirm existing render_context + graph_contract tests green (no regression).
- [x] 5.3 Verify zero new deps in pyproject.toml / uv.lock.
- [x] 5.4 REFACTOR: review store/ for docstrings, types, import hygiene.

## Risk Guardrails

- OQ-1 parent_id: Python-validated, not composite FK.
- read_only=True + stale schema: IncompatibleStoreError (UX for .exe deferred to #4).
- ADR-D1 save_graph: replace-only; collision detection is follow-up minor change.
- Mixed-dim embeddings: upsert mismatch raises CorruptVectorError per spec R4.3.
