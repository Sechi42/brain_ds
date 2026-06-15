# Tasks: brainds-harness-integrity-guards

Change: brainds-harness-integrity-guards
Strict TDD: yes (`uv run pytest`)
Delivery: single PR (~315 lines, under 400-line budget)
Commit groups: B → A → C (in that order)

---

## Commit Group B — R2: Graph-write Bystander Preservation

Target file: `tests/test_mcp_tools.py`
Estimated lines: ~40

### Task B-1 [RED] — Seed N-3 + B→C edge in setUp, assert bystander preservation after update_node(N-1)

- **Scenario**: R2 / "bystander node preserved after update_node"
- **File**: `tests/test_mcp_tools.py` — class `MCPToolsTests`
- **Action**: Extend `setUp` to also seed node N-3 (label "Gamma Source", type "Source") and add an edge from N-2 to N-3 (relation "feeds", confidence 0.9). Add test method `test_update_node_preserves_unrelated_node_and_edge` that:
  1. Calls `update_node(store, {graph_id, node_id:"N-1", label:"Alpha-v2"})`
  2. Asserts N-2's label, type, and details remain unchanged
  3. Asserts the N-2→N-3 edge still exists with original relation and confidence
  4. Asserts total node count in the graph is 3 (no ghost nodes created)
- **Expected**: GREEN (no upsert_node bug expected). If RED unexpectedly → ESCALATE, do not silence.
- **Parallel**: No — must run before A and C to establish regression baseline.

### Task B-2 [RED] — Assert updated node reflects new values

- **Scenario**: R2 / "updated node reflects new values"
- **File**: `tests/test_mcp_tools.py` — same test class
- **Action**: Add test method `test_update_node_write_takes_effect` that calls `update_node` for N-1 with `label="Alpha-v2"`, then calls `get_node` for N-1 and asserts `label == "Alpha-v2"`.
- **Expected**: GREEN (corroborates write path correctness alongside bystander guard).
- **Parallel**: Can be written together with B-1 in one commit.

> **Commit B checkpoint**: `uv run pytest tests/test_mcp_tools.py` — full class GREEN.

---

## Commit Group A — R1: Agent-definition Guards

Target files: `tests/test_harness_check.py` (new class), `brain_ds/harness_check.py`
Estimated lines: ~200 (tests ~120, impl ~80)

### Task A-1 [RED] — Write AgentFileCheckTests: pass case

- **Scenario**: R1 / "all agent files present with correct grants — PASS"
- **File**: `tests/test_harness_check.py` — new class `AgentFileCheckTests`
- **Action**: Write `setUp` that creates a temp project root with `.claude/agents/` containing all 4 files (`brainds-source-explorer.md`, `brainds-graph-mapper.md`, `brainds-connection-mapper.md`, `brainds-brd-writer.md`). Each file gets valid frontmatter (`name:` matching slug, `tools:` block listing all required grants per spec). Import `check_agent_files` from `brain_ds.harness_check` (will fail import → RED). Test `test_all_agents_pass` asserts every CheckResult has `status == "PASS"`.
- **State at write time**: RED (ImportError).
- **Parallel**: All A-1 through A-7 test methods can be written in one pass before any impl.

### Task A-2 [RED] — Write AgentFileCheckTests: missing-grant FAIL case

- **Scenario**: R1 / "missing required tool grant — FAIL"
- **File**: `tests/test_harness_check.py` — `AgentFileCheckTests`
- **Action**: Test `test_missing_grant_fails` — sets up all 4 agent files but writes `brainds-connection-mapper.md` without the `Write` tool grant. Asserts a CheckResult with name containing `brainds-connection-mapper` has `status == "FAIL"` and detail names the missing grant.
- **State**: RED.

### Task A-3 [RED] — Write AgentFileCheckTests: agent file absent FAIL case

- **Scenario**: R1 / "agent file absent — FAIL"
- **File**: `tests/test_harness_check.py`
- **Action**: Test `test_missing_file_fails` — omits `brainds-graph-mapper.md` from setup. Asserts a CheckResult with name `agent-file-brainds-graph-mapper` has `status == "FAIL"`.
- **State**: RED.

### Task A-4 [RED] — Write AgentFileCheckTests: name frontmatter mismatch FAIL case

- **Scenario**: R1 / "name: frontmatter mismatch — FAIL"
- **File**: `tests/test_harness_check.py`
- **Action**: Test `test_name_mismatch_fails` — writes `brainds-source-explorer.md` with `name: brainds-wrong`. Asserts a CheckResult with name containing `agent-name-brainds-source-explorer` has `status == "FAIL"`.
- **State**: RED.

### Task A-5 [RED] — Write AgentFileCheckTests: query-consultant mirror absent → SKIP not FAIL

- **Scenario**: R1 / "query-consultant prompt mirror absent — SKIP not FAIL"
- **File**: `tests/test_harness_check.py`
- **Action**: Test `test_query_consultant_mirror_skip` — all 4 agent files pass, no `prompts/brainds-query-consultant.md` present. Asserts no CheckResult has `status == "FAIL"` due to absent mirror (may be SKIP or omitted).
- **State**: RED.

### Task A-6 [RED] — Write AgentFileCheckTests: CRLF/BOM frontmatter robust parse

- **Scenario**: R1 / "CRLF / BOM frontmatter — robust parse"
- **File**: `tests/test_harness_check.py`
- **Action**: Test `test_crlf_bom_frontmatter_passes` — writes `brainds-brd-writer.md` with UTF-8 BOM (`\xef\xbb\xbf`) + CRLF line endings and all correct grants. Asserts the brd-writer CheckResult has `status == "PASS"`.
- **State**: RED.

### Task A-7 [RED] — Write AgentFileCheckTests: check_agent_files registered in _run_all_checks

- **Scenario**: R1 / "check_agent_files registered in _run_all_checks"
- **File**: `tests/test_harness_check.py`
- **Action**: Test `test_check_registered_in_runner` — uses a fully-wired temp project root (all 4 agent files passing). Calls `harness_check_main(project_root)` via `redirect_stdout`. Asserts at least one CheckResult name begins with `agent-` in the stdout output.
- **State**: RED.

> All A-1..A-7 tests written; run `uv run pytest tests/test_harness_check.py::AgentFileCheckTests` → all RED (ImportError or AttributeError).

### Task A-8 [GREEN] — Implement constants + check_agent_files() in harness_check.py

- **Scenarios**: R1 all scenarios
- **File**: `brain_ds/harness_check.py`
- **Action**:
  1. Add module constants:
     - `SUBAGENT_NAMES: list[str]` = `["brainds-source-explorer", "brainds-graph-mapper", "brainds-connection-mapper", "brainds-brd-writer"]`
     - `CLAUDE_AGENT_FILES: dict[str, str]` mapping each slug to its `.claude/agents/<slug>.md` filename
     - `REQUIRED_AGENT_GRANTS: dict[str, set[str]]` per spec table (graph-mapper has NO Write — encoded by absence)
  2. Add frontmatter parser: `_parse_agent_frontmatter(path: Path) -> dict` — reads with `utf-8-sig`, normalizes `\r\n`/`\r` to `\n`, scans lines between first and second `---`, extracts `name:` via regex, extracts `tools:` both as YAML block list and inline list.
  3. Add `check_agent_files(project_root: Path) -> list[CheckResult]` — for each slug in SUBAGENT_NAMES:
     - If file absent → `CheckResult("agent-file-{slug}", "FAIL", ...)`
     - Else parse frontmatter:
       - If `name:` != slug → `CheckResult("agent-name-{slug}", "FAIL", ...)`
       - Compute missing = `REQUIRED_AGENT_GRANTS[slug] - parsed_tools_set`; if non-empty → `CheckResult("agent-tools-{slug}", "FAIL", detail names missing grants)`
       - Else → `CheckResult("agent-file-{slug}", "PASS", ...)`
     - After subagent loop: check query-consultant mirror → `CheckResult("agent-file-query-consultant-mirror", "SKIP", ...)` (never FAIL for absence)
  4. Register `check_agent_files` in `_run_all_checks` tuple.
- **Expected after**: `uv run pytest tests/test_harness_check.py::AgentFileCheckTests` → all GREEN.

> **Commit A checkpoint**: `uv run pytest tests/test_harness_check.py` — full file GREEN.

---

## Commit Group C — R3: Per-cycle Subdir Scoping

Target files: `brain_ds/verify/elicit_compliance.py`, `tests/test_elicit_lifecycle.py`, `tests/test_dryrun_elicit_compliance.py`
Estimated lines: ~75 (prod ~10, tests ~55, dedup ~10)

### Task C-1 [RED] — Write subdir discovery test: artifact in subdir is found

- **Scenario**: R3 / "artifact in subdir is discovered"
- **File**: `tests/test_dryrun_elicit_compliance.py` (or new section; prefer existing file for locality)
- **Action**: Add test `test_subdir_artifact_discovered` — creates `tmp_path/changes/my-change/brd-my-change-2026-06-14.md` with a valid BRD JSON payload; no flat-level files. Calls `check_elicit_compliance(tmp_path)`. Asserts no CRITICAL finding for missing completeness_gate (brd found and processed).
- **State**: RED (glob only covers `*.md` today, subdir file invisible).
- **Parallel**: C-1 through C-4 can all be written before any prod change.

### Task C-2 [RED] — Write subdir test: README at subdir level ignored

- **Scenario**: R3 / "README ignored at subdir level"
- **File**: `tests/test_dryrun_elicit_compliance.py`
- **Action**: Test `test_subdir_readme_ignored` — creates `tmp_path/changes/README.md` plus a valid flat artifact. Calls `check_elicit_compliance(tmp_path)`. Asserts no CRITICAL for README.md.
- **State**: Expected GREEN (PHASE_PATTERN filtering handles this automatically once subdir glob is added), but must be written RED-first to confirm no regression.

### Task C-3 [RED] — Write subdir test: broken phase-named artifact in subdir yields CRITICAL

- **Scenario**: R3 / "phase-named but broken artifact in subdir yields CRITICAL"
- **File**: `tests/test_dryrun_elicit_compliance.py`
- **Action**: Test `test_subdir_broken_artifact_critical` — creates `tmp_path/changes/my-change/map-my-change-2026-06-14.md` with no fenced JSON block. Calls `check_elicit_compliance(tmp_path)`. Asserts a CRITICAL finding referencing the broken payload.
- **State**: RED (file not found by current glob).

### Task C-4 [RED] — Write subdir test: flat artifacts still discovered (backward compat)

- **Scenario**: R3 / "flat artifacts still discovered (backward compat)"
- **File**: `tests/test_dryrun_elicit_compliance.py`
- **Action**: Test `test_flat_artifact_still_discovered` — creates a valid flat-level elicit artifact. Calls `check_elicit_compliance(tmp_path)`. Asserts it is found and validated (no spurious CRITICAL).
- **State**: GREEN already (backward compat preserved by union glob), but must be written to lock regression prevention.

### Task C-5 [GREEN] — Implement additive glob in elicit_compliance.py

- **Scenario**: R3 all scenarios
- **File**: `brain_ds/verify/elicit_compliance.py`
- **Action**: Change line 134 from:
  ```python
  artifact_paths = sorted(path for path in elicit_dir.glob("*.md") if path.is_file())
  ```
  to:
  ```python
  artifact_paths = sorted(set(elicit_dir.glob("*.md")) | set(elicit_dir.glob("*/*.md")))
  artifact_paths = [p for p in artifact_paths if p.is_file()]
  ```
  (one level deep only; PHASE_PATTERN.match(path.name) already scopes correctly since it matches on filename only — subdirs inherit the bar for free.)
- **Expected**: C-1, C-3 go GREEN; C-2, C-4 remain GREEN; existing tests in test_dryrun_elicit_compliance.py stay GREEN.

### Task C-6 [GREEN] — Remove duplicated ELICIT_NAME_PATTERN from test_elicit_lifecycle.py; import from canonical source

- **Scenario**: R3 / "PHASE_PATTERN imported from canonical source"
- **File**: `tests/test_elicit_lifecycle.py`
- **Action**: Remove local `ELICIT_NAME_PATTERN = re.compile(...)` definition (line 38). Add import `from brain_ds.verify.elicit_compliance import PHASE_PATTERN as ELICIT_NAME_PATTERN`. Update any uses if the alias name differs.
- **Note**: `test_dryrun_elicit_compliance.py` also has a local duplicate `PHASE_PATTERN` — apply same dedup there (import instead of define) per design.
- **Expected**: `uv run pytest tests/test_elicit_lifecycle.py tests/test_dryrun_elicit_compliance.py` → GREEN.

> **Commit C checkpoint**: `uv run pytest tests/` — no regressions.

---

## Final Tasks (post-commit C, no separate commit — amend C or create fix commit)

### Task F-1 [MEASURE] — Correct AGENT_FLOW.md stale "12 checks" claim

- **Scenario**: R1 / "AGENT_FLOW.md check count reflects real post-implementation count"
- **File**: `AGENT_FLOW.md`
- **Action**:
  1. Run `uv run brain_ds check --project-root .` on a fully configured local project root (or call `_run_all_checks` in a Python snippet counting results).
  2. Count the actual number of `CheckResult` entries emitted by `_run_all_checks` after all three commit groups are applied.
  3. Replace the stale literal `"12 checks"` in `AGENT_FLOW.md` line 129 with the measured count.
  4. DO NOT invent or estimate — use the measured output.
- **Expected**: `uv run pytest` stays GREEN; `uv run brain_ds check` exits 0.

### Task F-2 [GREEN] — Full suite green gate

- **File**: all
- **Action**: Run `uv run pytest` (full suite) and `uv run brain_ds check --project-root .`. Both must exit 0. This is the PR gate.
- **Sequential**: Must be last.

---

## Dependency / Sequencing Graph

```
B-1, B-2   (parallel within group, no deps)
    |
    v
A-1..A-7   (parallel within group — all test writes)
    |
    v
A-8        (impl, depends on A-1..A-7 being RED)
    |
    v
C-1..C-4   (parallel within group — test writes)
    |
    v
C-5        (impl)
    |
    v
C-6        (dedup import — depends on C-5 for confidence)
    |
    v
F-1        (measure — requires full impl)
    |
    v
F-2        (gate — must be last)
```

**Groups B, A, C are strictly sequential** (each group's commit must land before the next group starts — RED baseline per group before GREEN impl).

---

## Review Workload Forecast

| Metric | Value |
|--------|-------|
| Estimated changed lines | ~315 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Decision needed before apply | No |
| Commit groups | 3 (B → A → C) |
| Delivery | Single PR |
| TDD mode | Strict (RED before GREEN per group) |

All three commit groups land in a single PR. No chained PR split needed — estimated delta is well under the 400-line budget.

---

Mirror: .elicit/sdd/brainds-harness-integrity-guards/tasks.md
Topic: sdd/brainds-harness-integrity-guards/tasks
