# Source Recon — live-e2e-synthetic

**Mode**: A (magnitude scan)
**Run date**: 2026-06-15
**Graph**: `live-e2e-synthetic`
**Data Source node**: `live-e2e-synthetic-data-source-orders-db`
**Source label**: Synthetic Orders DB
**Kind**: SQLite (sqlite)
**Path**: `tests/fixtures/synthetic_source.db`
**SQLite version**: 3.49.1
**File size**: 12 288 bytes
**DRY-RUN**: active — no graph writes performed

---

## Inventory

| Object | source_type | Container | approx_rows | Explorable? | Recommended next |
|---|---|---|---|---|---|
| customers | sqlite-table | main | 5 | yes | document columns (Mode B) |
| orders | sqlite-table | main | 5 | yes | document columns (Mode B) |
| unsupported-json-api | json-api | n/a | unknown | no | manual contract required |

---

## Size assessment

Total explorable tables: 2  
Total rows across explorable tables: ~10 (5 + 5)  
Unsupported objects requiring manual handling: 1  

**Recommended split**: `mono-agent` — the source is small (2 tiny tables). A single documenter can cover both `customers` and `orders` in one pass.

---

## Notes

- Both tables are fully readable via `explore_source`; no `query_source` calls were needed for sizing.
- `unsupported-json-api` is NOT explorable via `explore_source` or `query_source`. It is recorded here so the PLAN stage can mark it skip-by-design.
- No graph mutations were attempted or performed in this scan.

---

<!-- canonical-payload -->
```json
{
  "artifact_type": "recon",
  "graph_id": "live-e2e-synthetic",
  "data_source_node": "live-e2e-synthetic-data-source-orders-db",
  "run_date": "2026-06-15",
  "dry_run": true,
  "recommended_split": "mono-agent",
  "inventory": [
    {
      "object_id": "customers",
      "source_type": "sqlite-table",
      "container": "main",
      "approx_rows": 5,
      "explorable": true,
      "recommended_next": "document columns (Mode B)"
    },
    {
      "object_id": "orders",
      "source_type": "sqlite-table",
      "container": "main",
      "approx_rows": 5,
      "explorable": true,
      "recommended_next": "document columns (Mode B)"
    },
    {
      "object_id": "unsupported-json-api",
      "source_type": "json-api",
      "container": null,
      "approx_rows": null,
      "explorable": false,
      "recommended_next": "manual contract required"
    }
  ]
}
```
