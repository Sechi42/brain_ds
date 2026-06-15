# Exploration: brainds-live-agentic-cycle-validation

Artifact store: brain_ds-hybrid. Engram: `sdd/brainds-live-agentic-cycle-validation/explore` (#2147).

## Why this change exists
- #2143 — Design and TEST live brain_ds orchestrator behavior (real isolated sub-agents writing to `.elicit`), not just deterministic in-process doubles.
- #2145 — Model the workflow as ONE linear pipeline (Gentle AI style): `setup → intake → map → brd → verify → archive`, with `intake` as the branching phase (datasource path + human/org path).
- Predecessor `brainds-harness-orchestrator-flow-hardening` (archived) built the in-process deterministic dry-run (synthetic SQLite fixture, temp `.elicit/`, `elicit_compliance` verifier).

## Current State
- Delegation: `brainds-orchestrator` (opus) coordinates 6 sub-agents via Claude Code `Task`. `DELEGATION_PROTOCOL` in `grounding.py` is the cross-client source of truth (keys: role, session_setup, artifact_keys, handoff_rule, source_exploration_flow, skill_scope).
- In-process dry-run: `tests/conftest.py:dry_run_elicit_output` calls MCP tool functions directly and writes `.elicit/` files to `tmp_path`. "Handoffs" are Python dicts (`{"agent","prompt"}`) — no real `Task()` call. `brain_ds/verify/elicit_compliance.py` verifies artifacts structurally.
- Flow shape: 4 numbered phases in orchestrator prompt (Elicit → Data Source Deep Dive → Map → BRD). No named pipeline stages, no `verify`/`archive` stage.
- `harness_check.py` gap: CLAUDE.md references `SUBAGENT_NAMES`/`CLAUDE_AGENT_FILES` but they do not exist yet.

## Gap Analysis
1. Live sub-agent + `.elicit` verification: zero tests exercise real sub-agent launches; the seam is at the artifact/prompt boundary, not the `Task` call (no Python hook for native `Task`).
2. Linear pipeline: no `PIPELINE_STAGES` concept; flow is implicit in prose across orchestrator prompts.

## Approaches

### Requirement 1 — Live sub-agent + .elicit verification
| Approach | Pros | Cons | Effort |
|---|---|---|---|
| 1A subprocess CLI call | truly live | non-deterministic, needs API key, flaky TDD | High |
| **1B `LiveDelegationHarness` + `FakeDelegator` (REC)** | TDD-testable, exercises prompt shape, reuses compliance checker, CI-stable | doesn't test LLM quality | Medium |
| 1C recorded replay artifacts | real artifacts, no API calls | drift, no prompt-shape verification | Medium |

### Requirement 2 — Linear pipeline shape
| Approach | Pros | Cons | Effort |
|---|---|---|---|
| 2A rename keys + docs only | low impact | not cross-client | Low |
| **2B `PIPELINE_STAGES` constant in all grounding payloads (REC)** | cross-client source of truth, drift-guarded | mirrors must update together | Medium |
| 2C orchestrator prompt only | fastest | not cross-client, untestable | Very Low |

## Recommendation — two slices, strict TDD
- **Slice 1 (linear pipeline)**: add `PIPELINE_STAGES` Category-2 constant + `pipeline_stages`/`intake_paths` keys in `DELEGATION_PROTOCOL` → RED `test_elicit_lifecycle.py` `REQUIRED_PROTOCOL_KEYS` → update docs/SDD_FLOW.md, AGENT_FLOW.md, `.elicit/README.md`, orchestrator prompts, skill mirrors.
- **Slice 2 (live delegation harness)**: add `LiveDelegationHarness` protocol + `FakeDelegator` → refactor `conftest.py` `dry_run_elicit_output` → RED prompt-shape assertion tests → optional `check_agent_files()` in `harness_check.py`.

## Open decisions for proposal
- (a) exact shape of `PIPELINE_STAGES` dict
- (b) `verify` stage semantics: auto-run `check_elicit_compliance` vs label-only
- (c) `SUBAGENT_NAMES`/`CLAUDE_AGENT_FILES` in scope or follow-up
- (d) `intake_paths` key structure

## Risks
1. `FakeDelegator` seam at artifact/prompt boundary, not `Task` level — "live" = real artifact shape + compliance, not real LLM output.
2. Same-change rule cascade: `PIPELINE_STAGES` touches ~8-10 files in one commit (grounding.py + 3 composers + 3 skill mirrors + 2 orchestrator prompts + AGENT_FLOW.md + docs/SDD_FLOW.md).
3. `SUBAGENT_NAMES`/`CLAUDE_AGENT_FILES` scope decision.
4. `verify` stage semantics ambiguity.
5. `intake_paths` key shape must not make test guards brittle.
6. new Category-2 constant must be declared in drift guard or `CATEGORY2_EXEMPT`.

## Affected files
grounding.py, conftest.py, elicit_compliance.py, test_dryrun_elicit_compliance.py, test_elicit_lifecycle.py, test_grounding_drift_guard.py, harness_check.py, test_harness_check.py, docs/SDD_FLOW.md, AGENT_FLOW.md, .elicit/README.md, .claude/agents/brainds-orchestrator.md, prompts/brain-ds-orchestrator.md, skills/*/SKILL.md (+ .opencode mirror).
