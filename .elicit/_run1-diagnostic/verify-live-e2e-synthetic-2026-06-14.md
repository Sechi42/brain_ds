# Verify Gate — live-e2e-synthetic (2026-06-14)

**Stage**: verify (Auto-run minimalista gate)
**Cycle**: live-e2e-synthetic
**Verifier**: `brain_ds.verify.elicit_compliance.check_elicit_compliance(.elicit/)`
**Result**: **BLOCKED** — archive is NOT allowed.

## What ran live before this gate

| Stage | Sub-agent (real Task delegation) | Output |
|---|---|---|
| intake (datasource) | brainds-source-explorer | `.elicit/source-docs-orders-db-customers-2026-06-14.md`, `.elicit/source-docs-orders-db-orders-2026-06-14.md` |
| intake (graph push) | brainds-graph-mapper | Data Source card_sections (7) + Dataset nodes `customers`, `orders` |
| map | brainds-connection-mapper | 3 edges (contains ×2, references FK) |
| brd | brainds-brd-writer | graph node `brd-live-e2e-synthetic` + `.elicit/brd-live-e2e-synthetic-2026-06-14.md` |

Graph state: node_count 4, edge_count 3.

## Gate findings (4 CRITICAL)

| Severity | Artifact | Finding |
|---|---|---|
| CRITICAL | brd-live-e2e-synthetic-2026-06-14.md | missing a fenced JSON payload |
| CRITICAL | README.md | does not match the .elicit naming contract |
| CRITICAL | source-docs-orders-db-customers-2026-06-14.md | payload must be a JSON object |
| CRITICAL | source-docs-orders-db-orders-2026-06-14.md | payload must be a JSON object |

## Root cause (the live-vs-double gap this run exposed)

`check_elicit_compliance` was authored and validated against the **in-process dry-run doubles** (`tests/conftest.py`), which emit a machine-checkable JSON envelope (`documented_nodes`, `completeness_gate`, `brd_node`). The **real** sub-agents emit human-readable markdown:
- source-docs embed a `card_sections` JSON **array**, not the `{documented_nodes:[…], completeness_gate:{…}}` **object** the checker requires.
- the BRD artifact is pure markdown with no fenced JSON payload at all.
- `check_elicit_compliance` globs the flat `.elicit/` dir non-recursively, so `README.md` is swept in and flagged; the design intended a per-cycle subdir (`.elicit/<cycle>/`).

This is NOT a failure of the cycle — intake → map → brd all executed live. It is the verify gate doing its job: blocking archive because real-agent artifact shape diverges from the compliance contract.

```json
{
  "graph_id": "live-e2e-synthetic",
  "stage": "verify",
  "status": "BLOCKED",
  "critical_count": 4,
  "gate": "BLOCKED",
  "findings": [
    {"severity": "CRITICAL", "artifact": "brd-live-e2e-synthetic-2026-06-14.md", "message": "missing a fenced JSON payload"},
    {"severity": "CRITICAL", "artifact": "README.md", "message": "does not match the .elicit naming contract"},
    {"severity": "CRITICAL", "artifact": "source-docs-orders-db-customers-2026-06-14.md", "message": "payload must be a JSON object"},
    {"severity": "CRITICAL", "artifact": "source-docs-orders-db-orders-2026-06-14.md", "message": "payload must be a JSON object"}
  ]
}
```

## Decision

Gate = BLOCKED → **archive skipped** (correct behavior). Follow-up required: reconcile the real sub-agent artifact format with `check_elicit_compliance` (or scope the verifier to a per-cycle subdir and teach the agents to emit the JSON envelope).
