# Verify Gate — Golden Fixture

**Purpose**: Deterministic CI golden fixture for the live artifact contract guard.
This file represents the canonical format the orchestrator must emit for verify artifacts.

## Gate result

**Graph**: golden-fixture
**Stage**: verify
**Result**: PASS — archive is allowed.
**Findings**: 0 CRITICAL

<!-- canonical-payload -->
```json
{
  "artifact_type": "verify",
  "graph_id": "golden-fixture",
  "stage": "verify",
  "status": "PASS",
  "critical_count": 0,
  "findings": [],
  "gate": "PASS"
}
```
