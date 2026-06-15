# Tasks: brain_ds Harness / Orchestrator Flow Hardening

> Hybrid store: this file + Engram `sdd/brainds-harness-orchestrator-flow-hardening/tasks`.
> Reads design (#2120) and all 5 delta specs. Covers 4 chained PRs (slices).
> Strict TDD is ACTIVE — every implementation task with testable behavior is
> preceded by its failing-test task. sdd-apply MUST read skill-creator (registry
> obs #154) before editing any SKILL.md. Mirrors `skills/*` ↔ `.opencode/skills/*`
> must be kept byte-identical after every skill edit.

---

## Legend

- `[SKILL-EDIT]` — task edits one or more SKILL.md files; sdd-apply must invoke
  skill-creator (Skill tool / registry obs #154) BEFORE making the change and keep
  `skills/*` ↔ `.opencode/skills/*` mirrors byte-identical.
- `[HARNESS]` — task touches the harness-maintenance contract (CLAUDE.md §Harness
  maintenance): tool count (must stay 22), drift guards, BRD UI parity.
- `[TDD-FIRST]` — write the failing test BEFORE the implementation code.
- `→ depends on` — hard dependency; the listed task must be complete and green first.
- `// parallel` — tasks marked parallel at the same level can be done concurrently
  once their shared prerequisite is met.

---

## Slice 1 — BRD contract + tests (URGENT, no dependencies)

**PR1 target: ~280 lines changed.**
All Slice 1 tasks are self-contained. Tasks 1.1–1.3, 1.4–1.5, and 1.6–1.8 are
independent sub-groups that can be worked in parallel once the slice starts.

---

### Group A — brainds-docs carve-out + recurrence guard (D1 + D2)

#### Task 1.1 [x] [TDD-FIRST] Write failing recurrence-guard test
- **File**: `tests/test_mcp_grounding.py`
- **What**: Add `test_brainds_docs_brd_carveout_matches_contract()` that:
  1. Reads the content of both `skills/brainds-docs/SKILL.md` and
     `.opencode/skills/brainds-docs/SKILL.md`.
  2. Asserts each contains the literal strings `order: 0` and `icon: ""` (or
     equivalent pattern marking the BRD carve-out).
  3. Imports `BRD_GRAPH_PERSISTENCE_CONTRACT` from `brain_ds.mcp.grounding` and
     asserts `card_sections[0]["order"] == 0` and `card_sections[0]["icon"] == ""`.
  4. Asserts that the values in the skill text and the contract values are equal.
- **Spec**: `brd-persistence-contract/spec.md` §BRD persistence contract recurrence guard
- **AC**: 1.2
- **Accepts failure** until Task 1.2 lands.

#### Task 1.2 [x] [SKILL-EDIT] Add BRD/Unknown carve-out to brainds-docs skill
- **Files**: `skills/brainds-docs/SKILL.md`, `.opencode/skills/brainds-docs/SKILL.md`
- **What**: In the `card_sections Format` rules block, add an explicit carve-out
  clause stating:
  - BRD nodes (`node_id` starting with `brd-`, `type = "Unknown"`) are exempt
    from the generic `order ≥ 1` and non-empty icon rules.
  - Their shape is governed solely by `BRD_GRAPH_PERSISTENCE_CONTRACT` (order: 0,
    icon: "").
  - Reference the contract by name so future authors know the source of truth.
- **Also update**: `.atl/skill-registry.md` compact rule for `brainds-docs` (the
  "order is monotonically increasing from 1" line must acknowledge the BRD
  exception with a parenthetical or a note).
- **SKILL-EDIT note**: invoke skill-creator (Skill tool / registry obs #154) first;
  ensure frontmatter (name/description/license/metadata.author/metadata.version)
  is preserved; keep `skills/*` ↔ `.opencode/skills/*` byte-identical after edit.
- **Spec**: `brd-persistence-contract/spec.md` §brainds-docs carve-out for BRD/Unknown nodes
- **AC**: 1.1, 1.5
- **→ depends on**: Task 1.1 (test must be red first)
- **Harness**: touch CLAUDE.md "Harness maintenance" — skill prose mirror rule.

#### Task 1.3 [x] [HARNESS] Verify recurrence-guard test goes green
- **What**: Run `uv run pytest tests/test_mcp_grounding.py -k test_brainds_docs_brd_carveout_matches_contract`.
  Confirm green. Also confirm pre-existing BRD UI parity test (`test_brd_graph_persistence_contract_matches_ui_panel_convention`)
  stays green — both guards must pass together.
- **→ depends on**: Task 1.2

---

### Group B — Drift guard generalization (D3)

#### Task 1.4 [x] [TDD-FIRST] Write failing meta-test for Category-2 constant coverage
- **File**: `tests/test_grounding_drift_guard.py`
- **What**: Add `test_every_category2_constant_is_classified()` that:
  1. Uses `inspect`/`dir` to discover all module-level `dict` and `list`
     assignments in `brain_ds.mcp.grounding` whose names match
     `UPPER_SNAKE_CASE` (regex `^[A-Z][A-Z0-9_]+$`).
  2. Asserts every discovered name is either: (a) swept by the existing
     entity-name guard logic, OR (b) listed in the `CATEGORY2_EXEMPT` set
     (which does not exist yet — test is red).
  3. On failure, names the unclassified constant and instructs the author to
     add it to the swept set or to `CATEGORY2_EXEMPT` with a rationale.
- **Spec**: `harness-drift-guard/spec.md` §Category-2 drift guard enumerates every constant
- **AC**: 1.4

#### Task 1.5 [x] [HARNESS] Implement reflection sweep + CATEGORY2_EXEMPT registry
- **File**: `tests/test_grounding_drift_guard.py`
- **What**:
  1. Add a `CATEGORY2_EXEMPT` set with one-line rationale comments for every
     module-level constant in `grounding.py` that legitimately contains no
     entity-name-shaped tokens (e.g. `BRD_SECTION_ORDER`, `SECTION_RULES`
     entries without entity tokens, UI layout constants).
  2. Implement `_sweep_constant(name, value)` that walks nested str/list/dict
     and flags any token matching an entity-name shape (Title-case word, ≥8 chars,
     matching existing `EntityType.values`) that is NOT a real `EntityType.value`.
     Reuse existing `_entity_values()` helper.
  3. Wire sweep into the guard: for every discovered constant not in
     `CATEGORY2_EXEMPT`, run `_sweep_constant` and assert no drift tokens found.
  4. The meta-test from Task 1.4 must now pass.
  5. Add at least one smoke "stale entity name is caught" test:
     `test_sweep_catches_stale_entity_name()` asserting `_sweep_constant`
     returns a non-empty result for a crafted dict with a `"StaleEntity"` value.
- **Spec**: `harness-drift-guard/spec.md` §Sweep detects entity-name-shaped tokens,
  §Drift guard exits non-zero on any drift
- **AC**: 1.4
- **→ depends on**: Task 1.4

#### Task 1.6 [x] Verify drift-guard CI gate
- **What**: Run `uv run pytest tests/test_grounding_drift_guard.py`. All tests
  including the new meta-test and smoke test must be green. Confirm process exits
  non-zero when a synthetic stale token is injected (can be a temporary monkey-patch
  in the test itself — no production change needed).
- **→ depends on**: Task 1.5

---

### Group C — BRD render-contract e2e (Playwright)

#### Task 1.7 [x] [TDD-FIRST] Write failing Playwright e2e spec for BRD panel
- **File**: `brain_ds/ui/e2e/brd-panel.spec.ts` (new file)
- **What**: Scaffold three test scenarios (all initially failing or skipped):
  1. `wikilinks resolve to navigable node links` — given a persisted BRD node
     whose content has `[[EntityLabel]]`, assert rendered DOM has `<a>` pointing
     to the entity's node id and does NOT contain raw `[[` syntax.
  2. `freshness chip is visible` — given a BRD node with known `updated_at`,
     assert panel shows a chip whose text matches the value in the metadata region.
  3. `save round-trip via PATCH /api/nodes/:id` — trigger save from panel UI;
     assert PATCH is issued; re-fetch node; assert `card_sections[0]` still has
     `order == 0`, `icon == ""`, `title == "Contenido"`.
- **Spec**: `brd-persistence-contract/spec.md` §BRD render-contract end-to-end
- **AC**: 1.3
- **HARNESS**: touches BRD UI panel contract — see CLAUDE.md §BRD panel convention.

#### Task 1.8 [x] Implement / fix BRD panel render contract to make e2e green
- **Files**: `brain_ds/ui/src/panels/brd-panel.ts` (and supporting modules as
  needed: `markdown-mini.ts`, `brd-panel.spec.ts` fixture data, Playwright config)
- **What**: Ensure the three scenarios in Task 1.7 pass:
  - Wikilink `[[Label]]` / `[[Label|display]]` renders as `<a href="#node-id">display</a>`.
  - Freshness chip reads `updated_at` and renders human-readable text in the
    metadata region.
  - Save via PATCH `/api/nodes/:id` does not corrupt `card_sections[0]`; panel
    re-renders without a hard reload.
- **→ depends on**: Task 1.7 (spec must exist and be failing first)
- **HARNESS**: keep `BRD_GRAPH_PERSISTENCE_CONTRACT` in grounding.py consistent;
  `test_brd_graph_persistence_contract_matches_ui_panel_convention` must stay green.

#### Task 1.9 [x] Run full Slice 1 suite and assert green gate
- **What**: `uv run pytest tests/test_mcp_grounding.py tests/test_grounding_drift_guard.py`
  + `npx playwright test brain_ds/ui/e2e/brd-panel.spec.ts` + `brain_ds check`.
  All must pass. Tool count still 22.
- **→ depends on**: Tasks 1.3, 1.6, 1.8

---

## Slice 2 — `.elicit/` lifecycle + archive + flow docs [depends on Slice 1 being merged]

**PR2 target: ~220 lines changed.**
Tasks 2.1–2.3 and 2.4–2.5 can be worked in parallel once Slice 1 is merged.

---

### Group A — .elicit/ lifecycle document + guard (D4)

#### Task 2.1 [x] [TDD-FIRST] Write failing lifecycle naming/schema test
- **File**: `tests/test_elicit_lifecycle.py` (new)
- **What**: Add `test_elicit_naming_pattern()` that:
  1. Collects every `.md` file directly under `.elicit/` (non-recursive, excluding
     `changes/` subdirectory).
  2. Asserts each name matches `^(elicit|source-exploration|source-docs|map|brd)-[a-z0-9_-]+-\d{4}-\d{2}-\d{2}\.md$`.
  3. On failure, names the offending file.
  - Also add `test_lifecycle_doc_ownership_table_consistent()` that reads
    `.elicit/README.md` (doesn't exist yet — test is red) and asserts each of the
    5 phases has a documented owner agent that is one of the 6 known brain_ds agents.
- **Spec**: `elicit-artifact-lifecycle/spec.md` §.elicit/ structure mirrors DELEGATION_PROTOCOL
- **AC**: 2.1

#### Task 2.2 [x] Create .elicit/README.md (lifecycle document)
- **File**: `.elicit/README.md` (new)
- **What**: Document:
  - Layout: `.elicit/<phase>-<org-slug>-<ISO-date>.md` for active cycles.
  - Allowed phases: `elicit`, `source-exploration`, `source-docs`, `map`, `brd`.
  - Per-phase write ownership table (5 phases × owner sub-agent, matching
    `elicit-artifact-lifecycle/spec.md` §per-sub-agent write ownership).
  - Archive procedure: "Move all phase files for a completed cycle under
    `.elicit/changes/<change-name>/`. A cycle is completed when a BRD is written
    OR the orchestrator explicitly closes the cycle."
  - Note that archived files retain their original name (byte-identical move).
  - Grounded in: `DELEGATION_PROTOCOL.artifact_keys` (cite by constant name).
- **Spec**: `elicit-artifact-lifecycle/spec.md` (all requirements)
- **AC**: 2.1
- **→ depends on**: Task 2.1

#### Task 2.3 [x] Verify lifecycle tests green
- **What**: `uv run pytest tests/test_elicit_lifecycle.py`. Both tests must pass.
- **→ depends on**: Task 2.2

---

### Group B — SDD flow document (D4 continued)

#### Task 2.4 [x] [TDD-FIRST] Write failing flow-document guard test
- **File**: `tests/test_elicit_lifecycle.py` (add to same file)
- **What**: Add `test_sdd_flow_doc_references_delegation_protocol_constants()` that:
  1. Reads `docs/SDD_FLOW.md` (doesn't exist yet — test is red).
  2. Asserts each of the 6 strings appears at least once:
     `role`, `session_setup`, `artifact_keys`, `handoff_rule`,
     `source_exploration_flow`, `skill_scope`.
- **Spec**: `elicit-artifact-lifecycle/spec.md` §flow document grounded in DELEGATION_PROTOCOL
- **AC**: 2.2
- **// parallel with Task 2.1**

#### Task 2.5 [x] Create docs/SDD_FLOW.md
- **File**: `docs/SDD_FLOW.md` (new)
- **What**: Human-readable description of the SDD/orchestration flow. MUST:
  - Reference each DELEGATION_PROTOCOL key by its constant name: `role`,
    `session_setup`, `artifact_keys`, `handoff_rule`, `source_exploration_flow`,
    `skill_scope`.
  - Include a sub-agent sequence diagram (markdown, not Mermaid required) matching
    the data flow in design §Data Flow.
  - Include the `.elicit/` phase → owner table (consistent with `.elicit/README.md`).
  - Mention the archive lifecycle.
- **→ depends on**: Task 2.4
- **→ parallel with**: Tasks 2.1–2.3 (independent group)

---

### Group C — Skill-registry sync (D-registry)

#### Task 2.6 [x] [TDD-FIRST] Write failing registry agent-count guard
- **File**: `tests/test_elicit_lifecycle.py` (add to same file)
- **What**: Add `test_skill_registry_lists_all_6_brainds_agents()` that:
  1. Reads `.atl/skill-registry.md`.
  2. Reads `AGENT_FLOW.md`.
  3. Asserts each of the 6 agent names appears in BOTH files:
     `brainds-orchestrator`, `brainds-source-explorer`,
     `brainds-query-consultant`, `brainds-graph-mapper`,
     `brainds-connection-mapper`, `brainds-brd-writer`.
  4. Asserts the registry's Agent Definitions table has at least 6 rows.
- **Spec**: `elicit-artifact-lifecycle/spec.md` §skill-registry lists all 6 brain_ds sub-agents
- **AC**: 2.3
- **// parallel with Tasks 2.1 and 2.4**

#### Task 2.7 [x] Sync .atl/skill-registry.md — add 3 missing agents
- **File**: `.atl/skill-registry.md`
- **What**: Add Agent Definitions rows for the 3 missing agents:
  `brainds-graph-mapper`, `brainds-connection-mapper`, `brainds-brd-writer`.
  Copy the existing Agent Definitions format (name, description, file path,
  trigger conditions). Source: `.claude/agents/brainds-graph-mapper.md`,
  `.claude/agents/brainds-connection-mapper.md`,
  `.claude/agents/brainds-brd-writer.md` (these already exist on disk).
  Do NOT create new agent files.
- **→ depends on**: Task 2.6
- **AC**: 2.3

#### Task 2.8 [x] Mark AGENT_FLOW.md pendiente closed
- **File**: `AGENT_FLOW.md`
- **What**: Locate the open pendiente item about ".elicit cleanup convention"
  and mark it resolved, referencing `.elicit/README.md`. Keep the doc-only scope
  (do NOT add brainds-query-consultant to OpenCode global — proposal §Slice 2
  says doc-sync only).
- **→ depends on**: Task 2.2 (README.md must exist)

#### Task 2.9 [x] Run full Slice 2 suite and assert green gate
- **What**: `uv run pytest tests/test_elicit_lifecycle.py` (all tests must pass) +
  confirm `.atl/skill-registry.md` changes are reviewed for formatting.
- **→ depends on**: Tasks 2.3, 2.5, 2.7, 2.8

---

## Slice 3 — datasource read-only access + secret contract [depends on Slice 2 being merged]

**PR3 target: ~180 lines changed.**
Tasks 3.1–3.4 and 3.5–3.6 can be worked in parallel once Slice 2 is merged.

---

### Group A — secret_ref connector implementation (D5)

#### Task 3.1 [x] [TDD-FIRST] Write failing secret contract tests
- **File**: `tests/test_connector_secret_contract.py` (new)
- **What**: Add these failing tests:
  1. `test_secret_ref_stored_as_name_not_value()` — serializes a Data Source
     node whose `details.connection.secret_ref = "BRAINDS_SRC_PWD"` and asserts
     the serialized JSON contains `"BRAINDS_SRC_PWD"` but NOT the env-var's
     resolved value.
  2. `test_missing_secret_ref_fails_closed()` — with env var unset, connector
     open raises an error naming the missing var; no silent substitution.
  3. `test_readonly_holds_with_secret_ref()` — with env var set, connector opens
     SQLite in read-only mode; INSERT/UPDATE raises a read-only error.
  4. `test_anti_leak_sentinel_not_in_elicit()` — seeds `BRAINDS_SRC_PWD` to
     `SENTINEL-LEAK-CANARY-12345`; runs a fixture that writes mock `.elicit/`
     output; asserts no file under `.elicit/` contains the sentinel.
- **Spec**: `datasource-readonly-secrets/spec.md` (all scenarios)
- **AC**: 3.1, 3.2, 3.3

#### Task 3.2 [x] Implement secret_ref resolution in sqlite_connector.py
- **File**: `brain_ds/connectors/sqlite_connector.py`
- **What**:
  1. In `_open()`, check `connection_descriptor.get("secret_ref")`.
  2. If present, resolve from `os.environ`; raise a clear `KeyError`-derived
     exception naming the variable if it is unset.
  3. Use the resolved value for authentication (placeholder for non-SQLite auth;
     for SQLite this is a no-op beyond the URI, but the resolution path is
     exercised).
  4. Ensure `mode=ro` and `PRAGMA query_only` are issued regardless of whether
     `secret_ref` is present (compose, don't gate).
  5. The raw resolved value must not be logged or stored.
- **→ depends on**: Task 3.1
- **AC**: 3.1, 3.3

#### Task 3.3 [x] Verify connector secret tests green
- **What**: `uv run pytest tests/test_connector_secret_contract.py`. All 4 tests must pass.
- **→ depends on**: Task 3.2

---

### Group B — harness surfacing of secret contract (D5 harness side)

#### Task 3.4 [x] [TDD-FIRST] Write failing SOURCE_EXPLORATION_CONTRACT guard
- **File**: `tests/test_connector_secret_contract.py` (add to same file)
- **What**: Add `test_source_exploration_contract_mentions_secret_ref()` that:
  1. Imports `SOURCE_EXPLORATION_CONTRACT` from `brain_ds.mcp.grounding`.
  2. Converts to string.
  3. Asserts `"secret_ref"` appears in the string.
  4. Asserts a no-persistence clause appears (e.g., "not persisted" or
     "never stored" or similar — use a regex covering at least two phrasings).
- **Spec**: `datasource-readonly-secrets/spec.md` §secret contract surfaced in the harness
- **AC**: 3.1
- **// parallel with Task 3.1**

#### Task 3.5 [x] [HARNESS] Update SOURCE_EXPLORATION_CONTRACT in grounding.py
- **File**: `brain_ds/mcp/grounding.py`
- **What**: In `SOURCE_EXPLORATION_CONTRACT` (the Category-2 constant), add a
  `secret_ref` section explaining:
  - Field name: `secret_ref` in `details.connection`.
  - Source of resolution: `os.environ` at open time inside the connector.
  - No-persistence guarantee: the resolved credential value is never stored in
    the graph, card_sections, or `.elicit/` artifacts.
  - Keep the section concise (~6-8 lines of prose).
- **HARNESS**: this is a Category-2 constant — the drift guard meta-test (Task 1.5)
  must still pass after this change. Add `secret_ref` related keys to
  `CATEGORY2_EXEMPT` if the sweep flags them, or ensure no entity-name-shaped
  tokens are introduced.
- **→ depends on**: Task 3.4
- **AC**: 3.1

#### Task 3.6 [x] Run full Slice 3 suite and assert green gate
- **What**: `uv run pytest tests/test_connector_secret_contract.py tests/test_grounding_drift_guard.py` +
  `brain_ds check`. Tool count still 22.
- **→ depends on**: Tasks 3.3, 3.5

---

## Slice 4 — multi-agent dry-run + verify [depends on Slices 1-3 all merged]

**PR4 target: ~260 lines changed.**
Tasks 4.1 (fixture builder) and 4.2–4.3 (compliance test scaffold) can be started
in parallel once Slices 1-3 are merged.

---

### Group A — synthetic fixture

#### Task 4.1 [x] Create synthetic SQLite fixture + builder
- **Files**: `tests/fixtures/synthetic_source.db`, `tests/fixtures/build_synthetic_source.py` (new)
- **What**:
  - Builder creates a small SQLite database with at least 2 tables, 3 columns each,
    and 5 rows each.
  - Tables should have descriptive names (e.g., `customers`, `orders`) to produce
    realistic section docs.
  - Builder is idempotent (can be re-run safely).
  - Add a `conftest.py` fixture `synthetic_source_path` that returns the db path
    (or builds it on demand).
- **Spec**: `brain-ds-delegation-dry-run/spec.md` §dry-run exercises the full cycle
- **AC**: 4.1
- **Note**: `secret_ref` is NOT set on the synthetic source (unauthenticated path
  from Slice 3 is sufficient for the dry-run fixture).

---

### Group B — dry-run compliance tests

#### Task 4.2 [x] [TDD-FIRST] Write failing dry-run compliance test scaffold
- **File**: `tests/test_dryrun_elicit_compliance.py` (new)
- **What**: Scaffold these tests (all initially failing/skipped):
  1. `test_elicit_files_naming_pattern()` — reads `.elicit/` after a fixture-driven
     run and asserts all files match `<phase>-<org-slug>-<ISO-date>.md`.
  2. `test_source_docs_brainds_format()` — reads a `source-docs-*.md` from the
     dry-run output; asserts every documented node has `card_sections` with
     `order ≥ 1` (or BRD carve-out if `type == "Unknown"`), non-empty `icon`,
     non-empty `title`.
  3. `test_brd_persistence_contract_in_dry_run()` — if a `brd-*.md` file is
     present, reads the associated `brd-<graph-id>` node from the test graph and
     asserts `order == 0`, `icon == ""`, `type == "Unknown"`, `label == "BRD"`.
  4. `test_completeness_gate_recorded()` — asserts at least one
     `assess_completeness` call result is present in the dry-run output (either
     in a `.elicit/*.md` file or in the test graph's node records).
  5. `test_sub_agent_writes_only_to_elicit()` — a context-isolation assertion:
     given a mock orchestrator handoff, the sub-agent's prompt contains ONLY
     artifact refs + synthetic source path (no graph history, no Engram domain
     data).
- **Spec**: `brain-ds-delegation-dry-run/spec.md` (all scenarios)
- **AC**: 4.1, 4.2
- **→ depends on**: Task 4.1

#### Task 4.3 [x] Implement test fixtures and integration helpers to make compliance tests green
- **Files**: `tests/test_dryrun_elicit_compliance.py` (impl), `tests/conftest.py`
  (add `dry_run_elicit_output` fixture)
- **What**:
  1. `dry_run_elicit_output` fixture: exercises the full sequence (steps 1-5 from
     spec) against `synthetic_source.db`, writing to a temp `.elicit/`-like
     directory. Uses the real MCP tools (`list_source_connections`, `explore_source`,
     etc.) in-process against the synthetic source.
  2. Wire all 5 compliance tests to this fixture.
  3. The context-isolation test (test 5) uses a mock/spy on the orchestrator
     handoff method to capture the prompt content and assert it contains no
     extraneous context.
- **→ depends on**: Task 4.2
- **AC**: 4.1, 4.2

---

### Group C — sdd-verify acceptance checks

#### Task 4.4 [x] [TDD-FIRST] Write failing sdd-verify elicit-compliance acceptance test
- **File**: `tests/test_dryrun_elicit_compliance.py` (add section)
- **What**: Add `test_sddverify_reports_critical_on_noncompliant_node()` that:
  1. Plants a synthetic `source-docs-*.md` in the temp `.elicit/` directory with
     a documented node that has `card_sections[0].order == 0` and `type != "Unknown"`.
  2. Invokes the sdd-verify compliance check function (to be implemented in 4.5).
  3. Asserts the result contains a CRITICAL finding naming the file and the
     offending node.
- **Spec**: `brain-ds-delegation-dry-run/spec.md` §sdd-verify validates .elicit/ output
- **AC**: 4.2
- **// parallel with Task 4.2**

#### Task 4.5 [x] Implement sdd-verify elicit-compliance checker
- **File**: `brain_ds/verify/elicit_compliance.py` (new) or add to existing verify
  module if one exists
- **What**: Implement `check_elicit_compliance(elicit_dir: Path) -> list[Finding]`
  that checks:
  - (a) All files under `elicit_dir` match the naming pattern.
  - (b) `source-docs-*` and `map-*` files: every documented node has `order ≥ 1`
        (or BRD carve-out if `type == "Unknown"`), non-empty `icon`, non-empty `title`.
  - (c) `brd-*` files: associated BRD node satisfies the persistence contract.
  - (d) At least one `assess_completeness` recommendation is recorded.
  - Returns `Finding(severity, message, file)` for each violation; `severity == "CRITICAL"`
    for non-compliance.
- **→ depends on**: Task 4.4
- **AC**: 4.2

#### Task 4.6 [x] Run full Slice 4 suite and assert green gate
- **What**: `uv run pytest tests/test_dryrun_elicit_compliance.py` + full suite
  `uv run pytest` must be green. Confirm tool count still 22. `brain_ds check`
  must pass.
- **→ depends on**: Tasks 4.3, 4.5

---

## Cross-slice gates (apply to all slices)

- `ruff check` and `mypy` must remain clean after every task that modifies Python
  files.
- `skills/*` ↔ `.opencode/skills/*` mirrors: any `[SKILL-EDIT]` task must be
  validated by diffing both copies (they must be byte-identical after the change).
- tool count must remain 22 after every slice (assert via `brain_ds check` or
  `tests/test_harness_check.py`).
- `tests/test_grounding_drift_guard.py` must stay green throughout all slices
  (Category-2 sweep covers any new harness constants added).

---

## Dependency graph (summary)

```
Slice 1 (Tasks 1.1 – 1.9)
  ├── Group A: 1.1 → 1.2 → 1.3
  ├── Group B: 1.4 → 1.5 → 1.6   (parallel with Group A)
  └── Group C: 1.7 → 1.8 → 1.9   (parallel with A+B; 1.9 needs all)
        ↓ (Slice 1 merged)
Slice 2 (Tasks 2.1 – 2.9)
  ├── Group A: 2.1 → 2.2 → 2.3
  ├── Group B: 2.4 → 2.5          (parallel with Group A)
  ├── Group C: 2.6 → 2.7 → 2.8   (parallel with A+B)
  └── Gate:    2.9 (needs 2.3, 2.5, 2.7, 2.8)
        ↓ (Slice 2 merged)
Slice 3 (Tasks 3.1 – 3.6)
  ├── Group A: 3.1 → 3.2 → 3.3
  ├── Group B: 3.4 → 3.5          (parallel with Group A)
  └── Gate:    3.6 (needs 3.3, 3.5)
        ↓ (Slice 3 merged)
Slice 4 (Tasks 4.1 – 4.6)
  ├── Group A: 4.1 (fixture)
  ├── Group B: 4.1 → 4.2 → 4.3
  ├── Group C: 4.4 → 4.5          (parallel with Group B)
  └── Gate:    4.6 (needs 4.3, 4.5)
```

Total implementation tasks: 27 (including TDD-first tasks and gate verifications).

---

## Review Workload Forecast

| Slice | Estimated changed lines | 400-line budget risk | Notes |
|-------|------------------------|----------------------|-------|
| Slice 1 (PR1) | ~280 | Low | Largest single piece is Playwright spec (~80 lines) + drift sweep (~60 lines) + skill carve-out (~30 lines) + recurrence guard test (~40 lines) |
| Slice 2 (PR2) | ~220 | Low | Mostly new doc files (README.md, SDD_FLOW.md); registry sync is additive only |
| Slice 3 (PR3) | ~180 | Low | connector impl (~50 lines) + grounding addition (~30 lines) + new test file (~100 lines) |
| Slice 4 (PR4) | ~260 | Low | fixture builder (~40) + compliance tests (~120) + elicit_compliance.py (~100) |
| **Total** | **~940 lines** | N/A | Spread across 4 PRs |

**Chained PRs recommended**: Yes — 4 PRs, each independently reviewable, each within
the ~400-line budget. Sequential chain required: PR1 → PR2 → PR3 → PR4.

**Within-slice parallelism**: each slice has 2-3 parallel sub-groups (see dependency
graph above) that can be handled in separate commits or by concurrent work, but they
all land in the same PR.

**Decision needed before apply**: No new decision required. Delivery strategy is
confirmed as 4 chained PRs. The open questions from design (SDD_FLOW.md location →
`docs/`; query-consultant OpenCode addition → deferred) are resolved.
