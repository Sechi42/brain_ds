# Business Requirements Document — Golden Fixture

**Purpose**: Deterministic CI golden fixture for the live artifact contract guard.
This file represents the canonical format real agents must emit for BRD artifacts.

## Human-readable BRD content

**Graph**: golden-fixture
**Status**: PARTIAL
**Date**: 2026-06-14

[[Data Owner]] is responsible for [[Golden Fixture DB]], a synthetic data source
used exclusively for CI golden-fixture contract validation.

<!-- canonical-payload -->
```json
{
  "artifact_type": "brd",
  "graph_id": "golden-fixture",
  "markdown": "# BRD\n\n## Executive Summary\n[[Data Owner]] owns [[Golden Fixture DB]] and is responsible for its refresh cadence.\n",
  "brd_node": {
    "node_id": "brd-golden-fixture",
    "label": "BRD",
    "type": "Unknown",
    "card_sections": [
      {
        "title": "Contenido",
        "content": "# BRD\n\n## Executive Summary\n[[Data Owner]] owns [[Golden Fixture DB]] and is responsible for its refresh cadence.\n",
        "order": 0,
        "icon": ""
      }
    ]
  },
  "completeness_gate": {
    "pre_mapping_recommendation": "document"
  }
}
```
