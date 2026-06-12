---
name: map-connections
description: |
  Build a deterministic relationship map across domain entities stored in SQLite.
  Trigger: /map-connections, /map-connections --graph, or /map-connections --save
license: MIT
disable-model-invocation: true
metadata:
  author: sechi42
  version: "1.4.0"
---

# Map Connections Skill

## When to Use
- Run ONLY when the user explicitly triggers `/map-connections`.
- Use `/map-connections --save` only when the user explicitly wants to persist the generated report.
- This skill is manual slash-command only and MUST NOT auto-activate from conversational mentions.

## Workspace Scope (Mandatory)

- Work ONLY in the workspace that matches the folder the user is working in. The grounding payload's `workspace.active_project_root` is the folder the MCP server is bound to — it is NOT necessarily the user's folder.
- Before any read/write, compare the user's current folder with `active_project_root`. If they differ, call `open_workspace(path=<user folder>)` when that folder appears in `registered_workspaces`; otherwise STOP and ask the user which workspace to use (show `list_workspaces` options).
- If the user's folder is not registered, do not guess and do not fall back to another workspace: tell the user to run `brain_ds setup` in that folder or pick it in the brain_ds desktop app, then retry.

## Command Contract

| Command | Behavior |
|---|---|
| `/map-connections` | Read-only mode. Build and show inline Markdown report. No persistence. |
| `/map-connections --org <name|slug>` | Read-only mode with one-run org override; no active-org mutation. |
| `/map-connections --graph` | Read-only mode. Build and show Mermaid output (`graph TD`) with overview/detail blocks. No persistence. |
| `/map-connections --graph-json` | Read-only mode. Build graph JSON and save `<org>-graph.json` to disk. No persistence by default. |
| `/map-connections --graph-ui` | Build graph JSON, save `<org>-graph.json`, then auto-run `uv run brain_ds ui <org>-graph.json` when available. |
| `/map-connections --graph-json --save` | Build graph JSON, save to disk, then persist via `mem_save` with `type: discovery` and `topic_key: org/<slug>/domain/graph-json/{YYYY-MM-DD}`. |
| `/map-connections --save` | Build report, show it, then persist via `mem_save` with `type: discovery` and `topic_key: org/<slug>/domain/map/{YYYY-MM-DD}`. |

Default mode is read-only.

## Retrieval Workflow (Mandatory)

Resolve org first (priority: `--org` > `session/active-org` > `default`) and echo:
`Resolved organization: <name> (<source>)`.

Run typed SQLite retrievals against the resolved org graph.

### Required MCP reads

```json
[
  {"tool": "list_nodes", "graph_id": "<resolved-org-slug>", "type": "Department"},
  {"tool": "list_nodes", "graph_id": "<resolved-org-slug>", "type": "Role"},
  {"tool": "list_nodes", "graph_id": "<resolved-org-slug>", "type": "Data Source"},
  {"tool": "list_nodes", "graph_id": "<resolved-org-slug>", "type": "Heuristic"},
  {"tool": "list_nodes", "graph_id": "<resolved-org-slug>", "type": "Tacit Knowledge"},
  {"tool": "list_nodes", "graph_id": "<resolved-org-slug>", "type": "Problem / Improvement Area"},
  {"tool": "list_nodes", "graph_id": "<resolved-org-slug>", "type": "Project"},
  {"tool": "list_nodes", "graph_id": "<resolved-org-slug>", "type": "Risk"},
  {"tool": "list_nodes", "graph_id": "<resolved-org-slug>", "type": "Decision"},
  {"tool": "list_nodes", "graph_id": "<resolved-org-slug>", "type": "KPI"},
  {"tool": "list_nodes", "graph_id": "<resolved-org-slug>", "type": "Solution"},
  {"tool": "search_graph", "graph_id": "<resolved-org-slug>", "query": "<targeted substring only when needed>"}
]
```

Rules:
1. For LINKING a specific node, `suggest_connections` is the PRIMARY retrieval path (see Connection RAG Workflow below). For FULL REPORTS, `list_nodes` is the PRIMARY retrieval path: one typed call per entity family builds the complete dataset.
2. Use `search_graph` only for targeted substring expansion inside the same resolved org graph.
3. Never use `mem_search` / `mem_get_observation` for org domain retrieval in this workflow.
4. Never mix multiple graph IDs in one report.
5. If the resolved graph returns zero nodes, emit: `No domain knowledge captured yet in SQLite. Run /elicit-context first to populate the organization graph.`
6. typed SQL filters are not equivalent to Engram substring search. validate the difference on a seeded vault before assuming parity.

## Completeness Gate (Mandatory)

Before the FIRST `add_edge` of any mapping pass, call `assess_completeness(graph_id=<slug>)` and act on `pre_mapping_recommendation`:

- `elicit` (3+ entity types missing): do NOT map. Show the gap report (missing types, underspecified nodes) and ask the user: elicit first (recommended), or map with what exists accepting a PARTIAL BRD. Proceed only on explicit confirmation.
- `document`: underspecified nodes (empty `Where`, or `Learned` starting with `Underspecified`) are blocked from automatic edges — the server marks their suggestions `review-needed`. Document them before linking them.
- `proceed_with_gaps`: map normally.

Every first mapping pass of a session starts with a visible gap report, never with `add_edge`.

## Connection RAG Workflow (Mandatory)

When new information enters the graph, link it without re-reading the whole graph:

1. Immediately after creating or updating a node via `update_node`, call `suggest_connections(graph_id=<slug>, node_id=<id>)` for that node.
2. The server ranks compatible nodes (type rules + token overlap + shared neighbors), excludes already-connected nodes, and returns at most `limit` candidates above `threshold` (default 0.55, with `minimum_shared_tokens` default 2) with a `suggested_edge` (source, target, label).
3. Evaluate each candidate with your own knowledge of the org: accept, reject, or defer. Suggestions are candidates, not commands.
4. Candidates labeled `review-needed` are NEVER written as edges: they mark pairs without a canonical type rule, weak lexical evidence, or a sparse node. Surface them to the user; promoting one requires explicit confirmation and a real relationship label.
5. For accepted candidates call `add_edge` with the returned `suggested_edge`; adjust the label only when you have better evidence.
6. Use `get_node` only on top candidates that need more detail before deciding. Never bulk-read the whole graph to find link targets.
7. As the graph grows, raise `threshold` or lower `limit` to keep responses small — this keeps the flow scalable to thousands of nodes.

## Parsing and Normalization

For each SQLite node:
1. Read entity type from `type` using canonical names from `brain_ds.ontology.EntityType` (including `Organization` when present in graph outputs).
2. Extract `name` from `label`.
3. Normalize body fields from `details`:
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
| Problem / Improvement Area ↔ Data Source | Problem or improvement area references Data Source name/system |
| Problem / Improvement Area ↔ Role | Problem or improvement area `Where` overlaps Role `Where` |
| Project ↔ Department | Project departments overlap with Department names/tokens |
| Project ↔ Risk | Project `risk_ids` or textual overlap links to Risk entities |
| Decision ↔ Project/Risk | Decision `affects[]`/`supersedes` or contextual overlap |
| KPI ↔ Department | KPI owner dept maps to Department (`owned-by`) |
| KPI ↔ Role | KPI owner role maps to Role (`accountable`) |
| KPI ↔ Data Source | KPI measurement source maps to Data Source (`measured-by`) |
| KPI ↔ Problem / Improvement Area | KPI degraded by linked problems or improvement areas (`degraded-by`) |
| Solution ↔ KPI | Solution expected impact references KPI (`improves`) |
| Solution ↔ Problem / Improvement Area | Solution resolves linked problems or improvement areas (`resolves`) |
| Decision ↔ KPI | Decision rationale references KPI (`targets`) |
| Decision ↔ Solution | Solution links to decision context (`decided-by`) |

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
  - Problem / Improvement Area: "What problem or improvement area is slowing the workflow or creating risk?"
  - KPI: "What KPI should we track to measure outcome?"
  - Solution: "What solution could improve this KPI or resolve this problem/improvement area?"
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
- Problems/improvement areas and heuristics not mapped to data sources.

### Provenance Table columns
- Entity Type
- Entity Name
- Observation ID

## Graph JSON Output Mode (`--graph-json`)

When command includes `--graph-json`, produce JSON data contract output instead of Mermaid/Markdown report rendering.

### JSON Contract (Mandatory)

```json
{
  "schema_version": "2.0.0",
  "org": "Organization Name",
  "generated_at": "YYYY-MM-DDTHH:MM:SSZ",
  "evidence": [
    {
      "id": "obs-123",
      "type": "observation",
      "source": "engram",
      "content": "Operations depends on ETA feed",
      "provenance": {"session_id": "manual-save-brain_ds"},
      "timestamp": "2026-05-13T23:00:00Z"
    }
  ],
  "nodes": [
    {
      "id": "node_id",
      "label": "Display Name",
      "type": "Canonical `brain_ds.ontology.EntityType` value",
      "details": {
        "what": "...",
        "why": "...",
        "where": "...",
        "learned": "..."
      },
      "card_sections": [
        {"title": "What", "content": "...", "icon": "info", "order": 1},
        {"title": "Why", "content": "...", "icon": "target", "order": 2},
        {"title": "Where", "content": "...", "icon": "map-pin", "order": 3},
        {"title": "Learned", "content": "...", "icon": "lightbulb", "order": 4}
      ],
      "evidence_ids": ["obs-123"]
    }
  ],
  "edges": [
    {
      "source": "node_id_1",
      "target": "node_id_2",
      "label": "relationship type",
      "edge_id": "edge-001",
      "weight": 0.78,
      "reasons": ["Base relationship weight for depends-on: 0.60"],
      "evidence_ids": ["obs-123", "obs-456"]
    }
  ]
}
```

This JSON is the **v2 export shape** produced by `Graph.to_dict()`.
The canonical contract is Python-first (`brain_ds.ontology.graph_model.Graph` and related dataclasses).

Edge scoring fields are optional and backward-compatible:
- `weight`: float in `[0.0, 1.0]`
- `reasons`: deterministic explainability strings
- `evidence_ids`: supporting observation IDs used by scoring

Rules:
- Always run the SQLite retrieval workflow above.
- Build top-level `evidence[]` records from node/edge evidence already stored in SQLite when available; otherwise emit an empty list.
- Every node SHOULD include `card_sections` when `details` content exists; if all detail fields are empty, set `card_sections` to `null`.
- Every node SHOULD include `evidence_ids` linking to `evidence[].id` when source observations are known; use `null` when unavailable.
- Edges MUST keep `evidence_ids` linked to the same `evidence[].id` namespace used by nodes.
- Do not create entity-family-specific card templates in producer output; keep generic ordered sections only.
- Save JSON locally as `<resolved-org-slug>-graph.json`.
- `--graph-json` alone does **not** invoke Python viewer generation.

### JSON Persistence Rule (`--graph-json --save`)

Use only when command includes both `--graph-json` and `--save`:

```json
[
  {"tool": "create_graph", "graph_id": "<resolved-org-slug>", "name": "<resolved-org-name>", "project": "brain_ds"},
  {"tool": "update_node", "graph_id": "<resolved-org-slug>", "node_id": "<node-id>", "label": "<label>", "type": "<EntityType value>", "supertype": "<EntityType supertype>", "details": {"what": "...", "why": "...", "where": "...", "learned": "..."}},
  {"tool": "add_edge", "graph_id": "<resolved-org-slug>", "source": "<source-node-id>", "target": "<target-node-id>", "label": "<RelationshipType value>"}
]
```

If `create_graph` reports that the graph already exists, continue with `update_node` / `add_edge`.
If `--save` is absent, do NOT persist the generated graph back to SQLite.

## Graph UI Automation Mode (`--graph-ui`)

When command includes `--graph-ui`, run end-to-end automation:

1. Generate graph JSON exactly as `--graph-json` mode.
2. Save `<resolved-org-slug>-graph.json`.
3. Attempt viewer generation with:
   - `uv run brain_ds ui <resolved-org-slug>-graph.json`
4. On success, report both JSON and HTML output paths.
5. On failure (CLI unavailable, browser-open issue, Python missing, or command error), keep JSON output and show clear hint:
    - `uv sync`
   - If HTML generation succeeds but browser open fails, treat it as success and return the HTML path (graceful degradation).
   - If `--simple` is explicitly requested elsewhere and `pyvis` is missing, report that only simple fallback requires `pyvis`.

Graceful-degrade contract:
- Failure to generate HTML MUST NOT fail JSON generation.
- Always return the JSON artifact path even when viewer generation fails.

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
| Problem / Improvement Area | hexagon | `P_DUP{{Duplicate entry}}` |
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

Use ontology-backed relationship labels from `brain_ds.ontology.RelationshipType` where relevant (`owns`, `uses`, `depends-on`, `blocked-by`, `creates-risk`, `decided-by`, `measured-by`, `shared-with`, `owned-by`, `accountable`, `degraded-by`, `targets`, `improves`, `resolves`).

Canonical contract note (spec-facing):
- Canonical labels are defined in `brain_ds.ontology.RelationshipType`.
- Treat non-ontology labels (for example `impacted-by`, `impacts`, `authorized-by`) as legacy synonyms only in narrative discussion; do not emit them in Mermaid edges.

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
| Partial | `[Department] Operations` with `Where`; `[Role] Fleet Manager` without `Where` | Entity table includes sparse role flag; Missing Knowledge lists Data Source, Heuristic, Tacit Knowledge, Problem / Improvement Area prompts |
| Connected | Department and Role share "operations control room"; Data Source has same context | Role -> Data Source appears in Information Flows; Department ↔ Role overlap labeled `weak` or `strong` by token count |
| KPI-linked | KPI linked to owner/data source/problem or improvement area | KPI pill node plus `owned-by`, `accountable`, `measured-by`, `degraded-by` edges |
| Solution-linked | Solution linked to KPI/problem or improvement area/decision | Solution parallelogram node with `improves`, `resolves`, `decided-by` edges |
| Decision-linked | Decision references KPI and linked solutions | Decision rounded node with `targets` edge to KPI and `decided-by` linkage for solutions |

## Worked Graph Examples (Contract-level)

| Dataset State | Expected `--graph` behavior |
|---|---|
| Empty | Exact output: `%% No entities captured — run /elicit-context first` |
| Minimal (1 dept, 2 roles) | Single subgraph, 3 nodes, no dashed edges |
| LogiTrans-scale | 4 department detail subgraphs + dashed shared edges + legend |

## Optional Save Procedure

Use only when command is `/map-connections --save`:

1. Keep the inline Markdown report for the user.
2. Persist any newly synthesized nodes/edges with the same `create_graph` → `update_node` → `add_edge` SQLite MCP sequence.
3. Do NOT use Engram as the source of truth for org/domain graph persistence.

## Org Scoping Examples

| Scenario | Input | Expected |
|---|---|---|
| Explicit org override | `/map-connections --org megacorp` | use `megacorp`; include only `org/megacorp/domain/...` |
| Active-org fallback | `/map-connections` with `session/active-org=logitrans` | use `logitrans` scoped entities only |
| Default compatibility | no explicit org and no active state | resolve `default`; include legacy `domain/...` plus `org/default/domain/...` |
| Mixed-org guard | retrieved entities from two orgs | exclude non-resolved org; add warning if exclusions happened |
| No org data | resolved org has zero records | emit main-workflow guard warning and keep output deterministic |
