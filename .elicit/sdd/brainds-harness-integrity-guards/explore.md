# Exploration: brainds-harness-integrity-guards

Artifact store: brain_ds-hybrid. Engram: `sdd/brainds-harness-integrity-guards/explore` (#2186).
Theme: "everything the live fire test proved we don't validate." Strict TDD (`uv run pytest`). HARD: do not lower any existing guard bar.

## Current State

### Capability 1 — Agent-definition guards (deferred debt from brainds-live-agentic-cycle-validation)
`brain_ds/harness_check.py` registers only `check_project_mcp_entries()` + `check_skills_mirror()`. `SUBAGENT_NAMES`, `CLAUDE_AGENT_FILES`, `check_agent_files()` referenced in CLAUDE.md DO NOT EXIST. `brain_ds check` audits MCP entries + skill parity but NOT agent tool grants/model/name. ROOT CAUSE of the connection-mapper-Write live scare. AGENT_FLOW.md claims "12 checks" — stale/aspirational (real count ~4-5). Only existing tool-grant check is a post-hoc string-grep for connection-mapper Write in test_elicit_lifecycle.py.

### Capability 2 — Graph-write integrity (live follow-up #2)
`update_node` → `store.upsert_node()` → `NodeRepository.upsert_node()` (repository.py ~255-360) is a TARGETED safe upsert: Python merge preserves absent keys + SQL `ON CONFLICT DO UPDATE SET col=COALESCE(excluded.col, nodes.col)`, single `(graph_id, node_id)` row. Full-replace path (`save_graph()` delete+save, graph_store.py ~152-154) is used by `import_graph` ONLY, which graph-mapper does NOT have. **Verdict: the live Organization-node "loss" was a filtered-view misread (`list_nodes type="Data Source"`), not a delete.** Missing: a regression test proving update_node on A preserves bystander B + edges.

### Capability 3 — Per-cycle subdir scoping (live follow-up #3)
`check_elicit_compliance()` (elicit_compliance.py:134) globs flat `*.md`. Subdir artifacts invisible. `PHASE_PATTERN` (elicit_compliance.py) duplicated as `ELICIT_NAME_PATTERN` (test_elicit_lifecycle.py) — drift risk.

## Approaches (recommendations)
- **Cap 1 → C**: regex-extract frontmatter between `---` delimiters, set-membership scan of tools list. No new deps (no PyYAML). Read with `utf-8-sig`, normalize line endings.
- **Cap 2 → A**: regression test only (store is correct). RED ⇒ hidden bug; GREEN ⇒ blindado.
- **Cap 3 → A**: additive two-pass glob `glob("*.md")` ∪ `glob("*/*.md")`. Backward-compatible. Import canonical PHASE_PATTERN into the test to kill duplication.

## Slicing — ONE PR, 3 commit groups (~315 lines, no cross-slice coupling, under 400 budget)
- **Commit 1 / Slice B** (~40 lines): bystander-preservation regression test in test_mcp_tools.py.
- **Commit 2 / Slice A** (~200 lines): SUBAGENT_NAMES + CLAUDE_AGENT_FILES + check_agent_files() in harness_check.py, registered; AgentFileCheckTests in test_harness_check.py.
- **Commit 3 / Slice C** (~75 lines): additive glob in check_elicit_compliance(); update test_elicit_lifecycle.py glob + import canonical PHASE_PATTERN.

## Risks
1. query-consultant has NO prompt mirror (AGENT_FLOW pending) → check must SKIP/WARN, not FAIL.
2. Frontmatter CRLF/BOM → utf-8-sig + normalize before split on `---`.
3. AGENT_FLOW.md "12 checks" stale → set the real count after implementation, do not invent.
4. No grounding.py / drift-guard cascade — harness_check.py is isolated.
5. Slice B uses isolated temp stores (MCPToolsTests pattern) — live store safe.
6. PHASE_PATTERN duplication fixed in Slice C.

## Affected files
brain_ds/harness_check.py, tests/test_harness_check.py, brain_ds/verify/elicit_compliance.py, tests/test_elicit_lifecycle.py, tests/test_dryrun_elicit_compliance.py, tests/conftest.py, tests/test_mcp_tools.py, AGENT_FLOW.md.
