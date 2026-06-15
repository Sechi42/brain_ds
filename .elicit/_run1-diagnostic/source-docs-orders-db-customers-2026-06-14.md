# Source Documentation: Synthetic Orders DB — `customers` table

**Generated**: 2026-06-14
**Source node**: live-e2e-synthetic-data-source-orders-db
**Graph**: live-e2e-synthetic
**Table**: main.customers
**Row estimate**: 5
**Explored via**: brain_ds `explore_source` (live connector)

---

## card_sections (brainds-docs ready)

```json
[
  {
    "title": "Overview",
    "content": "The `customers` table is the master dimension for all customer accounts tracked in the Synthetic Orders DB, storing identity, market segment, and geographic region per customer.",
    "icon": "info",
    "order": 1
  },
  {
    "title": "Structure",
    "content": "Source: SQLite · Database: synthetic_source.db · Container: main · Table: customers · Estimated rows: 5 · Columns: 4",
    "icon": "database",
    "order": 2
  },
  {
    "title": "Columns / Fields",
    "content": "| Column | Type | Meaning | Notes |\n|---|---|---|---|\n| customer_id | INTEGER | Unique numeric identifier for each customer | Primary key (inferred) |\n| name | TEXT | Company or customer display name | Sample: \"Acme Logistics\" |\n| segment | TEXT | Market segment classification | Observed values: Enterprise, SMB, Mid Market |\n| region | TEXT | Geographic region of the customer | Observed values: LATAM, North America, EMEA |",
    "icon": "table",
    "order": 3
  },
  {
    "title": "Purpose",
    "content": "Acts as the customer dimension table; joined to `orders` via `customer_id` to enrich order data with segment and region attributes for reporting and analytics (inferred).",
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
| customer_id | INTEGER | 1 |
| name | TEXT | Acme Logistics |
| segment | TEXT | Enterprise |
| region | TEXT | LATAM |

## Preview (all 5 rows — truncated: false)

| customer_id | name | segment | region |
|---|---|---|---|
| 1 | Acme Logistics | Enterprise | LATAM |
| 2 | Beta Retail | SMB | LATAM |
| 3 | Cielo Health | Enterprise | North America |
| 4 | Delta Foods | Mid Market | EMEA |
| 5 | Evergreen Energy | Enterprise | North America |

## Quality Notes

- Row count is small (5 rows); this is a synthetic fixture, not a production dataset.
- `customer_id` values are sequential integers starting at 1 — consistent with a surrogate primary key.
- `segment` shows three distinct values across 5 rows (Enterprise x3, SMB x1, Mid Market x1); no nulls observed in preview.
- `region` shows three distinct values (LATAM x2, North America x2, EMEA x1); no nulls observed in preview.
- No explicit PRIMARY KEY or NOT NULL constraints are visible from the preview alone — PRAGMA introspection would confirm.

## Gaps (needs owner input)

- Confirm whether `customer_id` is enforced as PRIMARY KEY in the DDL.
- Clarify the full enum of allowed `segment` values beyond the 3 observed.
- Clarify the full enum of allowed `region` values beyond the 3 observed.
- Confirm data owner and refresh cadence.
