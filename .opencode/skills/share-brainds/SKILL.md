---
name: share-brainds
description: |
  Maintains a short, always-current context summary of every brain_ds skill so agents can cheaply know what each skill does without reading full SKILL.md files.
  Trigger: after creating/modifying any brain_ds skill, or /share-brainds
license: MIT
disable-model-invocation: true
metadata:
  author: sechi42
  version: "1.0.0"
---

# Share brain_ds Skill

## When to Use

- Run after creating, modifying, or removing any file under `skills/*/SKILL.md` or `.opencode/skills/*/SKILL.md`.
- Run when user explicitly triggers `/share-brainds`.
- Goal: regenerate `skills/SHARED_CONTEXT.md` so every agent and human collaborator gets a fast one-paragraph summary per skill.

## What to Do

### Step 1: Scan skills/

Glob `skills/*/SKILL.md` in the project root. For each skill file found:

1. Read the frontmatter fields: `name`, `description` (extract text after "Trigger:" as the trigger phrase).
2. Read the skill body to extract (in order of preference):
   - **When to Use** bullets → inputs/purpose.
   - **MCP tools** referenced (scan for `mcp__brain_ds__`, `list_nodes`, `search_graph`, `suggest_connections`, `run_elicit`, `map_connections`, `generate_brd`, `update_node`, `add_edge` etc.).
   - **Output** contract (from sections named "Output Contract", "Output Template", "Command Contract").
3. Synthesize a single paragraph (4-6 sentences max) covering: skill name, trigger, inputs, what it produces, MCP tools used.

### Step 2: Write skills/SHARED_CONTEXT.md

Write or overwrite `skills/SHARED_CONTEXT.md` with:

```markdown
# brain_ds Skills — Shared Context

_Auto-generated. Regenerate with `/share-brainds` after any skill change._

**Last updated**: <ISO date>

## <skill-name>

<one-paragraph summary>

---

## <next-skill-name>

<one-paragraph summary>

---
```

Rules:
- One `##` heading per skill, named after the frontmatter `name` field.
- Include sub-heading `**Trigger**:`, `**Inputs**:`, `**Outputs**:`, `**MCP tools**:` as bold labels inside the paragraph or as a tight 4-row table — whichever fits in under 6 lines.
- Never copy full SKILL.md content. Summaries only.
- If a skill has no MCP tool references, write `none` for MCP tools.
- Alphabetical order by skill name.

### Step 3: Mirror skills must also be noted

After writing `skills/SHARED_CONTEXT.md`, remind the user (one line) that `.opencode/skills/` mirrors must be kept identical — copy if needed.

## Critical Patterns

| Pattern | Rule |
|---------|------|
| Scan first | Always glob before writing — never assume which skills exist. |
| Summaries only | Never copy raw SKILL.md content into SHARED_CONTEXT.md. |
| Idempotent | Re-running `/share-brainds` must always produce a valid, current file. |
| Order | Alphabetical by skill name inside SHARED_CONTEXT.md. |
| Mirror reminder | Always end with a one-line reminder to sync `.opencode/skills/`. |
