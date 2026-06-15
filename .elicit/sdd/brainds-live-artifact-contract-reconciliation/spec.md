# Spec: brainds-live-artifact-contract-reconciliation

> SDD phase: **spec**. Artifact store: brain_ds-hybrid (this file + Engram `sdd/brainds-live-artifact-contract-reconciliation/spec`).
> This spec describes WHAT must be true after the change. It does NOT describe HOW.

---

## Overview

After this change is applied, every artifact produced by a real agentic elicit cycle (source-docs, map, brd, verify) MUST conform to the dual-contract format: human-readable markdown followed by exactly ONE canonical fenced JSON block. The verifier MUST select the LAST fenced block and MUST skip non-phase files silently. A golden-fixture CI guard MUST catch format regressions without live LLM calls. The connection-mapper agent MUST write its map artifact to `.elicit/map-*.md`. All of this is enforced without lowering the verifier bar on any existing check.

---

## Capability 1: Canonical Artifact Contract (dual-contract format)

**Invariant**: Every `.elicit/` artifact emitted by a real agent or the dry-run double is a markdown file whose LAST fenced JSON block (preceded optionally by `<!-- canonical-payload -->`) is a valid JSON object with a top-level `artifact_type` key matching the phase prefix.

### C1-S1 — source-docs required keys pass

```
Given: a file named source-docs-acme-2026-06-14.md in .elicit/
And:   its last fenced JSON block is a JSON object with keys:
         artifact_type="source-docs", graph_id, documented_nodes (non-empty array)
And:   each node in documented_nodes has: node_id, type, card_sections (non-empty)
And:   each card_section has: title (non-empty), content (non-empty), icon (non-empty), order >= 1
When:  check_elicit_compliance(.elicit/) is called
Then:  no CRITICAL findings are returned for that file
```

**Test file**: `tests/test_dryrun_elicit_compliance.py` (extend `test_source_docs_brainds_format`)

### C1-S2 — source-docs missing documented_nodes envelope raises CRITICAL

```
Given: a file named source-docs-acme-2026-06-14.md
And:   its canonical JSON block is a card_sections ARRAY (the old broken shape — not an object with documented_nodes)
When:  check_elicit_compliance(.elicit/) is called
Then:  a CRITICAL finding is returned: "payload must be a JSON object" OR "documented_nodes missing"
```

**Test file**: `tests/test_dryrun_elicit_compliance.py` (new test: `test_source_docs_array_shape_is_critical`)

### C1-S3 — brd required keys pass

```
Given: a file named brd-acme-2026-06-14.md
And:   its last fenced JSON block is a JSON object with keys:
         artifact_type="brd", graph_id="acme", markdown (contains "[["), brd_node
And:   brd_node has: node_id="brd-acme", label="BRD", type="Unknown",
         card_sections[0] = {title="Contenido", content (non-empty), order=0, icon=""}
When:  check_elicit_compliance(.elicit/) is called
Then:  no CRITICAL findings for that file
```

**Test file**: `tests/test_dryrun_elicit_compliance.py` (extend `test_brd_persistence_contract_in_dry_run`)

### C1-S4 — brd with no fenced JSON block raises CRITICAL

```
Given: a file named brd-acme-2026-06-14.md
And:   the file contains only pure markdown — no fenced JSON block at all
When:  check_elicit_compliance(.elicit/) is called
Then:  a CRITICAL finding is returned: "{filename} is missing a fenced JSON payload"
```

**Test file**: `tests/test_dryrun_elicit_compliance.py` (new test: `test_brd_no_json_block_is_critical`)

### C1-S5 — brd BRD carve-out enforced

```
Given: a file named brd-acme-2026-06-14.md
And:   its canonical JSON block has brd_node.card_sections[0].order != 0
         OR brd_node.card_sections[0].icon != ""
         OR brd_node.card_sections[0].title != "Contenido"
When:  check_elicit_compliance(.elicit/) is called
Then:  a CRITICAL finding is returned citing the BRD carve-out violation
```

**Test file**: `tests/test_dryrun_elicit_compliance.py` (existing `test_brd_persistence_contract_in_dry_run` — add negative sub-case)

### C1-S6 — brd missing wikilinks raises CRITICAL

```
Given: a file named brd-acme-2026-06-14.md
And:   the canonical JSON block's "markdown" value does NOT contain "[["
When:  check_elicit_compliance(.elicit/) is called
Then:  a CRITICAL finding is returned: "BRD markdown must include wikilinks"
```

**Test file**: `tests/test_dryrun_elicit_compliance.py` (new sub-case in BRD test)

### C1-S7 — map required keys pass

```
Given: a file named map-acme-2026-06-14.md
And:   its last fenced JSON block is a JSON object with keys:
         artifact_type="map", graph_id, documented_nodes (non-empty), edges,
         completeness_gate.pre_mapping_recommendation in {"elicit","document","proceed_with_gaps"}
When:  check_elicit_compliance(.elicit/) is called
Then:  no CRITICAL findings for that file and completeness is considered recorded
```

**Test file**: `tests/test_dryrun_elicit_compliance.py` (new test: `test_map_artifact_passes_compliance`)

### C1-S8 — verify required keys pass and archive allowed

```
Given: a file named verify-acme-2026-06-14.md
And:   its last fenced JSON block is a JSON object with keys:
         artifact_type="verify", graph_id, stage="verify",
         status="PASS", critical_count=0, findings=[], gate="PASS"
When:  check_elicit_compliance(.elicit/) is called
Then:  no CRITICAL findings for that file
```

**Test file**: `tests/test_elicit_lifecycle.py::test_verify_artifact_clean_passes_compliance` (add `artifact_type` key)

### C1-S9 — verify with gate=BLOCKED raises CRITICAL (archive blocked)

```
Given: a file named verify-acme-2026-06-14.md
And:   its canonical JSON block has gate="BLOCKED" or non-empty findings
When:  check_elicit_compliance(.elicit/) is called
Then:  a CRITICAL finding is returned: "verify gate is BLOCKED — archive is not allowed"
```

**Test file**: `tests/test_elicit_lifecycle.py::test_verify_artifact_blocked_gate_raises_critical` (existing)

### C1-S10 — extra/unknown top-level key is tolerated (forward-compat)

```
Given: a source-docs artifact whose canonical JSON block contains an unrecognized extra key "metadata"
When:  check_elicit_compliance(.elicit/) is called
Then:  no CRITICAL findings are raised solely due to the extra key
```

**Test file**: `tests/test_dryrun_elicit_compliance.py` (new: `test_extra_key_is_tolerated`)

### C1-S11 — malformed JSON in a phase-named file raises CRITICAL

```
Given: a file named source-docs-acme-2026-06-14.md
And:   its only fenced JSON block contains invalid JSON (e.g., trailing comma)
When:  check_elicit_compliance(.elicit/) is called
Then:  a CRITICAL finding is returned: "{filename} contains invalid JSON payload"
```

**Test file**: `tests/test_dryrun_elicit_compliance.py` (extend `test_sddverify_reports_critical_on_noncompliant_node` or new sibling)

---

## Capability 2: ARTIFACT_CONTRACT Constant

**Invariant**: `grounding.py` contains `ARTIFACT_CONTRACT: dict` — a top-level UPPER_SNAKE constant mapping each artifact type to its required keys, schema notes, and validator name. This constant is injected into the payloads returned by all three grounding composers. It is NOT in the drift-guard exempt list (sweeps clean automatically because no CamelCase compound tokens appear in its values).

### C2-S1 — ARTIFACT_CONTRACT exists and has the four artifact types

```
Given: brain_ds.mcp.grounding is imported
When:  grounding.ARTIFACT_CONTRACT is accessed
Then:  it is a dict with exactly these top-level keys:
         "source-docs", "map", "brd", "verify"
And:   each entry has at minimum keys: "required_keys" (list), "validator" (str)
```

**Test file**: `tests/test_elicit_lifecycle.py` (new test: `test_artifact_contract_constant_shape`)

### C2-S2 — ARTIFACT_CONTRACT injected into elicit_context

```
Given: grounding.elicit_context() is called
When:  the return value is inspected
Then:  it contains key "artifact_contract" equal to grounding.ARTIFACT_CONTRACT
```

**Test file**: `tests/test_elicit_lifecycle.py` (new: `test_artifact_contract_in_all_grounding_payloads`)

### C2-S3 — ARTIFACT_CONTRACT injected into map_connections_context

```
Given: grounding.map_connections_context() is called
When:  the return value is inspected
Then:  it contains key "artifact_contract" equal to grounding.ARTIFACT_CONTRACT
```

**Test file**: `tests/test_elicit_lifecycle.py` (same test as C2-S2, parameterized)

### C2-S4 — ARTIFACT_CONTRACT injected into generate_brd_context

```
Given: grounding.generate_brd_context() is called
When:  the return value is inspected
Then:  it contains key "artifact_contract" equal to grounding.ARTIFACT_CONTRACT
```

**Test file**: `tests/test_elicit_lifecycle.py` (same test as C2-S2, parameterized)

### C2-S5 — ARTIFACT_CONTRACT sweeps clean in drift guard

```
Given: the drift guard (_discover_category2_constants in test_grounding_drift_guard.py) runs
When:  it scans ARTIFACT_CONTRACT for CamelCase compound tokens not in EntityType values
Then:  zero flagged tokens are found (i.e., no drift-guard failure introduced by ARTIFACT_CONTRACT)
```

**Test file**: `tests/test_grounding_drift_guard.py` (existing test — must stay GREEN with the new constant)

### C2-S6 — ARTIFACT_CONTRACT required_keys include artifact_type for every entry

```
Given: grounding.ARTIFACT_CONTRACT is accessed
When:  each entry's "required_keys" list is inspected
Then:  "artifact_type" is present in the required_keys of every artifact type
```

**Test file**: `tests/test_elicit_lifecycle.py` (part of `test_artifact_contract_constant_shape`)

---

## Capability 3: Verifier Scoping (PHASE_PATTERN gate + LAST-block selection)

**Invariant**: `check_elicit_compliance` skips any `.elicit/*.md` file whose name does NOT match `PHASE_PATTERN` without emitting any finding. Any file whose name DOES match `PHASE_PATTERN` but has a missing, broken, or malformed canonical payload MUST raise CRITICAL. The verifier selects the LAST fenced JSON block (using `finditer(...)[-1]`), not the first.

### C3-S1 — README.md is silently ignored

```
Given: .elicit/ contains README.md (does not match PHASE_PATTERN)
And:   .elicit/ contains at least one valid phase artifact with completeness_gate recorded
When:  check_elicit_compliance(.elicit/) is called
Then:  no findings reference README.md
And:   no CRITICAL is emitted solely because README.md is present
```

**Test file**: `tests/test_dryrun_elicit_compliance.py` (new: `test_readme_is_silently_ignored`)

### C3-S2 — scratch.md is silently ignored

```
Given: .elicit/ contains scratch.md (does not match PHASE_PATTERN)
And:   .elicit/ contains at least one valid phase artifact
When:  check_elicit_compliance(.elicit/) is called
Then:  no findings reference scratch.md
```

**Test file**: `tests/test_dryrun_elicit_compliance.py` (same test as C3-S1 with extra non-phase file)

### C3-S3 — phase-named file with broken payload raises CRITICAL

```
Given: .elicit/ contains map-org-2026-06-14.md (matches PHASE_PATTERN)
And:   its only fenced JSON block is malformed (e.g., invalid JSON or non-object value)
When:  check_elicit_compliance(.elicit/) is called
Then:  a CRITICAL finding is returned for map-org-2026-06-14.md
```

**Test file**: `tests/test_dryrun_elicit_compliance.py` (new: `test_phase_named_broken_payload_is_critical`)

### C3-S4 — phase-named file with no JSON block raises CRITICAL

```
Given: .elicit/ contains brd-org-2026-06-14.md (matches PHASE_PATTERN)
And:   the file contains no fenced JSON block at all
When:  check_elicit_compliance(.elicit/) is called
Then:  a CRITICAL finding is returned for brd-org-2026-06-14.md
```

**Test file**: `tests/test_dryrun_elicit_compliance.py` (new: `test_phase_named_no_json_block_is_critical`)

### C3-S5 — LAST fenced block is selected when multiple blocks exist

```
Given: a file named source-docs-acme-2026-06-14.md
And:   the file contains an EXAMPLE fenced JSON block first (e.g., {"example": true})
And:   followed by the CANONICAL fenced JSON block last (valid source-docs payload)
And:   optionally preceded by <!-- canonical-payload --> sentinel
When:  check_elicit_compliance(.elicit/) is called
Then:  the verifier validates the LAST block (the canonical one) and emits no CRITICAL
And:   the example block does NOT cause a validation failure
```

**Test file**: `tests/test_dryrun_elicit_compliance.py` (new: `test_last_fenced_block_is_canonical`)

### C3-S6 — non-phase files do NOT affect completeness check

```
Given: .elicit/ contains only README.md and one valid source-docs artifact with completeness_gate recorded
When:  check_elicit_compliance(.elicit/) is called
Then:  no "No assess_completeness recommendation was recorded" CRITICAL is emitted
```

**Test file**: `tests/test_dryrun_elicit_compliance.py` (implicit in C3-S1 test)

---

## Capability 4: completeness_gate Ownership

**Invariant**: `map` is the canonical owner of `completeness_gate.pre_mapping_recommendation`. A valid `map-*.md` artifact carrying the gate satisfies the cycle-level completeness requirement. A cycle with ONLY verify artifacts (no non-verify artifact records the gate) MUST raise CRITICAL.

### C4-S1 — map artifact carrying completeness_gate satisfies the gate

```
Given: .elicit/ contains only a valid map-*.md artifact
And:   its canonical JSON block has completeness_gate.pre_mapping_recommendation = "proceed_with_gaps"
When:  check_elicit_compliance(.elicit/) is called
Then:  no "No assess_completeness recommendation was recorded" CRITICAL is emitted
```

**Test file**: `tests/test_dryrun_elicit_compliance.py` (new: `test_map_artifact_satisfies_completeness_gate`)

### C4-S2 — source-docs carrying completeness_gate also satisfies the gate

```
Given: .elicit/ contains only a valid source-docs-*.md artifact
And:   its canonical JSON block has completeness_gate.pre_mapping_recommendation = "document"
When:  check_elicit_compliance(.elicit/) is called
Then:  no "No assess_completeness recommendation was recorded" CRITICAL is emitted
```

**Test file**: `tests/test_dryrun_elicit_compliance.py` (extend `test_completeness_gate_recorded`)

### C4-S3 — cycle with NO non-verify artifact recording the gate raises CRITICAL

```
Given: .elicit/ contains only verify-*.md artifacts (no source-docs, map, or brd)
When:  check_elicit_compliance(.elicit/) is called
Then:  a CRITICAL finding is returned: "No assess_completeness recommendation was recorded"
```

**Test file**: `tests/test_dryrun_elicit_compliance.py` (new: `test_no_completeness_gate_in_verify_only_cycle_is_critical`)

### C4-S4 — completeness_gate with invalid recommendation value raises CRITICAL

```
Given: .elicit/ contains a map-*.md artifact (no other non-verify)
And:   its completeness_gate.pre_mapping_recommendation = "invalid_value"
When:  check_elicit_compliance(.elicit/) is called
Then:  a CRITICAL finding is returned due to unrecognized recommendation value
       OR the gate is not considered recorded → "No assess_completeness recommendation was recorded"
```

**Test file**: `tests/test_dryrun_elicit_compliance.py` (new: `test_invalid_completeness_recommendation_is_critical`)

---

## Capability 5: connection-mapper Writes map Artifact

**Invariant**: `brainds-connection-mapper` has the `Write` tool granted in its agent definition. After a real agentic cycle, a `map-<slug>-<ISO>.md` file exists in `.elicit/` with a valid dual-contract canonical payload. The cascade changes to both installer scripts and `harness_check.py` remain consistent with the tool grant.

### C5-S1 — connection-mapper agent definition includes Write tool

```
Given: .claude/agents/brainds-connection-mapper.md is read
When:  its tools: list is inspected
Then:  "Write" appears in the list
```

**Test file**: `tests/test_harness_check.py` (new assertion: connection-mapper has Write in its tools list, or extend existing agent-tools check)

### C5-S2 — prompts mirror matches agent definition

```
Given: .claude/agents/brainds-connection-mapper.md and prompts/brainds-connection-mapper.md are read
When:  the tools lists are compared
Then:  both include "Write" and their prose descriptions are byte-aligned for the map-writing step
```

**Test file**: `tests/test_harness_check.py` (extend parity check between .claude/agents and prompts/)

### C5-S3 — DELEGATION_PROTOCOL artifact_keys includes map_file

```
Given: grounding.DELEGATION_PROTOCOL is accessed (or grounding.map_connections_context() is called)
When:  the artifact_keys section is inspected
Then:  a "map_file" (or equivalent) key is present indicating the connection-mapper writes to .elicit/
```

**Test file**: `tests/test_elicit_lifecycle.py` (new: `test_delegation_protocol_includes_map_file`)

### C5-S4 — harness_check passes after Write grant (both clients)

```
Given: brain_ds/harness_check.py is run against the installed agents
When:  check results are inspected
Then:  no parity failure is reported for brainds-connection-mapper
And:   SUBAGENT_NAMES and CLAUDE_AGENT_FILES rosters are unchanged (no new agents added)
```

**Test file**: `tests/test_harness_check.py` (existing tests must stay GREEN; verify no roster count change)

### C5-S5 — installer scripts grant Write to connection-mapper

```
Given: install-opencode.ps1 and install-opencode.sh are read
When:  the connection-mapper subagent insertion section is inspected
Then:  the task allowlist for brainds-connection-mapper includes "write" (or "edit"/"write" per OpenCode naming)
```

**Test file**: `tests/test_harness_check.py` (new: verify installer allowlist contains Write for connection-mapper)

---

## Capability 6: FakeDelegator / Dry-Run Double Alignment

**Invariant**: `tests/conftest.py` `write_artifact()` and `_artifact_body()` emit artifacts conforming to `ARTIFACT_CONTRACT` — specifically including top-level `artifact_type` and correctly-positioned `completeness_gate`. `check_elicit_compliance` MUST pass on dry-run output without modification.

### C6-S1 — dry-run source-docs double includes artifact_type

```
Given: write_artifact("source-docs", ...) is called from conftest.py
When:  the written file's canonical JSON block is parsed
Then:  "artifact_type" == "source-docs" is present at the top level
```

**Test file**: `tests/test_dryrun_elicit_compliance.py` (extend `test_source_docs_brainds_format`)

### C6-S2 — dry-run brd double includes fenced JSON block

```
Given: write_artifact("brd", ...) is called from conftest.py
When:  the written file is read
Then:  it contains a fenced JSON block (not pure markdown)
And:   the JSON block has artifact_type="brd" and a valid brd_node with the BRD carve-out fields
```

**Test file**: `tests/test_dryrun_elicit_compliance.py` (extend `test_brd_persistence_contract_in_dry_run`)

### C6-S3 — dry-run map double includes artifact_type and completeness_gate

```
Given: write_artifact("map", ...) is called from conftest.py
When:  the written file's canonical JSON block is parsed
Then:  "artifact_type" == "map" is present
And:   "completeness_gate".pre_mapping_recommendation is one of the allowed values
```

**Test file**: `tests/test_dryrun_elicit_compliance.py` (extend `test_completeness_gate_recorded`)

### C6-S4 — full dry-run output passes check_elicit_compliance with no CRITICAL

```
Given: the complete dry_run_elicit_output fixture runs (all phases)
When:  check_elicit_compliance(elicit_dir) is called on the output
Then:  zero CRITICAL findings are returned
```

**Test file**: `tests/test_dryrun_elicit_compliance.py` (new: `test_full_dry_run_output_passes_compliance` or integrated into existing full-cycle test)

### C6-S5 — FakeDelegator prompt assertions still hold after prose updates

```
Given: agent prompts (source-explorer, brd-writer, connection-mapper) are updated
And:   conftest.py FakeDelegator records the prompt passed to each sub-agent
When:  the dry_run_elicit_output fixture runs
Then:  each handoff prompt contains "artifact" and the source path
And:   no forbidden terms ("engram", "graph history", "Observation #") appear in prompts
```

**Test file**: `tests/test_dryrun_elicit_compliance.py::test_sub_agent_writes_only_to_elicit` (existing — must stay GREEN)

---

## Capability 7: Golden-Fixture CI Guard

**Invariant**: `tests/fixtures/elicit/` contains at least one golden artifact per phase type (source-docs, map, brd, verify) in the dual-contract format. A dedicated test runs `check_elicit_compliance` over those fixtures and asserts they conform to `ARTIFACT_CONTRACT`. This guard catches format regressions in CI without any live LLM calls.

### C7-S1 — golden fixtures exist for all four artifact types

```
Given: tests/fixtures/elicit/ directory is listed
When:  file names are inspected
Then:  at least one file matches each prefix: source-docs-*, map-*, brd-*, verify-*
```

**Test file**: `tests/test_live_artifact_contract.py` (new file, new test: `test_golden_fixtures_exist_for_all_phases`)

### C7-S2 — golden fixtures pass check_elicit_compliance

```
Given: tests/fixtures/elicit/ contains golden artifacts in dual-contract format
When:  check_elicit_compliance(tests/fixtures/elicit/) is called
Then:  zero CRITICAL findings are returned
```

**Test file**: `tests/test_live_artifact_contract.py` (new: `test_golden_fixtures_pass_compliance`)

### C7-S3 — golden fixtures conform to ARTIFACT_CONTRACT required_keys

```
Given: each golden fixture in tests/fixtures/elicit/ is parsed
And:   grounding.ARTIFACT_CONTRACT is loaded
When:  the fixture's canonical JSON block is compared against ARTIFACT_CONTRACT[artifact_type].required_keys
Then:  all required keys are present in every golden fixture
```

**Test file**: `tests/test_live_artifact_contract.py` (new: `test_golden_fixtures_conform_to_artifact_contract`)

### C7-S4 — golden brd fixture includes wikilinks and BRD carve-out

```
Given: tests/fixtures/elicit/brd-*.md golden fixture
When:  its canonical JSON block is parsed
Then:  brd_node.card_sections[0].title == "Contenido"
And:   brd_node.card_sections[0].order == 0
And:   brd_node.card_sections[0].icon == ""
And:   the "markdown" value contains "[["
```

**Test file**: `tests/test_live_artifact_contract.py` (new: `test_golden_brd_fixture_carve_out`)

### C7-S5 — golden verify fixture allows archive (gate=PASS, empty findings)

```
Given: tests/fixtures/elicit/verify-*.md golden fixture
When:  its canonical JSON block is parsed
Then:  gate == "PASS" AND findings == [] AND critical_count == 0
```

**Test file**: `tests/test_live_artifact_contract.py` (new: `test_golden_verify_fixture_gate_pass`)

---

## Capability 8: Cross-Client Parity

**Invariant**: All client-facing artifacts (agent prompts, skill files, grounding.py) are in sync across Claude Code and OpenCode. Skills are byte-identical between `skills/*/SKILL.md` and `.opencode/skills/*/SKILL.md`. `brain_ds check` passes. `test_harness_check.py` passes. No new sub-agent is introduced.

### C8-S1 — skills byte-identical between skills/ and .opencode/skills/

```
Given: skills/generate-brd/SKILL.md and .opencode/skills/generate-brd/SKILL.md
  AND: skills/map-connections/SKILL.md and .opencode/skills/map-connections/SKILL.md
  AND: skills/brainds-docs/SKILL.md and .opencode/skills/brainds-docs/SKILL.md
When:  their contents are compared
Then:  each pair is byte-identical
```

**Test file**: `tests/test_harness_check.py` (new or extend existing mirror check)

### C8-S2 — .claude/agents/ and prompts/ mirrors are prose-aligned

```
Given: .claude/agents/brainds-source-explorer.md and prompts/brainds-source-explorer.md
  AND: .claude/agents/brainds-brd-writer.md and prompts/brainds-brd-writer.md
  AND: .claude/agents/brainds-connection-mapper.md and prompts/brainds-connection-mapper.md
When:  their key sections (tools, artifact format instructions) are compared
Then:  no material divergence (both describe the same canonical payload format and Write step for mapper)
```

**Test file**: `tests/test_harness_check.py` (existing mirror-parity tests — must stay GREEN; new assertion for connection-mapper Write step)

### C8-S3 — brain_ds check passes (harness_check.py)

```
Given: brain_ds/harness_check.py is run (or test_harness_check.py calls its check functions)
When:  the check completes
Then:  no parity failures are reported for any of the 6 sub-agents
And:   the connection-mapper Write grant is reflected correctly in both client configs
```

**Test file**: `tests/test_harness_check.py` (existing; must stay GREEN after changes)

### C8-S4 — no new sub-agent is introduced (roster unchanged)

```
Given: brain_ds/harness_check.py SUBAGENT_NAMES and CLAUDE_AGENT_FILES constants are read
When:  they are compared against the pre-change values
Then:  the set of agent names is identical (6 agents, unchanged)
And:   no new .claude/agents/*.md file has been added
```

**Test file**: `tests/test_harness_check.py` (existing roster assertions — must still pass)

### C8-S5 — drift guard stays GREEN with ARTIFACT_CONTRACT present

```
Given: tests/test_grounding_drift_guard.py runs the Category-2 sweep
When:  ARTIFACT_CONTRACT is present in grounding.py
Then:  zero CamelCase compound tokens are flagged from ARTIFACT_CONTRACT values
And:   ARTIFACT_CONTRACT is NOT in the exempt list (sweeps clean naturally)
```

**Test file**: `tests/test_grounding_drift_guard.py` (existing — must stay GREEN)

---

## Capability 9: Mandatory Live Acceptance (Non-CI)

**Invariant**: When a correctly-formatted live elicit cycle is run end-to-end (intake → map → brd → verify), the verifier returns gate=PASS and archive is allowed. This is the acceptance criterion for the change; it is validated by a manual re-run of the live-e2e-synthetic cycle, not by CI.

### C9-S1 — live cycle verify produces gate=PASS

```
Given: a live elicit cycle for live-e2e-synthetic completes (intake→map→brd→verify)
And:   all agents emit artifacts in dual-contract format (as specified by ARTIFACT_CONTRACT)
When:  check_elicit_compliance(.elicit/) is called on the resulting artifacts
Then:  zero CRITICAL findings are returned
And:   the verify artifact's gate == "PASS"
And:   archive is unblocked
```

**Validation method**: Manual live re-run during `/sdd-apply` (not a CI test). The apply step logs that this was confirmed.

### C9-S2 — golden-fixture guard catches a format regression (guard test)

```
Given: ARTIFACT_CONTRACT changes (e.g., a required key is renamed)
And:   tests/fixtures/elicit/ golden fixtures are NOT updated
When:  test_live_artifact_contract.py::test_golden_fixtures_conform_to_artifact_contract runs
Then:  the test fails, catching the regression without any live LLM call
```

**Test file**: `tests/test_live_artifact_contract.py` (verified by construction — if ARTIFACT_CONTRACT changes without fixture update, C7-S3 fails)

---

## Summary Table

| Capability | Scenarios | Primary test file(s) | Key invariant |
|---|---|---|---|
| C1: Canonical artifact contract | C1-S1 to C1-S11 | `test_dryrun_elicit_compliance.py`, `test_elicit_lifecycle.py` | Dual-contract format, all 4 artifact types, BRD carve-out |
| C2: ARTIFACT_CONTRACT constant | C2-S1 to C2-S6 | `test_elicit_lifecycle.py`, `test_grounding_drift_guard.py` | Exists in grounding.py, injected into 3 composers, sweeps clean |
| C3: Verifier scoping | C3-S1 to C3-S6 | `test_dryrun_elicit_compliance.py` | Non-phase files skipped; phase-named malformed = CRITICAL; last-block selection |
| C4: completeness_gate ownership | C4-S1 to C4-S4 | `test_dryrun_elicit_compliance.py` | map is canonical owner; no non-verify gate = CRITICAL |
| C5: connection-mapper writes map | C5-S1 to C5-S5 | `test_harness_check.py`, `test_elicit_lifecycle.py` | Write tool granted; map-*.md written; cascade consistent |
| C6: Dry-run double alignment | C6-S1 to C6-S5 | `test_dryrun_elicit_compliance.py` | Double output passes compliance; artifact_type present; FakeDelegator intact |
| C7: Golden-fixture CI guard | C7-S1 to C7-S5 | `tests/test_live_artifact_contract.py` (new) | Fixtures exist for all 4 types; pass compliance + ARTIFACT_CONTRACT check |
| C8: Cross-client parity | C8-S1 to C8-S5 | `test_harness_check.py`, `test_grounding_drift_guard.py` | Skills byte-identical; agents mirrored; brain_ds check green; roster unchanged |
| C9: Live acceptance | C9-S1 to C9-S2 | Manual + `test_live_artifact_contract.py` | Live cycle → verify PASS + archive allowed; golden guard catches regressions |

---

## Out-of-Scope (do not implement as part of this change)

- Lowering any verifier check (hard constraint from proposal)
- Real LLM calls in CI tests
- Any new sub-agent (only tool grant to existing agent)
- Per-cycle subdir `.elicit/<cycle>/` migration (deferred)
- Changes to `SUBAGENT_NAMES` or `CLAUDE_AGENT_FILES` rosters

---

## Files That MUST Change

| File | Reason |
|---|---|
| `brain_ds/mcp/grounding.py` | Add `ARTIFACT_CONTRACT` constant; inject into 3 composers; update `DELEGATION_PROTOCOL.artifact_keys` with `map_file` |
| `brain_ds/verify/elicit_compliance.py` | Non-phase file skip; `finditer[-1]` last-block selection |
| `.claude/agents/brainds-source-explorer.md` | Canonical fenced JSON block instructions |
| `prompts/brainds-source-explorer.md` | Mirror of above |
| `.claude/agents/brainds-brd-writer.md` | Canonical fenced JSON block instructions |
| `prompts/brainds-brd-writer.md` | Mirror of above |
| `.claude/agents/brainds-connection-mapper.md` | Add Write tool; map-*.md writing step |
| `prompts/brainds-connection-mapper.md` | Mirror of above |
| `install-opencode.ps1` | Write grant for connection-mapper task allowlist |
| `install-opencode.sh` | Same |
| `brain_ds/harness_check.py` | Accommodate connection-mapper Write grant in parity checks |
| `AGENT_FLOW.md` | Note connection-mapper now writes map-*.md to .elicit/ |
| `tests/conftest.py` | Add `artifact_type` to `_artifact_body()`; confirm `completeness_gate` placement |
| `skills/generate-brd/SKILL.md` | Cross-reference note (byte-identical to .opencode mirror) |
| `.opencode/skills/generate-brd/SKILL.md` | Mirror |
| `skills/map-connections/SKILL.md` | Cross-reference note |
| `.opencode/skills/map-connections/SKILL.md` | Mirror |
| `skills/brainds-docs/SKILL.md` | Cross-reference note |
| `.opencode/skills/brainds-docs/SKILL.md` | Mirror |
| `tests/test_dryrun_elicit_compliance.py` | New/extended tests for C1, C3, C4, C6 |
| `tests/test_elicit_lifecycle.py` | New tests for C2, C5 |
| `tests/test_harness_check.py` | New/extended tests for C5, C8 |
| `tests/test_grounding_drift_guard.py` | Must stay GREEN (C2-S5, C8-S5) — no structural change expected |
| `tests/test_live_artifact_contract.py` | **New file** — golden-fixture CI guard (C7, C9) |
| `tests/fixtures/elicit/` | **New directory** — golden artifacts for all 4 phase types |
