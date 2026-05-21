# Apply Progress: sqlite-graph-store (S1 + S2 + S3 + S4 + S5 + S6 + S7 remediation)

## Mode
Strict TDD

## PR Slice Boundary
- Strategy: chained PRs (stacked-to-main)
- Current slice: **S7 remediation only** (verify findings from `verify-report` #955)
- Start: verify finding remediation
- End: critical + warning implementation/test gaps resolved in code/tests
- Before: S1 1.1–1.7, S2 2.1–2.8, S3 3.1–3.3, S4 4.1–4.2, S5 5.1–5.4, S6 integration closure complete
- After: store change ready for re-verify
- Out of scope preserved: runtime launcher/UI/desktop packaging/MCP, coverage tooling/dependencies

## Completed Tasks (Cumulative)
- [x] 1.1–1.7
- [x] 2.1–2.8
- [x] 3.1–3.3
- [x] 4.1–4.2
- [x] 5.1–5.4
- [x] S7-R1 Add and implement `query_nodes(..., parent_id=...)` end-to-end
- [x] S7-R2 Add runtime WAL/file-backed close evidence test (stable checkpoint evidence)
- [x] S7-R3 Fix `list_graphs()` tie-breaker to `updated_at DESC, id ASC`
- [x] S7-R4 Add read-only stale-schema proactive incompatibility guard

## Verify finding → remediation mapping
1. **CRITICAL** missing `query_nodes(type, parent_id)`
   - Remediation: added RED tests for repository + public API scenario, then implemented `parent_id` filter in `NodeRepository.query_nodes` and `GraphStore.query_nodes`.
2. **WARNING** WAL/close runtime evidence missing
   - Remediation: added file-backed GraphStore test asserting `journal_mode=wal`; close remains safe/idempotent; stable post-close `-wal` size check when file exists.
3. **WARNING** ordering drift (`id DESC` vs `id ASC` tie-breaker)
   - Remediation: fixed SQL order clause and added tie-break test with forced equal `updated_at`.
4. **WARNING** read-only stale schema guard missing
   - Remediation: added proactive read-only schema compatibility check and RED test with stale schema version.

## TDD Cycle Evidence (S7 remediation)
| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| S7-R1 | `tests/store/test_node_repository.py`, `tests/store/test_graph_store_roundtrip.py` | Unit | ✅ `13/13` baseline | ✅ Added failing parent_id tests first | ✅ `18/18` focused pass | ✅ repository + public API scenarios | ✅ normalized type filter with `lower()` for API compatibility |
| S7-R2 | `tests/store/test_graph_store_roundtrip.py` | Unit (file-backed) | ✅ `13/13` baseline | ✅ Added WAL/close evidence test first | ✅ `18/18` focused pass | ✅ journal mode + close/idempotency/`-wal` file behavior | ➖ None needed |
| S7-R3 | `tests/store/test_graph_meta.py` | Unit | ✅ `13/13` baseline | ✅ Added tie-break failing test first | ✅ `18/18` focused pass | ✅ separate updated_at-desc and equal-updated_at cases | ➖ None needed |
| S7-R4 | `tests/store/test_graph_store_roundtrip.py` | Unit (file-backed) | ✅ `13/13` baseline | ✅ Added stale schema read-only failing test first | ✅ `18/18` focused pass | ✅ stale schema mismatch + read-only open flow | ✅ constructor now closes connection on init failure |

## Test Commands Run (S7)
- `uv run python -m unittest tests.store.test_node_repository tests.store.test_graph_meta tests.store.test_graph_store_roundtrip` (safety net) → `13/13` OK
- `uv run python -m unittest tests.store.test_node_repository tests.store.test_graph_meta tests.store.test_graph_store_roundtrip` (RED checkpoint) → expected failures/errors confirming gaps
- `uv run python -m unittest tests.store.test_node_repository tests.store.test_graph_meta tests.store.test_graph_store_roundtrip` (GREEN) → `18/18` OK
- `uv run python -m unittest tests.store.test_schema tests.store.test_migrations tests.store.test_serialization tests.store.test_graph_meta tests.store.test_node_repository tests.store.test_edge_repository tests.store.test_evidence_repository tests.store.test_cluster_repository tests.store.test_graph_store_roundtrip tests.store.test_embedding_repository -v` → `44/44` OK
- `uv run python -m unittest discover -s tests` → `660/660` OK (`skipped=4`)

## Files Changed in S7
- `brain_ds/store/repository.py` — `list_graphs()` tie-break SQL fix; `query_nodes()` `parent_id` filter + case-insensitive type match
- `brain_ds/store/graph_store.py` — public `query_nodes(..., parent_id=...)`; read-only stale-schema compatibility check; constructor cleanup on init failure
- `tests/store/test_node_repository.py` — new RED/GREEN test for `query_nodes(type, parent_id)`
- `tests/store/test_graph_meta.py` — deterministic updated_at ordering test + tie-break test
- `tests/store/test_graph_store_roundtrip.py` — public API parent filter scenario; file-backed WAL evidence; stale read-only schema guard test
- `openspec/changes/sqlite-graph-store/apply-progress.md` — this merged cumulative progress artifact

## Deviations
- None — remediation stayed within verify findings scope and maintained OQ-1 Python parent validation approach.

## Issues
- SQLite WAL checkpoint TRUNCATE direct assertion remains platform-sensitive; test asserts strongest stable runtime evidence (`journal_mode=wal`, close idempotency, and zero-byte `-wal` if present).
