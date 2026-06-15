# Proposal: brain_ds Harness / Orchestrator Flow Hardening

> Status: REVISED (v2). Supersedes v1. Hybrid artifact store: this file +
> Engram topic `sdd/brainds-harness-orchestrator-flow-hardening/proposal`.

## 1. Intent / Problem Statement

The brain_ds orchestration flow (ontology -> MCP grounding harness -> drift
guard -> brain_ds skills -> orchestrator/sub-agent delegation) is mature but
UNHARDENED. Concrete weaknesses make it fragile, and there is no end-to-end
behavioral check that the harness actually produces correct artifacts when the
real sub-agents run against it:

1. A HIGH-risk skill conflict: `brainds-docs/SKILL.md` (card_sections order
   starts at 1, icon from a fixed list) directly contradicts the BRD
   persistence contract (order:0, icon:""). Any session where both skills load
   will corrupt `/generate-brd --save` and break the UI BRD panel.
2. The BRD render path (`brd-panel.ts`, ~471 lines) — wikilink resolution,
   freshness chip, save round-trip — is ENTIRELY untested.
3. The drift guard covers only 3 of ~20 Category-2 constants in `grounding.py`,
   so most harness/skill prose can silently drift from the ontology.
4. The `.elicit/` grounding artifact store referenced by `DELEGATION_PROTOCOL`
   has no formal structure or archive lifecycle.
5. The SDD/orchestration flow is encoded only in `DELEGATION_PROTOCOL` Python
   constants — there is no human-facing document grounded in it.
6. The data-source cycle is half-built: there is read-only SQLite exploration
   but NO secret/credential contract, so connected sources requiring auth
   cannot be modeled or exercised.
7. The skill-registry is out of sync with the agent roster: all 6 brain_ds
   sub-agents exist (defined in `.claude/agents/` and documented in
   `AGENT_FLOW.md`), but `.atl/skill-registry.md` documents only 2 of the 6.

Why now: this is the FIRST SDD cycle for the project. We separate an URGENT
harness fix (Slice 1) from building out the brain_ds cycle operating system
(Slices 2-4), hardening before more skills/tools accrete and prevent compounding
drift and silent BRD corruption.

Success looks like: the brainds-docs/BRD conflict is definitively resolved with
a recurrence guard; the BRD render path has e2e coverage; the drift guard covers
ALL Category-2 constants; `.elicit/` is a formalized, documented store with an
archive lifecycle; the SDD flow is documented and the skill-registry matches
`AGENT_FLOW.md`; read-only datasource access has a secret contract; AND a
context-isolated live sub-agent dry-run produces `.elicit/` artifacts that
sdd-verify confirms comply with every harness spec.

## 2. Framing: urgent fix vs. cycle operating system

This change deliberately splits into two halves so review stays inside the
~400-line-per-PR budget and the urgent fix is not held hostage by the larger
build-out:

- **Slice 1 = the URGENT harness fix.** Self-contained correctness work that
  must land first regardless of the rest.
- **Slices 2-4 = the brain_ds cycle operating system.** The `.elicit/`
  lifecycle, datasource secret contract, and the live multi-agent dry-run that
  proves the harness end-to-end.

Each slice is an independently reviewable chained/stacked PR.

## 3. Scope — four slices

### Slice 1 — BRD contract + tests (URGENT) [no dependencies]

In-scope:
- Resolve the `brainds-docs` / BRD persistence conflict (HIGH) definitively so an
  agent loading both `brainds-docs` and `generate-brd` cannot corrupt a BRD node.
  BRD node uses node_id=`brd-<slug>`, type:"Unknown",
  card_sections[0]={title:"Contenido", order:0, icon:""}. Leading mechanism: a
  carve-out in `brainds-docs` for BRD/Unknown nodes; final mechanism decided in
  sdd-design.
- Add a **recurrence-guard test** that goes red if the two contracts diverge again.
- Add a **BRD render-contract e2e test** for `brd-panel.ts`: wikilink resolution,
  freshness chip rendering, and save round-trip (UI write -> persistence contract
  -> re-render).
- Expand the drift guard (`tests/test_grounding_drift_guard.py`) to cover ALL
  Category-2 constants: BRD_SECTION_ORDER, SECTION_RULES, TWO_PHASE_MAPPING,
  CONNECTION_RULES, COMPLETENESS_MATRIX_TEMPLATE, DELEGATION_PROTOCOL,
  NODE_WRITE_TEMPLATES, QUESTION_BANK, dataset_fingerprint_order, and the
  remaining ~20.

Acceptance criteria:
- AC1.1: With both `brainds-docs` and `generate-brd` loaded, `/generate-brd --save`
  produces a BRD node with card_sections[0]={order:0, icon:""} and the UI panel
  renders it without error.
- AC1.2: A recurrence guard fails (red) if the brainds-docs ordering/icon rules and
  the BRD persistence contract diverge again.
- AC1.3: A BRD render-contract e2e test exists and passes (wikilink, freshness chip,
  save round-trip).
- AC1.4: The drift guard fails (red) if ANY Category-2 constant drifts; coverage
  includes all ~20 constants, verified by enumeration.
- AC1.5: tool count remains 22; `brain_ds check`, `test_harness_check.py`,
  `test_grounding_drift_guard.py`, and the BRD persistence/UI parity test stay green;
  `skills/*` and `.opencode/skills/*` mirrors stay consistent.

### Slice 2 — `.elicit/` lifecycle + archive + flow docs [depends on Slice 1]

In-scope:
- Formalize the `.elicit/` structure as the grounding artifact store, matching
  `DELEGATION_PROTOCOL.artifact_keys` (elicit_file = `.elicit/<phase>-<slug>-<ISO-date>.md`;
  phases = elicit, source-exploration, source-docs, map, brd). Document layout,
  naming, per-sub-agent contract (which agent writes which phase file), and the
  **archive lifecycle** (how a completed cycle's `.elicit/` artifacts are closed/retained).
- Document the SDD/orchestration flow grounded in the `DELEGATION_PROTOCOL`
  constants in `grounding.py` (role, session_setup, artifact_keys, handoff_rule,
  source_exploration_flow, skill_scope).
- **Synchronize `.atl/skill-registry.md` with `AGENT_FLOW.md`** so all 6 brain_ds
  sub-agents are documented (Correction 3). NOTE: the agents already exist in
  `.claude/agents/`; this is a documentation-sync task, NOT agent creation.

Acceptance criteria:
- AC2.1: `.elicit/` has a documented, formalized structure consistent with
  `DELEGATION_PROTOCOL.artifact_keys`, including per-sub-agent write ownership and
  an archive lifecycle.
- AC2.2: A flow document exists, grounded in and consistent with the
  `DELEGATION_PROTOCOL` constants.
- AC2.3: `.atl/skill-registry.md` documents all 6 brain_ds sub-agents
  (brainds-orchestrator, brainds-source-explorer, brainds-query-consultant,
  brainds-graph-mapper, brainds-connection-mapper, brainds-brd-writer), matching
  `AGENT_FLOW.md`.

### Slice 3 — datasource read-only access + secret contract [depends on Slice 2]

In-scope (Correction 2 — REVERSED from v1's deferral):
- Define a **read-only datasource access + secret contract**: how a connected
  source declares required credentials, where secrets are sourced (env var /
  reference, never inlined into the store or `.elicit/` artifacts), and how
  read-only enforcement (PRAGMA query_only, mode=ro URI, path sandbox) composes
  with authenticated sources.
- Surface the secret contract in the harness so sub-agents know how to request /
  reference credentials during `list_source_connections` -> `explore_source`
  without ever persisting raw secrets.

Acceptance criteria:
- AC3.1: A documented read-only datasource access + secret contract exists and is
  reflected in the harness grounding.
- AC3.2: Secrets are referenced, never persisted into the store or `.elicit/`
  artifacts; a guard/test asserts no raw secret leaks into persisted output.
- AC3.3: Read-only enforcement still holds for authenticated sources.

Rationale for moving in-scope: without it the datasource cycle is half-built —
Slice 4's dry-run can only exercise an unauthenticated synthetic source, leaving
the authenticated path unspecified and untested.

### Slice 4 — multi-agent dry-run + verify [depends on Slices 1-3]

In-scope:
- The brainds-orchestrator launches the brain_ds sub-agents
  (brainds-source-explorer, brainds-graph-mapper, brainds-connection-mapper,
  brainds-brd-writer, brainds-query-consultant) against a FICTITIOUS / synthetic
  data source (small synthetic SQLite or CSV), **context-isolated** — sub-agents
  get NO other context, only artifact references + the synthetic source. They
  exercise the full cycle: `list_source_connections` -> `explore_source`
  magnitude scan -> sectioned documentation (hierarchy_template) -> map-connections
  (two-phase) -> generate-brd as applicable, writing ALL findings into `.elicit/`.
- sdd-verify inspects the `.elicit/` files and validates them against the harness
  specs.
- Optionally adapt the judgment-day flow for adversarial review of the dry-run
  output.

Acceptance criteria:
- AC4.1: The orchestrator-launched sub-agents complete the full exploration cycle on
  the synthetic source, context-isolated, and write artifacts into `.elicit/` only.
- AC4.2: sdd-verify inspects the `.elicit/` files and confirms compliance with:
  (a) brainds-docs documentation format, (b) the completeness gate
  (`assess_completeness`) recommendation, (c) the BRD persistence contract
  (order:0, icon:"", node_id `brd-<slug>`, type "Unknown") where a BRD is produced,
  and (d) the formalized `.elicit/` structure/naming from Slice 2. Non-compliance is
  a CRITICAL verify finding.

### Slice dependencies

- Slice 1 -> Slice 2 -> Slice 3 -> Slice 4 is the sane order.
- Slice 1 is fully independent and is the urgent landing target.
- Possible parallelization once Slice 1 is merged: Slice 2 (docs/registry) and the
  Slice 3 secret-contract DESIGN can be drafted in parallel, but Slice 3's harness
  surfacing should land after Slice 2 formalizes `.elicit/` (so secret-referencing
  rules can cite the structure). Slice 4 strictly requires 1-3 because its verify
  step asserts against the `.elicit/` structure (Slice 2) and the secret contract
  (Slice 3).

### Out-of-scope (explicit)

- EntityType.from_string() silent fallback to Unknown for typos (LOW) — not a
  harness-integrity blocker; defer.
- Adding new EntityTypes, RelationshipTypes, scoring factors, or MCP tools (none
  required; tool count stays 22).
- Non-SQLite connector backends (the secret contract is defined generically but
  only the SQLite path is implemented/exercised this cycle).

## 4. Approach

**Slice 1 (static correctness).** Resolve the brainds-docs/BRD contract conflict
at the skill level (carve-out for BRD/Unknown nodes is the leading candidate;
final mechanism in design) with a recurrence guard. Add an e2e Playwright test
for the BRD panel render contract. Generalize the drift guard so every Category-2
constant in `grounding.py` is asserted against its source of truth.

**Slice 2 (cycle OS — docs/lifecycle).** Create and document `.elicit/` per
`DELEGATION_PROTOCOL.artifact_keys` with per-sub-agent ownership and archive
lifecycle. Write the flow document derived from `DELEGATION_PROTOCOL`. Sync
`.atl/skill-registry.md` to `AGENT_FLOW.md`.

**Slice 3 (cycle OS — secrets).** Define the read-only datasource access + secret
contract, surface it in the harness, and guard against secret persistence.

**Slice 4 (cycle OS — behavioral proof).** The context-isolated multi-agent
dry-run against a synthetic source produces `.elicit/` artifacts; sdd-verify is the
acceptance gate against every harness spec.

## 5. Cross-phase constraints (later phases MUST honor)

- **sdd-design and sdd-apply MUST read the `skill-creator` skill BEFORE authoring
  or modifying ANY SKILL.md**, so skills are written to spec.
- Any skill change MUST keep `skills/*/SKILL.md` and `.opencode/skills/*/SKILL.md`
  mirrors consistent (CLAUDE.md "Harness maintenance").
- **strict_tdd is ACTIVE** (pytest / ruff / mypy / playwright): apply and verify run
  under Strict TDD Mode — tests first, no fallback to Standard Mode.
- The CLAUDE.md "Harness maintenance (MANDATORY)" contract must be preserved:
  changes to skill prose, persistence contract, delegation model, or UI BRD panel
  must update all mirrors and guards in the same change (tool count 22, drift guards,
  BRD UI parity).

## 6. Risks + Mitigations

- **HIGH — brainds-docs / BRD persistence conflict** WILL break `/generate-brd --save`
  where both skills load. Mitigation: Slice 1 resolves it definitively (carve-out for
  BRD/Unknown nodes preferred) AND adds a recurrence guard (AC1.2) so it cannot recur;
  verify via the Slice 4 dry-run if a BRD is produced.
- **MEDIUM — BRD render contract entirely untested.** Mitigation: AC1.3 e2e test added
  under strict TDD before any brd-panel.ts change.
- LOW — Category-2 constants outgrowing the drift guard. Mitigation: AC1.4 makes the
  guard enumerate ALL constants, so new ones are caught.
- MEDIUM — secret handling correctness (Slice 3). Mitigation: AC3.2 guards that no raw
  secret reaches the store or `.elicit/`; AC3.3 keeps read-only enforcement intact.
- Process risk — sub-agent dry-run context isolation: sub-agents must have NO access to
  other context. Mitigation: orchestrator passes only artifact references + the
  synthetic source; design specifies the isolation boundary.
- Process risk — review budget. Mitigation: 4 chained/stacked PRs, each independently
  reviewable, keep diffs near the ~400-line budget.

## 7. Affected areas / files

- Skills: `.opencode/skills/brainds-docs/SKILL.md` (+ `skills/` mirror),
  `.opencode/skills/generate-brd/SKILL.md` (+ mirror),
  `.opencode/skills/map-connections/SKILL.md` (+ mirror)
- Harness: `brain_ds/mcp/grounding.py` (Category-2 constants, DELEGATION_PROTOCOL,
  BRD_GRAPH_PERSISTENCE_CONTRACT, secret contract surfacing), `brain_ds/mcp/tools.py`,
  `brain_ds/mcp/security.py`, `brain_ds/mcp/completeness.py`
- Ontology: `brain_ds/ontology/entity_types.py`, `relationship_types.py`, `graph_model.py`
- Scoring: `brain_ds/scoring/engine.py`, `similarity.py`
- Connectors: `brain_ds/connectors/sqlite_connector.py`, `__init__.py` (secret contract +
  synthetic source for dry-run)
- API/UI: `brain_ds/api/routes.py`, `brain_ds/ui/server.py`, `render_context.py`,
  `template_renderer.py`, `src/panels/brd-panel.ts`, `src/panels/markdown-mini.ts`,
  `e2e/smoke.spec.ts`, `ecosystem.spec.ts` (new BRD render e2e)
- Tests/guards: `tests/test_grounding_drift_guard.py`, `tests/test_mcp_grounding.py`,
  `tests/test_harness_check.py`, `brain_ds/harness_check.py`
- Agents/registry/docs: `.claude/agents/brainds-*.md`, `prompts/brainds-*.md`,
  `AGENT_FLOW.md`, `.atl/skill-registry.md` (sync), flow document
- `.elicit/`: formalized structure + archive lifecycle;
  `.elicit/changes/brainds-harness-orchestrator-flow-hardening/` for cycle + dry-run output

## 8. Next phases

sdd-spec and sdd-design can run in parallel (both read this proposal). sdd-design must
read skill-creator. Then sdd-tasks -> sdd-apply -> sdd-verify (verify enforces AC4.1/AC4.2
against `.elicit/`). Recommend delivering as 4 chained/stacked PRs aligned to the slices.
