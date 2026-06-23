# Edge Judge Gold Set

This directory contains a **seed harness baseline**, not production-quality evidence.
Use it to verify that calibration mechanics are deterministic; do not use it to claim
real-world judge accuracy.

## Quick policy

- Commit only the named seed baseline: `metrics/seed-20260623.json`.
- `write_calibration_artifacts()` defaults write to the tracked seed baseline paths
  (`tests/gold/metrics` and `tests/gold/calibration_log.md`); pass explicit temp or
  scratch paths for ad-hoc reruns.
- Treat future generated metrics as local scratch unless a rollout-gate review explicitly accepts them.
- `provenance="generated"` is **not ground truth** by default and cannot satisfy rollout gates.
- `suspect` compatibility and calibration `abstain` are different dimensions.
- `evidence_ids` must be a JSON array of strings; the loader converts it to an
  immutable tuple and rejects malformed values with `path:line` context.

## Format

`edge_gold_set.jsonl` stores one labeled edge per line with the required SDD fields:
`edge_id`, `graph_id`, `label`, `source_type`, `target_type`, `weight`, `evidence_ids`,
`gold_verdict`, `gold_rationale`, and `provenance`.

## Provenance

- `seed`: synthetic ontology-shaped examples used to bootstrap the calibration harness.
- `hand_labeled`: future human-reviewed examples from real project graphs.
- `generated`: future generated candidates. They are excluded from calibration by default
  because generated labels are not independent ground truth.

The current set is intentionally `seed` only. It is enough to exercise per-class
threshold calculation, but it is not a production rollout gate.

## Seed vs production baseline

| Baseline | Meaning | Can satisfy rollout gates? |
|---|---|---|
| Seed metrics | Harness mechanics: loader, thresholds, abstain matrix, JSON/log writing | No |
| Hand-labeled metrics | Human-reviewed evidence from real graphs | Potentially, after hold-out review |
| Generated metrics | Synthetic or model-produced labels | No, unless reviewed and reclassified |

## Calibration labels vs compatibility labels

Calibration uses `valid | invalid | abstain` to describe evidence/weight uncertainty.
The ontology compatibility layer uses `valid | suspect | invalid` to describe structural
compatibility. `suspect` does **not** mean `abstain`; keep those signals separate until
Phase 5 defines advisory rollout behavior.
