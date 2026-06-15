# Tasks: brainds-live-artifact-contract-reconciliation

## Review Workload Forecast

| Metric | Slice 1 | Slice 2 | Total |
|---|---|---|---|
| Estimated changed lines | ~260 | ~150 | ~410 |
| Files changed | 14 | 5 | 19 |
| New test assertions | ~28 | ~20 | ~48 |
| 400-line budget risk | **High** (Slice 1 alone ~260; combined >400) | — | High |
| Chained PRs recommended | **Yes** — Slice 1 and Slice 2 as separate PRs | — | — |
| Decision needed before apply | **Yes** — orchestrator must confirm chained delivery before apply starts | — | — |

Slice 1 is the gate blocker and ships as PR-1. Slice 2 is additive golden-fixture coverage and ships as PR-2. Each slice leaves CI green independently.

---

## Slice 1 — Gate Blocker (~260 lines)

**Goal**: ARTIFACT_CONTRACT constant declared, injected into all 3 composers, verifier scoped to skip non-phase files and select the LAST JSON block, dry-run doubles updated, agent prompt pairs updated, connection-mapper gets Write tool, cross-client mirrors synced.

**Sequential order within the slice** (each task is a RED→GREEN commit pair):

### [x] T1-1 — RED: test_artifact_contract_constant_shape
- **File**: `tests/test_mcp_grounding.py`
- **What**: Add `test_artifact_contract_constant_shape` — asserts `grounding.ARTIFACT_CONTRACT` is a dict with exactly four keys (`source-docs`, `map`, `brd`, `verify`); each entry has `required_keys` list and `validator` string; `artifact_type` is in `required_keys` for all four entries; `verify` entry `required_keys` has exactly the 7 keys (`graph_id`, `stage`, `status`, `critical_count`, `findings`, `gate`, `artifact_type`).
- **Spec**: C2-S1, C2-S2
- **Depends on**: nothing (pure import check, RED immediately)

### [x] T1-2 — GREEN: Add ARTIFACT_CONTRACT to grounding.py
- **File**: `brain_ds/mcp/grounding.py`
- **What**: After `DELEGATION_PROTOCOL`, declare `ARTIFACT_CONTRACT: dict[str, object]` with four sub-dicts. Each has `required_keys` (list), `schema_notes` (str), `validator` (str snake_case name). `artifact_type` is first required key for all four. `verify` entry has `required_keys = ["artifact_type", "graph_id", "stage", "status", "critical_count", "findings", "gate"]`. Add `CANONICAL_SENTINEL = "<!-- canonical-payload -->"` constant above it.
- **Spec**: C2-S1 through C2-S4
- **Depends on**: T1-1 (GREEN fixes T1-1)

### [x] T1-3 — RED: test_artifact_contract_injected_in_all_composers (R5 key-count bump)
- **File**: `tests/test_mcp_grounding.py`
- **What**:
  - Update `test_elicit_context_has_all_14_keys` → assert 15 keys (add `artifact_contract` to expected set)
  - Update `test_map_connections_context_has_12_keys` → assert 13 keys
  - Update `test_generate_brd_context_has_10_keys` → assert 11 keys
  - Add `test_artifact_contract_present_in_all_composers`: loops over all three contexts, asserts `artifact_contract` key present and its value equals `grounding.ARTIFACT_CONTRACT`
- **Spec**: C2-S5, C2-S6
- **Depends on**: T1-2

### [x] T1-4 — GREEN: Inject artifact_contract into all 3 composers
- **File**: `brain_ds/mcp/grounding.py`
- **What**: Add `"artifact_contract": ARTIFACT_CONTRACT` to `elicit_context()`, `map_connections_context()`, `generate_brd_context()`. Update docstring key counts: 14→15, 12→13, 10→11.
- **Spec**: C2-S5, C2-S6
- **Depends on**: T1-3 (GREEN fixes T1-3)

### [x] T1-5 — RED: test_artifact_contract_discovered_and_not_exempt
- **File**: `tests/test_grounding_drift_guard.py`
- **What**: Mirror of `test_pipeline_stages_discovered_and_not_exempt`. Assert `ARTIFACT_CONTRACT` is in `_discover_category2_constants()` and NOT in `CATEGORY2_EXEMPT`. Also add `test_canonical_sentinel_discovered_and_not_exempt` for `CANONICAL_SENTINEL` (string constant — verify sweep classifies it as Category-2 and it sweeps clean: no CamelCase compound tokens).
- **Spec**: C2-S3 (drift guard must stay GREEN after adding constant)
- **Depends on**: T1-2 (constant must exist to be discovered)

### [x] T1-6 — VERIFY: confirm drift guard stays GREEN
- **What**: Run `uv run pytest tests/test_grounding_drift_guard.py` — must be GREEN. If `CANONICAL_SENTINEL` or `ARTIFACT_CONTRACT` contain any CamelCase-compound tokens that trigger the sweep, rename or restructure values. No code to write if sweep is already clean; otherwise fix grounding.py values.
- **Spec**: C2-S3
- **Depends on**: T1-5

### [x] T1-7 — RED: 4 verifier scoping canonical test cases
- **File**: `tests/test_dryrun_elicit_compliance.py`
- **What**: Add four parameterized or discrete test functions (each its own `def test_...`):
  1. `test_verifier_ignores_readme` — write `README.md` into a tmp `.elicit/` dir with no JSON; `check_elicit_compliance` returns zero findings.
  2. `test_verifier_ignores_scratch_file` — write `scratch.md` with arbitrary content; zero findings.
  3. `test_verifier_critical_on_phase_named_broken_map` — write `map-org-2026-06-14.md` with broken JSON; `check_elicit_compliance` returns ≥1 CRITICAL finding referencing that file.
  4. `test_verifier_critical_on_phase_named_no_json_brd` — write `brd-org-2026-06-14.md` with markdown only (no fenced block); ≥1 CRITICAL.
- **Spec**: C3-S1 through C3-S4
- **Depends on**: nothing (standalone isolation tests, RED immediately because current verifier raises CRITICAL on README.md)

### [x] T1-8 — GREEN: verifier scoping rule — skip non-PHASE_PATTERN files
- **File**: `brain_ds/verify/elicit_compliance.py`
- **What**: In `check_elicit_compliance`, replace the current `else` branch that appends CRITICAL for non-phase-named files with a `continue` (silent skip). The PHASE_PATTERN check at loop head already captures phase-named files; only non-matching names are skipped silently. Phase-named-but-broken remains CRITICAL (no change needed — that path stays as-is).
- **Spec**: C3-S1, C3-S2
- **Depends on**: T1-7 (GREEN fixes cases 1 & 2)

### [x] T1-9 — RED: test_verifier_selects_last_json_block + test_example_block_before_canonical
- **File**: `tests/test_dryrun_elicit_compliance.py`
- **What**:
  - `test_verifier_selects_last_json_block` — write `source-docs-org-2026-06-14.md` with TWO fenced JSON blocks: first is invalid/incomplete, last is a valid source-docs payload; `check_elicit_compliance` returns zero findings (validates against last block only).
  - `test_example_block_before_canonical` — write `map-org-2026-06-14.md` with an "example" fenced JSON block first (contains only `{"example": true}`), then `<!-- canonical-payload -->` sentinel comment, then a valid canonical map payload as the last block; zero findings (canonical validated, example ignored).
- **Spec**: C3-S5, C3-S6
- **Depends on**: T1-8

### [x] T1-10 — GREEN: elicit_compliance.py — LAST block selection + CANONICAL_SENTINEL
- **File**: `brain_ds/verify/elicit_compliance.py`
- **What**:
  - Import `CANONICAL_SENTINEL` from `grounding` (or define it locally as the same value if circular import risk; prefer import).
  - In `_load_payload`: replace `PAYLOAD_PATTERN.search(text)` with `matches = PAYLOAD_PATTERN.finditer(text); match = list(matches)[-1] if matches else None` — using the LAST match.
  - Add module-level `CANONICAL_SENTINEL` import/constant for documentation; the selection logic is positional (`[-1]`), not sentinel-anchored.
- **Spec**: C3-S5, C3-S6
- **Depends on**: T1-9

### [x] T1-11 — RED: test_dry_run_all_artifacts_have_artifact_type + test_dry_run_zero_criticals_after_contract
- **File**: `tests/test_dryrun_elicit_compliance.py`
- **What**:
  - `test_dry_run_all_artifacts_have_artifact_type` — iterates `dry_run_elicit_output["written_files"]`, parses last JSON block of each phase-named artifact, asserts `"artifact_type"` key present at top level.
  - `test_dry_run_zero_criticals_after_contract` — calls `check_elicit_compliance(elicit_dir)` on the full dry-run output dir; asserts zero CRITICAL findings.
- **Spec**: C6-S1 through C6-S3
- **Depends on**: T1-10

### [x] T1-12 — GREEN: conftest.py — add artifact_type to all dry-run doubles
- **File**: `tests/conftest.py`
- **What**: In `_artifact_body` or at the `write_artifact` call sites: inject `"artifact_type": phase` as the first key of every payload dict before serialization. Ensure the BRD artifact body wraps payload in sentinel + last-block structure (add `<!-- canonical-payload -->` comment before the final fenced block). Map artifact already has `completeness_gate` — verify it is present in the written payload.
- **Spec**: C6-S1 through C6-S5
- **Depends on**: T1-11

### [x] T1-13 — RED: test_connection_mapper_has_write_tool
- **File**: `tests/test_harness_check.py`
- **What**: Add `test_connection_mapper_has_write_tool` — reads `.claude/agents/brainds-connection-mapper.md`, parses YAML front matter, asserts `Write` appears in `tools` list (case-sensitive). Also add `test_connection_mapper_prompt_mentions_map_artifact_write` — reads `prompts/brainds-connection-mapper.md`, asserts it contains `.elicit/map-` and `Write`.
- **Spec**: C5-S1, C5-S2
- **Depends on**: nothing (RED immediately — `Write` not currently in YAML)

### [x] T1-14 — GREEN: Add Write tool to .claude/agents/brainds-connection-mapper.md + prose
- **Files**:
  - `.claude/agents/brainds-connection-mapper.md`: add `- Write` to the `tools:` YAML list (ONE line)
  - `prompts/brainds-connection-mapper.md`: add a step instructing the agent to write the map artifact to `.elicit/map-<slug>-<date>.md` with the canonical fenced JSON block + `<!-- canonical-payload -->` sentinel
  - `.opencode/skills/` mirrors: no agent YAML to mirror (OpenCode installer handles tool grants uniformly); ensure prose in `prompts/` is the cross-client source of truth
- **Spec**: C5-S1 through C5-S5
- **Depends on**: T1-13

### [x] T1-15 — GREEN: AGENT_FLOW.md + DELEGATION_PROTOCOL note
- **Files**:
  - `brain_ds/mcp/grounding.py`: add `artifact_keys` entry under `connection-mapper` in `DELEGATION_PROTOCOL` noting `map_file = ".elicit/map-<slug>-<date>.md"`
  - `AGENT_FLOW.md`: add one-line note that `brainds-connection-mapper` writes `.elicit/map-*.md`
- **Spec**: C5-S3, C5-S4
- **Depends on**: T1-14
- **Note**: harness_check.py does NOT assert per-agent tool rosters (grep-confirmed), so no change needed there.

### [x] T1-16 — RED: test_install_opencode_sh_grants_write_uniform
- **File**: `tests/test_harness_check.py`
- **What**: Add `test_install_opencode_sh_grants_write_uniform` — reads `install-opencode.sh`, asserts that the sub-agent dict template contains `"write": True` (confirming uniform grant; no per-agent override needed). This is a content-grep test, not execution.
- **Spec**: C5-S5 (installer parity R3)
- **Depends on**: nothing (already true — confirms the invariant won't regress)

### [x] T1-17 — RED: test_agent_prose_updated (cross-client)
- **File**: `tests/test_harness_check.py`
- **What**: Add `test_source_explorer_prose_mentions_artifact_contract` and `test_brd_writer_prose_mentions_canonical_sentinel` — read `.claude/agents/brainds-source-explorer.md` and `brainds-brd-writer.md`, assert each mentions `<!-- canonical-payload -->` or `ARTIFACT_CONTRACT` or the sentinel instruction (exact wording TBD by apply agent, test for the sentinel string).
- **Spec**: C8-S2 (agent prose aligned)
- **Depends on**: nothing (RED immediately)

### [x] T1-18 — GREEN: Update 3 agent .claude/agents + prompts/ pairs with canonical-payload instruction
- **Files**:
  - `.claude/agents/brainds-source-explorer.md`
  - `prompts/brainds-source-explorer.md`
  - `.claude/agents/brainds-brd-writer.md`
  - `prompts/brainds-brd-writer.md`
- **What**: In each agent's output-contract / return-contract / artifact-writing section, add instruction: "Always place `<!-- canonical-payload -->` on the line before the final ` ```json ` fence so verifiers select the correct block." Keep prose minimal — one sentence per agent.
- **Spec**: C1-S1 (dual-contract rule), C8-S2
- **Depends on**: T1-17

### [x] T1-19 — RED: test_skill_mirrors_byte_identical (already GREEN — brain_ds check confirmed)
- **File**: `tests/test_harness_check.py` (or `test_grounding_drift_guard.py`)
- **What**: For each of the 3 skill files (generate-brd, map-connections, brainds-docs), assert `skills/{name}/SKILL.md` and `.opencode/skills/{name}/SKILL.md` are byte-for-byte identical. This test already implicitly exists via `test_brainds_docs_brd_carveout_matches_contract` for content; this new test checks identity directly.
- **Spec**: C8-S1
- **Depends on**: nothing (RED if any skill has drifted from its mirror)

### [x] T1-20 — GREEN: Sync .opencode/skills mirrors to byte-identical (already byte-identical, confirmed)
- **Files**: `.opencode/skills/generate-brd/SKILL.md`, `.opencode/skills/map-connections/SKILL.md`, `.opencode/skills/brainds-docs/SKILL.md`
- **What**: Copy `skills/*/SKILL.md` → `.opencode/skills/*/SKILL.md` byte-for-byte. Add cross-ref note in each SKILL.md: "Artifact contract: see `ARTIFACT_CONTRACT` in `brain_ds/mcp/grounding.py`." Run T1-19 to confirm GREEN.
- **Spec**: C8-S1
- **Depends on**: T1-19

### [x] T1-21 — VERIFY: brain_ds check (harness_check.py) passes
- **What**: Run `uv run pytest tests/test_harness_check.py` — all green. Confirms C8-S3 (harness passes), C8-S4 (roster unchanged at 6 agents: brainds-source-explorer, brainds-graph-mapper, brainds-connection-mapper, brainds-brd-writer, brainds-query-consultant + orchestrator).
- **Spec**: C8-S3, C8-S4
- **Depends on**: T1-20

### [x] T1-22 — VERIFY: full Slice-1 test run GREEN
- **What**: `uv run pytest tests/test_mcp_grounding.py tests/test_grounding_drift_guard.py tests/test_dryrun_elicit_compliance.py tests/test_harness_check.py tests/test_elicit_lifecycle.py` — zero failures. Confirms dry-run double passes `check_elicit_compliance` with zero CRITICALs.
- **Spec**: C6-S4, C6-S5
- **Depends on**: T1-21

---

## Slice 2 — Live Test Coverage (~150 lines)

**Goal**: Golden fixtures + `test_live_artifact_contract.py` CI guard. No LLM calls. Regression-detects format drift without a live run.

**Sequential within slice; depends on Slice 1 being merged.**

### [x] T2-1 — GREEN (fixtures): Create tests/fixtures/elicit/ golden artifacts
- **Files** (new): `tests/fixtures/elicit/README.md`, `tests/fixtures/elicit/scratch.md`, `tests/fixtures/elicit/source-docs-golden-2026-06-14.md`, `tests/fixtures/elicit/map-golden-2026-06-14.md`, `tests/fixtures/elicit/brd-golden-2026-06-14.md`, `tests/fixtures/elicit/verify-golden-2026-06-14.md`
- **What**:
  - `README.md` and `scratch.md`: plain markdown with no JSON (verifier must skip them)
  - `source-docs-golden`: valid dual-contract markdown with `<!-- canonical-payload -->` + last JSON block containing `artifact_type`, `graph_id`, `documented_nodes` with proper `card_sections`
  - `map-golden`: same structure + `edges`, `completeness_gate` with valid `pre_mapping_recommendation`
  - `brd-golden`: `artifact_type`, `graph_id`, `markdown` with `[[wikilinks]]`, `brd_node` with BRD carve-out (order=0, icon="", title="Contenido")
  - `verify-golden`: all 7 required keys per ARTIFACT_CONTRACT, `gate=PASS`, `findings=[]`
- **Spec**: C7-S1 through C7-S5
- **Depends on**: Slice 1 merged (so ARTIFACT_CONTRACT and verifier exist)
- **Note**: This task has no RED predecessor — it creates NEW passing artifacts. The RED test in T2-2 drives the structure requirements.

### [x] T2-2 — RED: tests/test_live_artifact_contract.py (new)
- **File**: `tests/test_live_artifact_contract.py` (new)
- **What**: Five test functions:
  1. `test_each_phase_prefix_has_at_least_one_fixture` — scans `tests/fixtures/elicit/`, asserts ≥1 file per prefix in `{source-docs, map, brd, verify}`.
  2. `test_golden_fixtures_zero_criticals` — calls `check_elicit_compliance(Path("tests/fixtures/elicit/"))`, asserts zero CRITICAL findings.
  3. `test_each_fixture_has_required_keys_per_contract` — for each fixture, parse last JSON block, resolve `artifact_type`, look up `ARTIFACT_CONTRACT[artifact_type]["required_keys"]`, assert all keys present.
  4. `test_brd_golden_has_wikilinks_and_carveout` — asserts `[[` in markdown, `card_sections[0].title == "Contenido"`, `order == 0`, `icon == ""`.
  5. `test_verify_golden_gate_pass_and_empty_findings` — asserts `gate == "PASS"` and `findings == []`.
- **Spec**: C7-S1 through C7-S5, C9-S2
- **Depends on**: T2-1 must exist for tests to pass; tests are written RED first (file exists but fixtures don't yet, or fixture format is wrong)

### [x] T2-3 — GREEN: Fix golden fixtures until T2-2 passes
- **What**: Iterate on `tests/fixtures/elicit/*.md` content until `uv run pytest tests/test_live_artifact_contract.py` is GREEN. Primarily a content-alignment task — no code changes expected.
- **Spec**: C7 all scenarios
- **Depends on**: T2-2

### [x] T2-4 — VERIFY: regression guard self-test
- **What**: Manually break one required key in `tests/fixtures/elicit/source-docs-golden-2026-06-14.md` (remove `artifact_type`), confirm `test_each_fixture_has_required_keys_per_contract` goes RED, restore the key. Documents that C7-S3 ("change ARTIFACT_CONTRACT without updating fixtures → C7-S3 fails") is a live invariant.
- **Spec**: C9-S2
- **Depends on**: T2-3

### [x] T2-5 — VERIFY: full suite GREEN
- **What**: `uv run pytest` — full suite green including all Slice 1 + Slice 2 tests. Confirms `test_sub_agent_writes_only_to_elicit` (which relies on `synthetic_source_path` from conftest.py) still passes after conftest changes.
- **Spec**: C9-S1 (live acceptance preparation), C6-S5
- **Depends on**: T2-4

---

## Parallel Opportunities

| Can run in parallel | Tasks |
|---|---|
| Yes — within Slice 1, T1-5/T1-6 (drift guard) can run in parallel with T1-7/T1-8 (verifier scoping) after T1-2 is done | T1-5+T1-6 ‖ T1-7+T1-8 |
| Yes — T1-13/T1-14 (connection-mapper Write) can run in parallel with T1-11/T1-12 (conftest dry-run doubles) | T1-13+T1-14 ‖ T1-11+T1-12 |
| Yes — T1-16 (installer parity) and T1-19 (skill mirrors RED) can run in parallel after T1-14 | T1-16 ‖ T1-19 |
| No — T1-10 must precede T1-11 (verifier LAST block must exist before dry-run compliance test) | Sequential |
| No — Slice 2 entirely after Slice 1 merged | Sequential |

---

## Task Count Summary

| Slice | Tasks | Type |
|---|---|---|
| Slice 1 | 22 (T1-1 … T1-22) | 10 RED, 8 GREEN, 4 VERIFY |
| Slice 2 | 5 (T2-1 … T2-5) | 1 GREEN(fixture), 1 RED, 1 GREEN, 2 VERIFY |
| **Total** | **27** | |

---

## Watch-Out Notes

1. **`_load_payload` circular import risk**: importing `CANONICAL_SENTINEL` from `grounding.py` into `elicit_compliance.py` — check for circular imports via `brain_ds.mcp.grounding → brain_ds.verify.elicit_compliance`. If circular, define `CANONICAL_SENTINEL` locally in `elicit_compliance.py` and re-export from `grounding.py` pointing to the same string value.
2. **`artifact_type` in verify payload**: `_check_verify_payload` currently checks 6 hardcoded keys. After T1-2 adds `artifact_type` to `ARTIFACT_CONTRACT["verify"]["required_keys"]`, the verifier function is NOT auto-updated — it must explicitly add `"artifact_type"` to its `required_keys` tuple (or delegate to `ARTIFACT_CONTRACT`). Settle in T1-10 scope.
3. **`test_sub_agent_writes_only_to_elicit`**: relies on `dry_run_elicit_output["synthetic_source_path"]` being a real path. After conftest changes in T1-12, verify this key is still in the returned dict.
4. **`completeness_gate` invalid value**: spec says invalid recommendation → CRITICAL (not counted as recorded). Current code only checks `if recommendation in ALLOWED_RECOMMENDATIONS`. An invalid value silently skips recording. Implement explicit `elif recommendation is not None: findings.append(CRITICAL(...))` in T1-8 scope.
5. **Verifier scoping change is one-line** (T1-8) but must NOT remove the CRITICAL for phase-named broken files. Test case 3 and 4 in T1-7 confirm that invariant is preserved.
