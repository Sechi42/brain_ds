---
name: generate-brd
description: |
  Generate a deterministic 14-section Business Requirements Document from domain entities stored in SQLite.
  Trigger: /generate-brd or /generate-brd --save
license: MIT
disable-model-invocation: true
metadata:
  author: sechi42
  version: "1.4.0"
---

# Generate BRD Skill

## When to Use
- Run ONLY on explicit `/generate-brd`.
- Use `/generate-brd --save` only when user explicitly asks to persist BRD.

## Command Contract

| Command | BRD persistence | ADR persistence | Behavior |
|---|---|---|---|
| `/generate-brd` | No | Yes (always-on) | Build and show inline 14-section BRD. |
| `/generate-brd --org <name|slug>` | No | Yes (always-on) | One-run org override; no active-org mutation. |
| `/generate-brd --save` | Yes — graph node `brd-<slug>` (UI) + Engram `org/<slug>/domain/brd/{timestamp}` | Yes (always-on) | Build BRD, show inline, then persist BRD to the graph AND Engram + ADR. |
| `/generate-brd --strict [--save]` | Only if COMPLETE | Yes (always-on) | Gate on `assess_completeness`: if the matrix is not COMPLETE, refuse with an actionable gap list instead of generating. |

## Strict Mode (`--strict`)

- ALWAYS (strict or not): before composing, call `assess_completeness(graph_id)` and open the output with a **Gaps Detectados** section — entity counts per type, missing types, and which BRD sections will carry `[NEEDS DATA]`.
- With `--strict`: if the completeness matrix is not COMPLETE (any missing entity type or underspecified node), **refuse** to generate/persist. Return an actionable error listing each gap and the elicitation prompt that closes it.
- `--save` without `--strict` stays permissive: persist the PARTIAL BRD with explicit `[NEEDS DATA]` markers. `--strict --save` demands COMPLETE.

## Retrieval Workflow (Mandatory)

Resolve organization in order: `--org` > `session/active-org` > `default`, and echo:
`Resolved organization: <name> (<source>)`

Run typed SQLite retrievals against the resolved org graph.

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
1. `list_nodes` is the PRIMARY retrieval path for the BRD dataset fingerprint and section assembly.
2. Use `search_graph` only when a section needs targeted substring expansion inside the same graph.
3. Never use `mem_search` / `mem_get_observation` for org domain retrieval in this workflow.
4. typed SQL filters are not equivalent to Engram substring search; validate the difference on a seeded vault before assuming parity.
5. If the resolved graph is empty, generate the starter BRD from the SQLite-empty state, not from Engram fallbacks.

## Normalization Rules

Extract fields from SQLite rows: `entity_type` (`type`), `name` (`label`), `what`, `why`, `where`, `learned` (`details.*`), `tokens`, `source_id`.
Supported tags follow canonical ontology names from `brain_ds.ontology.EntityType`.

## BRD Output Contract (Section Order Mandatory)

Always output exactly:
1. `## Header`
2. `## Executive Summary`
3. `## Current State Analysis`
4. `## Requirements`
5. `## Data Sources & Dependencies`
6. `## Stakeholder Impact`
7. `## Solution Options`
8. `## ADR Log`
9. `## Data Provenance`
10. `## Risk Register`
11. `## Cross-Dept Overlap Map`
12. `## Project Portfolio`
13. `## KPI Dashboard`
14. `## Improvement Roadmap`

Header MUST include:
- `Status: EMPTY|PARTIAL|COMPLETE`
- `BRD Version: 1.2`
- `Organization: <resolved-org-name> (<resolved-org-slug>)`
- `Dataset Fingerprint:` counts in order: Department, Role, Data Source, Heuristic, Tacit Knowledge, Problem / Improvement Area, Project, Risk, Decision, KPI, Solution.

## Section Rules for KPI/Solution

### Section 13: KPI Dashboard
Columns:
- KPI
- Target/Current
- Unit
- Frequency
- Owner
- Data Source
- Linked Problems / Improvement Areas
- Linked Solutions
- Decision Impact

Rules:
- If no KPI entities: `[NEEDS DATA: KPI entities missing]`.
- If partial KPI fields: render row and fill unknown cells with `Unknown`.
- Trend cue from target/current: `↑` improvement target, `↓` reduction target, `→` no-change.

### Section 14: Improvement Roadmap
Columns:
- Solution
- Expected Impact
- Status
- Effort
- Owner
- Improves KPI
- Resolves Problem / Improvement Area
- Authorized By Decision

Rules:
- If no Solution entities: `[NEEDS DATA: Solution entities missing]`.
- Render available rows even when KPI table is empty.

## Empty / Partial / Complete

- **EMPTY**: zero normalized entities; produce Starter-BRD with all 14 sections and `[NEEDS DATA]` prompts.
- **PARTIAL**: populate what has evidence; missing sections get explicit NEEDS DATA markers.
- **COMPLETE**: all required bundles have evidence; no NEEDS DATA markers.

## Data Provenance Rules

For every section, list source observation IDs used; if none, write `No source observations` plus missing entity type(s).

## ADR Save Contract (Always-on)

Persist ADR on every invocation with:
- title: `[ADR] Create BRD {timestamp}`
- type: `architecture`
- topic_key: `architecture/adr/create-brd-{timestamp}`
- include completeness matrix and cited source IDs for all 14 sections.

## Optional BRD Save Contract (`--save` only)

`/generate-brd --save` persists the BRD to TWO stores. Both writes are mandatory — skipping either is a workflow violation.

### 1. Graph node (UI visibility — PRIMARY)

The brain_ds UI BRD panel reads exactly one node per organization: id `brd-<graph-id>`. Without this write the BRD never appears in the UI. Call `update_node`:

```json
{
  "graph_id": "<resolved-org-slug>",
  "node_id": "brd-<resolved-org-slug>",
  "label": "BRD",
  "type": "Unknown",
  "card_sections": [
    {"title": "Contenido", "content": "<full markdown BRD with 14 sections>", "order": 0, "icon": ""}
  ]
}
```

Rules:
- `node_id` MUST be exactly `brd-<graph-id>` — the UI panel looks up that id.
- `card_sections[0]` MUST keep title `Contenido` and order `0`; the panel reads that section.
- `update_node` is upsert-safe: re-running `--save` replaces the previous BRD content.
- The write emits a live node event, so a running UI refreshes without restart.
- Every mention of a graph entity in the BRD markdown MUST be a wikilink `[[<node label>]]` (or `[[<node label>|<display text>]]` for inline phrasing). The UI renders these as Obsidian-style navigable links to the node; plain-text mentions leave the BRD disconnected from the graph.

### 2. Engram mirror (agent memory)

```json
{
  "title": "[BRD] Generated business requirements document {timestamp}",
  "type": "discovery",
  "scope": "project",
  "topic_key": "org/{resolved-org-slug}/domain/brd/{timestamp}",
  "content": "<full markdown BRD with 14 sections>",
  "project": "brain_ds"
}
```

When persisting synthesized org/domain entities or links discovered during BRD generation, use the SQLite MCP write path (`create_graph` if needed, then `update_node` / `add_edge`) rather than Engram domain memories.

## Worked Examples

| Dataset state | Expected behavior |
|---|---|
| Empty | 14-section Starter-BRD, all `[NEEDS DATA]`, including KPI/Solution markers. |
| Partial KPI only | Section 13 populated, Section 14 marker for missing solutions. |
| Partial Solution only | Section 14 populated, Section 13 marker for missing KPIs. |
| Linked KPI+Solution+Decision | Section 13 and 14 populated with KPI/Solution linkage and Decision impact/authorization. |
