## Source Explorer Findings — customers table

**Source name**: orders-db (customers table)
**File / path**: tests/fixtures/synthetic_source.db
**Kind**: Relational DB (SQLite)
**Owner**: unknown
**Last modified**: unknown
**Refresh cadence**: unknown — ask owner

### Overview

The `customers` table is a reference dimension that identifies each customer account by name, commercial segment, and geographic region (inferred from 5 rows; synthetic fixture data).

### Structure

- Database: SQLite — `synthetic_source.db`
- Container: `main`
- Table: `customers`
- Row estimate: 5

### Columns / Fields

| Column | Type | Meaning | Notes |
|---|---|---|---|
| customer_id | INTEGER | Surrogate primary key for each customer account | Numeric, sequential starting at 1 |
| name | TEXT | Human-readable customer/company name | e.g. "Acme Logistics", "Beta Retail" |
| segment | TEXT | Commercial tier of the customer | Observed values: Enterprise, SMB, Mid Market |
| region | TEXT | Geographic region of the customer | Observed values: LATAM, North America, EMEA |

### Purpose

Dimension table used to look up customer identity and segmentation attributes, joinable to the `orders` table via `customer_id` (inferred).

### Quality Notes

- Row count is 5 — this is a synthetic fixture; production volume is unknown.
- `segment` and `region` appear to be free-text enumerations with no enforced constraint; canonical value lists should be confirmed with the owner.
- No null values observed in any column across all 5 rows.

### Gaps (needs owner input)

- Canonical list of allowed `segment` and `region` values.
- Refresh cadence (batch load, CDC, manual?).
- Whether `customer_id` is a system-generated surrogate or sourced from an upstream CRM.

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
          "content": "The customers table is a reference dimension that identifies each customer account by name, commercial segment, and geographic region (5 rows observed; synthetic fixture data).",
          "icon": "info",
          "order": 1
        },
        {
          "title": "Structure",
          "content": "SQLite database synthetic_source.db — container: main — table: customers — row estimate: 5",
          "icon": "database",
          "order": 2
        },
        {
          "title": "Columns / Fields",
          "content": "| Column | Type | Meaning | Notes |\n|---|---|---|---|\n| customer_id | INTEGER | Surrogate primary key for each customer account | Numeric, sequential starting at 1 |\n| name | TEXT | Human-readable customer/company name | e.g. \"Acme Logistics\", \"Beta Retail\" |\n| segment | TEXT | Commercial tier of the customer | Observed values: Enterprise, SMB, Mid Market |\n| region | TEXT | Geographic region of the customer | Observed values: LATAM, North America, EMEA |",
          "icon": "table",
          "order": 3
        },
        {
          "title": "Purpose",
          "content": "Dimension table used to look up customer identity and segmentation attributes, joinable to the orders table via customer_id (inferred).",
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
