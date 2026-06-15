# Apply Progress — brainds-live-artifact-contract-reconciliation

**Change**: brainds-live-artifact-contract-reconciliation
**Mode**: Strict TDD (RED → GREEN → REFACTOR per scenario)
**Batch**: 2 (Slice 1 done in batch 1; Slice 2 done in batch 2)
**Status**: Both slices done; live re-run + verify + archive pending orchestrator.

## Completed Tasks (27/27 total)

### Slice 1 (22/22) — ALL COMPLETE

- [x] T1-1 RED: test_artifact_contract_constant_shape (test_mcp_grounding.py)
- [x] T1-2 GREEN: ARTIFACT_CONTRACT constant added to grounding.py
- [x] T1-3 RED: test_artifact_contract_injected_in_all_composers / key-count bump 14/12/10→15/13/11
- [x] T1-4 GREEN: Inject artifact_contract into all 3 composers
- [x] T1-5 RED: test_artifact_contract_discovered_and_not_exempt (test_grounding_drift_guard.py)
- [x] T1-6 VERIFY: drift guard stays GREEN
- [x] T1-7 RED: 4 verifier scoping tests
- [x] T1-8 GREEN: verifier scoping rule — skip non-PHASE_PATTERN files silently
- [x] T1-9 RED: last-block selection + sentinel tests
- [x] T1-10 GREEN: elicit_compliance.py — finditer[-1]
- [x] T1-11 RED: dry-run artifact_type + zero criticals tests
- [x] T1-12 GREEN: conftest.py — write_artifact injects artifact_type; sentinel added
- [x] T1-13 RED: test_connection_mapper_claude_agent_has_write_tool
- [x] T1-14 GREEN: Write tool added to brainds-connection-mapper
- [x] T1-15 GREEN: AGENT_FLOW.md + DELEGATION_PROTOCOL
- [x] T1-16 RED+GREEN: installer write=True guard tests
- [x] T1-17 RED: agent prose canonical-payload tests
- [x] T1-18 GREEN: canonical-payload added to all 3 agent pairs
- [x] T1-19/T1-20 GREEN: skill mirrors byte-identical (confirmed)
- [x] T1-21 VERIFY: brain_ds check 4 PASS
- [x] T1-22 VERIFY: full suite 1344 passed

### Slice 2 (5/5) — ALL COMPLETE

- [x] T2-1 GREEN: tests/fixtures/elicit/ — 4 golden fixture files created
- [x] T2-2 RED: tests/test_live_artifact_contract.py — 10 tests written RED (fixtures missing + contract divergence)
- [x] T2-3 GREEN: golden fixtures aligned; _check_verify_payload enforces artifact_type; all 10 tests GREEN
- [x] T2-4 VERIFY: regression guard self-test confirmed live
- [x] T2-5 VERIFY: full suite 1379 passed, brain_ds check 4 PASS

## Key Contract Reconciliation (T2-5)

`_check_verify_payload` now enforces `artifact_type` as a required key, consistent with
`ARTIFACT_CONTRACT["verify"]["required_keys"]`. The real verify artifact
`.elicit/verify-live-e2e-synthetic-2026-06-14.md` already includes `"artifact_type": "verify"`,
so this is a safe tightening — not a relaxation.

## Files Changed (Slice 2)

| File | Action | What |
|---|---|---|
| `brain_ds/verify/elicit_compliance.py` | Modified | artifact_type added to _check_verify_payload required_keys |
| `tests/test_live_artifact_contract.py` | Created | 10 test CI guard functions |
| `tests/fixtures/elicit/source-docs-golden-2026-06-14.md` | Created | Golden fixture |
| `tests/fixtures/elicit/map-golden-2026-06-14.md` | Created | Golden fixture |
| `tests/fixtures/elicit/brd-golden-2026-06-14.md` | Created | Golden fixture |
| `tests/fixtures/elicit/verify-golden-2026-06-14.md` | Created | Golden fixture |
| `tests/test_elicit_lifecycle.py` | Modified | verify envelope in test updated with artifact_type |
| `.elicit/sdd/.../tasks.md` | Modified | T2-1 through T2-5 marked [x] |

## Full Suite Results

```
1379 passed, 3 skipped, 1 pre-existing Windows failure
brain_ds check: 4 PASS, 0 FAIL
```

Pre-existing failure: `test_register_path_copies_wrapper_sh` (OpenCode CLI not installed on Windows).
0 intentional REDs remaining.

## Next Recommended

sdd-verify (then orchestrator runs live re-run + verify, then sdd-archive)
