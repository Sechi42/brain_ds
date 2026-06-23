# Edge Judge Rollout

The semantic edge judge ships **advisory-first**. Edge findings are
`SUGGESTION` or `WARNING` only and MUST NOT block `archive`, `update_node`,
`add_edge`, or any other operation until **every** rollout gate below passes.

The machine-checkable half of this contract lives in
`brain_ds/verify/edge_rollout.py::evaluate_rollout_gates`, a pure, read-only
helper that turns an `EdgeCalibrationReport` plus its source gold records into a
`rollout_ready` vs `advisory_only` verdict with named `GateReason`s. It performs
no I/O, no MCP calls, no LLM calls, and no graph mutation.

## Rollout gates

| # | Gate (spec section E) | Enforced by | `GateReason` |
|---|---|---|---|
| 1 | Gold set covers all 14 `RelationshipType`s with ≥ 10 examples each | helper | `MISSING_CLASS_METRICS`, `INSUFFICIENT_EXAMPLES_PER_TYPE`, `INSUFFICIENT_HAND_LABELED` |
| 2 | Per-class precision ≥ 0.85 **and** recall ≥ 0.70 on hold-out | helper | `BELOW_PRECISION`, `BELOW_RECALL`, `ABOVE_FALSE_POSITIVE`, `ABOVE_FALSE_NEGATIVE`, `ABSTAIN_BAND_TOO_WIDE` |
| 3 | 2 consecutive calibration runs meet thresholds | helper (caller supplies `consecutive_passing_runs`) | `CONSECUTIVE_RUNS_INSUFFICIENT` |
| 4 | Human review of 20 random abstain-band edges | helper (caller supplies `human_reviewed_abstain_count`) | `HUMAN_ABSTAIN_REVIEW_INSUFFICIENT` |
| 5 | This document exists and is current | this file | — |

Two further provenance gates harden gate 1: a baseline built only from `seed`
records flips to `advisory_only` (`SEED_ONLY_BASELINE`), and any `generated`
record present does the same (`GENERATED_RECORDS_PRESENT`). Hand-labeled
coverage is checked both per `RelationshipType` and in total.

Until **all** gates pass, edge findings stay advisory: `archive` proceeds and
the finding is logged with `severity`, `dimension="edge_compatibility"`, and a
citation.

## What the helper does not gate

Large-graph snapshot safety — the MCP `snapshot_edges` `400 limit_required`
rejection and the ≤ 50-edge / ≤ 256 KiB payload caps from spec section G — is a
**separate, still-required follow-up**. The helper surfaces it as the
non-blocking advisory note `LARGE_GRAPH_SAFETY_PENDING` rather than as a failing
gate, because it is calibration-scoped, not snapshot-API-scoped. Closing that
follow-up is tracked under Phase 5 tasks 5.3 / 5.4.

## Usage

```python
from brain_ds.verify.edge_calibration import calibrate_edges, load_gold_set
from brain_ds.verify.edge_rollout import evaluate_rollout_gates

records = load_gold_set("tests/gold/edge_gold_set.jsonl")
report = calibrate_edges(records, run_id="rollout-check")

result = evaluate_rollout_gates(
    report,
    records,
    consecutive_passing_runs=2,      # gate 3: how many runs already passed
    human_reviewed_abstain_count=20, # gate 4: abstain edges reviewed so far
)

if result.status == "rollout_ready":
    ...  # all machine-checkable gates passed; confirm gate 5 then promote
else:
    print(result.failing_reasons)   # global reasons
    print(result.failing_by_class)  # per-RelationshipType attribution
    print(result.advisory_notes)    # e.g. LARGE_GRAPH_SAFETY_PENDING
```

A `rollout_ready` verdict satisfies gates 1–4. Gate 5 — this document — is a
human checkpoint: confirm it reflects the current thresholds before promoting
edge findings out of advisory mode.

## Tuning

Thresholds default to the spec section E and calibration values via
`RolloutPolicy`. Override individual fields to tighten or relax a single
dimension; the helper stays read-only against the report and records regardless
of policy. All rate fields are validated to `[0, 1]` and all count fields to
non-negative at construction.

## Current status

**Advisory.** The seed gold set is seed-only and does not yet meet gates 1–4,
so `evaluate_rollout_gates` returns `advisory_only`. Edge findings remain
`SUGGESTION` / `WARNING` and block nothing.
