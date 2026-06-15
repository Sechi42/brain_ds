# Design: brainds-harness-integrity-guards

Architecture-level HOW for the 3 additive harness guards. Strict TDD. HARD PRINCIPLE: every change ADDS a guard or coverage; no existing verifier/guard/test bar is lowered. Honors proposal out-of-scope list (no grounding.py constants, no EntityType/RelationshipType drift work, no query-consultant prompt creation, no `.md` agent content edits, no save_graph/import_graph full-replace change).

## Pattern & Layering

Pure-function checker pattern, already established in `brain_ds/harness_check.py`:
- Each `check_*` function takes `project_root: Path`, returns `list[CheckResult]`.
- `CheckResult(name, status, detail)` is frozen; `status ∈ {PASS, FAIL, SKIP}`.
- `_run_all_checks` fans out over a tuple of check functions and concatenates results.
- `harness_check_main` prints `[STATUS] name: detail`, summarizes, returns `1 if any FAIL else 0`.

The new `check_agent_files()` MUST conform to that contract exactly — no new abstractions, no PyYAML, no class. Read-only filesystem inspection. This keeps the runner uniform and the summary/exit-code logic untouched (a bar we do NOT change).

`elicit_compliance.py` keeps its `Finding`/severity model. R3 changes only the file-discovery glob inside `check_elicit_compliance`; the per-file scoping (`PHASE_PATTERN.match`) and all severity rules are reused verbatim — subdirs inherit the exact same bar.

---

## R1 — `check_agent_files()` (Commit Group A)

### Data structures (module-level constants in `harness_check.py`)

```python
SUBAGENT_NAMES = (
    "brainds-orchestrator",
    "brainds-source-explorer",
    "brainds-graph-mapper",
    "brainds-connection-mapper",
    "brainds-brd-writer",
    "brainds-query-consultant",
)

# Canonical Claude agent definition files (6, one per sub-agent).
CLAUDE_AGENT_FILES = {name: f".claude/agents/{name}.md" for name in SUBAGENT_NAMES}

# Prompt mirror filenames. NOTE the orchestrator mirror is hyphenated
# (brain-ds-orchestrator.md) and query-consultant has NO mirror yet (PENDING).
PROMPT_MIRRORS = {
    "brainds-orchestrator": "prompts/brain-ds-orchestrator.md",
    "brainds-source-explorer": "prompts/brainds-source-explorer.md",
    "brainds-graph-mapper": "prompts/brainds-graph-mapper.md",
    "brainds-connection-mapper": "prompts/brainds-connection-mapper.md",
    "brainds-brd-writer": "prompts/brainds-brd-writer.md",
    # brainds-query-consultant: intentionally absent -> SKIP, never FAIL.
}

# Required tool grants per agent (frontmatter `tools:` must be a SUPERSET).
# Verified against the real .claude/agents/*.md files on 2026-06-14.
REQUIRED_AGENT_GRANTS = {
    "brainds-orchestrator": frozenset(),  # coordinator; no hard tool floor asserted
    "brainds-source-explorer": frozenset({
        "Write",
        "mcp__brain_ds__list_source_connections",
        "mcp__brain_ds__explore_source",
        "mcp__brain_ds__query_source",
    }),
    "brainds-graph-mapper": frozenset({
        "mcp__brain_ds__update_node",
        "mcp__brain_ds__add_edge",
    }),  # NO Write by design — must NOT be added.
    "brainds-connection-mapper": frozenset({
        "Write",
    }),
    "brainds-brd-writer": frozenset({
        "Write",
        "mcp__brain_ds__generate_brd",
    }),
    "brainds-query-consultant": frozenset(),  # not load-bearing for the floor; presence-only.
}
```

Rationale for the grant map: it encodes the live-fire bug class (connection-mapper silently lost `Write`). The floor is a SUPERSET check — agents may grant more tools; they may not grant fewer than the listed minimum. graph-mapper's empty-on-`Write` is encoded by simply NOT listing `Write` for it, and there is no "forbidden tools" assertion (adding one would be a new bar beyond the proposal — out of scope; the proposal says "NO Write by design" as documentation, enforced by absence from the required set, not by a negative assertion).

### Frontmatter extraction — Approach C (regex, no PyYAML)

Helper `_extract_agent_tools(path: Path) -> tuple[str | None, frozenset[str]] | None`:

1. `text = path.read_text(encoding="utf-8-sig")` — `utf-8-sig` transparently strips a BOM. Returns `None` on `OSError` (caller turns that into FAIL "missing/unreadable").
2. Normalize line endings: `text = text.replace("\r\n", "\n").replace("\r", "\n")` — handles CRLF and lone-CR.
3. Frontmatter slice: split on the fence. The file starts with `---\n`; take everything between the first and second `---` line.
   ```python
   if not text.startswith("---"):
       return (None, frozenset())  # no frontmatter
   parts = text.split("\n---", 2)  # [front_with_leading---, body, ...]
   # Robust variant: scan lines, collect from after first '---' line to next '---' line.
   ```
   Use the line-scan variant (more robust than `split` against `---` appearing in prose):
   ```python
   lines = text.split("\n")
   if lines[0].strip() != "---":
       return (None, frozenset())
   front: list[str] = []
   for line in lines[1:]:
       if line.strip() == "---":
           break
       front.append(line)
   ```
4. `name`: regex on the frontmatter block `^name:\s*(\S+)\s*$` (MULTILINE) → captured slug or `None`.
5. `tools`: support BOTH YAML shapes.
   - **Block list** (the real shape today): lines after a `tools:` line that match `^\s*-\s*(\S+)`. Collect each captured token until a non-list, non-blank, dedented key line.
   - **Inline list**: `tools:\s*\[(.*)\]` → split on `,`, strip whitespace/quotes.
   Implementation: find the `tools:` line; if it has `[...]` inline, parse inline; else consume subsequent `^\s*-\s*(.+)$` lines (strip trailing comments/quotes). Return `frozenset` of tokens.

This is intentionally a small, tolerant scanner — it does not validate YAML, only extracts the two fields the guard needs.

### CheckResult emission — DECISION: one CheckResult PER agent (not aggregate)

Justification: the existing checks emit one result per logical assertion (`claude-mcp-entry`, `opencode-mcp-entry`, `mcp-roots-aligned`) so a failure names exactly what broke. An aggregate "agent-files" result would hide WHICH agent drifted in a single FAIL line, making the live-fire failure mode (one agent lost one tool) hard to read in the summary. Per-agent results keep `harness_check_main`'s `[FAIL] agent-file:brainds-connection-mapper: missing tool grants {Write}` actionable. Each result name is `f"agent-file:{name}"`.

Per agent, the function evaluates in order and emits the FIRST applicable status (one CheckResult per agent):

1. Claude file missing/unreadable → `FAIL` "`.claude/agents/{name}.md` missing — agent definition absent".
2. Frontmatter `name:` mismatch (≠ slug) → `FAIL` "frontmatter name '{got}' != '{name}'".
3. Required grants not a subset of extracted tools → `FAIL` "missing tool grants {sorted(missing)}".
4. Prompt mirror: if `name` has a `PROMPT_MIRRORS` entry and that file is missing → `FAIL` "prompt mirror {path} missing". If `name` has NO mirror entry (query-consultant) → this branch is skipped; the agent can still PASS or be SKIP'd (see below).
5. Otherwise → `PASS` "definition + grants + mirror OK".

SKIP semantics for the query-consultant: query-consultant has a Claude file but NO prompt mirror and an empty required-grant set. Its mirror is documented as PENDING. So the function emits `SKIP` for query-consultant's mirror dimension rather than PASS-with-no-mirror or FAIL. Concretely: query-consultant yields `SKIP` "prompt mirror pending (query-consultant) — not yet authored" as long as its Claude file exists and name matches; if its Claude file is missing it still `FAIL`s (presence of the definition is non-negotiable). This guarantees the guard "never FAILs on the missing query-consultant mirror" (proposal risk 2) while still catching a deleted/renamed definition.

Edge note: because each agent yields exactly one CheckResult, query-consultant's single result is `SKIP` (mirror pending) in the healthy state — it does not also produce a PASS. All other agents produce `PASS` in the healthy state.

### Registration in the runner

```python
def _run_all_checks(project_root: Path) -> list[CheckResult]:
    results: list[CheckResult] = []
    for check in (check_project_mcp_entries, check_skills_mirror, check_agent_files):
        results.extend(check(project_root))
    return results
```

No change to `_summarize_statuses`, `harness_check_main`, or the exit-code contract. A query-consultant `SKIP` increments the skip counter only — exit code stays 0 in the healthy repo (no new FAIL bar introduced for an already-passing tree).

### Tests — `AgentFileCheckTests` in `tests/test_harness_check.py`

Follows the existing `tempfile.mkdtemp` + `_by_name` style. RED first. Each test builds a minimal fake agent tree under `self.project`:
- `test_passes_on_healthy_agent_tree`: write all 6 `.claude/agents/*.md` with correct `name:` + superset tool block lists, and the 5 prompt mirrors. Assert every non-query-consultant `agent-file:*` is PASS and `agent-file:brainds-query-consultant` is SKIP.
- `test_fail_when_claude_agent_missing`: omit connection-mapper file → that result FAIL.
- `test_fail_on_name_mismatch`: frontmatter `name: wrong` → FAIL.
- `test_fail_when_required_grant_absent`: connection-mapper tools block without `Write` → FAIL, detail contains "Write".
- `test_graph_mapper_passes_without_write`: graph-mapper with update_node+add_edge but no Write → PASS (proves Write is not required for it).
- `test_query_consultant_mirror_pending_is_skip_not_fail`: query-consultant file present, no prompt mirror → SKIP, never FAIL.
- `test_fail_when_prompt_mirror_missing`: brd-writer mirror absent → FAIL.
- `test_bom_and_crlf_frontmatter_parsed`: write a file with `﻿` BOM + CRLF endings → still parses name/tools, PASS.
- `test_inline_tools_list_parsed`: `tools: [Write, mcp__brain_ds__generate_brd]` inline form → PASS for brd-writer.

A separate live-repo smoke (optional, mirrors `InstallerWriteGrantTests` style): run `check_agent_files(REPO_ROOT)` and assert no FAIL — proves the real tree is healthy today and turns future drift red.

---

## R2 — Graph-write integrity regression (Commit Group B, FIRST)

### Approach A — regression test only, no production change expected

Add `test_update_node_preserves_unrelated_node_and_edge` to the existing `MCPToolsTests` in `tests/test_mcp_tools.py`. The fixture already seeds node A=`N-1` and bystander B=`N-2` under one graph with `setUp`. Steps:

1. Create an edge on the bystander: `add_edge(self.store, {"graph_id", "source": "N-2", "target": "N-1", "label": "refs", "weight": 0.5})` (edge anchored on B; using N-1↔N-2 is fine since both pre-exist). To make B's edge truly "unrelated to the A-update", add a third node B-edge target is acceptable, but minimal: the edge `N-2 -> N-1` plus B's own fields are the preservation surface.
   - Cleaner: add a third node `N-3` ("Gamma") and edge `N-2 -> N-3` so the bystander edge does not touch A at all. Preferred — it isolates "A update must not disturb B's subgraph".
2. Snapshot B before: `get_node(self.store, {"graph_id", "node_id": "N-2"})` and the edge row.
3. Mutate A: `update_node(self.store, {"graph_id", "node_id": "N-1", "label": "Alpha Renamed", "details": {"summary": "changed"}})`.
4. Assertions (preservation proof):
   - `get_node(... "N-2")` still returns label "Beta Note", supertype "Knowledge", original details — byte-for-byte unchanged.
   - The `N-2 -> N-3` edge still exists (query via store edge repo / `list_*` or direct `conn.execute` on the edges table, mirroring `_last_outbox_event` raw-SQL style).
   - `list_nodes(graph_id)` count is unchanged (A updated in place, no node added/dropped). This directly rebuts the live-fire "node vanished" misread.
   - A itself reflects the new label (update actually applied).

What proves preservation: B's full field set + B's edge survive an A-only `update_node`, AND total node count is stable. If this goes RED, the proposal says ESCALATE — it is a genuine `upsert_node` isolation bug, not a test to silence.

No production code is touched in this group (proposal locks Approach A). If RED, stop and surface.

---

## R3 — Per-cycle subdir scoping (Commit Group C)

### Exact glob change in `check_elicit_compliance` (`elicit_compliance.py`)

Current:
```python
artifact_paths = sorted(path for path in elicit_dir.glob("*.md") if path.is_file())
```
New (additive two-pass, one subdir level):
```python
artifact_paths = sorted(
    {path for path in elicit_dir.glob("*.md") if path.is_file()}
    | {path for path in elicit_dir.glob("*/*.md") if path.is_file()}
)
```
`set | set` dedupes (a path can only appear in one pass anyway, but the union is defensive); `sorted()` restores deterministic ordering by full path. `Path` is hashable and sortable, so this is safe.

### Where the scoping rule already lives (subdirs inherit for free)

The per-file gate is `if not PHASE_PATTERN.match(path.name): continue` (line 139). `PHASE_PATTERN` matches on `path.name` only — the parent directory is irrelevant. Therefore:
- A `README.md` or `scratch.md` in a subdir is STILL silently ignored (name doesn't match) — no weakening.
- A `map-acme-2026-06-14.md` inside `.elicit/changes/foo/` is NOW subject to the SAME payload contract (missing payload still CRITICAL, invalid completeness_gate still CRITICAL). The bar is extended one directory level deeper, never lowered.
- `_check_documented_nodes` / `_check_brd_payload` / `_check_verify_payload` all key off `path.name` prefixes and the payload — they work unchanged on subdir files.

The `has_non_verify_artifacts and not completeness_recorded` aggregate now also considers subdir artifacts, which is strictly stronger (more files inspected). No bar lowered.

### PHASE_PATTERN import change in the test

`tests/test_elicit_lifecycle.py` and `tests/test_dryrun_elicit_compliance.py` each duplicate `PHASE_PATTERN`. R3 imports the canonical one from the source to kill drift:
```python
from brain_ds.verify.elicit_compliance import PHASE_PATTERN
```
- In `test_dryrun_elicit_compliance.py`: replace the local `PHASE_PATTERN = re.compile(...)` with the import (keep `re`/`json` imports as still used elsewhere). Existing tests that reference `PHASE_PATTERN` keep working — same regex object.
- In `test_elicit_lifecycle.py`: that file uses `ELICIT_NAME_PATTERN` (a duplicate). Import `PHASE_PATTERN` and either alias `ELICIT_NAME_PATTERN = PHASE_PATTERN` or replace usages. Minimal, non-breaking: `from brain_ds.verify.elicit_compliance import PHASE_PATTERN as ELICIT_NAME_PATTERN`. This removes the duplicated regex literal while keeping all assertions green.

New subdir-coverage tests (RED first), added to `test_dryrun_elicit_compliance.py` (tmp_path based):
- `test_phase_named_file_in_subdir_is_checked`: write `tmp/changes/foo/map-acme-2026-06-14.md` with NO payload → CRITICAL raised (proves subdir is now scanned).
- `test_readme_in_subdir_still_ignored`: `tmp/changes/foo/README.md` → zero findings (proves scoping not weakened).
- `test_flat_callers_unchanged`: existing flat tmp file still behaves identically (backward compat).

### Green-keeping confirmation

- `test_dryrun_elicit_compliance.py` calls `check_elicit_compliance` directly; additive union only ADDS files when subdirs contain `.md` — current fixtures write flat files only, so existing results are byte-identical. Stays green.
- `test_elicit_lifecycle.py` reads the real `.elicit` tree; if `.elicit` gains no subdir artifacts, behavior is identical; if it does, they're now validated (stronger, intended). The import swap is regex-identical. Stays green.
- No conftest/fixture change is required UNLESS the dry-run fixture must emit a subdir artifact to exercise the new path. Decision: do NOT modify the shared dry-run fixture (avoids touching unrelated artifact generation); cover subdirs with dedicated tmp_path tests instead. (Proposal allowed a fixture change "if needed" — it is not needed.)

---

## Commit-group ordering & file lists

Order B → A → C (per proposal; slices are independent, each RED-first under strict TDD).

**Group B (R2, ~40 lines)** — graph-write regression:
- `tests/test_mcp_tools.py` — add `test_update_node_preserves_unrelated_node_and_edge` (+ optional `N-3` seed inside the test, not the shared `setUp`).

**Group A (R1, ~200 lines)** — agent-file guards:
- `brain_ds/harness_check.py` — add `SUBAGENT_NAMES`, `CLAUDE_AGENT_FILES`, `PROMPT_MIRRORS`, `REQUIRED_AGENT_GRANTS`, `_extract_agent_tools`, `check_agent_files`, register in `_run_all_checks`.
- `tests/test_harness_check.py` — add `AgentFileCheckTests` (+ optional repo-smoke).

**Group C (R3, ~75 lines)** — subdir scoping:
- `brain_ds/verify/elicit_compliance.py` — two-pass glob union.
- `tests/test_dryrun_elicit_compliance.py` — import canonical `PHASE_PATTERN`, add 3 subdir tests.
- `tests/test_elicit_lifecycle.py` — import canonical `PHASE_PATTERN` (alias), drop duplicate literal.

**AGENT_FLOW.md count-correction (in Group A or C, after impl lands):**
The doc claims a stale "12 checks". MEASURE, do not invent. After `check_agent_files` is registered, the healthy-repo run emits: `check_project_mcp_entries` (3) + `check_skills_mirror` (1) + `check_agent_files` (6: 5 PASS + 1 SKIP) = **10 CheckResults from 3 check functions**. The correction step is: run `harness_check_main` against the repo, read the actual `Summary:` line + check-function count, and write THAT number into AGENT_FLOW.md. Do not hardcode "10" blindly — re-measure at apply time because the exact count depends on the real tree state.

---

## Edge cases (explicit handling)

1. **CRLF / BOM frontmatter** → `read_text(encoding="utf-8-sig")` strips BOM; explicit `\r\n`/`\r` → `\n` normalization before line scan. Covered by `test_bom_and_crlf_frontmatter_parsed`.
2. **Inline vs block YAML tools list** → `_extract_agent_tools` parses both (`tools: [a, b]` and `tools:\n  - a\n  - b`). Covered by `test_inline_tools_list_parsed`. Real files use block form today; inline support future-proofs without PyYAML.
3. **Empty `.elicit` dir** → `glob("*.md")` and `glob("*/*.md")` both yield nothing; `artifact_paths` empty; loop body skipped; `has_non_verify_artifacts` stays False → no completeness CRITICAL. Returns `[]`. No regression.
4. **Nested dir with only non-artifact files** (e.g. `.elicit/changes/foo/notes.md`, `README.md`) → discovered by `*/*.md` pass, but `PHASE_PATTERN.match` fails on each name → all `continue` → zero findings. Scoping preserved one level deep.
5. **Agent file with no frontmatter** (`text` doesn't start with `---`) → `_extract_agent_tools` returns `(None, frozenset())` → name-mismatch FAIL (name None ≠ slug) surfaces it as drift rather than silently passing.
6. **Deeper nesting than one level** (`.elicit/a/b/map-*.md`) → NOT covered by `*/*.md` (single level only). This is intentional and matches proposal scope ("one subdir level"). Documented as a known boundary, not a bug — adding `**/*.md` would be a larger bar than the proposal authorized.

## Risks / unresolved

- R2 RED ⇒ genuine `upsert_node` isolation bug → ESCALATE, do not silence (proposal risk 4).
- AGENT_FLOW.md count must be measured at apply time, not copied from this doc's "10" estimate (it depends on real tree state).
- One-level subdir scope (`*/*.md`) is a deliberate boundary; deeper nesting stays unscanned by design.
- No grounding cascade: `harness_check.py` does not feed the grounding drift guard, so no `grounding.py`/ontology edits are pulled in (stays inside out-of-scope fence).
```
