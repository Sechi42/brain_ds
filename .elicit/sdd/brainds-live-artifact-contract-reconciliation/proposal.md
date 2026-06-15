# Proposal: brainds-live-artifact-contract-reconciliation

> SDD phase: **propose**. Artifact store: brain_ds-hybrid (this file + Engram `sdd/brainds-live-artifact-contract-reconciliation/proposal`).
> Locked approach: **Option C (dual contract)** + Option 3/Hybrid execution from the exploration. Do NOT relitigate.

## 1. Intent / Why

A REAL live agentic cycle on `live-e2e-synthetic` (#2165) completed correctly — intake→map→brd ran via real Task delegation, the graph reached node_count 4 / edge_count 3 — but the verify gate **correctly BLOCKED** archive with 4 CRITICAL. The block was NOT a false positive: the verifier (`check_elicit_compliance`) was only ever validated against in-process dry-run **doubles**, while real sub-agents emit a different artifact shape. This is a contract divergence, not a verifier bug.

**The 5 concrete defects (live-vs-double divergence):**

| # | Defect | Evidence |
|---|--------|----------|
| D1 | source-docs artifacts embed a `card_sections` JSON **array**, not the `{documented_nodes:[...]}` **object** envelope | `_load_payload` rejects non-dict → "payload must be a JSON object" |
| D2 | BRD artifact is **pure markdown with NO fenced JSON block** | `PAYLOAD_PATTERN.search` finds nothing → "missing a fenced JSON payload" |
| D3 | Verifier globs `.elicit/*.md` flat (line 131) and sweeps `README.md`, which fails `PHASE_PATTERN` | `check_elicit_compliance` has no README carve-out (unlike `test_elicit_lifecycle.py:45`) |
| D4 | No canonical artifact-format source of truth in `grounding.py` → real agents and the dry-run double evolved independently | `grounding.py` has `BRD_GRAPH_PERSISTENCE_CONTRACT` but no artifact-envelope contract |
| D5 | `brainds-connection-mapper` writes the `map-*` artifact to **Engram only** — no `.elicit/map-*.md` — and its agent definition has **no `Write` tool** | `.claude/agents/brainds-connection-mapper.md` line 30 ("save receipt to engram"); tools list (lines 5-14) has no `Write` |

**Success looks like:** real agents emit markdown + ONE canonical fenced JSON block per artifact; the verifier validates that JSON without guessing markdown; the SAME bar passes on a live cycle ending in verify PASS + archive allowed; a CI golden-fixture guard catches format regressions **without** live LLM calls.

**HARD PRINCIPLE (locked):** the verifier bar is NOT lowered. Every check in §5 stays. We reconcile the producers (agents + double) to the contract, not the contract to the producers.

## 2. Scope

### In scope
- `ARTIFACT_CONTRACT` constant in `grounding.py` as the cross-client source of truth, injected into the 3 grounding composers.
- Glob/scoping fix in `check_elicit_compliance` (stop sweeping `README.md` and non-phase `.md`).
- 3 agent prompt **pairs** updated to emit the canonical fenced JSON block (source-explorer, brd-writer, connection-mapper — each `.claude/agents/` + `prompts/`).
- `brainds-connection-mapper` writes a real `.elicit/map-*.md` artifact → grant it the `Write` tool → harness cascade (D5).
- FakeDelegator / dry-run double (`tests/conftest.py`) confirmed byte-aligned to the SAME canonical format; prompt assertions reviewed.
- Golden-fixture CI guard + mandatory live-compliance test (Slice 2).
- Skill-file cross-reference notes (+ `.opencode/skills` mirrors byte-identical).

### Out of scope (explicit)
- **Lowering the verifier bar** — non-negotiable.
- **Real-LLM / subprocess CI calls** — coverage is golden-fixture-based, no live LLM in CI.
- **Any NEW sub-agent** — only a tool grant to an existing agent (D5). `SUBAGENT_NAMES` / `CLAUDE_AGENT_FILES` rosters are unchanged.
- **Per-cycle subdir migration (`.elicit/<cycle>/`)** — **DEFERRED** (see decision (c)). Slice 1 only stops the flat sweep from picking up `README.md` / non-phase files.

## 3. Approach (endorse Option 3 / Hybrid)

1. **Single source of truth**: add `ARTIFACT_CONTRACT` to `grounding.py` next to `BRD_GRAPH_PERSISTENCE_CONTRACT`; inject `artifact_contract` into `elicit_context()`, `map_connections_context()`, and `generate_brd_context()`. Real agents receive it via MCP tool return → cross-client automatically (Claude Code + OpenCode). Skill files get only a cross-reference note.
2. **Verifier scoping fix** (no bar change): exclude `README.md` and any file not matching `PHASE_PATTERN` from the *compliance* sweep — but keep a CRITICAL for phase-named files that are malformed (so we don't silently skip a real artifact).
3. **3 agent prompt pairs** updated to append the canonical fenced JSON block (markdown first, JSON last).
4. **connection-mapper writes `.elicit/map-*.md`** with the canonical `map` payload (carries `completeness_gate`) + gets the `Write` tool + harness cascade.
5. **Double alignment**: `conftest.py` `write_artifact()` already emits the object envelope; confirm it matches `ARTIFACT_CONTRACT` exactly (add `artifact_type` + `completeness_gate` placement) and that FakeDelegator prompt assertions still hold.
6. **Golden-fixture CI guard**: ship `tests/fixtures/elicit/` golden artifacts in the new dual-contract format; a test runs `check_elicit_compliance` against them AND asserts they conform to `ARTIFACT_CONTRACT` (a drift guard analogous to `test_grounding_drift_guard.py`).

## 4. Resolved decisions (a)–(e)

| # | Decision | Recommendation | One-line rationale |
|---|----------|----------------|--------------------|
| **(a)** | Who carries `completeness_gate.pre_mapping_recommendation` | **`map` artifact is the canonical owner; `source-docs` MAY also carry it.** Keep the existing "at least one non-verify artifact records it" rule. | The connection-mapper already calls `assess_completeness` (agent step 2) — it owns the gate result. Once it writes a real `map-*.md` (D5), the gate is recorded in the natural place; no new burden on source-explorer. |
| **(b)** | `PAYLOAD_PATTERN` block selection | **Mandate canonical-LAST AND change the verifier to `finditer(...)[-1]`** (belt + suspenders). | Agents may emit an example/schema block before the canonical one. Prose alone is fragile; selecting the last block makes the verifier robust even if an agent shows an example first. Add a `<!-- canonical-payload -->` sentinel in the contract prose as the documented anchor. |
| **(c)** | Per-cycle subdir `.elicit/<cycle>/` | **DEFERRED to a later slice.** Slice 1 keeps flat `.elicit/` and fixes scoping by filtering the glob. | Subdir migration is a separate blast radius (verifier call site, `DELEGATION_PROTOCOL.artifact_keys`, `.elicit/README.md`, `test_elicit_lifecycle.py` path constants, orchestrator cycle discovery). Decoupling keeps the gate-blocker slice small. |
| **(d)** | Add `Write` to `brainds-connection-mapper` | **In scope. Confirmed.** | Without `Write` the agent cannot produce `.elicit/map-*.md`; D5 is unfixable otherwise. It is a tool grant on an existing agent — no roster change. |
| **(e)** | `ARTIFACT_CONTRACT` Python shape + drift classification | **Dict `{artifact_type: {required_keys, schema_notes, validator}}`. It sweeps CLEAN (NOT exempt), like `PIPELINE_STAGES`.** | Auto-discovered by `_discover_category2_constants` (UPPER_SNAKE dict). The only entity-ish value is `"Unknown"` (a real `EntityType` value AND not a CamelCase compound, so the `\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b` sweep never flags it). Keep all entity-name values as real `EntityType` values so it stays sweep-clean. |

### (c) — how the verifier scopes artifacts in the chosen (flat) layout

`check_elicit_compliance` keeps `elicit_dir.glob("*.md")` but partitions:
- Files matching `PHASE_PATTERN` → validated normally (current behavior, full bar).
- Files NOT matching `PHASE_PATTERN` → **skipped silently** (README.md, scratch notes) instead of emitting CRITICAL.

This is the minimal scoping change. It does NOT relax any payload check — only stops flagging non-artifact files. (Today line 136-138 emits CRITICAL for any non-matching `.md`; we invert that to a skip, which matches what `test_elicit_lifecycle.py` already does at line 45.)

### (d) — connection-mapper Write-tool cascade (enumerated)

| Touch point | Change |
|-------------|--------|
| `.claude/agents/brainds-connection-mapper.md` | add `Write` to `tools:`; add step "write `.elicit/map-<slug>-<ISO>.md` with canonical payload" |
| `prompts/brainds-connection-mapper.md` | mirror the same (byte-aligned prose) |
| `install-opencode.ps1` task allowlist | grant `Write` (or `edit`/`write` per OpenCode tool naming) to the connection-mapper subagent insertion |
| `install-opencode.sh` task allowlist | same |
| `brain_ds/harness_check.py` | no roster change (`SUBAGENT_NAMES`/`CLAUDE_AGENT_FILES` unchanged); confirm any per-agent tool assertions accommodate the new grant |
| `AGENT_FLOW.md` | note connection-mapper now writes `map-*` to `.elicit` |
| `DELEGATION_PROTOCOL` (grounding.py) | confirm `artifact_keys` lists a `map_file` entry (cross-client source of truth) |

## 5. Canonical JSON schema per artifact type + validator mapping

Dual-contract rule: **human-readable markdown first, then exactly ONE fenced ```json block (the canonical payload, LAST in the file), preceded by `<!-- canonical-payload -->`.** The block is always a JSON **object** with a top-level `artifact_type`.

### source-docs → `_check_documented_nodes`
```json
{
  "artifact_type": "source-docs",
  "graph_id": "<slug>",
  "documented_nodes": [
    {"node_id": "<id>", "label": "<label>", "type": "<EntityType value>",
     "card_sections": [{"title": "...", "content": "...", "icon": "...", "order": 1}]}
  ],
  "completeness_gate": {"pre_mapping_recommendation": "elicit|document|proceed_with_gaps"}
}
```
Validator: `_check_documented_nodes` — non-empty `documented_nodes`, each with valid `card_sections` (title/content/icon non-empty, order>=1). `completeness_gate` optional here (see decision (a)).

### map → `_check_documented_nodes` + completeness check
```json
{
  "artifact_type": "map",
  "graph_id": "<slug>",
  "documented_nodes": [ { "...": "same node shape as source-docs" } ],
  "edges": [{"source": "<id>", "target": "<id>", "label": "<RelationshipType value>"}],
  "completeness_gate": {"pre_mapping_recommendation": "elicit|document|proceed_with_gaps"}
}
```
Validator: `_check_documented_nodes` for nodes; cycle-level completeness check (line 152-154) reads `completeness_gate.pre_mapping_recommendation`. **This is the canonical owner of the gate** (decision (a)).

### brd → `_check_brd_payload`
```json
{
  "artifact_type": "brd",
  "graph_id": "<slug>",
  "markdown": "# BRD\n\n[[wikilink]] ...",
  "brd_node": {
    "node_id": "brd-<slug>", "label": "BRD", "type": "Unknown",
    "card_sections": [{"title": "Contenido", "content": "<full BRD markdown>", "order": 0, "icon": ""}]
  }
}
```
Validator: `_check_brd_payload` — `brd_node.node_id == "brd-<graph_id>"`, `label=="BRD"`, `type=="Unknown"`, `card_sections[0]` keeps `title=="Contenido"`, `order==0`, `icon==""`, and `"[["` present in `markdown`. Must stay aligned with `BRD_GRAPH_PERSISTENCE_CONTRACT`.

### verify → `_check_verify_payload`
```json
{
  "artifact_type": "verify",
  "graph_id": "<slug>", "stage": "verify",
  "status": "PASS|BLOCKED", "critical_count": 0,
  "findings": [], "gate": "PASS|BLOCKED"
}
```
Validator: `_check_verify_payload` — all 6 required keys; archive allowed only when `gate=="PASS"` AND `findings` empty.

## 6. Cross-client cascade plan (every file each content touches)

| Content | Files |
|---------|-------|
| `ARTIFACT_CONTRACT` source of truth | `brain_ds/mcp/grounding.py` (new constant + inject into `elicit_context`, `map_connections_context`, `generate_brd_context`) |
| Verifier scoping + last-block selection | `brain_ds/verify/elicit_compliance.py` (glob skip non-phase; `PAYLOAD_PATTERN` → last match) |
| source-explorer prompt | `.claude/agents/brainds-source-explorer.md` + `prompts/brainds-source-explorer.md` |
| brd-writer prompt | `.claude/agents/brainds-brd-writer.md` + `prompts/brainds-brd-writer.md` |
| connection-mapper prompt + Write grant | `.claude/agents/brainds-connection-mapper.md` + `prompts/brainds-connection-mapper.md` + `install-opencode.ps1` + `install-opencode.sh` + `brain_ds/harness_check.py` + `AGENT_FLOW.md` |
| Skill cross-ref notes (byte-identical mirrors) | `skills/generate-brd/SKILL.md` ↔ `.opencode/skills/generate-brd/SKILL.md`; `skills/map-connections/SKILL.md` ↔ `.opencode/skills/map-connections/SKILL.md`; `skills/brainds-docs/SKILL.md` ↔ `.opencode/skills/brainds-docs/SKILL.md` |
| Double alignment | `tests/conftest.py` (`write_artifact()` / `_artifact_body()` → add `artifact_type`, confirm `completeness_gate` placement); review `tests/fixtures/delegation.py` prompt assertions |
| Drift guard for new constant | `tests/test_grounding_drift_guard.py` (no change expected — `ARTIFACT_CONTRACT` sweeps clean; add only if a CamelCase token slips in) |

**Mirror rule:** `skills/*/SKILL.md` and `.opencode/skills/*/SKILL.md` must be byte-identical; `.claude/agents/brainds-*.md` and `prompts/brainds-*.md` mirror each other. Run `/share-brainds` after skill edits. A red drift guard means "update the harness", never "suppress the test".

## 7. Slice plan

### Slice 1 — Contract fix (gate blocker)
- `ARTIFACT_CONTRACT` in `grounding.py` + inject into 3 composers (~40 lines)
- `elicit_compliance.py`: skip non-phase files + last-block selection (~15 lines)
- 3 agent prompt pairs updated (~120 lines across 6 files)
- connection-mapper Write grant + cascade (installers, harness_check, AGENT_FLOW) (~40 lines)
- `conftest.py` double alignment + RED→GREEN unit tests (~50 lines)
- **Estimate: ~265 changed lines.** Under 400 but in the upper band → **flag for ask-on-risk** if scope grows.

### Slice 2 — Live test coverage
- `tests/fixtures/elicit/` golden artifacts in dual-contract format (~80 lines, mostly fixtures)
- New `tests/test_live_e2e_compliance.py` (or extend `test_elicit_lifecycle.py`): run `check_elicit_compliance` on golden fixtures → PASS; assert fixtures conform to `ARTIFACT_CONTRACT` (~70 lines)
- **Estimate: ~150 changed lines.** Comfortably under 400.

**400-line budget:** Slice 1 ~265 (medium risk), Slice 2 ~150 (low). Combined >400 → **two chained PRs recommended** under delivery=ask-on-risk. Decision: ask the maintainer before apply only if Slice 1 alone breaches 400.

## 8. Risks & mitigations

| Risk | Mitigation |
|------|-----------|
| **Format drift recurs** (the original root cause: no cross-client format constant) | `ARTIFACT_CONTRACT` is the single source injected into all composers; golden-fixture CI guard fails on any format regression **without live LLM calls**. |
| **Verifier picks the wrong fenced block** (example before canonical) | `finditer(...)[-1]` + mandate canonical-LAST + `<!-- canonical-payload -->` sentinel (decision (b)). |
| **FakeDelegator / double silently drifts again** | `conftest.py` `write_artifact()` aligned to `ARTIFACT_CONTRACT`; add a test asserting the double's output conforms to the same contract the verifier enforces, and that FakeDelegator prompt assertions still match the new prose. |
| **connection-mapper Write grant breaks harness parity** | Full cascade enumerated in (d); `brain_ds check` + `test_harness_check.py` validate installed-vs-repo parity across both clients. |
| **Skill mirrors drift** | Byte-identical mirror rule; `/share-brainds` after edits; drift guard red = fix harness. |
| **Lowering the bar by accident** while fixing the glob | The glob fix only converts non-phase-file CRITICAL → skip; phase-named-but-malformed files still emit CRITICAL. No payload check is touched. |

## 9. Next recommended
`sdd-spec` and `sdd-design` can run in parallel (both read this proposal).
