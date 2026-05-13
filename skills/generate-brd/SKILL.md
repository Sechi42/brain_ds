---
name: generate-brd
description: |
  Generate a deterministic 14-section Business Requirements Document from domain memories in Engram.
  Trigger: /generate-brd or /generate-brd --save
license: MIT
disable-model-invocation: true
metadata:
  author: sechi42
  version: "1.3.1"
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
| `/generate-brd --save` | Yes (`org/<slug>/domain/brd/{timestamp}`) | Yes (always-on) | Build BRD, show inline, then persist BRD + ADR. |

## Retrieval Workflow (Mandatory)

Resolve organization in order: `--org` > `session/active-org` > `default`, and echo:
`Resolved organization: <name> (<source>)`

Run these **11 queries in parallel**:
`[Department]`, `[Role]`, `[Data Source]`, `[Heuristic]`, `[Tacit Knowledge]`, `[Problem / Improvement Area]`, `[Project]`, `[Risk]`, `[Decision]`, `[KPI]`, `[Solution]`.

Then:
1. Dedupe IDs.
2. Call `mem_get_observation(id)` for every ID.
3. Never synthesize from `mem_search` preview snippets.
4. Filter to `org/<resolved-slug>/domain/...`; include bare `domain/...` only when slug=`default`.
5. Never mix org prefixes.

## Normalization Rules

Extract fields: `entity_type`, `name`, `what`, `why`, `where`, `learned`, `tokens`, `source_id`.
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

Save BRD only for `/generate-brd --save`:

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

## Worked Examples

| Dataset state | Expected behavior |
|---|---|
| Empty | 14-section Starter-BRD, all `[NEEDS DATA]`, including KPI/Solution markers. |
| Partial KPI only | Section 13 populated, Section 14 marker for missing solutions. |
| Partial Solution only | Section 14 populated, Section 13 marker for missing KPIs. |
| Linked KPI+Solution+Decision | Section 13 and 14 populated with KPI/Solution linkage and Decision impact/authorization. |
