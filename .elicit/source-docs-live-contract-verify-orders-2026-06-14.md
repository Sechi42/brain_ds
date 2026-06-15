## Source Explorer Findings — orders table

**Source name**: orders-db (orders table)
**File / path**: tests/fixtures/synthetic_source.db
**Kind**: Relational DB (SQLite)
**Owner**: unknown
**Last modified**: unknown
**Refresh cadence**: unknown — ask owner

### Overview

The `orders` table records individual sales transactions, linking each order to a customer, carrying a monetary total, a lifecycle status, and a creation date (inferred from 5 rows; synthetic fixture data).

### Structure

- Database: SQLite — `synthetic_source.db`
- Container: `main`
- Table: `orders`
- Row estimate: 5

### Columns / Fields

| Column | Type | Meaning | Notes |
|---|---|---|---|
| order_id | INTEGER | Surrogate primary key for each order | Numeric, observed starting at 101 |
| customer_id | INTEGER | Foreign key referencing customers.customer_id | Links each order to a customer account |
| order_total | REAL | Monetary value of the order | Observed range: 980.0 – 12500.5; currency unit [needs clarification] |
| status | TEXT | Lifecycle state of the order | Observed values: fulfilled, pending, cancelled |
| created_at | TEXT | Date the order was created | Stored as ISO-8601 date string (e.g. "2026-06-10"); time component absent |

### Purpose

Fact table capturing transactional order data. Joins to `customers` via `customer_id` to enable per-customer, per-segment, and per-region revenue and fulfillment analysis (inferred).

### Quality Notes

- Row count is 5 — this is a synthetic fixture; production volume is unknown.
- `order_total` is typed REAL; verify whether decimal precision is sufficient for the target currency.
- `created_at` is stored as TEXT, not a native SQLite DATE type; consumers must cast when doing date arithmetic.
- `status` appears to be a free-text enumeration (fulfilled, pending, cancelled) with no enforced constraint; additional states may exist in production.
- No null values observed across all 5 rows.

### Gaps (needs owner input)

- Currency unit for `order_total`.
- Full canonical list of `status` values.
- Whether `created_at` ever includes a time component in production.
- Refresh cadence (streaming, batch, CDC?).

<!-- canonical-payload -->
```json
{
  "artifact_type": "source-docs",
  "graph_id": "live-contract-verify",
  "documented_nodes": [
    {
      "node_id": "live-contract-verify-data-source-orders-db",
      "label": "orders-db",
      "type": "Data Source",
      "card_sections": [
        {
          "title": "Overview",
          "content": "The orders table records individual sales transactions linking each order to a customer, with a monetary total, a lifecycle status, and a creation date (5 rows observed; synthetic fixture data).",
          "icon": "info",
          "order": 1
        },
        {
          "title": "Structure",
          "content": "SQLite database synthetic_source.db — container: main — table: orders — row estimate: 5",
          "icon": "database",
          "order": 2
        },
        {
          "title": "Columns / Fields",
          "content": "| Column | Type | Meaning | Notes |\n|---|---|---|---|\n| order_id | INTEGER | Surrogate primary key for each order | Numeric, observed starting at 101 |\n| customer_id | INTEGER | Foreign key referencing customers.customer_id | Links each order to a customer account |\n| order_total | REAL | Monetary value of the order | Observed range: 980.0–12500.5; currency unit [needs clarification] |\n| status | TEXT | Lifecycle state of the order | Observed values: fulfilled, pending, cancelled |\n| created_at | TEXT | Date the order was created | ISO-8601 date string; no time component observed; stored as TEXT not DATE |",
          "icon": "table",
          "order": 3
        },
        {
          "title": "Purpose",
          "content": "Fact table capturing transactional order data. Joins to customers via customer_id to enable per-customer, per-segment, and per-region revenue and fulfillment analysis (inferred).",
          "icon": "target",
          "order": 4
        },
        {
          "title": "Owner",
          "content": "unknown — ask data platform team",
          "icon": "user",
          "order": 5
        },
        {
          "title": "Refresh Cadence",
          "content": "unknown — ask owner",
          "icon": "clock",
          "order": 6
        }
      ]
    }
  ],
  "completeness_gate": {
    "pre_mapping_recommendation": "document"
  }
}
```
