# Design: brain_ds Harness / Orchestrator Flow Hardening

> Hybrid store: this file + Engram `sdd/brainds-harness-orchestrator-flow-hardening/design`.
> Reads proposal v2 (#2119). Covers all 4 slices. Delivered as 4 chained PRs.

## Technical Approach

Harden the existing harness in place — no new EntityTypes, RelationshipTypes,
scoring factors, or MCP tools (count stays 22). Slice 1 fixes correctness
(skill conflict + drift coverage + BRD e2e) under strict TDD. Slices 2-4 build
the cycle OS: `.elicit/` lifecycle, secret contract, and a context-isolated
multi-agent dry-run validated by sdd-verify. Every skill edit goes through the
`skill-creator` spec and keeps `skills/*` ↔ `.opencode/skills/*` byte-identical.
**sdd-apply MUST read skill-creator before editing any SKILL.md** (skill-creator
is not on disk; its compact rules in registry obs #154 are the authoritative spec
— frontmatter `name`/`description`/`license`/`metadata.author`/`metadata.version`,
Critical Patterns first, register in AGENTS.md).

## Architecture Decisions

### D1 — brainds-docs / BRD conflict resolution
| Option | Tradeoff | Decision |
|---|---|---|
| (a) Carve-out: brainds-docs exempts BRD/Unknown nodes (node_id `brd-*`, type `Unknown`) from the order≥1 + icon-list rules | Minimal blast radius; BRD contract stays sole owner of its node shape; both contracts coexist | **CHOSEN** |
| (b) Align both: change BRD to order≥1 + a real icon | Breaks brd-panel.ts (`s.order === 0`), grounding contract, UI parity test — large ripple | Rejected |

Rationale: the BRD persistence contract is already the source of truth read by
`brd-panel.ts` (line 69: `s.order === 0 || s.title === 'Contenido'`), grounding
`BRD_GRAPH_PERSISTENCE_CONTRACT`, and AGENT_FLOW. brainds-docs is the outlier.
Edit: add an explicit "BRD / Unknown carve-out" note in the brainds-docs
`card_sections Format` rules block stating order may be `0` and icon may be `""`
for the BRD node, deferring to BRD_GRAPH_PERSISTENCE_CONTRACT. Mirror in BOTH
`skills/brainds-docs/SKILL.md` and `.opencode/skills/brainds-docs/SKILL.md`, plus
the registry compact rule (#154 line "order is monotonically increasing from 1").

### D2 — Recurrence guard (where it lives)
| Option | Decision |
|---|---|
| Python test asserting brainds-docs carve-out text references the BRD order:0/icon:"" values AND that they equal `BRD_GRAPH_PERSISTENCE_CONTRACT.update_node_template.card_sections[0]` | **CHOSEN** — add to `tests/test_mcp_grounding.py` next to the existing UI-parity test |
Rationale: parity test already lives there; co-locate so the two BRD contracts
are guarded as one unit. Goes red if either contract drifts.

### D3 — Drift guard generalization (maintainable, not a list of 20)
| Option | Tradeoff | Decision |
|---|---|---|
| Reflection sweep: introspect `grounding` module, collect every Category-2 constant, recursively walk strings, assert any token matching an entity-name shape is a real `EntityType.value` | Self-maintaining: new constants auto-covered; no hardcoded list | **CHOSEN** |
| Hardcode all ~20 constant names | Drifts the moment a 21st is added | Rejected |

Rationale: build a `CATEGORY2_CONSTANTS` discovery helper that yields
`(name, value)` for module-level dict/list constants (excludes Category-1
`build_*` functions, which are enum-derived). A registry set
`CATEGORY2_EXEMPT` (analogous to `ELICIT_EXEMPT_TYPES`) names constants with no
entity refs. A meta-test asserts every discovered constant is either swept or
exempt — so a NEW constant fails until consciously classified. Entity-name
detection reuses `_entity_values()`; the sweep walks nested str/list/dict.

### D4 — `.elicit/` lifecycle ownership
Anchor on `DELEGATION_PROTOCOL.artifact_keys` (already in grounding): file
pattern `.elicit/<phase>-<slug>-<ISO-date>.md`, phases `elicit`,
`source-exploration`, `source-docs`, `map`, `brd`. Per-phase write owner maps to
AGENT_FLOW agents. Archive lifecycle: completed cycles move under
`.elicit/changes/<change-name>/` (the SDD convention already used by this very
change). Closes AGENT_FLOW pendiente "Convención de limpieza para `.elicit/`".

### D5 — Secret contract (Slice 3)
Decision: secrets are **referenced, never stored**. A Data Source `details.connection`
gains an optional `secret_ref` field naming an env var (e.g. `{"kind":"sqlite",
"path":"...","secret_ref":"BRAINDS_SRC_PWD"}`). The connector resolves the value
from `os.environ` at open time; the raw value never enters the store, card_sections,
or `.elicit/`. Read-only enforcement is unchanged (mode=ro + PRAGMA query_only +
path sandbox) and composes with auth by resolving credentials only inside `_open()`.
Anti-leak guard: a test asserts that for a node with `secret_ref`, neither the
persisted node JSON nor any `.elicit/` artifact contains the resolved secret value
(seed a sentinel env value, assert it never appears in serialized output).

### D6 — Dry-run context isolation (Slice 4)
Sub-agents receive ONLY: (1) artifact references (paths/topic keys) and (2) the
synthetic source path. The orchestrator passes no graph history, no Engram domain
data, no unrelated files. Isolation is enforced by the existing prompt rule
(handoff_rule: references not content) plus the OpenCode `permission.task: deny`
allowlist. Each agent writes ONLY to `.elicit/`.

## Data Flow

    Slice 4 dry-run:
    orchestrator ──refs+synthetic.db──► source-explorer ─►.elicit/source-exploration-*.md
         │                                              └─►.elicit/source-docs-*.md
         ├──► graph-mapper      ──► update_node/add_edge (synthetic graph) ─►.elicit/map-*.md
         ├──► connection-mapper ──► suggest_connections ─► .elicit/map-*.md
         └──► brd-writer        ──► brd-<slug> node + .elicit/brd-*.md
                                          │
    sdd-verify ◄── reads .elicit/* ──────┘ asserts: docs format, completeness
                                            gate, BRD contract, .elicit structure

## File Changes

| File | Action | Description |
|---|---|---|
| `skills/brainds-docs/SKILL.md` + `.opencode/` mirror | Modify | D1 carve-out for BRD/Unknown nodes (~12 lines) |
| `.atl/skill-registry.md` | Modify | D1 compact rule fix; D-registry add 3 missing agents |
| `tests/test_mcp_grounding.py` | Modify | D2 recurrence guard |
| `tests/test_grounding_drift_guard.py` | Modify | D3 reflection sweep + `CATEGORY2_EXEMPT` |
| `brain_ds/ui/e2e/brd-panel.spec.ts` | Create | BRD render-contract e2e |
| `.elicit/README.md` (or `.elicit/LIFECYCLE.md`) | Create | D4 layout, naming, ownership, archive |
| `docs/SDD_FLOW.md` | Create | Slice 2 flow doc grounded in DELEGATION_PROTOCOL |
| `brain_ds/connectors/sqlite_connector.py` | Modify | D5 `secret_ref` resolution in `_open()` |
| `brain_ds/mcp/grounding.py` | Modify | D5 surface secret contract in SOURCE_EXPLORATION_CONTRACT |
| `tests/test_connector_secret_contract.py` | Create | D5 anti-leak guard |
| `tests/fixtures/synthetic_source.db` + builder | Create | Slice 4 synthetic source |
| `tests/test_dryrun_elicit_compliance.py` | Create | Slice 4 verify checks |
| `AGENT_FLOW.md` | Modify | mark `.elicit` pendiente closed; query-consultant if added |

## Interfaces / Contracts

```jsonc
// D5 Data Source connection descriptor (extended)
{"kind": "sqlite", "path": "<project-relative>", "secret_ref": "ENV_VAR_NAME"}
// secret_ref optional; value resolved from os.environ at open; never persisted.

// D4 .elicit/ naming
.elicit/<phase>-<org-slug>-<ISO-date>.md   // active cycle
.elicit/changes/<change-name>/             // archived cycle artifacts
```

## Testing Strategy (tests-first, strict TDD)

| Layer | What | Approach |
|---|---|---|
| Unit | D3 sweep covers all Cat-2 constants | reflection meta-test + exempt set |
| Unit | D2 brainds-docs ⇄ BRD contract parity | assert values equal |
| Unit | D5 secret never leaks to store/.elicit | sentinel env value sweep |
| Unit | D5 read-only holds with secret_ref | reuse existing query_only tests |
| Integration | D4 .elicit naming/schema | validate fixtures against schema |
| E2E | BRD render: wikilink resolve, freshness chip, save round-trip | Playwright, PATCH `/api/nodes/:id`, re-read card_sections[0] |
| Integration | Slice 4 .elicit compliance | docs format + completeness gate + BRD contract |

## Migration / Rollout

No data migration. 4 chained PRs (work-unit commits, ~400-line budget each):
- **PR1 (Slice 1, ~280 lines):** carve-out + recurrence guard + drift sweep + BRD e2e.
- **PR2 (Slice 2, ~220 lines):** .elicit lifecycle doc + SDD_FLOW.md + registry 3-agent sync.
- **PR3 (Slice 3, ~180 lines):** secret_ref resolution + harness surfacing + anti-leak guard.
- **PR4 (Slice 4, ~260 lines):** synthetic source + dry-run + compliance tests; optional judgment-day adversarial pass over .elicit output.

## Open Questions

- [ ] SDD_FLOW.md location: `docs/` vs repo root next to AGENT_FLOW.md (lean `docs/`).
- [ ] Whether to also add `brainds-query-consultant` to OpenCode global in this cycle (AGENT_FLOW pendiente) or keep doc-sync only — proposal says doc-sync only.
