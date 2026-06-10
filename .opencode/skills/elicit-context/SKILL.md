---
name: elicit-context
description: |
  Structured context interview for Data Science domain discovery.
  Trigger: /elicit-context
license: MIT
disable-model-invocation: true
metadata:
  author: sechi42
  version: "1.3.2"
---

# Elicit Context Skill

## When to Use
- Run ONLY when the user explicitly triggers `/elicit-context`.
- Goal: capture high-value domain knowledge as structured SQLite graph entities.
- Session limit: max 5 questions per run. Continue later with another `/elicit-context` session.

## Entity Schema Representation

Canonical source of truth: `brain_ds.ontology.EntityType`.

| Entity Type | What it captures | Example |
|---|---|---|
| Organization | Business org boundary and identity | LogiTrans Logistics |
| Department | Business area involved in a workflow | Operations, Finance |
| Role | Human responsibility and decision owner | Fleet Manager, Data Analyst |
| Data Source | System/file/API feeding decisions | PostgreSQL table, Excel sheet |
| Heuristic | Rule-of-thumb used in practice | "If delay > 20 min, reroute manually" |
| Tacit Knowledge | Important undocumented know-how | "Vendor quality drops on Fridays" |
| Problem / Improvement Area | Problem, bottleneck, workaround, confusion, or opportunity to improve | Duplicate entry in two tools |
| KPI | Measurable business outcome and target gap | On-Time Delivery % |
| Solution | WHAT operational improvement is proposed/implemented | Auto-reroute dispatch queue |
| Decision | WHY a strategic/product/architecture choice was made | Adopt event-driven notifications |

## Interview Workflow

1. Ask exactly ONE question.
2. Wait for the user response before anything else.
3. Resolve organization first (priority: `--org <name|slug>` > `session/active-org` > `default`).
4. Echo `Resolved organization: <name> (<source>)` before persisting.
5. Ask Data Source questions before Department/Role questions whenever coverage is still missing.
6. Interpret response into one of the entity types.
7. If user says `skip`, `pass`, or `next`, mark current item as unanswered and continue.
8. Stop after 5 asked questions OR when user says `done`, `save`, or `stop`.
9. Show a summary draft of captured observations.
10. Run the **Remaining Gaps / Follow-up Needed** check (below) before confirmation.
11. Show a `Remaining Gaps / Follow-up Needed` section listing all missing or underspecified items.
12. Ask for explicit confirmation before persistence: `Confirm save? (yes/no/edit)`.
13. If `edit`, apply requested edits and re-show summary + remaining gaps before asking confirmation again.
14. Persist only after explicit `yes`/`save`.

### Organization Resolution Contract (Slice 1)

- Supported override: `/elicit-context --org <name|slug>`.
- Slice 1 scope uses embedded `--org` behavior only; do NOT introduce a standalone `/organization` skill trigger yet.
- Persist active org state at `session/active-org` with fields: `org_slug`, `org_name`, `set_at` (ISO timestamp).
- If no explicit or persisted org exists, use `default` and warn once: `No organization set. Saving under org/default. Use /elicit-context --org <name|slug> to override.`
- Organization slug rules:
  - lowercase kebab-case
  - `&` -> `and`
  - spaces, `_`, `/` -> `-`
  - strip chars outside `[a-z0-9-]`
  - collapse repeated `-`
- Collision handling: if `create_graph(graph_id=<slug>)` indicates the slug belongs to a different organization name, STOP and request explicit slug/name correction before saving.

### Remaining Gaps / Follow-up Needed (MANDATORY before save)

The interview is **not complete** unless you explicitly evaluate coverage for all ten entities:
- Organization
- Data Source
- Department
- Role
- Heuristic
- Tacit Knowledge
- Problem / Improvement Area
- KPI
- Solution
- Decision

For each entity, label one status:
- `Covered`
- `Missing`
- `Underspecified`

If any entity is `Missing` or `Underspecified`, include exact follow-up prompts in a section titled:
`Remaining Gaps / Follow-up Needed`.

Do NOT present vague completion claims such as "data source captured" if identifiers are generic.

#### Data Source completeness rule (strict)

For `Data Source`, require concrete identifiers whenever known. Mark as `Underspecified` if any critical identifier is vague or unknown without being called out.

Capture/check these fields:
- Kind of source (relational DB, NoSQL, Excel/CSV, API, SaaS, other)
- System name (exact product/service)
- Database name
- Table name (or collection for NoSQL)
- Excel/CSV file name
- Workbook name
- Sheet/hoja name
- Key columns/fields and what each one means (document as a markdown table: | Column/Field | Type | Meaning | Notes |)
- Purpose — what the source is used for and which decisions depend on it
- Owner or supplier — who manages it day-to-day

Examples that are **underspecified** unless expanded:
- "an Excel"
- "the database"
- "an API from finance"

Partial saves are allowed, but every missing/vague field MUST appear as a follow-up item.

## Question Bank

Use these as defaults. Ask one at a time.

| Entity | Questions |
|---|---|
| Organization | 1) What is the organization name? 2) What industry and region should we register for this org? |
| Data Source | 1) What systems/files/APIs feed this process? 2) What kind of source is it (relational DB, NoSQL, Excel/CSV, API, SaaS)? 3) For a database: which database and tables? For Excel/CSV: which workbook and sheets? 4) Which key columns/fields matter, and what does each one mean? 5) What is this source used for, and which decisions depend on it? 6) Who owns or manages it day-to-day? 7) How often is it refreshed or updated (real-time, daily, weekly, manual)? 8) Which data source is least trusted and why? |
| Department | 1) Which departments participate in this workflow? 2) Which department owns final accountability for the outcome? |
| Role | 1) Who makes the key decisions day-to-day? 2) Which role is blocked most often and why? |
| Heuristic | 1) What manual rules do people apply when data is incomplete? 2) Which shortcut is used to decide faster under pressure? |
| Tacit Knowledge | 1) What critical knowledge exists only in people's heads? 2) What do experienced teammates know that new hires usually miss? |
| Problem / Improvement Area | 1) What problem or improvement area is slowing the workflow or creating risk? 2) What workaround appears most frequently? |
| KPI | 1) What KPI should we track? 2) What are current vs target values and unit? 3) How often is it measured, by whom, and from which data source? |
| Solution | 1) What operational improvement are we proposing or implementing? 2) Which KPI does it improve or which problem/improvement area does it resolve? 3) What are status and effort (low/med/high)? |
| Decision | 1) What key decision was made and why? 2) Which alternatives were considered, and what does this decision supersede or authorize? |

Default behavior:
- If Solution status is omitted, default `Status` to `proposed`.
- If the user explicitly describes active implementation, ask for explicit status (`in-progress`, `completed`, or `deprecated`).

Validation prompts (mandatory when data is inconsistent or incomplete):
- KPI trend sanity: if target appears below current for a "higher-is-better" KPI, ask: `Target (<target>) is below current (<current>) — is a decrease the actual goal?`
- Solution linkage: if no related KPI or Problem / Improvement Area is provided, ask: `What KPI does this improve, or what problem/improvement area does it resolve?`
- Decision depth: if rationale or alternatives are missing, ask: `What made you choose this option over the alternatives?`

## SQLite MCP Write Contracts

For each confirmed save, persist domain entities to SQLite in this order:

1. Ensure the org graph exists:

```json
{
  "tool": "create_graph",
  "args": {
    "graph_id": "<org-slug>",
    "name": "<org-name>",
    "project": "brain_ds"
  }
}
```

- Call `create_graph` once per save batch.
- If it reports the graph already exists, continue — do NOT abort.

2. Save each confirmed entity with `update_node`:

```json
{
  "tool": "update_node",
  "args": {
    "graph_id": "<org-slug>",
    "node_id": "<org-slug>-<entity-type-slug>-<short-name-slug>",
    "label": "<short-name>",
    "type": "<EntityType value>",
    "supertype": "<EntityType supertype>",
    "details": {
      "what": "<fact captured>",
      "why": "<business motivation / impact>",
      "where": "<org/process/system location>",
      "learned": "<non-obvious nuance, heuristic, problem, or improvement area>"
    }
  }
}
```

Node id rules (mandatory):
- Organization entity: `<org-slug>-organization-<org-slug>`
- Domain entities: `<org-slug>-<entity-type-slug>-<short-name-slug>`

3. Save confirmed relationships with `add_edge`:

```json
{
  "tool": "add_edge",
  "args": {
    "graph_id": "<org-slug>",
    "source": "<source-node-id>",
    "target": "<target-node-id>",
    "label": "<RelationshipType value>"
  }
}
```

KPI/Solution/Decision details must stay additive inside `details.learned`:
- KPI: include target/current/unit/frequency/owner/data source/related problems/related solutions.
- Solution: include status/effort/owner/related KPIs/related problems/related decisions.
- Decision: include alternatives/supersedes/version/date/impacted KPIs/authorized solutions.

Keep `session/active-org` in Engram via `mem_save`; it remains session state, NOT domain truth.

Semantic boundary (strict):
- **Solution** = WHAT operational improvement is proposed/implemented.
- **Decision** = WHY a strategic/architectural/product choice was made.
- If user mixes both in one answer, split into two draft observations before confirmation.

### Copy-paste `update_node` example

```json
{
  "tool": "update_node",
  "args": {
    "graph_id": "logitrans",
    "node_id": "logitrans-heuristic-delay-triage-over-20-minutes",
    "label": "Delay triage over 20 minutes",
    "type": "Heuristic",
    "supertype": "process",
    "details": {
      "what": "Dispatchers reroute manually when predicted delay exceeds 20 minutes.",
      "why": "SLA penalties rise quickly after 20 minutes and auto-routing is too slow in peak hours.",
      "where": "Operations control room, afternoon dispatch workflow.",
      "learned": "Team ignores model confidence when weather alerts are active."
    }
  }
}
```

## Interaction Example (One Question)

- Agent: "What systems or files feed this process?"
- User: "A daily Excel extract and the fleet_postgres.deliveries table."
- Agent: "Draft summary: [Data Source] Daily Excel + deliveries table. Confirm save? (yes/no/edit)"
- User: "yes"
- Agent: Calls `create_graph` (continue on already-exists), then `update_node` for the Data Source.

## Remaining Gaps Example (before final confirmation)

```text
Remaining Gaps / Follow-up Needed

- Department: Covered
- Role: Covered
- Data Source: Underspecified
  - Need exact database + table name for "deliveries" source.
  - Need workbook + sheet/hoja name for the daily Excel extract.
  - Need owner/supplier for both sources.
- Heuristic: Missing
  - Ask: "What rule-of-thumb do operators apply when ETAs look unreliable?"
- Tacit Knowledge: Missing
  - Ask: "What critical know-how is not documented anywhere?"
- Problem / Improvement Area: Covered
```

## Output Contract for Future Skills

- Keep node ids stable as `<org-slug>-<entity-type-slug>-<short-name-slug>`.
- Persist domain entities through MCP SQLite tools, not `mem_save`.
- Save active org context in `session/active-org` whenever org is explicitly selected or created.
- This enables `/map-connections` to map links between departments, roles, and data sources.
- This enables `/generate-brd` to synthesize requirements from verified heuristics, tacit knowledge, and problems/improvement areas.

## Table-Driven Org Examples

| Case | Input | Expected |
|---|---|---|
| Slugging | `--org LogiTrans Logistics` | resolved slug `logitrans-logistics`; `Resolved organization: LogiTrans Logistics (explicit)` |
| Collision stop | incoming slug exists but different org display name | stop and ask for explicit disambiguation before any `update_node` |
| First capture | no active org, user sets `--org` | ensure graph with `create_graph(graph_id=<slug>)`, save org node id `<slug>-organization-<slug>`, and write `session/active-org` |
| Implicit default | no `--org`, no active state | warning + save to graph `default` with node ids prefixed `default-...` |

## KPI / Solution / Decision Worked Examples

| Dataset state | User input (summary) | Expected capture behavior |
|---|---|---|
| Empty KPI/Solution/Decision coverage | "No KPI defined yet; we only know delays are bad." | Save problem/improvement area and known entities as provided; mark KPI/Solution/Decision as `Missing` in **Remaining Gaps / Follow-up Needed** with their default follow-up questions. |
| Partial KPI (missing owner/source) | "Track On-Time Delivery: current 92, target 98, percent." | Create `[KPI]` draft with provided values; mark owner and data source as `Underspecified`; ask follow-up before final confirmation. |
| Linked Solution with omitted status | "Auto-reroute should improve On-Time Delivery and reduce late dispatches." | Create `[Solution]` draft linked to KPI + problem/improvement area; apply default `Status: proposed`; collect effort/owner if absent. |
| Decision with supersedes and links | "We chose event-driven routing over cron batches; this replaces monolith-first and authorizes auto-reroute." | Create `[Decision]` draft including rationale, alternatives, `Supersedes`, and `Authorizes Solutions`; prompt if KPI impact links are missing. |
