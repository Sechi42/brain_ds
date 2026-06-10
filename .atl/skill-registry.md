# Skill Registry

**Delegator use only.** Any agent that launches sub-agents reads this registry to resolve compact rules, then injects them directly into sub-agent prompts. Sub-agents do NOT read this registry or individual SKILL.md files.

See `_shared/skill-resolver.md` for the full resolution protocol.

## User Skills

| Trigger | Skill | Path |
|---------|-------|------|
| `/elicit-context` — Structured context interview for Data Science domain discovery | `elicit-context` | `brain_ds/skills/elicit-context/SKILL.md` |
| `/generate-brd` or `/generate-brd --save` — Generate a 14-section BRD from SQLite domain entities | `generate-brd` | `brain_ds/skills/generate-brd/SKILL.md` |
| `/map-connections`, `/map-connections --graph`, `--save` — Build relationship map from domain entities | `map-connections` | `brain_ds/skills/map-connections/SKILL.md` |
| When creating a pull request, opening a PR, or preparing changes for review | `branch-pr` | `brain_ds/.claude/skills/branch-pr/SKILL.md` |
| When a PR would exceed 400 changed lines, planning chained/stacked PRs, or reviewable slices | `chained-pr` | `brain_ds/.claude/skills/chained-pr/SKILL.md` |
| When writing guides, READMEs, RFCs, onboarding docs, architecture docs, or review-facing documentation | `cognitive-doc-design` | `brain_ds/.claude/skills/cognitive-doc-design/SKILL.md` |
| When drafting or posting feedback, review comments, maintainer replies, Slack messages, or GitHub comments | `comment-writer` | `brain_ds/.claude/skills/comment-writer/SKILL.md` |
| When user asks "how do I do X", "find a skill for X", or wants to extend agent capabilities | `find-skills` | `brain_ds/.agents/skills/find-skills/SKILL.md` |
| When writing Go tests, using teatest, or adding test coverage | `go-testing` | `brain_ds/.claude/skills/go-testing/SKILL.md` |
| When creating a GitHub issue, reporting a bug, or requesting a feature | `issue-creation` | `brain_ds/.claude/skills/issue-creation/SKILL.md` |
| When user says "judgment day", "judgment-day", "review adversarial", "dual review", "juzgar", "que lo juzguen" | `judgment-day` | `brain_ds/.claude/skills/judgment-day/SKILL.md` |
| Building n8n workflows, webhook processing, HTTP API integration, database operations, AI agent workflows, or scheduled tasks | `n8n-workflow-patterns` | `brain_ds/.agents/skills/n8n-workflow-patterns/SKILL.md` |
| Fast DataFrame operations with Polars: select, filter, group_by, joins, lazy evaluation, CSV/Parquet I/O | `polars` | `brain_ds/.agents/skills/polars/SKILL.md` |
| When user asks to create a new skill, add agent instructions, or document patterns for AI | `skill-creator` | `brain_ds/.claude/skills/skill-creator/SKILL.md` |
| When modifying graph_viewer.html, brain_ds/ui/templates/*, brain_ds/ui/src/**, or any workspace-shell/center-canvas/rail/panel work | `frontend-spectacular-design` | built-in (Claude Code system skill) |
| When building web components, pages, or applications — high design quality, production-grade UI | `ui-design` | `brain_ds/.agents/skills/ui-design/SKILL.md` |
| When implementing a change, preparing commits, splitting PRs, or planning chained or stacked PRs | `work-unit-commits` | `brain_ds/.claude/skills/work-unit-commits/SKILL.md` |

## Compact Rules

Pre-digested rules per skill. Delegators copy matching blocks into sub-agent prompts as `## Project Standards (auto-resolved)`.

### elicit-context
- Trigger ONLY on explicit `/elicit-context` — never auto-activate from conversational mentions.
- Ask exactly ONE question, wait for user response before anything else.
- Max 5 questions per session. Use skip/pass/next to move on.
- Resolve org first: `--org` flag > `session/active-org` > `default`. Echo `Resolved organization: <name> (<source>)` before persisting.
- Ask Data Source questions before Department/Role whenever coverage is missing.
- Before confirmation, evaluate all 10 entity types and show `Remaining Gaps / Follow-up Needed` with explicit status (Covered / Missing / Underspecified) for each.
- Data Source MUST have: system name, database/table name, file/workbook/sheet name, and owner. Mark as Underspecified if any identifier is vague ("an Excel", "the database").
- Persist confirmed entities via MCP SQLite (`create_graph` → `update_node` → `add_edge`). Do NOT use `mem_save` for domain entities.
- Node id format: `<org-slug>-<entity-type-slug>-<short-name-slug>`. Organization itself: `<org-slug>-organization-<org-slug>`.
- Save `session/active-org` in Engram via `mem_save` as session state only — not domain truth.
- Split ambiguous answers: Solution = WHAT improvement is proposed; Decision = WHY a choice was made.

### generate-brd
- Trigger ONLY on `/generate-brd` or `/generate-brd --save` — never auto-run.
- Always resolve org: `--org` flag > `session/active-org` > `default`. Echo resolution before retrieval.
- Use `list_nodes` (typed, per entity family) as primary retrieval — never `mem_search` for org domain data.
- Use `search_graph` only for targeted substring expansion in the same graph; never mix graph IDs.
- Output exactly 14 sections in mandatory order: Header, Executive Summary, Current State Analysis, Requirements, Data Sources & Dependencies, Stakeholder Impact, Solution Options, ADR Log, Data Provenance, Risk Register, Cross-Dept Overlap Map, Project Portfolio, KPI Dashboard, Improvement Roadmap.
- Header MUST include Status (EMPTY/PARTIAL/COMPLETE), BRD Version: 1.2, Organization, and Dataset Fingerprint with entity counts in order.
- Missing sections get `[NEEDS DATA: <entity type> entities missing]` — never omit a section.
- Always persist an ADR on every invocation (`topic_key: architecture/adr/create-brd-{timestamp}`).
- Persist BRD only when command includes `--save` (`topic_key: org/{slug}/domain/brd/{timestamp}`).
- If graph is empty, produce a Starter-BRD with all 14 sections and NEEDS DATA markers — never fall back to Engram for org domain data.

### map-connections
- Trigger ONLY on explicit `/map-connections` — never auto-activate from conversational mentions.
- Default is read-only mode. Persist only when command explicitly includes `--save`.
- Resolve org first: `--org` > `session/active-org` > `default`. Echo resolution.
- Use `list_nodes` (typed per entity family) as primary retrieval. Never `mem_search` for org domain data.
- Never mix multiple graph IDs in one report.
- If graph returns zero nodes, emit: "No domain knowledge captured yet. Run `/elicit-context` first."
- Sparse entities (missing `Where`) are flagged with `[sparse: no Where]` — never silently skipped or promoted to strong links.
- Output 7 sections in mandatory order: Entity Table, Information Flows, Overlaps, Broken Links, Missing Knowledge, DS Intervention Opportunities, Provenance Table.
- Cross-department edges MUST be dashed (`-.->`) in Mermaid output.
- Use Mermaid shape conventions per entity type (department=rectangle, role=circle, data source=cylinder, etc.).
- Condense graph when >24 nodes OR >40 edges: Overview Graph + per-department Detail Graphs.
- Edge labels MUST use ontology `RelationshipType` values — no legacy synonyms in Mermaid edges.
- `--graph-json` produces v2 JSON contract; `--graph-ui` also runs `uv run brain_ds ui <org>-graph.json`.

### branch-pr
- Every PR MUST link an approved issue (`Closes #N`, `Fixes #N`, or `Resolves #N`).
- Every PR MUST have exactly one `type:*` label.
- Branch names MUST match: `^(feat|fix|chore|docs|style|refactor|perf|test|build|ci|revert)\/[a-z0-9._-]+$`.
- Commit messages MUST match: `^(build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test)(\([a-z0-9\._-]+\))?!?: .+`.
- Never add `Co-Authored-By` trailers to commits.
- Run `shellcheck` on any modified shell scripts before pushing.
- PR body MUST include: linked issue, PR type checkbox, summary, changes table, test plan, contributor checklist.
- Do not open a PR if the linked issue lacks `status:approved`.

### chained-pr
- MUST split any PR exceeding 400 changed lines (`additions + deletions`) unless maintainer has applied `size:exception`.
- Design each PR for approximately 60-minute review time.
- Every chained PR must state: where it starts, where it ends, what came before, what comes next.
- Every chained PR MUST include a dependency diagram marking the current PR with `📍`.
- Each slice must be autonomous: CI green, one deliverable scope, reasonable rollback, verification included.
- Do NOT mix unrelated refactors, features, tests, or docs in one PR.
- For Feature Branch Chain: PR #1 targets the feature/tracker branch; each later child targets its immediate parent branch — NOT main, NOT the tracker.
- Tracker PR is a map, not the review surface — keep it draft/no-merge until the chain completes.
- Cache strategy choice (Stacked PRs to main / Feature Branch Chain / size:exception) for the session — do not ask again.
- If SDD tasks forecast a >400-line workload, honor `delivery_strategy` before `sdd-apply` writes code.

### cognitive-doc-design
- Lead with the answer: put decision, action, or outcome first; context comes after.
- Use progressive disclosure: happy path first, then details, edge cases, references.
- Chunk related info into small sections; keep flat lists short.
- Use headings, labels, callouts, and summaries so readers know where they are (signposting).
- Prefer tables, checklists, examples, and templates over prose requiring recall.
- For PR docs: state what to review first, what is out of scope, and link previous/next PR in chained work.
- Use this structure: outcome-oriented title → one-paragraph summary → quick path → details table → checklist → next step.

### comment-writer
- Start with the actionable point — do not recap the whole PR before feedback.
- Be warm and direct: sound like a thoughtful teammate, not a corporate bot.
- Keep comments short: 1-3 short paragraphs or a tight bullet list.
- Give the technical reason when asking for a change.
- Comment on the highest-value issue, not every tiny preference.
- Match thread language. In Spanish: use Rioplatense Spanish/voseo (`podés`, `tenés`, `fijate`).
- Never use em dashes — use commas, periods, or parentheses instead.
- Formula: Direct observation → Why it matters (only if needed) → Concrete next action.

### find-skills
- Use when user asks "how do I do X", "find a skill for X", "is there a skill for X", or wants to extend capabilities.
- Search with `npx skills find [query]` before answering from memory.
- Present: skill name, what it does, install command, and link to skills.sh.
- Offer to install globally with `npx skills add <owner/repo@skill> -g -y`.
- If no skill found, acknowledge, help directly, and suggest `npx skills init my-xyz-skill`.

### go-testing
- Use table-driven tests for multiple cases: `tests := []struct{...}{...}` with `t.Run`.
- Test Bubbletea Model state transitions directly via `m.Update(tea.KeyMsg{...})`.
- Use `teatest.NewTestModel(t, m)` for full TUI interactive flow tests.
- Use golden file testing (`testdata/*.golden`) for visual output comparison; support `-update` flag.
- Co-locate test files with the production files they test (`model_test.go` beside `model.go`).
- Use `t.TempDir()` for file operations in tests.
- Skip integration tests with `--short` flag; use `t.TempDir()` for file ops.

### issue-creation
- Blank issues are disabled — MUST use a template (bug report or feature request).
- Search existing issues for duplicates before creating.
- Questions go to Discussions, not issues.
- Every new issue gets `status:needs-review` automatically; a maintainer MUST add `status:approved` before any PR can be opened.
- Bug report requires: pre-flight checks, description, reproduction steps, expected vs actual behavior, OS, agent/client, shell.
- Feature request requires: pre-flight checks, problem description, proposed solution, affected area.
- Never open a PR for an issue that lacks `status:approved`.

### judgment-day
- Trigger ONLY on: "judgment day", "judgment-day", "review adversarial", "dual review", "juzgar", "que lo juzguen".
- Resolve skill registry BEFORE launching judges; inject matching compact rules into BOTH judge prompts and the fix agent prompt.
- Launch Judge A and Judge B in parallel (async delegate) — never sequentially, never do the review yourself as orchestrator.
- Each judge is blind: neither knows about the other — no cross-contamination.
- Classify every WARNING: `WARNING (real)` = can a normal user trigger this through intended use? `WARNING (theoretical)` = requires contrived or malicious scenario — report as INFO, do NOT fix, do NOT re-judge.
- Synthesize: Confirmed (both judges) → fix immediately. Suspect (one judge) → triage. Contradiction → flag for manual decision.
- Round 1: present verdict, ASK user before fixing. Round 2+: only re-judge for confirmed CRITICALs.
- After 2 fix iterations, ASK the user whether to continue — never escalate automatically.
- NEVER declare APPROVED until: 0 confirmed CRITICALs + 0 confirmed real WARNINGs.
- NEVER push/commit after fixes until re-judgment completes.

### n8n-workflow-patterns
- Choose the right core pattern: Webhook Processing (event-driven), HTTP API Integration (fetch/sync), Database Operations (ETL/query), AI Agent Workflow (conversational + tools), Scheduled Tasks (recurring automation).
- Always include an error handler node in HTTP API Integration workflows.
- Webhook workflows: Webhook → Validate → Transform → Respond/Notify.
- AI Agent workflows: Trigger → AI Agent (Model + Tools + Memory) → Output.
- Scheduled tasks: Schedule → Fetch → Process → Deliver → Log.
- Never mix trigger types in a single workflow — keep concerns separated.

### polars
- Prefer lazy evaluation (`scan_csv`, `LazyFrame`) over eager for large datasets; call `.collect()` at the end.
- Use `pl.col("name")` expression API — never index with pandas-style `df["col"]` for transformations.
- Chain `.filter()`, `.select()`, `.with_columns()`, `.group_by()` in a single lazy query for optimizer benefits.
- Use `scan_parquet` / `write_parquet` for columnar storage; avoid CSV for large production datasets.
- Do not use `.to_pandas()` unless interfacing with pandas-only libraries — stay in Polars for performance.
- Use `.alias()` to name computed columns explicitly; avoid positional references.

### skill-creator
- Create a skill only when a pattern is reusable and AI needs guidance — not for one-off tasks or trivial patterns.
- Required frontmatter: `name`, `description` (includes trigger keywords), `license: Apache-2.0`, `metadata.author`, `metadata.version`.
- Structure: SKILL.md (required) + `assets/` (templates/schemas) + `references/` (local doc links only — no web URLs).
- Naming: generic `{technology}`, project-specific `{project}-{component}`, workflow `{action}-{target}`.
- Content: start with Critical Patterns; use tables for decision trees; minimal focused code examples; include Commands section.
- Do NOT add Keywords section; do NOT duplicate existing docs (reference instead); do NOT use web URLs in references.
- After creating, register the skill in `AGENTS.md`.

### frontend-spectacular-design
- Apply when modifying `graph_viewer.html`, `brain_ds/ui/templates/*`, `brain_ds/ui/src/**`, or any workspace-shell/center-canvas/rail/panel work.
- Use token-disciplined design: define CSS custom properties for all colors, spacing, and typography; no magic numbers.
- WCAG 2.1 AA minimum: contrast ratio ≥ 4.5:1 for text, ≥ 3:1 for large text and UI components.
- Use semantic HTML elements; keyboard-navigable interactive elements; ARIA labels where semantic HTML is insufficient.
- Mandatory reviewable HTML checkpoint after each PR — do not bundle UI + logic changes in a single PR.
- Icon-rich UI: prefer SVG inline icons from a consistent icon set; no mixed icon libraries.
- Progressive disclosure: show summary data first, detail on demand (hover/click/expand).

### ui-design
- Establish a clear visual hierarchy; maintain WCAG 2.1 AA contrast (≥4.5:1 for text).
- Use semantic HTML to enhance screen reader compatibility; provide alt text for images.
- Ensure keyboard navigability for all interactive elements; test with assistive technologies.
- Use relative units (%, em, rem) not fixed pixels; interactive touch targets min 44x44px.
- Optimize images and assets; implement lazy loading for non-critical resources; monitor Core Web Vitals.
- Use CSS Grid and Flexbox for flexible layouts; prefer CSS animations over JavaScript animations.
- Design mobile-first; use familiar UI components to reduce cognitive load.
- Develop and maintain a design system; position recurring elements predictably.

### work-unit-commits
- Commit by deliverable behavior, fix, migration, or docs unit — never by file type (models then services then tests).
- Keep tests in the same commit as the behavior they verify.
- Keep docs with the user-visible change they explain.
- Each commit must have one clear purpose, a clean rollback, and an outcome-explaining message.
- The repo must still make sense after applying only this commit.
- If SDD tasks forecast a >400-line change, group commits into chained PR slices before implementing.
- Use Conventional Commits format: `type(scope): description`.

## Project Conventions

| File | Path | Notes |
|------|------|-------|
| `CLAUDE.md` | `brain_ds/CLAUDE.md` | Project instructions: MCP tool inventory, setup, harness maintenance checklist, security boundary |
| `AGENTS.md` | `brain_ds/AGENTS.md` | Quick commands for `/elicit-context`, `/map-connections`, `/generate-brd`; references this registry |
