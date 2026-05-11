---
name: map-connections
description: |
  Build a deterministic relationship map across domain entities captured in Engram.
  Trigger: /map-connections, /map-connections --graph, or /map-connections --save
license: MIT
disable-model-invocation: true
metadata:
  author: sechi42
  version: "1.3.1"
---

# Map Connections Skill

## When to Use
- Run ONLY when the user explicitly triggers `/map-connections`.
- Use `/map-connections --save` only when the user explicitly wants to persist the generated report.
- This skill is manual slash-command only and MUST NOT auto-activate from conversational mentions.

## Command Contract

| Command | Behavior |
|---|---|
| `/map-connections` | Read-only mode. Build and show inline Markdown report. No persistence. |
| `/map-connections --org <name|slug>` | Read-only mode with one-run org override; no active-org mutation. |
| `/map-connections --graph` | Read-only mode. Build and show Mermaid output (`graph TD`) with overview/detail blocks. No persistence. |
| `/map-connections --save` | Build report, show it, then persist via `mem_save` with `type: discovery` and `topic_key: org/<slug>/domain/map/{YYYY-MM-DD}`. |

Default mode is read-only.

## Retrieval Workflow (Mandatory)

Resolve org first (priority: `--org` > `session/active-org` > `default`) and echo:
`Resolved organization: <name> (<source>)`.

Run these **12 queries in parallel**:

| # | Query | Target |
|---|---|---|
| 1 | `[Department]` | Department entities |
| 2 | `[Role]` | Role entities |
| 3 | `[Data Source]` | Data Source entities |
| 4 | `[Heuristic]` | Heuristic entities |
| 5 | `[Tacit Knowledge]` | Tacit Knowledge entities |
| 6 | `[UX Friction]` | UX Friction entities |
| 7 | `[Project]` | Project entities |
| 8 | `[Risk]` | Risk entities |
| 9 | `[Decision]` | Decision entities |
| 10 | `domain/` | Catch-all for entities not bracket-tagged |
| 11 | `[KPI]` | KPI entities |
| 12 | `[Solution]` | Solution entities |

Then:
1. Dedupe by observation ID across all query results.
2. For **every** unique ID, call `mem_get_observation(id)`.
3. Never analyze only `mem_search` previews; previews are truncated.
4. Filter scoped records:
   - Include `org/<resolved-slug>/domain/...`
   - Include legacy `domain/...` only when resolved slug = `default`
   - Exclude all other org prefixes
5. Never merge multiple org prefixes into one report.
6. If no explicit org, no `session/active-org`, and resolved `default` returns zero scoped + legacy records, emit guard warning in the main output: `No organization set. Graph may show mixed or incomplete data. Use /elicit-context --org <name|slug> to target one organization.`

## Parsing and Normalization

For each full observation:
1. Parse entity type from title tag: `[Department]`, `[Role]`, `[Data Source]`, `[Heuristic]`, `[Tacit Knowledge]`, `[UX Friction]`, `[Project]`, `[Risk]`, `[Decision]`, `[KPI]`, `[Solution]`.
2. Extract `name` from title remainder.
3. Normalize body fields:
   - `What`
   - `Why`
   - `Where`
   - `Learned`
4. If `Where` is missing/empty, mark entity as `[sparse: no Where]`.

## Deterministic Connection Rules

Tokenize to lowercase terms, remove punctuation and obvious stopwords, then score overlaps.

| Connection | Rule |
|---|---|
| Department ↔ Role | Shared substring/token in `Where` |
| Role ↔ Data Source | Overlap between Role `Where`/`Why` and Data Source `Where` |
| Heuristic ↔ Department | Heuristic `Where` overlaps Department `Where` |
| Heuristic ↔ Role | Heuristic mentions Role domain or decision point |
| Tacit Knowledge ↔ Role | Tacit `Where` maps to Role area |
| UX Friction ↔ Data Source | Friction references Data Source name/system |
| UX Friction ↔ Role | Friction `Where` overlaps Role `Where` |
| Project ↔ Department | Project departments overlap with Department names/tokens |
| Project ↔ Risk | Project `risk_ids` or textual overlap links to Risk entities |
| Decision ↔ Project/Risk | Decision `affects[]`/`supersedes` or contextual overlap |
| KPI ↔ Department | KPI owner dept maps to Department (`owned-by`) |
| KPI ↔ Role | KPI owner role maps to Role (`accountable`) |
| KPI ↔ Data Source | KPI measurement source maps to Data Source (`measured-by`) |
| KPI ↔ UX Friction | KPI degraded by linked frictions (`degraded-by`) |
| Solution ↔ KPI | Solution expected impact references KPI (`improves`) |
| Solution ↔ UX Friction | Solution resolves linked frictions (`resolves`) |
| Decision ↔ KPI | Decision rationale references KPI (`targets`) |
| Decision ↔ Solution | Decision authorizes solution (`authorizes`) |

Strength labels:
- `weak`: <=1 shared token
- `strong`: >=3 shared tokens

If an entity is sparse (no `Where`), keep it in output and avoid promoting it to strong links.

## Broken Links and Sparse-Memory Rules

- Broken Link: observation references a named entity/system that does not exist in current retrieved set.
- Sparse entity: missing `Where` is explicitly flagged, never silently skipped.
- Unknown KPI/Solution/Decision references MUST appear under **Broken Links**.

## Empty and Partial State Handling

### Empty state (no domain observations)
Return a first-class Markdown block:

```markdown
No domain knowledge captured yet.

Run `/elicit-context` first to capture entities.
```

For `--graph`, return exact Mermaid comment output:

```mermaid
%% No entities captured — run /elicit-context first
```

### Partial state (some entity types missing)
- Produce report from available entities.
- Add missing types under **Missing Knowledge**.
- Use follow-up prompts adapted from `skills/elicit-context/SKILL.md` question bank:
  - Department: "Which departments participate in this workflow?"
  - Role: "Who makes the key decisions day-to-day?"
  - Data Source: "What systems/files/APIs feed this process?"
  - Heuristic: "What manual rules do people apply when data is incomplete?"
  - Tacit Knowledge: "What critical knowledge exists only in people's heads?"
  - UX Friction: "Where do users get frustrated or abandon the flow?"
  - KPI: "What KPI should we track to measure outcome?"
  - Solution: "What solution could improve this KPI or resolve this friction?"
  - Decision: "What key decision was made and what alternatives were considered?"

## Output Template (Section Order is Mandatory)

1. **Entity Table**
2. **Information Flows**
3. **Overlaps**
4. **Broken Links**
5. **Missing Knowledge**
6. **DS Intervention Opportunities**
7. **Provenance Table**

### Entity Table columns
- Type
- Name
- Where
- Obs ID

### Information Flows
- Focus on Role -> Data Source directional links.

### Overlaps
- Group shared operational contexts.

### Broken Links
- List unresolved references.

### Missing Knowledge
- Missing entity types + concrete follow-up prompts.

### DS Intervention Opportunities
- Frictions/heuristics not mapped to data sources.

### Provenance Table columns
- Entity Type
- Entity Name
- Observation ID

## Graph Output Mode (`--graph`)

When command is `/map-connections --graph`, return Mermaid output instead of Markdown report sections.

### Mermaid Contract (Mandatory)

- Output starts with `graph TD`
- Include **Legend** block in every graph output
- Include department-colored subgraphs in detail views
- Cross-department shared edges MUST be dashed (`-.->`)
- Use informative comments for condensation and missing data

### Shapes by Entity Type

| Type | Shape | Example |
|---|---|---|
| Department | rectangle | `D_OPS[Operations]` |
| Role | circle | `R_FLEET((Fleet Manager))` |
| Data Source | cylinder | `S_ETA[(ETA Feed)]` |
| Heuristic | diamond | `H_DELAY{Delay > 20m}` |
| Tacit Knowledge | triangle | `T_VENDOR[/Vendor degrades on Fridays/]` |
| UX Friction | hexagon | `U_DUP{{Duplicate entry}}` |
| Project | double-rectangle | `P_REPLAN[[Replan Automation]]` |
| Risk | asymmetric | `K_SLA> SLA Penalty ]` |
| Decision | rounded node | `N_ROUTE(Route policy)` |
| KPI | pill | `K_ONTIME([On-Time Delivery %])` |
| Solution | parallelogram | `S_REROUTE[/Auto-reroute/]` |
| Organization | rounded rectangle | `O_LOGI([LogiTrans Logistics])` |

Organization node rules:
- Include exactly one Organization node for resolved org.
- Add edges from Organization -> Department with label `owns`.
- If no departments exist, keep org node and add comment `%% [NEEDS DATA] Department entities missing`.

### Edge Labels

Use these normalized edge labels where relevant: `uses`, `owns`, `blocked-by`, `depends-on`, `creates-risk`, `decided-by`, `shared-with`, `owned-by`, `accountable`, `measured-by`, `degraded-by`, `targets`, `improves`, `resolves`, `authorizes`.

Canonical contract note (spec-facing):
- Canonical labels are `degraded-by`, `targets`, and `authorizes`.
- Treat `impacted-by`, `impacts`, and `authorized-by` as legacy synonyms only in narrative discussion; do not emit them in Mermaid edges.

### Readability Threshold and Fallback

- If graph exceeds ~24 nodes OR ~40 edges:
  1. Emit condensed **Overview Graph** with highest-value nodes/edges.
  2. Emit one **Department Detail Graph** per department.
  3. Add comment: `%% Graph condensed for readability`.
- If below threshold:
  - Emit single full graph.

### Required Structure for Condensed Output

1. `### Mermaid Overview`
2. Mermaid code block with `graph TD`
3. `### Department Detail: <Department Name>` blocks (one per department)
4. Each detail block is a valid Mermaid `graph TD`

### Missing Data Behavior in Graph Mode

- Missing entity types must not fail rendering.
- Omit absent nodes and add comment notes, e.g.:
  - `%% [NEEDS DATA] Risk entities missing`
  - `%% [NEEDS DATA] Project entities missing`

## Worked Examples (Table-Driven)

| Dataset State | Inputs (summary) | Expected highlights |
|---|---|---|
| Empty | No results from all 12 queries | Output only empty-state block + `/elicit-context` guidance |
| Partial | `[Department] Operations` with `Where`; `[Role] Fleet Manager` without `Where` | Entity table includes sparse role flag; Missing Knowledge lists Data Source, Heuristic, Tacit Knowledge, UX Friction prompts |
| Connected | Department and Role share "operations control room"; Data Source has same context | Role -> Data Source appears in Information Flows; Department ↔ Role overlap labeled `weak` or `strong` by token count |
| KPI-linked | KPI linked to owner/data source/friction | KPI pill node plus `owned-by`, `accountable`, `measured-by`, `degraded-by` edges |
| Solution-linked | Solution linked to KPI/friction/decision | Solution parallelogram node with `improves`, `resolves`, `authorizes` edges |
| Decision-linked | Decision references KPI and authorizes Solution | Decision rounded node with `targets` edge to KPI and `authorizes` edge to Solution |

## Worked Graph Examples (Contract-level)

| Dataset State | Expected `--graph` behavior |
|---|---|
| Empty | Exact output: `%% No entities captured — run /elicit-context first` |
| Minimal (1 dept, 2 roles) | Single subgraph, 3 nodes, no dashed edges |
| LogiTrans-scale | 4 department detail subgraphs + dashed shared edges + legend |

## Optional Save Procedure

Use only when command is `/map-connections --save`:

```json
{
  "title": "[Map] Domain connection map {YYYY-MM-DD}",
  "type": "discovery",
  "scope": "project",
  "topic_key": "org/{resolved-org-slug}/domain/map/{YYYY-MM-DD}",
  "content": "<full markdown report>",
  "project": "brain_ds"
}
```

If command is `/map-connections` or `/map-connections --graph` (without `--save`), do NOT call `mem_save`.

## Org Scoping Examples

| Scenario | Input | Expected |
|---|---|---|
| Explicit org override | `/map-connections --org megacorp` | use `megacorp`; include only `org/megacorp/domain/...` |
| Active-org fallback | `/map-connections` with `session/active-org=logitrans` | use `logitrans` scoped entities only |
| Default compatibility | no explicit org and no active state | resolve `default`; include legacy `domain/...` plus `org/default/domain/...` |
| Mixed-org guard | retrieved entities from two orgs | exclude non-resolved org; add warning if exclusions happened |
| No org data | resolved org has zero records | emit main-workflow guard warning and keep output deterministic |
