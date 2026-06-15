# Proposal: brainds-harness-integrity-guards

Change: `brainds-harness-integrity-guards`
Project: brain_ds
Artifact store: hybrid (engram + `.elicit/` mirror)
Strict TDD: active (`uv run pytest`)
Delivery: single PR, ~315 lines (under 400 budget), 3 logical commit groups

## Intent / Motivation

A live fire test (a real elicit → map → BRD run) exposed three integrity gaps in the
brain_ds agent harness, none of which were caught by automation:

1. **Agent-definition drift went uncaught.** During the live run the
   `brainds-connection-mapper` sub-agent appeared to lack the `Write` tool grant.
   The fix (adding `Write`) was applied **manually** and is only protected by a
   single string-grep test in `test_elicit_lifecycle.py`. There is no structural
   `brain_ds check` guard that audits each `.claude/agents/brainds-*.md` for
   presence, name match, and required tool grants. Worse: `CLAUDE.md` already
   documents `check_agent_files()`, `SUBAGENT_NAMES`, and `CLAUDE_AGENT_FILES` as
   if they exist — **they do not**. This is deferred debt the docs already promised.

2. **A node appeared to vanish.** In the live run an Organization node looked like
   it was dropped after `update_node` calls on a Data Source node. Investigation
   (see exploration) concluded the store upsert is **correct** (Python-level merge
   plus DB-level `COALESCE` targeted upsert) and the apparent drop was a
   filtered-view misread (`list_nodes(type="Data Source")`), not a store bug. But
   there is **no regression test** proving `update_node` on node A preserves an
   unrelated node B and its edges. The scare must become a permanent guard.

3. **Per-cycle artifacts are invisible to the verifier.** The `.elicit/` cleanup
   convention archives artifacts under `.elicit/changes/<change-name>/`, but
   `check_elicit_compliance()` uses a flat `glob("*.md")` and never descends one
   level. The forward path (writing new cycle artifacts into a subdir) is
   unsupported, and `PHASE_PATTERN` is duplicated between `elicit_compliance.py`
   and `test_elicit_lifecycle.py` (drift risk).

**Success looks like:** `brain_ds check` structurally audits every brain_ds
sub-agent definition; a regression test permanently proves graph-write isolation;
the elicit verifier sees per-cycle subdir artifacts without weakening any existing
rule; `CLAUDE.md`'s promised symbols become real; and `AGENT_FLOW.md`'s stale
"12 checks" claim is corrected to the true post-implementation count.

**Hard principle:** this SDD only ADDS guards. No existing verifier/guard bar is
lowered. README/scratch artifacts stay ignored; phase-named-but-broken artifacts
stay CRITICAL.

## Scope

### In scope
- `brain_ds/harness_check.py`: add `SUBAGENT_NAMES`, `CLAUDE_AGENT_FILES`,
  `check_agent_files()`; register it in `_run_all_checks()`.
- `tests/test_harness_check.py`: add `AgentFileCheckTests` (RED-first).
- `tests/test_mcp_tools.py`: add a graph-write integrity regression test.
- `brain_ds/verify/elicit_compliance.py`: additive two-pass glob in
  `check_elicit_compliance()`.
- `tests/test_elicit_lifecycle.py`: import canonical `PHASE_PATTERN` from
  `elicit_compliance.py` (kill the duplicate); cover subdir artifacts.
- `tests/conftest.py` / `tests/test_dryrun_elicit_compliance.py`: subdir fixture
  variant if needed by the subdir tests.
- `AGENT_FLOW.md`: replace the stale "12 checks" claim with the real count after
  implementation.

### Out of scope (explicit)
- Changing any `grounding.py` constant (Category-1/Category-2 harness context). No
  cascade — `harness_check.py` does not feed the grounding drift guard.
- Any `EntityType` or `RelationshipType` change (and therefore no
  `test_grounding_drift_guard.py` work).
- Creating the `prompts/brainds-query-consultant.md` mirror. It stays PENDING; the
  new check must SKIP/WARN for it, never FAIL.
- Editing any `.claude/agents/brainds-*.md` or `prompts/brainds-*.md` content
  (read-only for the checks).
- Any change to the full-replace `save_graph()` / `import_graph` path — out of
  scope; graph-mapper has no `import_graph` grant by design.

## Requirements (the three capabilities)

### R1 — Agent-definition guards (Capability 1)
`brain_ds check` MUST audit every brain_ds sub-agent. Implement in
`harness_check.py`:
- `SUBAGENT_NAMES`: the 5 functional sub-agents
  (`brainds-source-explorer`, `brainds-graph-mapper`, `brainds-connection-mapper`,
  `brainds-brd-writer`, `brainds-query-consultant`) plus orchestrator handling as
  appropriate; `CLAUDE_AGENT_FILES`: the `.claude/agents/brainds-*.md` paths.
- `check_agent_files()` MUST verify, per agent:
  1. The `.claude/agents/brainds-*.md` file is present → FAIL if missing.
  2. The frontmatter `name:` matches the filename slug → FAIL on mismatch.
  3. Required tool grants present (FAIL if absent):
     - `connection-mapper` → `Write`
     - `brd-writer` → `Write` + `generate_brd`
     - `source-explorer` → `Write` + connector tools
     - `graph-mapper` → `update_node` + `add_edge` (NO `Write` — by design)
  4. Prompt mirror in `prompts/` present where it should exist. The orchestrator
     mirror is named `brain-ds-orchestrator.md` (note the hyphen). The
     `query-consultant` prompt mirror is **PENDING** → SKIP/WARN, never FAIL.
- Register `check_agent_files` in `_run_all_checks()`.

### R2 — Graph-write integrity (Capability 2)
Add a regression test in `tests/test_mcp_tools.py` (isolated temp store, same
pattern as `MCPToolsTests`) that:
1. Creates node A and an unrelated node B, plus an edge on B.
2. Calls `update_node` on A.
3. Asserts B and B's edge are byte-for-byte intact.
The store upsert is believed correct; the test confirms it. **If RED, escalate as
a real `upsert_node` bug** — do not paper over it.

### R3 — Per-cycle subdir scoping (Capability 3)
Extend `check_elicit_compliance()` with an additive two-pass glob:
`elicit_dir.glob("*.md")` ∪ `elicit_dir.glob("*/*.md")`, merged + deduplicated.
- Backward-compatible: flat-only callers see no behavior change.
- Import canonical `PHASE_PATTERN` from `elicit_compliance.py` into
  `test_elicit_lifecycle.py` to eliminate the duplicated pattern.
- Do NOT weaken scoping: README/scratch still ignored; phase-named-but-broken
  artifacts still CRITICAL — now also inside one level of subdir.

## Approach (LOCKED — not re-litigated)

- **R1 → Approach C**: regex-extract the frontmatter block between the first
  `---` delimiters; parse the tools list with `re` (no PyYAML / no new dep). Read
  with `utf-8-sig` and normalize CRLF before split (consistent with `_load_json`).
  Validate tool presence via set membership.
- **R2 → Approach A**: regression test only; no production-code change expected.
  The COALESCE targeted upsert is the existing safety; the test is the guard.
- **R3 → Approach A**: additive two-pass glob; non-breaking; `PHASE_PATTERN`
  already matches on filename regardless of parent dir.

### Rationale
Approach C keeps the zero-external-dep style of the codebase while being far less
fragile than string-grep (it scopes parsing to the bounded frontmatter block).
Approach A (R2) reflects the exploration's confirmed finding that the store is
correct — the value is a permanent CI net, not a fix. Approach A (R3) is the only
option that preserves every existing caller's behavior with a one-line glob change.

## Delivery decision (single PR)

Total estimate ~315 lines, under the 400 budget; delivery strategy `ask-on-risk`
resolves to a **single PR** with three logical commit groups, ordered **B → A → C**
per the exploration (smallest/safest first):
1. **Commit B** — R2 graph-write integrity regression test (~40 lines, no prod
   code, easiest green; proves the pattern).
2. **Commit A** — R1 agent-definition guards (~200 lines: harness_check.py + tests;
   most impactful).
3. **Commit C** — R3 subdir scoping (~75 lines: additive glob + canonical
   `PHASE_PATTERN` import + tests).

The three slices are fully independent (no shared code path). All MUST go RED
first under strict TDD before implementation.

## Risks / open questions

1. **Frontmatter brittleness (R1)**: BOM/CRLF/leading whitespace before `---`.
   Mitigation: `utf-8-sig` read + CRLF strip before split (locked into Approach C).
2. **query-consultant prompt mirror missing (R1)**: must SKIP/WARN, never FAIL —
   it is intentionally PENDING. Enforced by the requirement; needs a SKIP-path test.
3. **"12 checks" claim accuracy (R1)**: after `check_agent_files()` the runner
   yields ~8–10 CheckResults, NOT 12. `AGENT_FLOW.md` MUST be set to the *real*
   count measured after implementation — do not hardcode 12.
4. **R2 escalation path**: if the regression test is RED, it signals a genuine
   `upsert_node` bug — that would expand scope and must be surfaced, not silenced.
5. **R3 caller compatibility**: `test_dryrun_elicit_compliance.py` calls
   `check_elicit_compliance(...)` directly; the additive glob keeps it green when
   no subdirs exist — verify in the RED/GREEN cycle.
6. **No grounding cascade**: confirmed — `harness_check.py` changes do not touch
   `grounding.py` or the EntityType/RelationshipType drift guard.

## Next phases
`sdd-spec` and `sdd-design` (can run in parallel) → `sdd-tasks` → `sdd-apply`.
