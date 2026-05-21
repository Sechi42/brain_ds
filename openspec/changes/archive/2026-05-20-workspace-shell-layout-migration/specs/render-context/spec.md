# Delta for render-context

## ADDED Requirements

None. No new data shapes, fields, or API behaviors.

## MODIFIED Requirements

None. `build_render_context` output is byte-identical before and after migration.

## REMOVED Requirements

None.

## Contract Preservation Affirmation

The template rendering path (`graph_viewer.html`) is being structurally rewritten, but the `RENDER_CONTEXT` JSON object produced by `build_render_context` is **not** changed. All existing contract fields (R01–R08 from `backend-ui-contract`) remain present with identical values. No contract version bump. No new fields. No field renames.

**Preserved invariants**:
- `contract_version` = `"1.0.0"` (R01)
- `meta.workspace` with all 4 sub-fields (R02)
- `nodes[*].score`, `.updated_at`, `.neighbor_count` (R03–R05)
- All existing fields from pre-contract era (P01–P03)
- Golden fixtures byte-identical (R07)
- TabModel schema unchanged (R08)

**Verification**: all 26 spec scenarios from `openspec/specs/render-context/spec.md` MUST remain compliant. No assertion in `test_render_context_contract.py` or `test_render_context_golden.py` may be modified.
