# Design — brainds-live-artifact-contract-reconciliation

**Status**: design complete
**Approach**: Option C dual contract (human markdown + ONE canonical fenced JSON block per artifact) reconciled with `check_elicit_compliance` WITHOUT lowering the verifier bar.
**Source of truth**: `brain_ds/mcp/grounding.py` `ARTIFACT_CONTRACT` (Category-2, cross-client).

---

## 1. Architecture at a glance

The defect (live run #2165) is a **contract mismatch across two writers**:

| Writer | Emits today | Verifier expects |
|---|---|---|
| Real source-explorer | `card_sections` JSON **array** | `{documented_nodes:[...]}` object |
| Real brd-writer | pure markdown, no fenced JSON | `{graph_id, markdown, brd_node, completeness_gate}` |
| Real connection-mapper | Engram only, no `.elicit/map-*.md` | a `map-*.md` with `{documented_nodes, completeness_gate}` |
| Dry-run double (conftest) | correct envelope | correct envelope |

The fix has ONE canonical contract, declared ONCE in `grounding.py` (`ARTIFACT_CONTRACT`), injected into the three composers so BOTH Claude Code and OpenCode agents read the same shape, mirrored by the dry-run double, and enforced by the verifier. The verifier is also taught to SKIP non-phase files (README/scratch) while keeping phase-named-but-broken files at CRITICAL.

```
                  grounding.ARTIFACT_CONTRACT  (single source of truth, Category-2)
                           │
        ┌──────────────────┼───────────────────────────────┐
        │                  │                                │
 elicit_context()  map_connections_context()  generate_brd_context()
        │                  │                                │
   (Claude agents + OpenCode agents read it via the MCP grounding payload)
        │                  │                                │
   source-explorer    connection-mapper                brd-writer
        │                  │                                │
   source-docs-*.md     map-*.md                        brd-*.md     ──► .elicit/
        └──────────────────┴────────────────┬───────────────┘
                                             ▼
                          check_elicit_compliance(.elicit/)
                          (skip non-phase, CRITICAL on broken,
                           last-fenced-block selection, same structural checks)
                                             ▲
                          tests/conftest.py double emits the SAME canonical format
                          tests/fixtures/elicit/* golden artifacts guard the format (Slice 2)
```

**Layering boundaries (unchanged)**: `grounding.py` declares contract → composers expose → agents consume → `elicit_compliance.py` validates. No new module, no new agent, no per-cycle subdir.

---

## 2. `ARTIFACT_CONTRACT` — concrete Python structure

Lives in `grounding.py` immediately after `DELEGATION_PROTOCOL` (so it can reference `PIPELINE_STAGES` phase names conceptually, though it does not import them). It is an UPPER_SNAKE module-level `dict[str, object]` → auto-discovered by `_discover_category2_constants`, NOT exempt, sweeps clean.

```python
# Harness-owned canonical artifact contract — the ONE machine-checkable shape each
# .elicit/ phase artifact must carry, IN ADDITION to its human-readable markdown.
# Mirrored by the dry-run double (tests/conftest.py) and enforced by
# brain_ds/verify/elicit_compliance.py. Cross-client: Claude Code + OpenCode agents
# both receive this via the three grounding composers. Keep skill prose in sync.
ARTIFACT_CONTRACT: dict[str, object] = {
    "dual_contract_rule": (
        "Every .elicit/<phase>-<slug>-<ISO-date>.md artifact is DUAL: human-readable "
        "markdown for people, PLUS exactly ONE canonical fenced ```json block that the "
        "verify gate parses. The canonical block MUST be the LAST fenced json block in "
        "the file and MUST be immediately preceded by the line '<!-- canonical-payload -->'. "
        "Illustrative example json blocks may appear earlier; only the last one is canonical."
    ),
    "canonical_sentinel": "<!-- canonical-payload -->",
    "selection_rule": (
        "The verifier selects the LAST fenced ```json block (finditer[-1]); the sentinel "
        "comment is a human/agent marker and a belt-and-suspenders signal, not a parse anchor."
    ),
    "artifacts": {
        "source-docs": {
            "required_keys": ["graph_id", "documented_nodes"],
            "schema_notes": (
                "documented_nodes: list of {node_id, label, type, card_sections[]}. "
                "Each card_section: {title, content, icon, order}. Non-Unknown nodes use "
                "order>=1 and a non-empty icon. MAY carry completeness_gate."
            ),
            "validator": "_check_documented_nodes",
        },
        "map": {
            "required_keys": ["graph_id", "documented_nodes", "completeness_gate"],
            "schema_notes": (
                "documented_nodes as in source-docs, plus edges[] {source,target,label}. "
                "OWNS the completeness_gate (assess_completeness output) for the cycle — its "
                "pre_mapping_recommendation must be one of elicit|document|proceed_with_gaps."
            ),
            "validator": "_check_documented_nodes",
        },
        "brd": {
            "required_keys": ["graph_id", "markdown", "brd_node"],
            "schema_notes": (
                "brd_node: {node_id 'brd-<graph_id>', label 'BRD', type 'Unknown', "
                "card_sections[0] {title 'Contenido', order 0, icon ''}}. markdown MUST "
                "contain [[wikilinks]]. MAY carry completeness_gate."
            ),
            "validator": "_check_brd_payload",
        },
        "verify": {
            "required_keys": ["graph_id", "stage", "status", "critical_count", "findings", "gate"],
            "schema_notes": (
                "gate 'PASS' with empty findings allows archive; gate 'BLOCKED' or any "
                "findings blocks archive. Verify artifacts carry NO completeness_gate."
            ),
            "validator": "_check_verify_payload",
        },
    },
}
```

### Why it sweeps clean (drift-guard integration)

`_sweep_constant` finds CamelCase-compound tokens `\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b` not in `EntityType` values nor `SAFE_ENTITYISH_TOKENS`. The only entity-ish literal in `ARTIFACT_CONTRACT` is `"Unknown"` (a single word → not a CamelCase compound → never matched) and `"BRD"` (all-caps, not matched). Validator names like `_check_documented_nodes` are snake_case, not matched. So `ARTIFACT_CONTRACT` behaves exactly like `PIPELINE_STAGES`: auto-discovered, NOT in `CATEGORY2_EXEMPT`, sweeps clean. **No change to `test_grounding_drift_guard.py` is required** — but Slice 1 adds an explicit assertion mirroring the `PIPELINE_STAGES` pattern (see §10) to lock that intent.

### How composers expose it

Add the key `"artifact_contract": ARTIFACT_CONTRACT` to the return dict of all three composers:

- `elicit_context()` → becomes 15 keys (was 14). Update the docstring key list.
- `map_connections_context()` → becomes 13 keys (was 12). Update the docstring key list.
- `generate_brd_context()` → becomes 11 keys (was 10). Update the docstring key list.

### How it reads for OpenCode

OpenCode agents receive the identical grounding payload from the same MCP tools (`run_elicit`, `map_connections`, `generate_brd`) — there is no client-specific branch. `grounding.py` is the single source of truth; the `.opencode/skills/*/SKILL.md` prose must add the same dual-contract note byte-identical to `skills/*/SKILL.md`.

---

## 3. Canonical JSON schema per artifact type (final form)

### source-docs (validator `_check_documented_nodes`)
```json
{
  "graph_id": "live-e2e-synthetic",
  "documented_nodes": [
    {
      "node_id": "live-e2e-synthetic-data-source-orders-db",
      "label": "Synthetic Orders DB",
      "type": "Data Source",
      "card_sections": [
        {"title": "Overview", "content": "...", "icon": "info", "order": 1}
      ]
    }
  ]
}
```
Each `card_sections` entry checked by `_check_documented_nodes`: non-empty title, non-empty content; non-BRD nodes require `order` int >= 1 and non-empty `icon`.

### map (validator `_check_documented_nodes` + cycle completeness)
```json
{
  "graph_id": "live-e2e-synthetic",
  "documented_nodes": [ { "...": "same shape as source-docs" } ],
  "edges": [ {"source": "...", "target": "...", "label": "owns"} ],
  "completeness_gate": {"pre_mapping_recommendation": "proceed_with_gaps"}
}
```
`completeness_gate.pre_mapping_recommendation` ∈ `ALLOWED_RECOMMENDATIONS` satisfies the cycle completeness rule (validated in `check_elicit_compliance`, not in `_check_documented_nodes`).

### brd (validator `_check_brd_payload`)
```json
{
  "graph_id": "live-e2e-synthetic",
  "markdown": "# Business Requirements Document ... [[Synthetic Orders DB]] ...",
  "brd_node": {
    "node_id": "brd-live-e2e-synthetic",
    "label": "BRD",
    "type": "Unknown",
    "card_sections": [
      {"title": "Contenido", "content": "<full markdown>", "order": 0, "icon": ""}
    ]
  },
  "completeness_gate": {"pre_mapping_recommendation": "proceed_with_gaps"}
}
```
`_check_brd_payload` checks: `brd_node.node_id == brd-<graph_id>`, label `BRD`, type `Unknown`, `card_sections[0]` title `Contenido`/order 0/icon ``, and `markdown` contains `[[`.

### verify (validator `_check_verify_payload`)
```json
{
  "graph_id": "live-e2e-synthetic",
  "stage": "verify",
  "status": "PASS",
  "critical_count": 0,
  "findings": [],
  "gate": "PASS"
}
```
Unchanged shape; verify already emits a canonical block today.

**No structural check is relaxed.** The contract only adds the dual-contract envelope and the canonical-LAST selection; every existing assertion in `_check_documented_nodes` / `_check_brd_payload` / `_check_verify_payload` / the completeness rule stays as-is.

---

## 4. Verifier changes — `brain_ds/verify/elicit_compliance.py`

### (i) Payload selection: last fenced block + sentinel (`_load_payload`)

**Before**
```python
PAYLOAD_PATTERN = re.compile(r"```json\n(.*?)\n```", re.DOTALL)
...
def _load_payload(path: Path) -> tuple[dict | None, Finding | None]:
    text = path.read_text(encoding="utf-8")
    match = PAYLOAD_PATTERN.search(text)
    if not match:
        return None, _critical(f"{path.name} is missing a fenced JSON payload", path)
    try:
        payload = json.loads(match.group(1))
    ...
```

**After**
```python
PAYLOAD_PATTERN = re.compile(r"```json\n(.*?)\n```", re.DOTALL)
CANONICAL_SENTINEL = "<!-- canonical-payload -->"
...
def _load_payload(path: Path) -> tuple[dict | None, Finding | None]:
    text = path.read_text(encoding="utf-8")
    matches = list(PAYLOAD_PATTERN.finditer(text))
    if not matches:
        return None, _critical(f"{path.name} is missing a fenced JSON payload", path)
    match = matches[-1]                      # canonical block is ALWAYS last
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        return None, _critical(f"{path.name} contains invalid JSON payload: {exc}", path)
    if not isinstance(payload, dict):
        return None, _critical(f"{path.name} payload must be a JSON object", path)
    return payload, None
```
Rationale: the sentinel is a human/agent marker; selection is purely positional (`finditer[-1]`) so an illustrative `card_sections` example earlier in the file never shadows the canonical envelope. This single change fixes D1 (source-docs array example before canonical) and D2 (brd now carries a canonical block).

> Decision: positional selection is the parse contract; the sentinel is documented in `ARTIFACT_CONTRACT` and required of agents, but the verifier does NOT hard-fail a file that lacks the sentinel as long as the last fenced block is a valid envelope. This keeps the bar at "valid canonical payload present", not "comment present". (Belt-and-suspenders, not a new failure mode.)

### (ii) Scoping branch — rule #5 (`check_elicit_compliance`)

**Before**
```python
for path in artifact_paths:
    if not PHASE_PATTERN.match(path.name):
        findings.append(_critical(f"{path.name} does not match the .elicit naming contract", path))
        continue
    payload, error = _load_payload(path)
    ...
```

**After**
```python
for path in artifact_paths:
    if not PHASE_PATTERN.match(path.name):
        # Non-phase files (README.md, scratch.md, notes) are NOT cycle artifacts.
        # Skip them silently — they are out of the verifier's scope.
        continue
    # Phase-named files MUST be well-formed. A missing/broken canonical payload
    # in a phase-named file is a CRITICAL gate failure (does NOT get skipped).
    payload, error = _load_payload(path)
    if error is not None:
        findings.append(error)
        continue
    ...
```

The 4 canonical scoping cases this produces:

| File | PHASE_PATTERN match | Result |
|---|---|---|
| `README.md` | no | **ignored** (skipped, no finding) |
| `scratch.md` | no | **ignored** (skipped, no finding) |
| `map-org-2026-06-14.md` (broken JSON) | yes | **CRITICAL** ("invalid JSON payload") |
| `brd-org-2026-06-14.md` (no payload) | yes | **CRITICAL** ("missing a fenced JSON payload") |

This fixes D3 (README sweep) while preserving the HARD principle: the bar is not lowered — a phase-named file with a broken payload still blocks archive.

### (iii) Accept new envelopes WITHOUT relaxing checks

No edits to `_check_documented_nodes`, `_check_brd_payload`, `_check_verify_payload`, or the completeness-rule tail. The agents now EMIT the envelope these functions already require; the verifier changes are only (i) selection and (ii) scoping. The BRD carve-out (order 0 / icon ''), the documented_nodes order/icon rules, and the "≥1 non-verify artifact records completeness_gate" rule remain exactly as written (lines 41–168 unchanged except the loop head in §4(ii)).

### Sync the sibling PHASE_PATTERN

`tests/test_dryrun_elicit_compliance.py` defines its own copy of `PHASE_PATTERN` (line 13). It is unchanged (the naming contract is unchanged), but Slice 1 must not let it drift; no edit needed this change.

---

## 5. Dry-run alignment — `tests/conftest.py`

The double already emits the correct envelopes (`documented_nodes`, `brd_node`, `completeness_gate`). The ONLY format change is the canonical-LAST + sentinel wrapper so the double's files match the real-agent dual contract that the verifier now selects via `finditer[-1]`.

**Before**
```python
def _artifact_body(title: str, payload: dict) -> str:
    import json
    return f"# {title}\n\n```json\n{json.dumps(payload, indent=2)}\n```\n"
```

**After**
```python
def _artifact_body(title: str, payload: dict) -> str:
    import json
    from brain_ds.mcp.grounding import ARTIFACT_CONTRACT
    sentinel = ARTIFACT_CONTRACT["canonical_sentinel"]
    body = json.dumps(payload, indent=2)
    return (
        f"# {title}\n\n"
        "## Human-readable summary\n\n"
        f"_See the canonical payload below for the machine-checkable {title} envelope._\n\n"
        f"{sentinel}\n"
        f"```json\n{body}\n```\n"
    )
```
This proves the double exercises the SAME selection path: sentinel line + canonical block as the last fenced block. `write_artifact` is unchanged (it already names files `<phase>-<slug>-<ISO-date>.md`). Importing the sentinel from `grounding` keeps the double bound to the single source of truth.

**FakeDelegator needs no change** — it records prompts, it does NOT write artifacts (confirmed: `delegation.py` only builds prompt strings; artifact writing lives in `conftest.write_artifact`). `test_sub_agent_writes_only_to_elicit` asserts on `handoffs` prompts (`synthetic_source_path` present, `artifact` substring, forbidden terms absent) and on `written_files` — all still hold because the prompt strings and file paths are unchanged; only file BODY changed.

---

## 6. Agent prompt edits (both clients, byte-identical pairs)

Each executor agent gets a "Canonical payload contract" instruction. Add to BOTH `.claude/agents/brainds-<x>.md` and `prompts/brainds-<x>.md` (prose only — OpenCode tools come from the installer; `.claude` YAML tools edited only for connection-mapper, §7).

Shared instruction block (adapt the schema reference per phase):
> **Canonical payload (MANDATORY)**: write your `.elicit/<phase>-<slug>-<ISO-date>.md` as DUAL content — human-readable markdown PLUS, at the END of the file, the line `<!-- canonical-payload -->` immediately followed by ONE fenced ```json block matching `ARTIFACT_CONTRACT["artifacts"]["<phase>"]` from your grounding payload. It MUST be the LAST fenced json block. The verify gate parses only this block.

Per-agent specifics:

| Agent | Phase | Canonical schema to emit |
|---|---|---|
| `brainds-source-explorer` | `source-docs` | `{graph_id, documented_nodes:[{node_id,label,type,card_sections[]}]}` — wrap the card_sections array it produces today into a documented_nodes node (fixes D1). |
| `brainds-connection-mapper` | `map` | `{graph_id, documented_nodes, edges, completeness_gate}` — and WRITE the file (fixes D5, §7). |
| `brainds-brd-writer` | `brd` | `{graph_id, markdown, brd_node, completeness_gate?}` — add the canonical block to the markdown BRD it already writes (fixes D2). |

connection-mapper map-artifact write step (new step in its job list, both clients):
> After mapping, WRITE `.elicit/map-<slug>-<ISO-date>.md` (markdown receipt of structural + cross-cutting edges and the gap report) with the canonical `map` payload as the last fenced json block. This is IN ADDITION to the Engram receipt (`mem_save`). The `completeness_gate` you already obtain from `assess_completeness(graph_id)` is the cycle's canonical gate — record it here.

---

## 7. connection-mapper Write-tool cascade

| Target | Change | Reason |
|---|---|---|
| `.claude/agents/brainds-connection-mapper.md` | Add `- Write` to the `tools:` YAML list (after `mcp__plugin_engram_engram__mem_save` or near top, ordering irrelevant). | Claude Code grants tools per-agent; without Write it cannot create `.elicit/map-*.md`. |
| `prompts/brainds-connection-mapper.md` | Add the map-artifact write step (§6). No YAML tools block here. | OpenCode prompt prose. |
| `install-opencode.ps1` | **No change needed** — line 84 already sets `write = $true` for ALL sub-agents uniformly. | Confirmed in code: the sub-agent loop grants `read/write/engram` to every name in `$subagentNames`, which already includes `brainds-connection-mapper` (line 38). |
| `install-opencode.sh` | **Verify same uniform grant**; if it mirrors the `.ps1` per-agent write grant, no change. (Slice 1 task: confirm parity; edit only if `.sh` is NOT uniform.) | Cross-client parity. |
| `harness_check.py` | **No change** — it validates MCP entries + skills mirror only; it does NOT assert per-agent tool rosters. The CLAUDE.md `SUBAGENT_NAMES`/`CLAUDE_AGENT_FILES` reference is for a roster guard that does not currently assert tools. Rosters are unchanged (tool grant only, no new agent). | Confirmed via grep: no roster/tool assertion exists. |
| `AGENT_FLOW.md` | Note that connection-mapper now writes `.elicit/map-*.md` in the map stage. | Doc parity. |
| `DELEGATION_PROTOCOL.artifact_keys` | `map` is already in the `phases` list (line 752). Add a clarifying note that the connection-mapper owns the `map` elicit_file. No structural key change required. | Keep the protocol accurate. |

> Net: the Write grant is a ONE-LINE change in `.claude/agents/brainds-connection-mapper.md` plus prose; OpenCode is already covered by the uniform installer grant.

---

## 8. Golden-fixture CI guard (Slice 2)

Create committed golden artifacts that represent the REAL canonical format, validated with NO live LLM calls.

```
tests/fixtures/elicit/
  source-docs-golden-2026-06-14.md   # dual: markdown + sentinel + canonical block
  map-golden-2026-06-14.md
  brd-golden-2026-06-14.md
  verify-golden-2026-06-14.md        # gate PASS, empty findings
  README.md                          # non-phase → must be IGNORED
  scratch.md                         # non-phase → must be IGNORED
```

`tests/test_live_artifact_contract.py`:
```python
def test_golden_elicit_dir_passes_gate(tmp_path):
    # copy tests/fixtures/elicit/* into tmp_path
    findings = check_elicit_compliance(tmp_path)
    assert findings == []          # clean cycle, archive allowed

def test_golden_artifacts_match_contract():
    # each golden's last fenced json block has the required_keys from
    # ARTIFACT_CONTRACT["artifacts"][<phase>] — proves agents+golden+contract agree
    ...

def test_non_phase_files_are_ignored():
    # README.md and scratch.md present → still findings == []

def test_phase_named_broken_payload_is_critical(tmp_path):
    # write map-org-2026-06-14.md with broken JSON → CRITICAL
    # write brd-org-2026-06-14.md with no payload  → CRITICAL
```
This catches format-drift recurrence (the top risk) at CI with zero LLM/subprocess cost. The goldens double as living examples for agent authors and mirror the real `.elicit/source-docs-orders-db-*` shape (post-fix).

---

## 9. Drift-guard integration (summary)

- `ARTIFACT_CONTRACT` is discovered by `_discover_category2_constants` (UPPER_SNAKE, dict).
- It is NOT in `CATEGORY2_EXEMPT` → it is swept.
- It sweeps clean: only entity-ish literals are `"Unknown"` (single word) and `"BRD"` (all-caps) — neither matches the CamelCase-compound regex; validator names are snake_case.
- Slice 1 adds `test_artifact_contract_discovered_and_not_exempt` (mirror of the existing `test_pipeline_stages_discovered_and_not_exempt`) to lock the intent.
- Same-change rule honored: `grounding.py` + `skills/*/SKILL.md` + `.opencode/skills/*/SKILL.md` (byte-identical) + agent pairs all updated in Slice 1.

---

## 10. Slice boundaries & line estimates

### Slice 1 — gate blocker (PR 1) — ~250–280 lines
1. `ARTIFACT_CONTRACT` constant in `grounding.py` (~55) + inject into 3 composers + docstrings (~15).
2. Verifier: `_load_payload` finditer[-1] + sentinel const (~10); `check_elicit_compliance` scoping branch (~6).
3. `conftest.py` `_artifact_body` dual wrapper (~12).
4. Agent prose: source-explorer, brd-writer, connection-mapper canonical instruction + map-write step — `.claude/agents/*` and `prompts/*` (6 files, ~50).
5. connection-mapper `.claude` YAML `- Write` (1 line) + `install-opencode.sh` parity confirm.
6. Cross-client: `skills/*/SKILL.md` + `.opencode/skills/*/SKILL.md` dual-contract note (byte-identical), `AGENT_FLOW.md`, `DELEGATION_PROTOCOL` note (~40).
7. RED tests (§11).

### Slice 2 — golden-fixture CI guard + live acceptance (PR 2) — ~140–160 lines
1. `tests/fixtures/elicit/*` golden artifacts (4 phase + README + scratch).
2. `tests/test_live_artifact_contract.py` (4 tests).
3. Re-run the live cycle on `live-e2e-synthetic`; confirm verify gate now PASSES; update the `.elicit/source-docs-*`, `brd-*`, add `map-*`, refresh `verify-*`.

**Combined > 400 lines → two chained PRs recommended under `delivery=ask-on-risk`.** Slice 1 must land and pass before Slice 2 (goldens depend on the final contract). The proposal flagged this; orchestrator should ASK before apply.

---

## 11. Test plan (RED → GREEN, strict TDD)

### Slice 1 RED tests (write first)
| Test file | Test | Asserts (currently RED) |
|---|---|---|
| `tests/test_grounding_drift_guard.py` | `test_artifact_contract_discovered_and_not_exempt` | `ARTIFACT_CONTRACT` in discovered set, not in `CATEGORY2_EXEMPT`. |
| `tests/test_mcp_grounding.py` | `test_artifact_contract_in_all_three_composers` | `artifact_contract` key present in elicit/map/brd context payloads with the 4 artifact types. |
| `tests/test_elicit_compliance.py` (new or extend) | `test_selects_last_fenced_block` | file with an illustrative json array block THEN canonical envelope → payload = canonical (not the array). |
| ″ | `test_non_phase_file_skipped` | README.md / scratch.md produce NO finding. |
| ″ | `test_phase_named_broken_payload_critical` | `map-org-2026-06-14.md` broken + `brd-org-...` no-payload → 2 CRITICAL. |
| `tests/test_dryrun_elicit_compliance.py` | extend existing | double's `_artifact_body` now emits sentinel + canonical-last; `check_elicit_compliance` over the dry-run dir returns `[]`; existing `test_sub_agent_writes_only_to_elicit` STILL passes unchanged. |
| `tests/test_mcp_claude_config.py` (if it asserts agent tools) / new | `test_connection_mapper_has_write_tool` | `.claude/agents/brainds-connection-mapper.md` tools list contains `Write`. |

### Slice 2 RED tests
| Test file | Test | Asserts |
|---|---|---|
| `tests/test_live_artifact_contract.py` | `test_golden_elicit_dir_passes_gate` | goldens → `findings == []`. |
| ″ | `test_golden_artifacts_match_contract` | each golden's last block has `required_keys`. |
| ″ | `test_non_phase_files_are_ignored` | README/scratch present, still clean. |
| ″ | `test_phase_named_broken_payload_is_critical` | broken phase file → CRITICAL. |

---

## 12. ADR-style decisions

**ADR-1 — Single contract constant in grounding.py (not per-agent prose).**
Chosen: `ARTIFACT_CONTRACT` Category-2 dict, injected into 3 composers. Rejected: duplicating the schema in each agent .md — drifts across clients, no drift-guard coverage. Rationale: grounding.py is the cross-client source of truth and is drift-guarded.

**ADR-2 — Positional last-block selection + advisory sentinel.**
Chosen: `finditer[-1]` parse + `<!-- canonical-payload -->` documented-but-not-hard-required. Rejected: sentinel-anchored parse (hard fail if comment missing) — too brittle for real agents; rejected: first-block parse — illustrative examples would shadow the canonical envelope. Rationale: tolerant input, strict structure.

**ADR-3 — Skip non-phase files, CRITICAL on phase-named-but-broken.**
Chosen: scope by PHASE_PATTERN at the loop head. Rejected: per-cycle subdir `.elicit/<cycle>/` (deferred, separate blast radius) and rejected: lowering README to a non-finding by name allowlist. Rationale: fixes D3 without lowering the bar and without the subdir migration.

**ADR-4 — completeness_gate owner = map artifact.**
Chosen: connection-mapper records it (it already calls `assess_completeness`). source-docs/brd MAY also carry it. Kept the "≥1 non-verify artifact records it" rule. Rationale: the map stage is where the gate is computed; no rule weakening.

**ADR-5 — connection-mapper gains Write (tool grant only, no new agent).**
Chosen: add Write to `.claude` YAML; OpenCode already uniform. Rejected: a new map-writer sub-agent — out of scope, more roster churn. Rationale: minimal blast radius.

---

## 13. Risks & assumptions

- **R1 (top)**: format-drift recurrence — real agents emit a new shape again. Mitigation: golden-fixture CI guard (Slice 2) fails on regression with no LLM calls.
- **R2**: combined > 400 lines → chained PRs; if Slice 1 alone creeps past 400, re-flag ask-on-risk before apply.
- **R3 (assumption)**: `install-opencode.sh` mirrors the `.ps1` uniform `write=true` sub-agent grant. Verify in Slice 1; edit only if not uniform.
- **R4 (assumption)**: no existing test asserts per-agent tool rosters from `harness_check.py` (confirmed by grep). If a roster guard is added later it must accept connection-mapper's Write.
- **R5**: `test_mcp_grounding.py` may assert exact key COUNTS per composer; adding `artifact_contract` bumps 14→15 / 12→13 / 10→11. Update those count assertions in Slice 1.
