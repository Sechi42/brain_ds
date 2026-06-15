# Exploration: brain_ds Harness/Orchestrator Flow Hardening

## Current State

The brain_ds project has a mature but unhardened SDD-like orchestration flow:

1. **Ontology** (`brain_ds/ontology/`) — 13 EntityTypes + 12 RelationshipTypes, all enum-derived with supertypes, colors, expected sections
2. **MCP Grounding Harness** (`brain_ds/mcp/grounding.py`) — three categories: Category-1 (runtime-derived, zero drift), Category-2 (hand-maintained skill prose mirrors), Category-3 (live workspace scoping)
3. **Drift Guard** (`tests/test_grounding_drift_guard.py`) — asserts Category-2 constants stay in sync with EntityType enum; `ELICIT_EXEMPT_TYPES` includes `Project`, `Risk`, `Unknown`
4. **Skills** — 3 brain_ds-specific skills (`elicit-context`, `map-connections`, `generate-brd`) with shared contract in `grounding.py`
5. **Completeness Gate** (`brain_ds/mcp/completeness.py`) — pre-mapping/before BRD: assess graph hollow => `elicit`, underspecified => `document`, OK => `proceed_with_gaps`
6. **UI** (`brain_ds/ui/`) — FastAPI + vanilla TS, BRD panel reads `brd-{graphId}` node, render contract has NO e2e coverage
7. **Connectors** (`brain_ds/connectors/`) — SQLite (read-only, PRAGMA query_only), CSV (utf-8-sig), no secrets handling
8. **No `.elicit/` directory** exists yet — first SDD-like cycle will create it

## Findings per Investigation Area

### 1. BRD Graph Persistence Contract (generate-brd/SKILL.md)

**Evidence**: generate-brd/SKILL.md lines 146-171, grounding.py `BRD_GRAPH_PERSISTENCE_CONTRACT` lines 626-662, brd-panel.ts lines 51-69

The contract is fully specified:
- `node_id = "brd-<org-slug>"` — UI panel looks this up exactly
- `type: "Unknown"` — intentional, not a domain entity
- Single `card_sections[0]` with `title: "Contenido"`, `order: 0`, `icon: ""`, full markdown content
- Wikilinks `[[node label]]` mandatory for graph entity references
- `update_node` is upsert-safe; emits live node event

**Status**: ✅ Contract is well-defined, mirror exists in grounding.py Category-2 constants.

### 2. brainds-docs Conflict with BRD Persistence

**Evidence**: brainds-docs/SKILL.md lines 54-69, generate-brd/SKILL.md lines 154-164

| Rule | brainds-docs says | BRD persistence uses | Conflict? |
|------|-------------------|---------------------|-----------|
| `order` | Monotonically increasing, starts at **1** | `order: 0` | ⚠️ YES — 0 vs 1 |
| `icon` | From specific list: info, database, table, etc. | `icon: ""` (empty string) | ⚠️ YES — empty not in list |
| Sections structure | Entity-type section map per type | single "Contenido" with raw BRD | Expected exception |

brainds-docs trigger includes "BRD content" (line 5 of trigger description). If an agent applies brainds-docs validation to the BRD node, it will flag `order: 0` and `icon: ""` as violations.

**Verdict**: Real conflict. Needs either:
- An explicit exception carve-out in brainds-docs: "BRD persistence nodes are exempt from order/icon rules"
- Or a rule in generate-brd: "brainds-docs validation does NOT apply to the BRD node"
- Or raise `order` to 1 and give a valid icon (less desirable, changes established convention)

**Risk**: HIGH — an agent applying brainds-docs rules to a BRD save will reject or "correct" the persistence format, breaking the UI contract.

### 3. "Unknown" Type in Ontology and Drift Guard

**Evidence**: entity_types.py lines 30-31, 58-64, 83; drift guard lines 32-38; completeness.py lines 30-32

- `EntityType.UNKNOWN` exists as a valid member with value `"Unknown"`, supertype `"problem"`, empty expected sections
- `from_string()` defaults to `UNKNOWN` for None/empty/unknown (line 54-59): `if value is None: return cls.UNKNOWN`
- Drift guard: `ELICIT_EXEMPT_TYPES` includes `"Unknown"` (line 37) — explicitly exempt from question bank
- Drift guard test `test_every_entity_type_is_elicited_or_exempt()`: passes because Unknown is listed in exempt
- Completeness: `ASSESSED_TYPES` explicitly EXCLUDES `UNKNOWN` (line 30-32) — Unknown nodes are not counted as missing

**Verdict**: ✅ No contradiction. Unknown is a valid EntityType, explicitly exempted from elicitation and completeness assessment. The BRD using type "Unknown" is the intended pattern. However, `from_string` defaulting to Unknown for any unrecognized input means a typo in entity type never fails — it silently falls back to Unknown, which could hide data-entry errors.

### 4. UI BRD Rendering and Render-Contract Test Gap

**Evidence**: brd-panel.ts (full 471 lines), markdown-mini.ts (full 133 lines), api/routes.py lines 21-92

BRD panel flow:
1. Mount: checks `detailIndex` for `brd-{graphId}` node → if not found, fetches `GET /api/nodes?graph_id=...`
2. Finds section with `order === 0 || title === 'Contenido'` → extracts content
3. Renders summary panel: extracts Status, Organization, section count, Executive Summary preview
4. "Abrir BRD completo" button → `openFullReader()` → `selectAndReveal(brdNodeId())` → opens center markdown reader
5. Editor mode: textarea → `POST /api/nodes` (new) or `PATCH /api/nodes/{brdNodeId}` (update)
6. Wikilinks: `renderWikilinks()` regex replaces `[[label]]` → HTML link with `data-wikilink-target`
7. Freshness chip: compares brd modified_at vs all other nodes

**Render-contract test gap**: NO existing test verifies:
- That the BRD panel loads and renders content from a `brd-{graphId}` node
- That wikilinks in BRD content resolve correctly
- That the freshness chip renders correctly
- That save/create round-trips work end-to-end
- That the `extractPreview()` function correctly parses the Executive Summary from the 14-section markdown

Only the `markdown-mini.ts` renderer has implicit tests (it powers the reader too), but no BRD-specific e2e exists.

### 5. Grounding Harness Category-2 Constants That Mirror Skill Prose

**Evidence**: grounding.py lines 75-740

Constants that mirror skill prose and need updating when skills change:

| Constant | Lines | Source Skill | What It Mirrors |
|----------|-------|-------------|-----------------|
| `QUESTION_BANK` | 76-125 | elicit-context | Elicitation questions per entity type |
| `ORG_SLUG_RULES` | 128-140 | elicit-context | Slug normalization rules |
| `NODE_ID_FORMAT` | 143-146 | elicit-context | Node id format string |
| `NODE_WRITE_TEMPLATES` | 149-281 | elicit-context | update_node templates per entity type |
| `ELICIT_WORKFLOW` | 284-323 | elicit-context | 6-step persistence workflow |
| `MAP_RETRIEVAL_CONTRACT` | 326-332 | map-connections | Retrieval path for mapping |
| `MAP_RAG_WORKFLOW` | 335-362 | map-connections | 5-step RAG workflow |
| `CONNECTION_RULES` | 366-398 | map-connections | Deterministic connection rules + strength labels |
| `TWO_PHASE_MAPPING` | 403-438 | map-connections | Phase 1 + Phase 2 structure |
| `COMPLETENESS_GATE` | 444-465 | map-connections | Pre-mapping gate rules |
| `BRD_RETRIEVAL_CONTRACT` | 468-473 | generate-brd | Typed vs search retrieval |
| `BRD_SECTION_ORDER` | 477-492 | generate-brd | 14-section order |
| `SECTION_RULES` | 495-535 | generate-brd | KPI/Solution section rules + NEEDS_DATA |
| `COMPLETENESS_MATRIX_TEMPLATE` | 538-558 | generate-brd | Status values + fingerprint order |
| `BRD_GRAPH_PERSISTENCE_CONTRACT` | 626-662 | generate-brd | update_node template + rules |
| `BRD_STRICT_MODE` | 667-686 | generate-brd | --strict gate rules |
| `DELEGATION_PROTOCOL` | 692-740 | brainds-orchestrator | Orchestrator flow, session setup, artifacts |
| `SOURCE_EXPLORATION_CONTRACT` | 589-620 | elicit-context + map | Exploration workflow + tool reference |
| `WORKSPACE_PROTOCOL` | 566-584 | Harness | Workspace scope rules |

**Drift guard** currently only tests:
- `QUESTION_BANK` keys match EntityType values
- `NODE_WRITE_TEMPLATES` type keys match EntityType values
- `COMPLETENESS_MATRIX_TEMPLATE.dataset_fingerprint_order` matches EntityType

Drift guard does NOT test:
- BRD_SECTION_ORDER / SECTION_RULES / BRD_GRAPH_PERSISTENCE_CONTRACT consistency
- WORKSPACE_PROTOCOL / DELEGATION_PROTOCOL / SOURCE_EXPLORATION_CONTRACT
- TWO_PHASE_MAPPING / CONNECTION_RULES / MAP_RAG_WORKFLOW / COMPLETENESS_GATE

### 6. Data Source Exploration / MCP Source Exploration

**Evidence**: mcp/tools.py lines 551-711, connectors/sqlite_connector.py (full), security.py (full)

- `explore_source` (3-level: source→containers→tables with schema+preview)
- `query_source` (SELECT-only, capped at 200 rows, regex-forbidden keywords, PRAGMA query_only, mode=ro URI)
- `list_source_connections` (discovers Data Source nodes with connection descriptors)
- Path sandbox: `validate_path_within_root` — strict `..` traversal guard + `os.path.realpath` prefix check
- 3-level `connection` setup: `{kind: "sqlite"|"csv", path: "<project-relative>"}` stored in `details.connection`

**Secret handling**: NONE. No support for:
- Environment variable references in paths
- API keys or tokens for cloud sources
- Encrypted configuration
- Credentials in connection strings (PRAGMA key for encrypted SQLite, etc.)
- Google Sheets: explicitly delegated to MCP Google Drive tools (not handled in connectors)

### 7. Existing `.elicit` Structure

**Evidence**: No `.elicit/` directory exists in the project.

The `DELEGATION_PROTOCOL` in grounding.py (lines 698-703) defines the contract:
```python
"session_setup": "At the start of a session...ask the user ONCE how to store...'.elicit' (project-local .elicit/ folder)..."
"elicit_file": ".elicit/<phase>-<slug>-<ISO-date>.md"
```

But `.elicit/` has never been created. For this change, we're creating:
```
.elicit/changes/brainds-harness-orchestrator-flow-hardening/exploration.md
```

The `.elicit/` folder is referenced as an optional artifact store alongside Engram but has no existing structure or files. For brain_ds SDD cycles, the convention should follow what the DELEGATION_PROTOCOL defines.

### 8. brain_ds-Specific SDD Flow Design

**Evidence**: grounding.py DELEGATION_PROTOCOL lines 692-740, completeness.py lines 30-81, score/similarity.py TYPE_PAIR_SUGGESTIONS lines 21-72

The proposed brain_ds SDD flow:

```
Session Start
  ├── Ask user: artifact storage (engram / .elicit / both)
  ├── Resolve org (--org > session/active-org > default)
  │
  ├── [Elicit Loop]
  │   ├── DELEGATE to elicit sub-agent
  │   │   ├── run_elicit() → get grounding context
  │   │   ├── Question bank Q&A (max 5 per session, prioritize Data Source)
  │   │   ├── Completeness gate: follow-up until fields are complete
  │   │   ├── Persist to SQLite: update_node + add_edge
  │   │   └── Persist to Engram: session narrative
  │   └── suggest_connections for each new node
  │
  ├── [Source Exploration Loop]
  │   ├── 1. SCOPE: read-only magnitude scan (containers, tables, row estimates)
  │   ├── 2. PLAN: split into non-overlapping sections (by table/sheet/endpoint)
  │   ├── 3. DOCUMENT: explore assigned sections → structured findings
  │   └── 4. CONSOLIDATE + PUSH: update_node (card_sections) + add_edge
  │
  ├── [Map Connections]
  │   ├── assess_completeness() → gate
  │   ├── Phase 1 (structural): org→dept→role→datasource edges
  │   └── Phase 2 (cross-cutting): KPI/Problem/Solution/Decision/Risk edges
  │
  ├── [BRD Gate]
  │   ├── assess_completeness() → gaps report
  │   ├── If strict+incomplete: refuse, return actionable gap list
  │   ├── If permissive or complete: compose 14-section BRD
  │   └── --save: persist to graph (card_sections) + Engram mirror + ADR
  │
  └── [Archive]
      ├── Sync delta specs to main specs
      └── Report: what was created, what changed, outstanding gaps
```

Key design decisions:
- All sub-agents receive **artifact references** (topic keys/file paths), never full content
- Sub-agents read their inputs directly from the artifact store
- `DELEGATION_PROTOCOL.handoff_rule` enforces this: "Pass artifact references...never full content"
- Return contract: status + executive_summary + artifacts + next_recommended + risks
- `skill_scope`: Only brain_ds-owned skills, never cross-project skill leakage

## Approaches

### Approach 1: Fix Identified Issues Only (Minimal)

Fix the immediate issues discovered in this exploration:
- Add brainds-docs exception for BRD persistence nodes
- Add BRD render-contract e2e test to brd-panel.spec.ts
- Hardcode `order: 1` with valid icon or document exemption

**Pros**: Fast, low-risk, addresses the most urgent conflicts  
**Cons**: Doesn't address the broader harness hardening, no SDD flow formalization  
**Effort**: Low

### Approach 2: Full Harness + Flow Hardening (Recommended)

All of Approach 1 plus:
- Add drift guard coverage for ALL Category-2 constants (not just question bank + templates + fingerprint)
- Add BRD render-contract e2e test suite
- Add brainds-docs SKILL.md trigger clarification for BRD exemption
- Formalize `.elicit/` structure per DELEGATION_PROTOCOL
- Add SDD flow documentation grounded in actual DELEGATION_PROTOCOL (no duplicating orchestrator)

**Pros**: Complete coverage, prevents future drift, formalizes the SDD cycle  
**Cons**: More work, touches multiple files requiring coordinated changes  
**Effort**: Medium

### Approach 3: Refactor to Eliminate Category-2 Drift

Replace all Category-2 hand-maintained constants with runtime-derivation from ontology/skill-registry content:
- Derive BRD_SECTION_ORDER, CONNECTION_RULES, etc. from the skill registry at startup
- Store skill-prose constants in a JSON file read at runtime
- Remove drift guard entirely (Category-2 becomes Category-1 — zero drift by construction)

**Pros**: Eliminates drift permanently, simpler maintenance  
**Cons**: High-effort refactor, changes the grounding architecture, risk of breaking MCP tool output shape  
**Effort**: High

## Recommendation

**Approach 2** — Full Harness + Flow Hardening. 

The project already has the foundational structure (Category-1/2/3, completeness gate, two-phase mapping, drift guard). What's missing is:
1. Coverage of the drift guard (only tests 3 of ~20 Category-2 constants)
2. A BRD render-contract test (critical path has zero e2e coverage)
3. Documentation of the brainds-docs / BRD type conflict
4. Formalization of the `.elicit/` structure
5. An explicit diagram of the SDD flow grounded in actual code constants

This is the right effort/value tradeoff: medium effort, eliminates the blind spots that WILL cause production bugs (an agent applying brainds-docs rules to a BRD save is a matter of when, not if).

## Risks

1. **HIGH** — brainds-docs / BRD persistence conflict: any agent that reads brainds-docs and validates a BRD `update_node` will reject `order: 0` and/or `icon: ""`. This WILL break `/generate-brd --save` in any session where both skills are loaded.

2. **MEDIUM** — Untested BRD render contract: the 471-line BRD panel (wikilink resolution, freshness chip, save round-trip) has zero e2e coverage. A backend store change or API route refactor can silently break BRD visibility without any test catching it.

3. **LOW** — `EntityType.from_string()` silent fallback to Unknown: any typo in entity type never reveals itself. This is an existing design choice but worth documenting.

4. **LOW** — No secrets handling in connectors: SQLite connector could accept an API key as a path if someone puts credentials in `details.connection.path`. The path sandbox prevents traversal but not credential leakage.

5. **LOW** — Category-2 constants outgrowing drift guard: 18+ hand-maintained constants, drift guard covers 3. Adding a new entity type or skill changes could silently break the grounding harness.

## Ready for Proposal

**Yes** — this exploration has enough evidence to move to the proposal phase. The immediate risks (brainds-docs conflict, missing BRD render test, partial drift guard) are clearly identified and actionable. The orchestrator should proceed with `sdd-propose`.

## Files Examined

- `.opencode/skills/generate-brd/SKILL.md` — full BRD persistence contract and rules
- `.opencode/skills/brainds-docs/SKILL.md` — generic card_sections rules that conflict with BRD
- `brain_ds/ontology/entity_types.py` — EntityType enum, Unknown definition
- `brain_ds/ontology/relationship_types.py` — RelationshipType enum, BASE_WEIGHTS
- `brain_ds/ontology/graph_model.py` — Node, Edge, CardSection, Graph dataclasses
- `brain_ds/ontology/__init__.py` — public API
- `brain_ds/mcp/grounding.py` — full 831-line harness with Category-1/2/3
- `brain_ds/mcp/tools.py` — TOOL_REGISTRY with all MCP tool implementations
- `brain_ds/mcp/security.py` — TOOL_SCHEMAS, validate_card_sections, path validation
- `brain_ds/mcp/completeness.py` — assess_graph_completeness logic
- `brain_ds/scoring/engine.py` — ScoringEngine with factor_weights
- `brain_ds/scoring/similarity.py` — suggest_connections, TYPE_PAIR_SUGGESTIONS
- `brain_ds/connectors/__init__.py` — read-only connector API
- `brain_ds/connectors/sqlite_connector.py` — read-only SQLite with PRAGMA query_only
- `brain_ds/api/routes.py` — FastAPI routes for nodes/edges/events
- `brain_ds/ui/server.py` — FastAPI/uvicorn server
- `brain_ds/ui/render_context.py` — build_render_context with detail_index
- `brain_ds/ui/template_renderer.py` — HTML template rendering
- `brain_ds/ui/src/panels/brd-panel.ts` — BRD panel TypeScript (471 lines)
- `brain_ds/ui/src/panels/markdown-mini.ts` — custom markdown renderer
- `brain_ds/ui/e2e/smoke.spec.ts` — existing smoke tests
- `brain_ds/ui/e2e/ecosystem.spec.ts` — ecosystem validation tests
- `tests/test_grounding_drift_guard.py` — drift guard with ELICIT_EXEMPT_TYPES
