# Skill Registry

**Delegator use only.** Any agent that launches sub-agents reads this registry to resolve compact rules, then injects them directly into sub-agent prompts. Sub-agents do NOT read this registry or individual SKILL.md files.

See `_shared/skill-resolver.md` for the full resolution protocol.

## User Skills

| Trigger | Skill | Path |
|---------|-------|------|
| When writing/updating node documentation, card_sections, or BRD content | brainds-docs | brain_ds\skills\brainds-docs\SKILL.md |
| After adding/renaming entity types, relationship types, MCP tools, or editing any SKILL.md | brainds-registry | brain_ds\skills\brainds-registry\SKILL.md |
| /map-connections, --graph, --save | map-connections | brain_ds\skills\map-connections\SKILL.md |
| /elicit-context | elicit-context | brain_ds\skills\elicit-context\SKILL.md |
| /generate-brd or /generate-brd --save | generate-brd | brain_ds\skills\generate-brd\SKILL.md |
| After creating/modifying any brain_ds skill, or /share-brainds | share-brainds | brain_ds\skills\share-brainds\SKILL.md |
| When a PR would exceed 400 changed lines; planning chained/stacked PRs | chained-pr | brain_ds\skills\chained-pr\SKILL.md |
| When implementing a change, preparing commits, splitting PRs | work-unit-commits | 
.claude\skills\work-unit-commits\SKILL.md |
| When writing guides, READMEs, RFCs, onboarding/architecture/review docs | cognitive-doc-design | \.claude\skills\cognitive-doc-design\SKILL.md |
| When creating a PR, opening a PR, preparing changes for review | branch-pr | 
\.claude\skills\branch-pr\SKILL.md |
| When creating a GitHub issue, reporting a bug, requesting a feature | issue-creation | \.claude\skills\issue-creation\SKILL.md |
| When drafting PR/issue/review comments, maintainer replies, Slack/GitHub comments | comment-writer | \.claude\skills\comment-writer\SKILL.md |
| "judgment day", "dual review", "juzgar", "que lo juzguen" | judgment-day | 
\.claude\skills\judgment-day\SKILL.md |
| When creating a new skill or documenting patterns for AI | skill-creator | 
\.claude\skills\skill-creator\SKILL.md |
| When writing Go tests, using teatest (Gentleman.Dots) | go-testing | \.claude\skills\go-testing\SKILL.md |
| When creating/reviewing UI; accessibility, performance, responsive | ui-design | brain_ds\.claude\skills\ui-design\SKILL.md |
| When modifying graph_viewer.html, ui/templates/*, ui/src/**, chrome/rails/panels | frontend-spectacular-design | brain_ds\.claude\skills\frontend-spectacular-design\SKILL.md |

## Compact Rules

Pre-digested rules per skill. Delegators copy matching blocks into sub-agent prompts as `## Project Standards (auto-resolved)`.

### brainds-docs
- Lead with the answer; one concept per `card_section`, keep each under 10 lines.
- Use canonical section order per entity type (Data Source: Overview, Structure, Columns/Fields, Purpose, Owner, Refresh Cadence). Unknown types: Overview → Details → domain sections.
- `card_sections` `order` is monotonic from 1; `icon` from the allowed set (info, database, table, target, user, clock, lightbulb, alert, map-pin, link). Plain Markdown only, never raw HTML.
- BRD nodes (`brd-<slug>`, type `Unknown`) are the ONLY carve-out: `card_sections[0]` uses title `Contenido`, `order: 0`, `icon: ""`.
- Data Source `Columns / Fields` MUST use the 4-col table `| Column / Field | Type | Meaning | Notes |`; mark vague columns `[needs clarification]`, never omit.
- Reference other nodes as wikilinks `[[node-id|Label]]`; never fabricate node ids — use `[link pending]` if target absent.
- `details` object: what/why/where/learned, each under 3 sentences; omit `learned` if none.
- Typed sources: use `list_source_connections` then `explore_source`/`query_source`; NEVER call `list_secret_handles` (admin-only). Honor `change_detection` verdict (unchanged→skip, changed→delta, new/unknown-baseline→full) and write `details.schema_baseline` back per-table.

### brainds-registry
- Harness updates go in the SAME commit as the ontology/tool/skill change — never deferred.
- New/renamed MCP tool → update `TOOL_REGISTRY` (tools.py), the count assertion in EVERY test that pins it (`assert len(...) ==`), the CLAUDE.md tool inventory table AND the verification checklist count, and AGENTS.md if workflows change.
- New/renamed EntityType → add `QUESTION_BANK` entry in grounding.py (or `ELICIT_EXEMPT_TYPES` in the drift guard), review `NODE_WRITE_TEMPLATES` + `COMPLETENESS_MATRIX_TEMPLATE` string refs, update elicit-context + brainds-docs entity tables.
- New/renamed RelationshipType → Category-1 context is enum-derived (auto), but review `CONNECTION_RULES` prose + map-connections edge tables.
- Any SKILL.md edit → mirror byte-identical to `.opencode/skills/`, update grounding.py Category-2 constants, run `/share-brainds`, update `.atl/skill-registry.md` compact rules.
- A red `tests/test_grounding_drift_guard.py` means the harness needs updating — never suppress it. Audit: `uv run pytest tests/test_grounding_drift_guard.py -v`.
- `skills/*/SKILL.md` and `.opencode/skills/*/SKILL.md` MUST stay byte-identical at all times.

### map-connections
- Manual slash-command only (`/map-connections`); MUST NOT auto-activate from conversation. Default mode is read-only; persist only with `--save`.
- Workspace scope: act only in the folder matching `workspace.active_project_root`; `open_workspace` if registered, else STOP and ask. Never read another workspace's files by path.
- Before the FIRST `add_edge`, call `assess_completeness` and act on `pre_mapping_recommendation` (elicit / document / proceed_with_gaps). Every first pass shows a gap report, never starts with `add_edge`.
- Two-phase mapping, never mixed: Phase 1 structural (Org→Dept→Role→Data Source), Phase 2 cross-cutting (after elicitation/confirmation). Report `structural_edges` and `cross_cutting_edges` separately.
- Connection RAG: after each `update_node`, call `suggest_connections(node_id)`; candidates are suggestions, not commands. `review-needed` candidates are NEVER written as edges without explicit confirmation + a real label.
- Use ontology labels from `RelationshipType`; never emit legacy synonyms in output. `DataContainer`/`DataField` are Data Source-internal, not top-level endpoints.

### elicit-context
- Manual `/elicit-context` only. Ask exactly ONE question, then STOP and wait. Max 5 questions per run.
- Completeness gate: if an answer is partial/vague, stay on the SAME question with one focused follow-up; never advance half-answered.
- Resolve org first (`--org` > `session/active-org` > `default`), echo `Resolved organization: <name> (<source>)`. Ask Data Source questions before Department/Role when coverage is missing.
- Run the `Remaining Gaps / Follow-up Needed` check over all 10 entities (Covered/Missing/Underspecified) BEFORE asking `Confirm save? (yes/no/edit)`. Persist only after explicit yes/save.
- Dual persistence on confirmed save: SQLite MCP (`update_node`/`add_edge`) is the single source of truth for domain entities; Engram (`mem_save`) stores narrative/decisions only — NEVER domain entities alone. Never fall back to files/chat.
- Node ids: `<org-slug>-<entity-type-slug>-<short-name-slug>`; Organization: `<org-slug>-organization-<org-slug>`. After each node, call `suggest_connections`.
- Semantic boundary: Solution = WHAT operational improvement; Decision = WHY a strategic choice. Split if mixed.

### generate-brd
- Run only on explicit `/generate-brd`; persist BRD only with `--save`. ADR save is always-on every invocation.
- Always call `assess_completeness` first and open with a `Gaps Detectados` section. `--strict` refuses to generate unless COMPLETE; `--save` alone persists PARTIAL with `[NEEDS DATA]` markers.
- Resolve org (`--org` > `session/active-org` > `default`); `list_nodes` per type is the primary retrieval path; `search_graph` only for targeted expansion. Never use `mem_search` for domain retrieval.
- Output EXACTLY the 14 sections in order; Header includes Status (EMPTY/PARTIAL/COMPLETE), BRD Version, Organization, and Dataset Fingerprint counts.
- `--save` writes BOTH stores (skipping either is a violation): graph node `brd-<slug>` (type `Unknown`, `card_sections[0]` title `Contenido` order 0) for UI, AND Engram `org/<slug>/domain/brd/{timestamp}`. Every entity mention in the BRD must be a wikilink `[[label]]`.

### share-brainds
- After any `skills/*/SKILL.md` change, regenerate `skills/SHARED_CONTEXT.md`. Glob first, never assume which skills exist.
- One `##` heading per skill (frontmatter `name`), alphabetical; one 4-6 sentence summary with Trigger/Inputs/Outputs/MCP tools. Never copy raw SKILL.md content.
- End with a one-line reminder to keep `.opencode/skills/` mirrors identical.

### chained-pr
- MUST split when a PR exceeds 400 changed lines (additions+deletions) unless maintainer-approved `size:exception`. Design each PR for ≤60-min review.
- One deliverable work unit per PR; each PR autonomous (CI green, reviewable alone, clean rollback). State start/end/before/after/out-of-scope.
- Ask the user the chain strategy once (Stacked-to-main vs Feature Branch Chain vs size:exception) and cache it; don't mix strategies mid-chain.
- Every child PR includes a dependency diagram marking the current PR with 📍 + a status table. Chains >2 PRs need a draft `no-merge` tracker PR.
- Feature Branch Chain: PR #1 targets the feature/tracker branch; later children target the immediate previous PR branch. Diff is source of truth — if a child shows prior changes, its base is wrong.

### work-unit-commits
- A commit = one deliverable behavior/fix/migration/docs unit. Never commit by file-type batch (models, then services, then tests).
- Keep tests in the SAME commit as the behavior they verify; keep docs with the user-visible change they explain.
- Commit message explains the outcome, not the file list. Conventional Commits format. Repo must still make sense after applying only that commit.
- High SDD workload risk → follow cached `delivery_strategy` and group commits into chained PR slices before implementation.

### cognitive-doc-design
- Lead with the answer/decision/outcome; context after. Progressive disclosure: happy path first, then edge cases/references.
- Chunk into small sections; prefer tables, checklists, examples, templates over prose (recognition over recall). Signpost with headings/labels.
- For PR/review docs: state what to review first, what's out of scope, link prev/next PR in a chain. Default shape: Outcome title → Quick path → Details table → Checklist → Next step.

### branch-pr
- Every PR MUST link an approved issue (`Closes/Fixes/Resolves #N`, issue has `status:approved`) and carry exactly one `type:*` label.
- Branch name regex `^(feat|fix|chore|docs|style|refactor|perf|test|build|ci|revert)/[a-z0-9._-]+$`.
- Conventional commit regex `^(build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test)(\(scope\))?!?: .+`. No `Co-Authored-By` trailers.
- PR body: linked issue, one type checkbox+label, summary, changes table, test plan, contributor checklist all checked.

### issue-creation
- Blank issues are disabled — use a template (bug_report.yml or feature_request.yml). Search for duplicates first.
- Every issue auto-gets `status:needs-review`; a maintainer must add `status:approved` before any PR can open. Questions go to Discussions, not issues.
- Fill ALL required template fields and pre-flight checkboxes.

### comment-writer
- Start with the actionable point; be warm and direct, 1-3 short paragraphs or a tight bullet list. Explain WHY when requesting a change.
- Comment on the highest-value issue, avoid pile-ons. Match thread language (Spanish → Rioplatense voseo). No em dashes — use commas/periods/parentheses.
- Formula: direct observation/request → why it matters (if needed) → concrete next action.

### judgment-day
- Orchestrator NEVER reviews itself — launch TWO blind judges via async delegation in parallel (never sequential); the Fix Agent is a separate delegation.
- Resolve skills first (Pattern 0): read registry, match by code+task context, inject `## Project Standards (auto-resolved)` into BOTH judges AND the Fix Agent identically.
- Judges classify warnings: WARNING (real) = a normal user can trigger it → fix; WARNING (theoretical) = contrived scenario → report as INFO, don't fix/re-judge.
- Synthesize verdict (Confirmed = both judges; Suspect = one; Contradiction = disagree). APPROVED = 0 confirmed CRITICALs + 0 confirmed real WARNINGs.
- After 2 fix iterations with issues remaining, ASK the user before continuing. Never push/commit/summarize until every JD reaches APPROVED or ESCALATED.

### skill-creator
- Create a skill only for reusable patterns/conventions/workflows — not for trivial or one-off tasks, or when docs already exist (reference instead).
- SKILL.md frontmatter requires name (lowercase-hyphens), description (what + Trigger), license Apache-2.0, metadata.author, metadata.version (string).
- Lead with critical patterns; use tables for decision trees; minimal focused code examples; include a Commands section. No Keywords section, no web URLs in references (local paths only).
- Naming: generic `{tech}`, project-specific `{project}-{component}`, testing `{project}-test-{component}`, workflow `{action}-{target}`. Register in AGENTS.md.

### go-testing
- Use table-driven tests (slice of named structs with input/expected/wantErr); subtest with `t.Run(tt.name, ...)`.
- Bubbletea: test `Model.Update()` state transitions directly; full flows via `teatest.NewTestModel`; visual output via golden files (`-update` to regenerate); key handling via `tea.KeyMsg`.
- Test both success and error cases; use `t.TempDir()` for file ops; gate integration tests behind `-short`.
- (Go/Gentleman.Dots-specific — not applicable to the brain_ds Python codebase.)

### ui-design
- Establish clear visual hierarchy; WCAG 2.1 AA contrast; consistent styling and terminology.
- Keyboard navigable, semantic HTML, alt text; min 44×44 touch targets; relative units (rem/em/%) over fixed px.
- Responsive/mobile-first with Grid/Flexbox; lazy-load non-critical assets; monitor Core Web Vitals; inline form validation with clear errors and loading indicators.

### frontend-spectacular-design
- Design references in `brain_ds/ui/design/sections/*` are GROUND TRUTH — open the matching section file and copy its CSS verbatim before writing chrome.
- Token discipline: NEVER hardcode hex in templates — use `var(--*)`. New token → add to `brain_ds/ui/theme.py` THEME_TOKENS first, then mirror to `_tokens.css`.
- Hit targets: primary controls 44×44 min; tab rows 36px (ADR-009), file-tree rows 28px (ADR-004) are the only exemptions — anything else under 44px is rejected.
- Toolbar exposes 4 `data-toolbar-zone` slots (nav/view/overflow/system-chrome — never paint system-chrome). Tabs use `role=tablist`/`role=tab`/`aria-selected`, active 2px `--accent-mora` underline.
- Every control needs default/hover/focus-visible/disabled/(pressed) states; silence motion under `prefers-reduced-motion`; both dark+light themes must render via token overrides only.
- Use Lucide icons (inline SVG, `currentColor`, stroke-width 2) where the reference uses icons, not text buttons.
- MANDATORY post-PR review checkpoint: emit a static HTML preview and/or a live-viewer command + `review/<pr-slug>-review.md`. Run `tests/test_viewer.py` and `tests/test_render_context_golden.py` after every chrome change.

## Agents

Sub-agents available for delegation. Orchestrators read this table to know which agents to launch for each phase.

| Agent | Model | Purpose |
|-------|-------|---------|
| `brainds-orchestrator` | opus | Coordinates elicit → source-docs → map → BRD and owns the dry-run recipe |
| `brainds-source-explorer` | sonnet | Read-only source recon and sectioned documentation |
| `brainds-query-consultant` | sonnet | Read-only graph Q&A — answers questions about nodes, data sources, owners |
| `brainds-graph-mapper` | sonnet | Consolidates pipeline artifacts and pushes the documented source into the graph |
| `brainds-connection-mapper` | sonnet | Runs the connection-mapping pass with completeness gating |
| `brainds-brd-writer` | sonnet | Builds the deterministic BRD and persists it to the graph and Engram |

## Project Conventions

| File | Path | Notes |
|------|------|-------|
| CLAUDE.md | brain_ds\CLAUDE.md | MCP tool inventory, workspace scoping, harness maintenance checklist (MANDATORY same-change harness sync) |
| AGENTS.md | brain_ds\AGENTS.md | Agent/sub-agent table and workflows |
| AGENT_FLOW.md | brain_ds\AGENT_FLOW.md | Delegation model (orchestrator + sub-agents), pipeline stages |

Read the convention files listed above for project-specific patterns and rules. All referenced paths have been extracted — no need to read index files to discover more.
