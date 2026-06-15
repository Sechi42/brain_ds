# Source Documentation: Synthetic Orders DB — `orders` table

**Generated**: 2026-06-14
**Source node**: live-e2e-synthetic-data-source-orders-db
**Graph**: live-e2e-synthetic
**Table**: main.orders
**Row estimate**: 5
**Explored via**: brain_ds `explore_source` (live connector)

---

## card_sections (brainds-docs ready)

```json
[
  {
    "title": "Overview",
    "content": "The `orders` table records every individual order placed by customers, capturing the monetary value, fulfillment status, and creation date for each transaction.",
    "icon": "info",
    "order": 1
  },
  {
    "title": "Structure",
    "content": "Source: SQLite · Database: synthetic_source.db · Container: main · Table: orders · Estimated rows: 5 · Columns: 5",
    "icon": "database",
    "order": 2
  },
  {
    "title": "Columns / Fields",
    "content": "| Column | Type | Meaning | Notes |\n|---|---|---|---|\n| order_id | INTEGER | Unique numeric identifier for each order | Primary key (inferred); sample starts at 101 |\n| customer_id | INTEGER | Foreign key linking to `customers.customer_id` | Join key (inferred); no FK constraint visible from preview |\n| order_total | REAL | Monetary value of the order | Currency unit [needs clarification]; sample range 980.0 – 12500.5 |\n| status | TEXT | Current fulfillment status of the order | Observed values: fulfilled, pending, cancelled |\n| created_at | TEXT | Date the order was created | Stored as TEXT in ISO 8601 date format (YYYY-MM-DD); no time component in sample |",
    "icon": "table",
    "order": 3
  },
  {
    "title": "Purpose",
    "content": "The central fact table for order analytics; joins to `customers` via `customer_id` to enable revenue reporting by segment, region, and time period (inferred).",
    "icon": "target",
    "order": 4
  },
  {
    "title": "Owner",
    "content": "[needs clarification] — no owner metadata present on the node. Ask the data source owner to confirm.",
    "icon": "user",
    "order": 5
  },
  {
    "title": "Refresh Cadence",
    "content": "[needs clarification] — cadence not derivable from the SQLite file alone. Ask owner whether this is a static fixture or a regularly refreshed extract.",
    "icon": "clock",
    "order": 6
  }
]
```

---

## Raw Schema (from explore_source)

| Column | Type | Sample Value |
|---|---|---|
| order_id | INTEGER | 101 |
| customer_id | INTEGER | 1 |
| order_total | REAL | 12500.5 |
| status | TEXT | fulfilled |
| created_at | TEXT | 2026-06-10 |

## Preview (all 5 rows — truncated: false)

| order_id | customer_id | order_total | status | created_at |
|---|---|---|---|---|
| 101 | 1 | 12500.50 | fulfilled | 2026-06-10 |
| 102 | 2 | 980.00 | pending | 2026-06-11 |
| 103 | 3 | 4430.75 | fulfilled | 2026-06-11 |
| 104 | 1 | 2175.20 | cancelled | 2026-06-12 |
| 105 | 5 | 8890.10 | pending | 2026-06-13 |

## Quality Notes

- Row count is small (5 rows); this is a synthetic fixture, not a production dataset.
- `order_id` is sequential starting at 101 — consistent with a surrogate primary key.
- `customer_id` 4 (Delta Foods) has no orders in the preview set; referential integrity not enforced at the SQLite layer by default.
- `order_total` is stored as REAL (floating point); monetary use cases may prefer NUMERIC/DECIMAL for precision — flag to owner.
- `created_at` is stored as TEXT, not a DATE or DATETIME type; date-range queries will work if values are consistently ISO 8601, but type coercion will be required in most query engines.
- Three distinct `status` values observed: fulfilled, pending, cancelled — full enum unknown.
- Date range in preview: 2026-06-10 to 2026-06-13 (4-day window, synthetic).

## Gaps (needs owner input)

- Confirm the currency unit for `order_total` (USD assumed, [needs clarification]).
- Confirm whether `created_at` ever includes a time component (only date portion seen in sample).
- Clarify the full enum of allowed `status` values (e.g., is "refunded" or "shipped" possible?).
- Confirm whether `customer_id` has a foreign key constraint enforced in the DDL.
- Confirm data owner and refresh cadence.
