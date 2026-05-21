# Verification Report — sqlite-graph-store

**Change**: `sqlite-graph-store`
**Mode**: Strict TDD
**Verdict**: **PASS WITH WARNINGS**
**Overall**: All four findings from verify report #955 are closed, the required runtime suites pass (`18/18`, `44/44`, `40/40`, `660/660`), and tasks `1.1–5.4` remain complete. Residual warnings are artifact/spec coherence issues, not S7 implementation regressions.

## What to review first

1. **Closure of previous FAIL findings** — `query_nodes(..., parent_id=...)`, `list_graphs()` tie-breaker, read-only stale-schema guard, and file-backed WAL/close evidence are now all present and runtime-proven.
2. **Behavioral proof** — full suite `660/660` passed (`skipped=4`), store-focused suite `44/44` passed, render/contract regression suite `40/40` passed, and the S7-focused subset passed `18/18`.
3. **Residual warnings** — the implementation is green, but the artifact set still has spec/design wording drift around `:memory:` WAL behavior, evidence back-pointers, and the design signature snippet for `query_nodes`.

## Scope / out of scope

- **In scope**: verification only, strict TDD evidence, runtime tests, spec/design/tasks/apply-progress compliance, previous finding closure.
- **Out of scope**: implementation fixes, build/type-check, dependency changes, UI/runtime launcher work.

---

## Completeness

| Metric | Value |
|---|---:|
| Tasks total | 24 |
| Tasks complete | 24 |
| Tasks incomplete | 0 |

All checklist items `1.1–5.4` remain `[x]` in `openspec/changes/sqlite-graph-store/tasks.md`, and `apply-progress.md` records cumulative completion plus S7 remediation tasks `S7-R1` through `S7-R4`.

---

## Build & Tests Execution

**Build**: Skipped by user instruction: never build

**Tests run**

| Command | Result |
|---|---|
| `uv run python -m unittest tests.store.test_node_repository tests.store.test_graph_meta tests.store.test_graph_store_roundtrip` | ✅ `18/18` passed |
| `uv run python -m unittest tests.store.test_schema tests.store.test_migrations tests.store.test_serialization tests.store.test_graph_meta tests.store.test_node_repository tests.store.test_edge_repository tests.store.test_evidence_repository tests.store.test_cluster_repository tests.store.test_graph_store_roundtrip tests.store.test_embedding_repository -v` | ✅ `44/44` passed |
| `uv run python -m unittest tests.test_render_context_contract tests.test_render_context_golden tests.test_graph_contract -v` | ✅ `40/40` passed |
| `uv run python -m unittest discover -s tests` | ✅ `660/660` passed, `skipped=4` |
| `git diff -- pyproject.toml uv.lock` | ✅ no output (no dependency file diffs) |

**Coverage**: ➖ Not available — no coverage tool/cached capability was found

---

## TDD Compliance

| Check | Result | Details |
|---|---|---|
| TDD Evidence reported | ✅ | Found in `apply-progress.md` / Engram #949 |
| All remediation tasks have tests | ✅ | `S7-R1..S7-R4` each name concrete test files and behaviors |
| RED confirmed (tests exist) | ✅ | Referenced files exist: `test_node_repository.py`, `test_graph_meta.py`, `test_graph_store_roundtrip.py` |
| GREEN confirmed (tests pass) | ✅ | S7-focused subset now passes `18/18`; store-focused suite passes `44/44` |
| Triangulation adequate | ✅ | Repository + public API coverage exists for `parent_id`; ordering and read-only guard each have dedicated cases |
| Safety Net internally coherent | ✅ | Historical `13/13` baseline claims are consistent with the command trail, and the post-remediation subset now passes `18/18` |

**TDD Compliance**: `6/6` checks passed

---

## Test Layer Distribution

| Layer | Tests | Files | Tools |
|---|---:|---:|---|
| Unit | 44 | 10 | `unittest` |
| Integration | 0 | 0 | not added by this change |
| E2E | 0 | 0 | not installed |
| **Total** | **44** | **10** | |

---

## Changed File Coverage

Coverage analysis skipped — no coverage tool detected.

---

## Assertion Quality

**Assertion quality**: ✅ All reviewed assertions verify real behavior

Manual audit of the S7-touched store tests found no tautologies, ghost loops, smoke-only assertions, or assertion-free tests.

---

## Quality Metrics

**Linter**: ➖ Not available
**Type Checker**: ➖ Skipped by user instruction: never build

---

## Previous Finding Closure Summary

| Previous finding (#955) | Current evidence | Status |
|---|---|---|
| `query_nodes(..., parent_id=...)` missing | `GraphStore.query_nodes(..., parent_id=...)` exists in `brain_ds/store/graph_store.py`; `NodeRepository.query_nodes(..., parent_id=...)` exists in `brain_ds/store/repository.py`; runtime tests `test_query_nodes_by_type_and_parent_id` and `test_query_nodes_filters_by_type_and_parent_id` passed | ✅ Closed |
| `list_graphs()` tie-breaker drift | `GraphMetaRepository.list_graphs()` orders by `updated_at DESC, id ASC`; runtime test `test_list_graphs_tie_breaker_is_id_asc_when_updated_at_equal` passed | ✅ Closed |
| `read_only=True` stale schema guard missing | `GraphStore._assert_read_only_schema_compatible()` raises `IncompatibleStoreError`; runtime test `test_read_only_mode_raises_on_stale_schema_version` passed | ✅ Closed |
| WAL/close runtime evidence missing | file-backed runtime test `test_file_backed_connection_uses_wal_mode_and_close_is_safe` passed and proves `journal_mode=wal`, safe double-close, and zero-byte `-wal` if the sidecar remains present | ✅ Closed |

---

## Spec Compliance Matrix

| Requirement | Scenario | Test(s) | Result |
|---|---|---|---|
| Database Initialization & Migrations | First connection to new database | `tests.store.test_graph_store_roundtrip.GraphStoreRoundtripTests.test_file_backed_connection_uses_wal_mode_and_close_is_safe`; `tests.store.test_migrations.TestMigrations.test_fresh_store_reports_version_one`; `tests.store.test_schema.TestSchema.test_v1_creates_all_eight_tables`; `tests.store.test_schema.TestSchema.test_v1_creates_all_indices`; `tests.store.test_schema.TestSchema.test_pragmas_set_on_connect` | ⚠️ PARTIAL |
| Database Initialization & Migrations | Existing database with older schema | `tests.store.test_migrations.TestMigrations.test_second_connect_is_noop`; `tests.store.test_migrations.TestMigrations.test_forward_version_raises_incompatible`; `tests.store.test_graph_store_roundtrip.GraphStoreRoundtripTests.test_read_only_mode_raises_on_stale_schema_version` | ✅ COMPLIANT |
| Database Initialization & Migrations | Closing connection | `tests.store.test_graph_store_roundtrip.GraphStoreRoundtripTests.test_file_backed_connection_uses_wal_mode_and_close_is_safe`; `tests.store.test_graph_store_roundtrip.GraphStoreRoundtripTests.test_close_is_idempotent`; `tests.store.test_graph_store_roundtrip.GraphStoreRoundtripTests.test_context_manager_closes_on_exit` | ✅ COMPLIANT |
| JSON Import and Export | Import valid JSON | `tests.store.test_graph_store_roundtrip.GraphStoreRoundtripTests.test_import_json_then_export_json_matches_input` | ✅ COMPLIANT |
| JSON Import and Export | Export graph to JSON | `tests.store.test_graph_store_roundtrip.GraphStoreRoundtripTests.test_import_json_then_export_json_matches_input` | ✅ COMPLIANT |
| Entity Queries | Query nodes by type and parent | `tests.store.test_node_repository.NodeRepositoryTests.test_query_nodes_by_type_and_parent_id`; `tests.store.test_graph_store_roundtrip.GraphStoreRoundtripTests.test_query_nodes_filters_by_type_and_parent_id` | ✅ COMPLIANT |
| Entity Queries | Query edges by target | `tests.store.test_edge_repository.EdgeRepositoryTests.test_query_edges_by_source_and_target` | ✅ COMPLIANT |
| Embeddings and Cosine Similarity | Insert new embedding | `tests.store.test_embedding_repository.EmbeddingRepositoryTests.test_upsert_embedding_is_idempotent` | ✅ COMPLIANT |
| Embeddings and Cosine Similarity | Nearest embeddings query | `tests.store.test_embedding_repository.EmbeddingRepositoryTests.test_nearest_embeddings_orders_by_cosine`; `tests.store.test_embedding_repository.EmbeddingRepositoryTests.test_nearest_embeddings_excludes_self`; `tests.store.test_embedding_repository.EmbeddingRepositoryTests.test_nearest_embeddings_filters_by_model`; `tests.store.test_embedding_repository.GraphStoreEmbeddingApiTests.test_graph_store_embedding_methods_delegate` | ✅ COMPLIANT |
| Embeddings and Cosine Similarity | Mixed dimensions | `tests.store.test_embedding_repository.EmbeddingRepositoryTests.test_upsert_embedding_mixed_dim_raises` | ✅ COMPLIANT |

**Compliance summary**: `9/10` compliant, `1/10` partial, `0` failing, `0` untested

---

## Correctness (Static — Structural Evidence)

| Requirement / source | Status | Notes |
|---|---|---|
| Database Initialization & Migrations | ✅ Implemented with one spec wording caveat | DDL, migrations, PRAGMAs, rollback path, read-only incompatibility gate, and close checkpoint call exist in code |
| JSON Import and Export | ✅ Implemented | `GraphStore.import_json/export_json/save_graph/load_graph` exist and runtime roundtrip tests pass |
| Entity Queries | ✅ Implemented | Node `parent_id` filtering now exists in both repository and public API; edge/evidence/cluster repositories remain present |
| Embeddings and Cosine Similarity | ✅ Implemented | CHECK enum, packed float32 BLOBs, dimension guard, cosine ranking, self-exclusion, and GraphStore delegation exist |
| Spec OQ-2 evidence back-pointers (`node_ids` / `edge_ids`) | ⚠️ Artifact drift | `spec.md` says these MUST exist on evidence rows, but `schema.py`, `repository.py`, tests, and design artifacts do not model them |

---

## Coherence (Design)

| Decision / contract | Followed? | Notes |
|---|---|---|
| Stdlib-only persistence | ✅ Yes | No dependency file diffs in `pyproject.toml` / `uv.lock` |
| Explicit WAL checkpoint on close | ✅ Yes | `graph_store.py` executes `PRAGMA wal_checkpoint(TRUNCATE)` before closing |
| `list_graphs()` ordering `updated_at DESC, id ASC` | ✅ Yes | `repository.py` now matches design and runtime test passes |
| Read-only stale schema should raise immediately | ✅ Yes | `GraphStore._assert_read_only_schema_compatible()` now enforces it |
| Public node query supports `parent_id` from proposal/spec | ✅ Yes in code, ⚠️ stale design snippet | Implementation and tests match, but the signature snippet in `design.md` still omits `parent_id` |

---

## Issues Found

### CRITICAL (must fix before archive)

None.

### WARNING (should fix)

1. **Initialization scenario is only partially aligned with the current spec wording** — runtime evidence proves WAL for file-backed stores, but `tests.store.test_schema.TestSchema.test_pragmas_set_on_connect` also proves SQLite `:memory:` connections report `journal_mode=memory`, so the spec's combined “file or `:memory:` → WAL” wording is too strong.
2. **Spec/design/implementation drift on evidence back-pointers** — `spec.md` OQ-2 says evidence rows MUST store `node_ids` / `edge_ids`, but the design, schema, repository layer, and tests do not implement that shape.
3. **Design doc snippet is stale** — the `design.md` public API signature block still omits `parent_id` from `query_nodes`, even though the implementation and tests now include it.

### SUGGESTION (nice to have)

1. Clarify the artifact set before archive: either narrow the spec's `:memory:` WAL wording and remove/implement OQ-2 back-pointers, or add explicit follow-up work so the archive trail does not preserve contradictory contracts.

---

## Risks

- If the change is archived without reconciling the artifact drift, future phases may read contradictory contracts about evidence back-pointers and `:memory:` WAL behavior.
- Coverage tooling is still unavailable, so changed-file coverage remains unverifiable even though runtime behavior is green.

---

## Verdict

**PASS WITH WARNINGS**

S7 remediation successfully closed every prior verification finding and restored runtime/spec coverage for the blocking behaviors. The remaining issues are **artifact coherence warnings**, not failing implementation behavior.
