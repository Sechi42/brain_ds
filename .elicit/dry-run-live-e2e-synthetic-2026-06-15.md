# Dry-run Consolidation Report — live-e2e-synthetic

**Phase**: consolidation (dry-run)
**Run date**: 2026-06-15
**Graph**: `live-e2e-synthetic`
**Data Source node**: `live-e2e-synthetic-data-source-orders-db`
**DRY-RUN**: active — no graph writes performed
**Source of record**: backfilled by orchestrator from engram receipt #2256 (graph-mapper has no Write tool)

---

## Outcome title

Report-only consolidation validation for the `live-e2e-synthetic` source-documentation pipeline. Completeness invariant HOLDS, zero gaps, zero duplicates, and zero graph writes. The merged node card and FK edge that a live run WOULD push are described but NOT executed.

## Quick path / summary

The consolidation read the recon, plan, and slice-001 source-docs artifacts and validated delivered objects against the plan. Every supported object was documented; the simulated unsupported object is recorded as skip-by-design and does not count as a gap.

| object name | type | status | reason-if-skipped |
|---|---|---|---|
| customers | sqlite table | documented | |
| orders | sqlite table | documented | |
| unsupported-json-api | json endpoint | skipped | unsupported source type — manual contract required |

## Details table

Per-object consolidation outcome. `source_type` and `type_fields` echo the recon/source-docs contract; SQL fields (schema, columns, primary keys, foreign keys, sample row count) are carried from slice-001.

| object name | source_type | schema | columns | primary keys | foreign keys | sample row count | type_fields |
|---|---|---|---|---|---|---|---|
| customers | sqlite | main | customer_id:int, name:text, segment:text, region:text | customer_id | (none) | 5 | schema, columns, primary keys, foreign keys, sample row count |
| orders | sqlite | main | order_id:int, customer_id:int, order_total:real, status:text, created_at:text | order_id | customer_id -> customers.customer_id | 5 | schema, columns, primary keys, foreign keys, sample row count |

**Would-write (NOT executed):** one `update_node` on `live-e2e-synthetic-data-source-orders-db` with 8 card_sections (Overview, Structure, Columns/Fields, Purpose, Owner, Refresh Cadence, Table:customers, Table:orders) and one FK edge `orders.customer_id → customers.customer_id` (confidence 0.95).

## Coverage checklist

- [x] documented customers (4/4 columns)
- [x] documented orders (5/5 columns)
- [ ] skipped unsupported-json-api (unsupported source type — manual contract required)
- [x] completeness invariant: union(plan slices) ∪ skips == recon inventory
- [x] zero gaps, zero duplicates among supported objects
- [x] graph_writes_attempted = false (store unchanged, fixture read-only)

## Next step

Consolidate is validated; do NOT write in this dry-run. Before a live consolidation pass, resolve the four open clarifications (customers.region normalisation, orders.order_total currency, orders.status full enum, orders.created_at timezone). A live run would then push the merged card and the orders→customers FK edge.

---

<!-- canonical-payload -->
```json
{
  "artifact_type": "dry-run",
  "phase": "consolidation",
  "graph_id": "live-e2e-synthetic",
  "data_source_node": "live-e2e-synthetic-data-source-orders-db",
  "run_date": "2026-06-15",
  "dry_run": true,
  "recon_inventory": ["customers", "orders", "unsupported-json-api"],
  "delivered_objects": ["customers", "orders"],
  "skipped_by_design": ["unsupported-json-api"],
  "completeness": {
    "invariant": "union(plan_slices) ∪ skips == recon_inventory",
    "is_complete": true,
    "missing_objects": [],
    "duplicate_objects": []
  },
  "would_write": {
    "update_node": {"node_id": "live-e2e-synthetic-data-source-orders-db", "card_sections": 8},
    "add_edge": [{"source": "orders", "target": "customers", "label": "references", "confidence": 0.95}]
  },
  "open_clarifications": [
    "customers.region — normalisation standard unknown",
    "orders.order_total — currency denomination not encoded",
    "orders.status — full allowed enum set unknown",
    "orders.created_at — timezone assumption not captured"
  ],
  "graph_writes_attempted": false,
  "source": "backfilled from engram receipt #2256"
}
```
