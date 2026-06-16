# Source Docs — live-e2e-synthetic / slice-001

**Mode**: B (sectioned documentation)
**Slice**: slice-001
**Assigned objects**: `customers`, `orders` (container `main`)
**Run date**: 2026-06-15
**Graph**: `live-e2e-synthetic`
**Data Source node**: `live-e2e-synthetic-data-source-orders-db`
**DRY-RUN**: active — no graph writes performed

---

## 1. Outcome Title

Full column-level documentation for `customers` and `orders` tables in the Synthetic Orders DB SQLite source, ready for brain_ds node card population.

---

## 2. Quick Path / Summary

Both assigned tables were explored via `explore_source` (schema + full preview, 5 rows each, no truncation). Two targeted `query_source` SELECT calls confirmed segment distribution and order status breakdown. All 9 columns across both tables are documented with inferred business meaning and quality notes. No nulls observed in the 5-row fixture dataset. The `orders.customer_id` column is a foreign key referencing `customers.customer_id`, establishing the join relationship between the two tables.

**Source characteristics at a glance:**

| Table | Rows | Columns | Primary Key | FK to |
|---|---|---|---|---|
| customers | 5 | 4 | customer_id | — |
| orders | 5 | 5 | order_id | customers.customer_id |

---

## 3. Details Table

### Table: `customers`

Container: `main` | Estimated rows: 5 | SQLite

| Column | Type | Business Meaning (inferred) | Quality Notes |
|---|---|---|---|
| `customer_id` | INTEGER | Surrogate primary key — unique integer identifier per customer record | No nulls observed; values sequential (1–5); no duplicates in sample |
| `name` | TEXT | Legal or trading name of the customer organisation | No nulls observed; all values are company names (not personal names); format is free-text |
| `segment` | TEXT | Commercial tier or market segment the customer belongs to | No nulls; 3 distinct values observed: `Enterprise` (3), `Mid Market` (1), `SMB` (1); enum-like — consider constraining in downstream models |
| `region` | TEXT | Geographic region associated with the customer | No nulls; 3 distinct values in sample: `LATAM` (2), `North America` (2), `EMEA` (1); free-text, no ISO standard applied — normalisation [needs clarification] |

**Sample rows (all 5 — complete dataset):**

| customer_id | name | segment | region |
|---|---|---|---|
| 1 | Acme Logistics | Enterprise | LATAM |
| 2 | Beta Retail | SMB | LATAM |
| 3 | Cielo Health | Enterprise | North America |
| 4 | Delta Foods | Mid Market | EMEA |
| 5 | Evergreen Energy | Enterprise | North America |

---

### Table: `orders`

Container: `main` | Estimated rows: 5 | SQLite

| Column | Type | Business Meaning (inferred) | Quality Notes |
|---|---|---|---|
| `order_id` | INTEGER | Surrogate primary key — unique integer identifier per order | No nulls; values start at 101 (not 1) — numbering offset suggests fixture seed, not a full table; no duplicates in sample |
| `customer_id` | INTEGER | Foreign key referencing `customers.customer_id` — links each order to its customer | No nulls; customer_id 4 (Delta Foods) has no orders in the sample — referential completeness [needs clarification] for full dataset |
| `order_total` | REAL | Monetary value of the order (currency unit unknown — likely USD, inferred) | No nulls; range 980.00 – 12 500.50; floating-point type — rounding behaviour in aggregations should be verified; currency denomination not encoded in schema [needs clarification] |
| `status` | TEXT | Lifecycle state of the order | No nulls; 3 distinct values: `fulfilled` (2), `pending` (2), `cancelled` (1); enum-like — full allowed set [needs clarification] (e.g. is `returned` or `processing` valid?) |
| `created_at` | TEXT | Date the order was created | No nulls; stored as TEXT in ISO 8601 date format (`YYYY-MM-DD`); no time component; SQLite has no native DATE type — downstream consumers must cast; timezone not captured [needs clarification] |

**Sample rows (all 5 — complete dataset):**

| order_id | customer_id | order_total | status | created_at |
|---|---|---|---|---|
| 101 | 1 | 12500.50 | fulfilled | 2026-06-10 |
| 102 | 2 | 980.00 | pending | 2026-06-11 |
| 103 | 3 | 4430.75 | fulfilled | 2026-06-11 |
| 104 | 1 | 2175.20 | cancelled | 2026-06-12 |
| 105 | 5 | 8890.10 | pending | 2026-06-13 |

---

## 4. Coverage Checklist

| Assigned Object | Explored | Columns Documented | Quality Notes Added | Status |
|---|---|---|---|---|
| `customers` | yes | 4 / 4 | yes | COMPLETE |
| `orders` | yes | 5 / 5 | yes | COMPLETE |
| `unsupported-json-api` | NOT assigned to this slice | — | — | SKIPPED (by design) |

All assigned objects covered. No assigned object was skipped or partially documented.

---

## 5. Next Step

1. **Consolidation** — pass this artifact and any parallel slice artifacts to the consolidation agent (`brainds-graph-mapper` or equivalent) to populate `card_sections` on node `live-e2e-synthetic-data-source-orders-db`.
2. **Owner clarification** — before publishing, resolve the four `[needs clarification]` items: `region` normalisation standard, `order_total` currency denomination, full `status` enum set, and `created_at` timezone assumption.
3. **Relationship edge** — an edge between `orders` and `customers` (via `customer_id` FK) should be proposed; this is a graph-write action and must NOT happen in this dry-run.
4. **`unsupported-json-api`** — requires a manual contract: the object is not explorable via `explore_source`; the owner must provide an OpenAPI spec or equivalent schema description.

---

## Suggested brain_ds card_sections (customers)

```json
[
  {"title": "Overview",         "content": "Customer master table. Stores one record per client organisation with segment and region classification.",  "icon": "info",     "order": 1},
  {"title": "Structure",        "content": "SQLite table `customers` in container `main`. 5 rows (fixture). 4 columns.",                              "icon": "database", "order": 2},
  {"title": "Columns / Fields", "content": "| Column | Type | Meaning |\n|---|---|---|\n| customer_id | INTEGER | Surrogate PK |\n| name | TEXT | Organisation name |\n| segment | TEXT | Commercial tier (Enterprise / Mid Market / SMB) |\n| region | TEXT | Geographic region (LATAM / North America / EMEA) |", "icon": "table", "order": 3},
  {"title": "Purpose",          "content": "Dimension table — provides customer context for orders and downstream analytics.",                          "icon": "target",   "order": 4},
  {"title": "Owner",            "content": "unknown — ask owner",                                                                                      "icon": "user",     "order": 5},
  {"title": "Refresh Cadence",  "content": "unknown — ask owner",                                                                                      "icon": "clock",    "order": 6}
]
```

## Suggested brain_ds card_sections (orders)

```json
[
  {"title": "Overview",         "content": "Transactional orders table. Each row is one order placed by a customer, with monetary total, lifecycle status, and creation date.", "icon": "info",     "order": 1},
  {"title": "Structure",        "content": "SQLite table `orders` in container `main`. 5 rows (fixture). 5 columns. FK: customer_id → customers.customer_id.",                "icon": "database", "order": 2},
  {"title": "Columns / Fields", "content": "| Column | Type | Meaning |\n|---|---|---|\n| order_id | INTEGER | Surrogate PK (starts at 101) |\n| customer_id | INTEGER | FK to customers |\n| order_total | REAL | Order value (currency TBC) |\n| status | TEXT | fulfilled / pending / cancelled |\n| created_at | TEXT | ISO 8601 date, no time component |", "icon": "table", "order": 3},
  {"title": "Purpose",          "content": "Fact table — core transaction log for revenue analytics and order lifecycle tracking.",                                             "icon": "target",   "order": 4},
  {"title": "Owner",            "content": "unknown — ask owner",                                                                                                              "icon": "user",     "order": 5},
  {"title": "Refresh Cadence",  "content": "unknown — ask owner",                                                                                                              "icon": "clock",    "order": 6}
]
```

---

<!-- canonical-payload -->
```json
{
  "artifact_type": "source-docs",
  "graph_id": "live-e2e-synthetic",
  "slice_id": "slice-001",
  "assigned_objects": ["customers", "orders"],
  "run_date": "2026-06-15",
  "dry_run": true,
  "data_source_node": "live-e2e-synthetic-data-source-orders-db",
  "documented_objects": [
    {
      "object_id": "customers",
      "container": "main",
      "row_estimate": 5,
      "column_summary": [
        {"name": "customer_id", "type": "INTEGER", "meaning": "Surrogate primary key", "quality": "clean — no nulls, sequential"},
        {"name": "name",        "type": "TEXT",    "meaning": "Organisation trading name", "quality": "clean — no nulls; free-text format"},
        {"name": "segment",     "type": "TEXT",    "meaning": "Commercial tier (Enterprise / Mid Market / SMB)", "quality": "enum-like; 3 values; no nulls"},
        {"name": "region",      "type": "TEXT",    "meaning": "Geographic region", "quality": "no nulls; normalisation standard needs clarification"}
      ]
    },
    {
      "object_id": "orders",
      "container": "main",
      "row_estimate": 5,
      "column_summary": [
        {"name": "order_id",    "type": "INTEGER", "meaning": "Surrogate primary key (seed starts at 101)", "quality": "clean — no nulls, no duplicates"},
        {"name": "customer_id", "type": "INTEGER", "meaning": "FK to customers.customer_id", "quality": "no nulls in sample; customer_id 4 has no orders — referential completeness needs clarification"},
        {"name": "order_total", "type": "REAL",    "meaning": "Monetary order value", "quality": "no nulls; currency unit not encoded — needs clarification"},
        {"name": "status",      "type": "TEXT",    "meaning": "Order lifecycle state (fulfilled / pending / cancelled)", "quality": "enum-like; full allowed set needs clarification"},
        {"name": "created_at",  "type": "TEXT",    "meaning": "Order creation date (ISO 8601, date only)", "quality": "no nulls; stored as TEXT not DATE; no timezone — needs clarification"}
      ]
    }
  ],
  "gaps": [
    "customers.region — normalisation standard unknown",
    "orders.order_total — currency denomination not encoded in schema",
    "orders.status — full allowed enum set unknown",
    "orders.created_at — timezone assumption not captured",
    "unsupported-json-api — not explorable; requires manual contract from owner"
  ],
  "graph_writes_attempted": false
}
```
