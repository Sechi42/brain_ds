# Exploration: brainds-live-artifact-contract-reconciliation

Artifact store: brain_ds-hybrid. Engram: `sdd/brainds-live-artifact-contract-reconciliation/explore` (#2168).
Approach LOCKED: Option C (dual contract = markdown + canonical fenced JSON). HARD PRINCIPLE: do NOT lower the verifier bar.

## Current State — two divergent formats
**Format A — dry-run double** (`tests/conftest.py` `_artifact_body()`): every artifact is `# Title` + a fenced JSON **object** with a known envelope (`documented_nodes`, `completeness_gate`, `brd_node`, `markdown`). `check_elicit_compliance` was written ONLY for this.

**Format B — real agents** (live `.elicit/`):
- `brainds-source-explorer` → human markdown + a `card_sections` JSON **array** → checker: "payload must be a JSON object".
- `brainds-brd-writer` → 14-section markdown, **no fenced JSON at all** → "missing a fenced JSON payload".
- `README.md` at `.elicit/` root swept by flat `glob("*.md")` → "does not match naming contract".
- `brainds-connection-mapper` → **Engram-only, writes NO `.elicit/map-*.md`** (5th defect, not seen in the live run because the file simply never existed). It also lacks a Write tool in its agent definition.

## Gap Analysis vs the 6 required contents
1. Single artifact contract → missing; two formats coexist.
2. Per-cycle scoping → not implemented; flat `.elicit/` swept.
3. Real agent prompts → none emit the JSON envelope; connection-mapper writes nothing.
4. FakeDelegator aligned → the double emits Format A; must converge on the new contract.
5. Verifier updated → must accept canonical JSON without lowering the bar; today rejects arrays + missing payloads.
6. Mandatory live test → no live-shaped artifact CI coverage exists.

## Proposed canonical JSON (dual-contract; markdown first, ONE fenced JSON block last)
- **source-docs**: `{artifact_type, graph_id, documented_nodes:[{node_id,label,type,card_sections}], completeness_gate:{pre_mapping_recommendation}}`
- **map**: `{artifact_type, graph_id, documented_nodes, edges:[{source,target,label}], completeness_gate}` — connection-mapper must now ALSO write this file.
- **brd**: `{artifact_type, graph_id, markdown, brd_node:{node_id,label,type,card_sections[0]={title:"Contenido",order:0,icon:""}}, completeness_gate}`
- **verify**: already correct (`graph_id, stage, status, critical_count, findings, gate`) — no change.

## Schema source of truth
Add `ARTIFACT_CONTRACT: dict[str,dict]` to `grounding.py` next to `BRD_GRAPH_PERSISTENCE_CONTRACT`; inject into all 3 composers so both clients get it. Skill files only get a cross-reference note.

## Approaches
| Approach | Fixes all defects | Blast radius | Effort |
|---|---|---|---|
| 1 Minimal (glob + prompts, flat) | 3 of 4 | Low | Low |
| 2 Full (per-cycle subdir + dual contract) | All | Medium | Medium |
| **3 Hybrid (glob fix + dual contract + ARTIFACT_CONTRACT, flat preserved) — REC** | All | Low-medium | Low-medium |

Recommendation: Option 3 — fix glob (exclude README), add ARTIFACT_CONTRACT, update 3 agent prompt pairs, teach connection-mapper to write `map-*.md` (+ give it Write tool), defer per-cycle subdir to a later slice.

## Slices
- **Slice 1 (gate blocker)**: elicit_compliance.py glob fix + PAYLOAD_PATTERN last-block; ARTIFACT_CONTRACT in grounding.py + composers; source-explorer/brd-writer/connection-mapper prompt pairs (both clients); connection-mapper gets Write tool + map artifact; generate-brd/map-connections SKILL cross-ref (byte-identical mirrors). ~150-200 lines.
- **Slice 2 (live test coverage)**: golden dual-contract fixtures in tests/fixtures/elicit/; `tests/test_live_artifact_contract.py`; CI drift-guard that golden fixtures satisfy check_elicit_compliance; optional per-cycle subdir. ~60-100 lines.

400-line risk: Low per slice. Chained PRs: optional (each slice autonomous).

## Risks
1. PAYLOAD_PATTERN matches FIRST fenced block — agents emitting example blocks first break it. Use `finditer(...)[-1]` or mandate canonical-last.
2. completeness_gate ownership (source-docs vs map) must be explicit in proposal.
3. connection-mapper currently has NO Write tool — must add it to emit map-*.md (harness/installer + harness_check implications).
4. FakeDelegator `to_handoffs()` prompt assertions (synthetic_source_path) must still hold after prompt changes.
5. Drift recurred invisibly until a live run — add a CI golden-fixture guard so format regressions fail without live LLM calls.

## Affected files
brain_ds/verify/elicit_compliance.py, brain_ds/mcp/grounding.py, .claude/agents/brainds-{source-explorer,brd-writer,connection-mapper}.md + prompts/brainds-* mirrors, tests/conftest.py, tests/fixtures/delegation.py, tests/test_dryrun_elicit_compliance.py, tests/test_elicit_lifecycle.py, tests/test_live_artifact_contract.py (new), tests/fixtures/elicit/ (new), skills/{generate-brd,map-connections}/SKILL.md + .opencode mirrors, AGENT_FLOW.md/harness_check.py if connection-mapper tool list changes.
