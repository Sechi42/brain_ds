# Proposal: brainds-live-agentic-cycle-validation

Artifact store: brain_ds-hybrid. Engram topic key: `sdd/brainds-live-agentic-cycle-validation/proposal`.
Reads: `sdd/brainds-live-agentic-cycle-validation/explore` (#2147).

## Intent / Why

Two requirements, both in scope, framed by the user as "make the agentic cycle a real,
observable, testable linear pipeline":

1. **Live sub-agent + `.elicit` verification.** Today the only coverage is the predecessor's
   in-process deterministic dry-run (`conftest.py:dry_run_elicit_output`): MCP tool functions
   are called directly and "handoffs" are plain `{"agent","prompt"}` dicts — no real delegation
   boundary is exercised. We want a strict-TDD-testable seam (`LiveDelegationHarness` /
   `FakeDelegator`) at the **artifact/prompt boundary**, because the native Claude Code `Task`
   call has no Python hook. "Live" here means real artifact shape + real `check_elicit_compliance`
   over a real `.elicit/<cycle>` directory — not a live LLM call.

2. **Linear pipeline shape as a cross-client constant.** Right now the flow is implicit prose
   spread across orchestrator prompts. The user wants ONE linear pipeline
   `setup → intake → map → brd → verify → archive` encoded as a `PIPELINE_STAGES` constant in
   `grounding.py`, propagated to every client (skills, prompts, docs) and drift-guarded — the same
   discipline `DELEGATION_PROTOCOL` already has.

The keystone of the pipeline is the **`verify` stage as an Auto-run minimalista (observable
gate)**: the orchestrator runs `check_elicit_compliance(.elicit/<cycle>)`, writes
`.elicit/verify-<org-slug>-<date>.md`, and only archives if verify passes.

## Scope

### In scope
- `PIPELINE_STAGES` Category-2 constant in `grounding.py` (6 linear stages + `intake_paths` branch model).
- `pipeline_stages` + `intake_paths` keys threaded into `DELEGATION_PROTOCOL` (or referenced from it).
- `verify` and `archive` as **explicit** pipeline stages; `verify` = auto-run `check_elicit_compliance`
  producing `.elicit/verify-<org-slug>-<date>.md`; gate blocks archive on failure.
- `LiveDelegationHarness` protocol + `FakeDelegator` test double at the artifact/prompt seam;
  refactor `conftest.py:dry_run_elicit_output` to route handoffs through it.
- Prompt-shape assertion tests (delegation prompt carries the right artifact refs + stage).
- Cascade: byte-identical skill mirrors, orchestrator prompt mirrors, docs, AGENT_FLOW.md.
- Drift-guard registration of the new constant.
- Extend the lifecycle naming contract to admit `verify`/`archive` (+ optional `setup`/`intake`)
  artifact prefixes so the gate artifact is legal.

### Out of scope (explicit)
- **No subprocess / live-LLM calls in CI.** The seam stops at the artifact/prompt boundary.
- **No mega-verifier.** REUSE `brain_ds/verify/elicit_compliance.py::check_elicit_compliance`;
  do NOT build a parallel validation engine.
- **Nothing that breaks the byte-identical `skills/` ↔ `.opencode/skills/` mirror contract.**
- **No new sub-agents.** The 6 known agents stay as-is; `intake` branches across existing agents.
- Live evaluation of LLM *output quality* (that is a human-review concern, not a test).

## Approach

Endorse the exploration's two-slice, strict-TDD path. Slice 1 lands the linear pipeline as a
cross-client constant plus the explicit `verify`/`archive` stages; Slice 2 lands the delegation
seam and exercises the verify gate through it.

### Slice 1 — Linear pipeline + verify/archive stages
1. RED: add the new `PIPELINE_STAGES` expectation to `test_elicit_lifecycle.py` (and a drift-guard
   classification entry) — they go red because the constant and the verify/archive prefixes don't exist.
2. GREEN: add `PIPELINE_STAGES` to `grounding.py`; add `pipeline_stages` + `intake_paths` to the
   delegation surface; extend `ALLOWED_PHASES` / `ELICIT_NAME_PATTERN` / `PHASE_PATTERN`
   (`elicit_compliance.py`) to admit `verify` (and `setup`/`intake`/`archive` as needed).
3. CASCADE: update the skill mirrors, orchestrator prompts, `docs/SDD_FLOW.md`, `AGENT_FLOW.md`,
   `.elicit/README.md` — all in the SAME commit (same-change rule).

### Slice 2 — Live delegation harness + verify gate exercised
1. RED: prompt-shape tests asserting each handoff prompt carries `{agent, artifact refs, stage}`
   and that the `verify` stage runs `check_elicit_compliance` and gates archive.
2. GREEN: introduce `LiveDelegationHarness` Protocol + `FakeDelegator`; refactor
   `dry_run_elicit_output` so `handoff(...)` goes through the delegator; add the verify step that
   calls `check_elicit_compliance(elicit_dir)` and only writes/permits `archive-*` when findings
   are empty.

**Where the verify Auto-run gate lives:** its *definition* (stage semantics, artifact name,
gate-blocks-archive rule) is part of Slice 1's `PIPELINE_STAGES`; its *exercised behavior*
(run `check_elicit_compliance`, assert pass→archive / fail→block) is Slice 2's harness test.

## Resolved decisions

### (a) Shape of `PIPELINE_STAGES`
**Recommendation:** a flat ordered list of stage dicts, with `intake` carrying a nested
`intake_paths` map. Stage values are PROSE-only (descriptions + agent names already covered by
`KNOWN_AGENTS`), so the drift sweep stays non-brittle.

```python
PIPELINE_STAGES: list[dict[str, object]] = [
    {"stage": "setup", "description": "...", "agents": ["brainds-orchestrator"]},
    {"stage": "intake", "description": "Branching stage: datasource and/or human/org intake.",
     "agents": ["brainds-orchestrator"],
     "intake_paths": {
         "datasource": ["brainds-source-explorer", "brainds-graph-mapper"],
         "human_org":  ["brainds-orchestrator", "brainds-graph-mapper"]}},
    {"stage": "map",     "description": "...", "agents": ["brainds-connection-mapper"]},
    {"stage": "brd",     "description": "...", "agents": ["brainds-brd-writer"]},
    {"stage": "verify",  "description": "Auto-run check_elicit_compliance(.elicit/<cycle>); "
                                        "writes verify-<org-slug>-<date>.md; blocks archive on failure.",
     "agents": ["brainds-orchestrator"]},
    {"stage": "archive", "description": "...", "agents": ["brainds-orchestrator"]},
]
```
*Rationale:* a list preserves linear order for free; the lifecycle test can assert
`[s["stage"] for s in PIPELINE_STAGES] == EXPECTED_ORDER` (one strong, non-brittle invariant).
Agent names are already-real strings (no new entity tokens), keeping the Category-2 sweep clean.

### (c) `SUBAGENT_NAMES` / `CLAUDE_AGENT_FILES` / `check_agent_files()` in `harness_check.py`
**Recommendation: DEFER to a follow-up — do NOT implement in this change.**
*Rationale:* consistent with "Auto-run minimalista." These symbols are referenced by `CLAUDE.md`
prose but nothing imports them, and `test_elicit_lifecycle.py` already enforces the 6-agent roster
via `KNOWN_AGENTS` against `.atl/skill-registry.md` + `AGENT_FLOW.md`. Adding a parallel agent-file
parity checker now is scope creep that does not serve either requirement. We will note the gap in
risks; if reviewers insist, it is a clean independent slice.

### (d) `intake_paths` key structure
**Recommendation:** a dict with two named keys `datasource` and `human_org`, each mapping to an
ordered list of agent names (the branch's sub-pipeline). Nested under the `intake` stage entry
(see (a)).
*Rationale:* names the two branches explicitly (matches the locked decision), keeps each branch
as a small ordered list the harness can assert against, and avoids inventing a richer schema that
would make guards brittle. `datasource` = `source-explorer → source-docs → graph-mapper`;
`human_org` = `elicit → graph-mapper` (expressed as agent ownership).

### Drift-guard handling for `PIPELINE_STAGES`
**Recommendation: list it in the active sweep, NOT in `CATEGORY2_EXEMPT`.**
*Rationale:* `PIPELINE_STAGES` contains free prose and agent names but NO graph-entity-type
literals, so the `_sweep_constant` token check passes cleanly. Letting it be swept gives us free
protection if someone later pastes an EntityType into a stage description. (If a description ever
*must* contain an entity-like CamelCase token, add it to `SAFE_ENTITYISH_TOKENS`, not to the
exempt set.) `test_every_category2_constant_is_classified` auto-discovers it; since it's a `list`
of `dict`, it qualifies — we simply do NOT add it to `CATEGORY2_EXEMPT`, and it falls into the
swept bucket automatically. No test edit needed beyond confirming green.

## Same-change cascade plan (~8–10 files, one commit per slice deliverable)

`PIPELINE_STAGES` / pipeline-shape changes touch:

| # | File | Change |
|---|------|--------|
| 1 | `brain_ds/mcp/grounding.py` | add `PIPELINE_STAGES`; add `pipeline_stages`/`intake_paths` keys |
| 2 | `brain_ds/verify/elicit_compliance.py` | `PHASE_PATTERN` admits `verify` (+ `setup`/`intake`/`archive`) |
| 3 | `tests/test_elicit_lifecycle.py` | `ALLOWED_PHASES`/`ELICIT_NAME_PATTERN` + `PIPELINE_STAGES` order assertion |
| 4 | `tests/test_grounding_drift_guard.py` | confirm new constant swept (no edit unless green needs it) |
| 5 | `docs/SDD_FLOW.md` | document 6 linear stages + verify gate |
| 6 | `AGENT_FLOW.md` | mirror pipeline + intake branches |
| 7 | `.elicit/README.md` | lifecycle table includes verify/archive |
| 8 | `skills/*/SKILL.md` | mirror pipeline prose where relevant |
| 9 | `.opencode/skills/*/SKILL.md` | **byte-identical** mirror of #8 |
| 10 | `prompts/brain-ds-orchestrator.md` + `.claude/agents/brainds-orchestrator.md` | name the linear stages |

**Mirror discipline:** edit `skills/<name>/SKILL.md` first, then copy bytes verbatim to
`.opencode/skills/<name>/SKILL.md`; `check_skills_mirror()` and the registry's byte-identical rule
are the guard. Run `/share-brainds` after skill edits.

## Risks & mitigations

| Risk | Mitigation |
|------|-----------|
| `verify-*` artifact fails current naming contract (`PHASE_PATTERN`/`ELICIT_NAME_PATTERN` exclude it) | Slice 1 explicitly extends both patterns — this is a RED-first step, not a surprise |
| "Live" overclaim — seam is artifact/prompt level, not real `Task`/LLM | Documented in scope; tests assert prompt SHAPE + compliance, never LLM quality |
| Cascade drift across 10 files / byte-identical mirrors | Same-commit rule; `check_skills_mirror`; `/share-brainds`; lifecycle + drift guards |
| New constant trips the Category-2 sweep | Prose+agent-names only; swept clean; `SAFE_ENTITYISH_TOKENS` escape hatch if ever needed |
| Deferring `SUBAGENT_NAMES`/`CLAUDE_AGENT_FILES` leaves CLAUDE.md referencing nonexistent symbols | Documented as known gap + clean follow-up slice; existing roster guard covers the real invariant |
| `intake` branch model makes lifecycle guards brittle | `intake_paths` = two named ordered lists; assert order, not full structure |

## Rough size / slice estimate (delivery strategy: ask-on-risk)

- **Slice 1 (linear pipeline + verify/archive stages + cascade):** ~250–350 changed lines, but
  spread across ~10 files including doc/prompt/skill prose. **Flag:** the cascade pushes this
  toward the 400-line budget. Recommend treating the doc/prompt/skill mirror updates as a
  reviewable sub-unit; if the total trips >400, split into "constant + tests + patterns" then
  "docs/prompts/skill mirrors" as stacked commits.
- **Slice 2 (`LiveDelegationHarness` + `FakeDelegator` + prompt-shape/verify-gate tests):**
  ~150–250 changed lines (mostly `conftest.py` refactor + new tests). Comfortably under budget.

**Recommendation:** ship as two chained PRs (Slice 1, then Slice 2). Surface the Slice-1
size risk to the maintainer before apply per ask-on-risk.
