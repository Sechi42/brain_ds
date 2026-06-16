# Documentation Plan — live-e2e-synthetic (DRY-RUN)

**Plan date**: 2026-06-15
**Graph**: `live-e2e-synthetic`
**Data Source node**: `live-e2e-synthetic-data-source-orders-db`
**Source of truth**: recon-live-e2e-synthetic-2026-06-15.md
**Split strategy**: mono-agent (small source: 2 explorable tables, ~5 rows each)

## 1. Outcome Title
Deterministic slice-to-agent assignment for the synthetic orders DB. One slice covers both explorable tables; the unsupported json-api object is recorded as an explicit skip-by-design.

## 2. Quick Path / Summary
Recon inventoried 3 objects: 2 explorable sqlite tables (`customers`, `orders`) and 1 non-explorable object (`unsupported-json-api`, json-api). Because the source is tiny, a single documenter handles both tables in `slice-001`. The unsupported object is NOT assigned to any slice — it is an explicit skip so it can never be silently omitted.

## 3. Details Table — Slice Assignments
| slice_id | assigned_objects | container | assigned_agent | status |
|---|---|---|---|---|
| slice-001 | customers, orders | main | brainds-source-explorer | assigned |

### Skips (by design)
| object_id | source_type | reason | recommended_next |
|---|---|---|---|
| unsupported-json-api | json-api | not explorable (no connection descriptor) | manual contract required |

## 4. Coverage Checklist — Completeness Invariant
- Recon inventory: { customers, orders, unsupported-json-api }
- union(plan slices) = { customers, orders }
- skips = { unsupported-json-api }
- union(slices) ∪ skips = { customers, orders, unsupported-json-api }
- **Invariant union(slices) ∪ skips == recon inventory: HOLDS**
- No object planned twice (no duplicates). No explorable object left unassigned (no gaps).

## 5. Next Step
Dispatch slice-001 to brainds-source-explorer (Mode B sectioned documentation). The unsupported object is deferred to a manual contract track and must surface in the consolidation report as skipped-by-design, never as a gap.

<!-- canonical-payload -->
```json
{
  "artifact_type": "plan",
  "graph_id": "live-e2e-synthetic",
  "data_source_node": "live-e2e-synthetic-data-source-orders-db",
  "split_strategy": "mono-agent",
  "slices": [
    {"slice_id": "slice-001", "assigned_objects": ["customers", "orders"], "container": "main", "assigned_agent": "brainds-source-explorer"}
  ],
  "skipped_by_design": [
    {"object_id": "unsupported-json-api", "source_type": "json-api", "reason": "not explorable (no connection descriptor)", "recommended_next": "manual contract required"}
  ],
  "recon_inventory": ["customers", "orders", "unsupported-json-api"],
  "invariant_result": "HOLDS",
  "gaps": [],
  "duplicates": [],
  "graph_writes_attempted": false
}
```
