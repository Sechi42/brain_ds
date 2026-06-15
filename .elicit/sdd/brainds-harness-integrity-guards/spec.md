# Spec: brainds-harness-integrity-guards

Change: brainds-harness-integrity-guards
Strict TDD: yes (`uv run pytest`)
Artifact store: hybrid
HARD PRINCIPLE: only ADDS guards; lowers no existing verifier/guard bar.

---

## R1 — Agent-definition Guards

### Requirement: check_agent_files exists and is registered

The system MUST expose `check_agent_files(project_root: Path) -> list[CheckResult]` in `brain_ds/harness_check.py` and MUST register it in `_run_all_checks`.

`SUBAGENT_NAMES` MUST list exactly the 4 subagent slugs:
`brainds-source-explorer`, `brainds-graph-mapper`, `brainds-connection-mapper`, `brainds-brd-writer`.

`CLAUDE_AGENT_FILES` MUST map each slug to its `.claude/agents/` filename.

The required tool grant table MUST be:
- `brainds-connection-mapper` → `{"Write"}`
- `brainds-brd-writer` → `{"Write", "mcp__brain_ds__generate_brd"}`
- `brainds-source-explorer` → `{"Write", "mcp__brain_ds__explore_source"}`
- `brainds-graph-mapper` → `{"mcp__brain_ds__update_node", "mcp__brain_ds__add_edge"}`

Target test file: `tests/test_harness_check.py` — class `AgentFileCheckTests`.

#### Scenario: all agent files present with correct grants — PASS

- GIVEN a temp project root with all 4 `.claude/agents/brainds-*.md` files each having valid frontmatter `name:` matching its slug AND all required tool grants listed in `tools` array
- WHEN `check_agent_files(project_root)` is called
- THEN every CheckResult in the returned list has `status == "PASS"`

#### Scenario: missing required tool grant — FAIL

- GIVEN a temp project root where `brainds-connection-mapper.md` frontmatter lists no `Write` tool grant
- WHEN `check_agent_files(project_root)` is called
- THEN the CheckResult for `agent-tools-brainds-connection-mapper` has `status == "FAIL"` and the detail message names the missing grant

#### Scenario: agent file absent — FAIL

- GIVEN a temp project root where `brainds-graph-mapper.md` does not exist
- WHEN `check_agent_files(project_root)` is called
- THEN the CheckResult for `agent-file-brainds-graph-mapper` has `status == "FAIL"`

#### Scenario: name: frontmatter mismatch — FAIL

- GIVEN `brainds-source-explorer.md` frontmatter has `name: brainds-wrong`
- WHEN `check_agent_files(project_root)` is called
- THEN the CheckResult for `agent-name-brainds-source-explorer` has `status == "FAIL"`

#### Scenario: query-consultant prompt mirror absent — SKIP not FAIL

- GIVEN a temp project root with all 4 sub-agent files passing all checks AND no `prompts/brainds-query-consultant.md`
- WHEN `check_agent_files(project_root)` is called
- THEN no CheckResult has `status == "FAIL"` due to the missing query-consultant mirror (status MAY be "SKIP" or "WARN")

#### Scenario: CRLF / BOM frontmatter — robust parse

- GIVEN `brainds-brd-writer.md` is written with CRLF line endings and a UTF-8 BOM and has all correct grants
- WHEN `check_agent_files(project_root)` is called
- THEN the CheckResult for `brainds-brd-writer` grants check is `status == "PASS"` (BOM/CRLF do not cause a false FAIL)

#### Scenario: check_agent_files registered in _run_all_checks

- GIVEN a project root passing all checks
- WHEN `harness_check_main(project_root)` (or `_run_all_checks`) is called
- THEN the returned results include at least one CheckResult whose name begins with `agent-`

#### Scenario: AGENT_FLOW.md check count reflects real post-implementation count

- GIVEN the live `AGENT_FLOW.md` in the repo root
- WHEN its content is read
- THEN it MUST NOT contain the stale literal string "12 checks" (or equivalent false claim); the stated check count MUST equal the actual count of CheckResult entries produced by `_run_all_checks` on a fully configured project

---

## R2 — Graph-write Bystander Preservation

### Requirement: update_node does not mutate unrelated nodes or edges

The system MUST preserve the label, type, details, and all edges of node B when `update_node` targets node A, even when A and B share the same graph.

Target test file: `tests/test_mcp_tools.py`.

#### Scenario: bystander node preserved after update_node

- GIVEN an isolated SQLite store containing graph G with node A (label "Alpha") and node B (label "Beta"), and an edge from B to a third node C
- WHEN `update_node` is called for node A with a new label or detail field
- THEN node B's label, type, and details remain unchanged AND the edge from B to C still exists with its original confidence and relation

#### Scenario: updated node reflects new values

- GIVEN the same isolated graph as above
- WHEN `update_node` is called for node A with `label="Alpha-v2"`
- THEN `get_node(node_id=A)` returns `label == "Alpha-v2"` (write took effect)

---

## R3 — Per-cycle Subdir Scoping in elicit_compliance

### Requirement: check_elicit_compliance scans one subdir level in addition to flat

`check_elicit_compliance(elicit_dir)` MUST discover and validate phase-named `.md` files located at `elicit_dir/<subdir>/*.md` (one level of nesting) in addition to `elicit_dir/*.md` (flat).

The combined artifact list MUST be deduplicated (a file counted once regardless of which glob matched it).

Backward compatibility MUST be maintained: callers passing a flat `.elicit/` dir receive the same results as before this change.

PHASE_PATTERN MUST be imported from `brain_ds.verify.elicit_compliance` in `tests/test_elicit_lifecycle.py` — the local duplicate definition MUST be removed.

Scoping rules (MUST NOT be weakened):
- Files not matching PHASE_PATTERN are silently ignored at both levels (README, scratch, etc.)
- Phase-named files with broken or missing JSON payload yield CRITICAL findings at both levels
- The `completeness_gate` check and `brd` / `verify` / `source-docs` / `map` sub-checks apply identically to artifacts found at both levels

Target test files: `tests/test_elicit_lifecycle.py`, `tests/test_dryrun_elicit_compliance.py`.

#### Scenario: artifact in subdir is discovered

- GIVEN `.elicit/changes/my-change/brd-my-change-2026-06-14.md` exists with a valid BRD JSON payload and `.elicit/` is empty otherwise
- WHEN `check_elicit_compliance(Path(".elicit"))` is called
- THEN the findings list does NOT contain a CRITICAL for missing completeness_gate (i.e. the brd artifact was found and its completeness_gate processed)

#### Scenario: flat artifacts still discovered (backward compat)

- GIVEN `.elicit/elicit-my-project-2026-06-14.md` exists at the flat level with a valid payload
- WHEN `check_elicit_compliance(Path(".elicit"))` is called
- THEN the artifact is found and its payload is validated (no "not found" or spurious CRITICAL)

#### Scenario: README ignored at subdir level

- GIVEN `.elicit/changes/README.md` exists alongside a valid flat artifact
- WHEN `check_elicit_compliance(Path(".elicit"))` is called
- THEN no CRITICAL is raised for README.md

#### Scenario: phase-named but broken artifact in subdir yields CRITICAL

- GIVEN `.elicit/changes/my-change/map-my-change-2026-06-14.md` exists but contains no fenced JSON block
- WHEN `check_elicit_compliance(Path(".elicit"))` is called
- THEN a CRITICAL finding with message referencing the broken payload is returned

#### Scenario: PHASE_PATTERN imported from canonical source

- GIVEN `tests/test_elicit_lifecycle.py` is loaded
- WHEN the module is inspected
- THEN `PHASE_PATTERN` (or `ELICIT_NAME_PATTERN`) used in the test is the object imported from `brain_ds.verify.elicit_compliance`, not a locally defined duplicate

---

## Out-of-scope (binding — do not include in tasks or apply)

- grounding.py constant edits
- EntityType / RelationshipType changes or drift-guard updates
- Creating prompts/brainds-query-consultant.md
- Editing any existing agent/prompt .md content
- save_graph() / import_graph() behavioral changes

---

Mirror: .elicit/sdd/brainds-harness-integrity-guards/spec.md
Project: brain_ds
Topic: sdd/brainds-harness-integrity-guards/spec
