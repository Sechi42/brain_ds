# Skill Registry

**Delegator use only.** Any agent that launches sub-agents reads this registry to resolve compact rules, then injects them directly into sub-agent prompts. Sub-agents do NOT read this registry or individual SKILL.md files.

See `_shared/skill-resolver.md` for the full resolution protocol.

## User Skills

| Trigger | Skill | Path |
|---------|-------|------|
| when implementing a change, preparing commits, splitting PRs, or planning chained or stacked PRs | work-unit-commits | <USER_HOME>/.config/opencode/skills/work-unit-commits/SKILL.md |
| when drafting or posting feedback, review comments, maintainer replies, Slack messages, or GitHub comments | comment-writer | <USER_HOME>/.config/opencode/skills/comment-writer/SKILL.md |
| when writing guides, READMEs, RFCs, onboarding docs, architecture docs, or review-facing documentation | cognitive-doc-design | <USER_HOME>/.config/opencode/skills/cognitive-doc-design/SKILL.md |
| when a PR would exceed 400 changed lines, when planning chained PRs, stacked PRs, or reviewable slices | gentle-ai-chained-pr | <USER_HOME>/.config/opencode/skills/chained-pr/SKILL.md |
| When creating a GitHub issue, reporting a bug, or requesting a feature | issue-creation | <USER_HOME>/.config/opencode/skills/issue-creation/SKILL.md |
| When creating a pull request, opening a PR, or preparing changes for review | branch-pr | <USER_HOME>/.config/opencode/skills/branch-pr/SKILL.md |
| When user asks to create a new skill, add agent instructions, or document patterns for AI | skill-creator | <USER_HOME>/.config/opencode/skills/skill-creator/SKILL.md |
| When user says `/elicit-context` or needs domain context | elicit-context | skills/elicit-context/SKILL.md |
| When user says `/map-connections` or `/map-connections --save` | map-connections | skills/map-connections/SKILL.md |
| When user says `/generate-brd` or `/generate-brd --save` | generate-brd | skills/generate-brd/SKILL.md |
| When writing Go tests, using teatest, or adding test coverage | go-testing | <USER_HOME>/.config/opencode/skills/go-testing/SKILL.md |
| When user says "judgment day", "judgment-day", "review adversarial", "dual review", "doble review", "juzgar", "que lo juzguen" | judgment-day | <USER_HOME>/.config/opencode/skills/judgment-day/SKILL.md |

## Compact Rules

Pre-digested rules per skill. Delegators copy matching blocks into sub-agent prompts as `## Project Standards (auto-resolved)`.

### work-unit-commits
- Commit by deliverable behavior, fix, migration, or docs unit, never by file type.
- Keep tests in the same commit as the behavior they verify.
- Keep docs with the user-visible change or workflow they explain.
- Each commit should have one clear purpose, reasonable rollback, and a message explaining the outcome.
- If SDD forecasts >400 changed lines, group work units into chained PR slices before implementation.

### comment-writer
- Start with the actionable point, not a long recap.
- Be warm, direct, and useful; prefer 1-3 short paragraphs or tight bullets.
- Explain the technical reason when requesting a change.
- Comment on the highest-value issue, not every tiny preference.
- Match the thread language; in Spanish use natural Rioplatense voseo.
- Avoid em dashes.

### cognitive-doc-design
- Lead with the answer: decision, action, or outcome first, context second.
- Use progressive disclosure: happy path first, then details, edge cases, references.
- Chunk related information into small sections and keep lists short.
- Use headings, labels, tables, checklists, examples, and templates for recognition over recall.
- For review docs, state what to review first, what is out of scope, and linked previous/next PRs if chained.

### gentle-ai-chained-pr
- Split PRs above 400 changed lines unless maintainer-approved `size:exception` exists.
- Design each PR for roughly <=60 minutes of review and one autonomous work unit.
- Every chained PR must state start, end, before, after, dependencies, and out-of-scope work.
- Every chained PR needs a dependency diagram marking the current PR.
- Feature Branch Chain requires a draft/no-merge tracker PR; child PRs target the immediate parent branch.
- If a child PR shows previous PR changes, retarget/rebase because its base is wrong.
- Follow the chosen chain strategy consistently for the full chain.

### issue-creation
- Blank issues are disabled; use bug report or feature request templates.
- Search existing issues for duplicates before creating a new one.
- Every new issue gets `status:needs-review`; a maintainer must add `status:approved` before any PR.
- Questions go to Discussions, not issues.
- Fill all required template fields and pre-flight checkboxes.

### branch-pr
- Every PR must link an approved issue and contain exactly one `type:*` label.
- Branch names must match `^(feat|fix|chore|docs|style|refactor|perf|test|build|ci|revert)/[a-z0-9._-]+$`.
- Use Conventional Commits matching `type(scope): description`; never add `Co-Authored-By` trailers.
- PR body must include linked issue, PR type, summary, changes table, test plan, and checklist.
- Automated checks must pass; blank PRs without issue linkage are blocked.

### skill-creator
- Create a skill only for repeated AI guidance, project-specific conventions, complex workflows, or decision trees.
- Do not create a skill for trivial, one-off, or already-documented patterns.
- Use `skills/{skill-name}/SKILL.md` with required frontmatter: name, description with Trigger, license, metadata author/version.
- Keep critical patterns clear, code examples minimal, and commands copy-pasteable.
- Do not add Keywords sections, duplicate existing docs, use long troubleshooting, or link web URLs in references.
- Register created skills in `AGENTS.md` when applicable.

### go-testing
- Prefer table-driven tests for multiple cases and explicit success/error branches.
- Test Bubbletea state transitions directly through `Model.Update()`.
- Use `teatest.NewTestModel()` for full interactive TUI flows.
- Use golden files for stable visual output snapshots.
- For side effects, mock dependencies; for file operations use `t.TempDir()`.
- Skip real command integration tests under `--short` when appropriate.

### judgment-day
- Before launching judges, resolve skills from Engram `skill-registry` or `.atl/skill-registry.md` and inject matching compact rules.
- Launch two blind independent judge sub-agents in parallel with identical target and criteria.
- Classify findings as CRITICAL, WARNING (real), WARNING (theoretical), or SUGGESTION.
- Treat theoretical warnings as INFO: report them, do not block or fix by default.
- Synthesize confirmed, suspect, and contradictory findings before fixing.
- Fix only confirmed criticals or real warnings, then re-judge; after two iterations escalate to the user.

### map-connections
- Trigger only on explicit `/map-connections` command (manual slash-command skill).
- Run 12 parallel Engram searches (`[Department]`, `[Role]`, `[Data Source]`, `[Heuristic]`, `[Tacit Knowledge]`, `[Problem / Improvement Area]`, `[Project]`, `[Risk]`, `[Decision]`, `[KPI]`, `[Solution]`, `domain/`) and dedupe IDs.
- Always fetch full records with `mem_get_observation`; never map from `mem_search` preview snippets.
- Default is read-only inline report; persist only with explicit `--save`.
- Keep output section order fixed: Entity Table, Information Flows, Overlaps, Broken Links, Missing Knowledge, DS Intervention Opportunities, Provenance Table.

### generate-brd
- Trigger only on explicit `/generate-brd` command (manual slash-command skill).
- Run 11 parallel Engram searches (`[Department]`, `[Role]`, `[Data Source]`, `[Heuristic]`, `[Tacit Knowledge]`, `[Problem / Improvement Area]`, `[Project]`, `[Risk]`, `[Decision]`, `[KPI]`, `[Solution]`) and dedupe IDs.
- Always fetch full records with `mem_get_observation`; never synthesize from `mem_search` previews.
- `/generate-brd` is BRD read-only by default; `/generate-brd --save` persists BRD to `domain/brd/{timestamp}`.
- ADR audit logging is explicit and always-on for every invocation via `architecture/adr/create-brd-{timestamp}`.
- Keep output section order fixed: Header, Executive Summary, Current State Analysis, Requirements, Data Sources & Dependencies, Stakeholder Impact, Solution Options, ADR Log, Data Provenance, Risk Register, Cross-Dept Overlap Map, Project Portfolio, KPI Dashboard, Improvement Roadmap.
- Empty state must return Starter-BRD with `[NEEDS DATA]` markers in all fourteen sections.

## Local Skill Versions

| Skill | Version |
|---|---|
| elicit-context | 1.3.2 |
| generate-brd | 1.3.1 |
| map-connections | 1.3.2 |

## Project Conventions

| File | Path | Notes |
|------|------|-------|

Read the convention files listed above for project-specific patterns and rules. All referenced paths have been extracted — no need to read index files to discover more.
