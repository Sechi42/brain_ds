# Map Artifact — Golden Fixture

**Purpose**: Deterministic CI golden fixture for the live artifact contract guard.
This file represents the canonical format real agents must emit for map artifacts.

## Human-readable summary

**Phase**: map
**Graph**: golden-fixture
**Edges mapped**: 1 (Role → Data Source)
**Completeness gate**: document (data source sparse)

<!-- canonical-payload -->
```json
{
  "artifact_type": "map",
  "graph_id": "golden-fixture",
  "documented_nodes": [
    {
      "node_id": "golden-fixture-role-data-owner",
      "label": "Data Owner",
      "type": "Role",
      "card_sections": [
        {
          "title": "Overview",
          "content": "Role responsible for the Golden Fixture DB data source.",
          "icon": "link",
          "order": 1
        }
      ]
    }
  ],
  "edges": [
    {
      "source": "golden-fixture-role-data-owner",
      "target": "golden-fixture-source-db",
      "label": "owns"
    }
  ],
  "completeness_gate": {
    "pre_mapping_recommendation": "document",
    "missing_entity_types": ["Organization", "Department"],
    "sparse_nodes": ["golden-fixture-source-db"]
  }
}
```
