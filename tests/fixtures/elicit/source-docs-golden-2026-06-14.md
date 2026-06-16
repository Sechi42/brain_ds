# Source Documentation

## Outcome title
Golden fixture source-docs artifact for the synthetic source contract.

## Quick path / summary
| object name | type | status | reason-if-skipped |
|---|---|---|---|
| items | table | documented | |

## Details table
| object name | source_type | schema | columns | primary keys | foreign keys | sample row count | type_fields |
|---|---|---|---|---|---|---|---|
| items | sqlite | main | item_id:int, label:text | item_id | (none) | 5 | schema, columns, primary keys, foreign keys, sample row count |

## Coverage checklist
- [x] documented items
- [ ] skipped unsupported-json-api (manual contract required)

## Next step
Consolidate this slice and keep unsupported objects as skip-by-design.

<!-- canonical-payload -->
```json
{
  "artifact_type": "source-docs",
  "graph_id": "golden-fixture",
  "slice_id": "slice-001",
  "assigned_objects": ["items"],
  "documented_nodes": [
    {
      "node_id": "golden-fixture-source-db",
      "label": "Golden Fixture DB",
      "type": "Data Source",
      "card_sections": [
        {
          "title": "Overview",
          "content": "Synthetic data source for CI golden-fixture contract validation.",
          "icon": "info",
          "order": 1
        },
        {
          "title": "Structure",
          "content": "DB: golden_fixture / schema: main / tables: items",
          "icon": "database",
          "order": 2
        },
        {
          "title": "Columns / Fields",
          "content": "| Column | Type | Meaning | Notes |\n|---|---|---|---|\n| item_id | INTEGER | Unique identifier | Primary key |\n| label | TEXT | Item label | Synthetic fixture |",
          "icon": "table",
          "order": 3
        },
        {
          "title": "Refresh Cadence",
          "content": "Static fixture — never refreshed automatically.",
          "icon": "clock",
          "order": 4
        }
      ]
    }
  ],
  "completeness_gate": {
    "pre_mapping_recommendation": "document"
  }
}
```
