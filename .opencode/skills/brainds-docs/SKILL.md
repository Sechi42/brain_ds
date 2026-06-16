---
name: brainds-docs
description: |
  Write node documentation and card_sections content for brain_ds graph nodes with low cognitive load, following ontology rules and progressive disclosure patterns.
  Trigger: when writing or updating node documentation, card_sections, or BRD content
license: MIT
disable-model-invocation: true
metadata:
  author: sechi42
  version: "1.0.0"
---

# brain_ds Docs Skill

## When to Use

- When populating or editing `card_sections` on any graph node.
- When writing the `details` object (what/why/where/learned) for `update_node` calls.
- When generating BRD section content that will be stored back as node documentation.
- When a node's documentation feels dense, unstructured, or hard to scan.

## Critical Patterns

| Pattern | Rule |
|---------|------|
| Lead with answer | Put the fact first; motivation and context come after. |
| Progressive disclosure | `Overview` section first, detail sections after (Columns, Refresh, Owner). |
| Recognition over recall | Use markdown tables for Columns/Fields; use checklists for quality notes. |
| Wikilinks | Reference related nodes as `[[node-id\|Display Label]]` so the UI can render links. |
| Chunking | One concept per `card_section`; keep each section under 10 lines. |
| Signposting | Use the standard section titles below — agents and the UI expect them. |

## Entity-Type Section Map

Each entity type has canonical expected sections. Always include sections in this order.

| Entity Type | Expected Sections (in order) |
|---|---|
| Data Source | Overview, Structure, Columns / Fields, Purpose, Owner, Refresh Cadence |
| KPI | Overview, Current vs Target, Formula, Owner, Data Source, Linked Problems |
| Solution | Overview, Expected Impact, Status & Effort, Owner, Linked KPIs, Linked Decisions |
| Decision | Overview, Rationale, Alternatives Considered, Supersedes, Authorized Solutions |
| Problem / Improvement Area | Overview, Impact, Affected Departments, Workarounds, Linked Data Sources |
| Heuristic | Overview, When Applied, Known Limitations |
| Tacit Knowledge | Overview, Who Knows, Risk if Lost |
| Department | Overview, Responsibilities, Key Roles |
| Role | Overview, Accountabilities, Tools Used |
| Organization | Overview, Industry & Region, Key Contacts |

For entity types not in this table, use: `Overview`, then `Details`, then any domain-specific sections.

## card_sections Format

```json
[
  {"title": "Overview",         "content": "One-sentence lead answer.",          "icon": "info",     "order": 1},
  {"title": "Structure",        "content": "DB: fleet_postgres / table: deliveries", "icon": "database", "order": 2},
  {"title": "Columns / Fields", "content": "| Column | Type | Meaning | Notes |\n|---|---|---|---|\n| eta | datetime | Estimated arrival | UTC |", "icon": "table", "order": 3},
  {"title": "Purpose",          "content": "Feeds daily dispatch decisions.",    "icon": "target",   "order": 4},
  {"title": "Owner",            "content": "[[org-role-fleet-manager|Fleet Manager]]", "icon": "user", "order": 5},
  {"title": "Refresh Cadence",  "content": "Real-time via CDC.",                 "icon": "clock",    "order": 6}
]
```

Rules:
- `order` must be monotonically increasing starting at 1.
- `icon` values: `info`, `database`, `table`, `target`, `user`, `clock`, `lightbulb`, `alert`, `map-pin`, `link`.
- BRD nodes (`node_id` starting with `brd-`, `type = "Unknown"`) are the ONLY carve-out: defer to `BRD_GRAPH_PERSISTENCE_CONTRACT`, so `card_sections[0]` uses `order: 0` and `icon: ""`.
- `content` is plain Markdown — tables, bullets, and wikilinks are all valid.
- Never put raw HTML inside `content`.

## Columns / Fields Table (Data Source mandatory)

When writing a Data Source node, the `Columns / Fields` section MUST use this exact table format:

```markdown
| Column / Field | Type | Meaning | Notes |
|---|---|---|---|
| delivery_id | integer | Unique delivery identifier | Primary key |
| eta | datetime | Estimated time of arrival | UTC, nullable during route init |
| status | varchar | Current delivery state | Enum: pending, in-transit, delivered, failed |
```

Mark vague columns with `[needs clarification]` in the Notes cell — never omit them.

## Change Detection (re-documentation decision)

At `level==table`, `explore_source` returns a `change_detection` block with a `verdict`. Use it to decide HOW to document a Data Source — never blindly rewrite:

| Verdict | Action |
|---|---|
| `unchanged` | Skip — report a no-op; do NOT re-document. |
| `changed` | Delta mode — re-document only what `change_detection.delta` lists (added/removed/altered columns, added/removed tables) as a Reflexion-style critique, not a full rewrite. |
| `new` | Full first-time documentation pass. |
| `unknown-baseline` | Full pass to re-establish the baseline (node predates this feature). |

After documenting a `new`/`unknown-baseline`/`changed` table, write the baseline back via `update_node` under `details.schema_baseline` (`schema_hash`, `documented_schema_snapshot`, `last_documented_at`). Because `explore_source` hashes **one table at a time**, a multi-table source stores `schema_baseline` as a **per-table map** — `{<table_name>: {schema_hash, documented_schema_snapshot, last_documented_at}, ...}` — so write/refresh ONLY the entry for each table you (re-)documented and preserve the others (a single-table source may use the flat shape directly; the reader accepts both). The baseline is a **graph write only** — change detection never writes to the source. Canonicalization means column reorder, varchar widening, and type synonyms never trigger a false `changed`.

## Wikilink Syntax

Use `[[node-id|Display Label]]` to reference related nodes so the graph UI renders clickable cards.

```markdown
Owner: [[logitrans-role-fleet-manager|Fleet Manager]]
Feeds: [[logitrans-kpi-on-time-delivery|On-Time Delivery %]]
Blocked by: [[logitrans-problem-duplicate-entry|Duplicate Entry]]
```

Rules:
- `node-id` must be a valid existing node id in the same graph (format: `<org-slug>-<entity-type-slug>-<short-name-slug>`).
- If the target node does not exist yet, use plain text and note `[link pending — node not yet created]`.
- Never fabricate node ids.

## details Object (update_node)

The `details` object feeds `card_sections` generation. Keep each field under 3 sentences.

```json
{
  "what": "Daily ETL extract from fleet_postgres.deliveries table.",
  "why": "Feeds ETA predictions and dispatch queue prioritization.",
  "where": "Operations control room; accessed by Fleet Manager and Dispatch team.",
  "learned": "Vendor quality drops on Fridays; ETAs become unreliable after 17:00."
}
```

- `what`: fact statement — system name, table name, file name, or measurement definition.
- `why`: business motivation — which decision depends on it.
- `where`: org/process/system location — department, role, or context.
- `learned`: non-obvious nuance, heuristic, or quality note. Omit if none.

## Progressive Disclosure Order

1. `Overview` (one sentence — the lead answer).
2. Structural details (table, system name, URL, path).
3. Semantic content (purpose, impact, formula, rationale).
4. Ownership & process (owner, cadence, review cycle).
5. Quality & risks (known issues, gaps, caveats) — only when relevant.

## Commands

```bash
# Validate card_sections JSON shape (requires jq)
echo '<card_sections_json>' | jq '[.[] | {title, content, icon, order}]'

# Search for wikilink targets in the active graph
brain_ds mcp list_nodes --graph-id <org-slug>
```
