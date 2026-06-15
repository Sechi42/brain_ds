# brain_ds Skills — Shared Context

_Auto-generated. Regenerate with `/share-brainds` after any skill change._

**Last updated**: 2026-06-14

---

## brainds-docs

**Trigger**: when writing or updating node documentation, card_sections, or BRD content.
**Inputs**: entity type, entity details (what/why/where/learned), related node ids for wikilinks.
**Outputs**: populated `card_sections` JSON array and `details` object ready for `update_node`; markdown tables for Columns/Fields sections; wikilink references using `[[node-id|Label]]` syntax.
**MCP tools**: none (documentation authoring skill — does not call MCP directly; produced output is passed to `update_node` by the calling agent).

This skill encodes brain_ds ontology rules for writing node content with low cognitive load. It defines canonical section ordering per entity type (e.g., Data Source: Overview → Structure → Columns / Fields → Purpose → Owner → Refresh Cadence), mandatory markdown table format for Columns/Fields, and wikilink syntax for cross-node references. It applies progressive disclosure (Overview first, details after) and recognition-over-recall patterns (tables over prose, checklists over paragraphs).

---

## brainds-registry

**Trigger**: after adding/renaming entity types, relationship types, MCP tools, or editing any SKILL.md.
**Inputs**: the changed artifact (entity_types.py, relationship_types.py, tools.py, scoring/engine.py, or SKILL.md).
**Outputs**: a checklist of files that must be updated in the same commit; confirmation that the drift guard, harness, CLAUDE.md, and skill mirrors are all in sync.
**MCP tools**: none (registry audit skill — produces a checklist for the developer to execute).

This skill encodes the brain_ds harness-maintenance contract from CLAUDE.md. For each change type it prescribes the exact downstream files to update: EntityType changes require QUESTION_BANK entries in grounding.py and ELICIT_EXEMPT_TYPES in the drift guard test; RelationshipType changes require CONNECTION_RULES prose review; MCP tool count changes require CLAUDE.md inventory and test assertion updates; skill prose changes require grounding.py Category-2 constant updates and `.opencode/skills/` mirror sync.

---

## elicit-context

**Trigger**: `/elicit-context` (explicit slash command only — never auto-activated).
**Inputs**: user answers to a structured interview (max 5 questions per session); optional `--org <name|slug>` flag.
**Outputs**: domain entities persisted to SQLite via brain_ds MCP (`create_graph` → `update_node` → `add_edge`); active org state saved to engram at `session/active-org`.
**MCP tools**: `create_graph`, `update_node`, `add_edge`, `suggest_connections`.

This skill runs a completeness-gated domain knowledge interview for Data Science discovery. It resolves the active organization, asks one question at a time, evaluates coverage across all 10 entity types (Organization, Data Source, Department, Role, Heuristic, Tacit Knowledge, Problem / Improvement Area, KPI, Solution, Decision), and shows a Remaining Gaps checklist before any persistence. Data Source nodes require concrete identifiers (system name, table/sheet name, column table, owner) before they can be marked complete. This skill runs during the **`intake`** stage of the six-stage pipeline (`setup → intake → map → brd → verify → archive`), specifically on the `human_org` path of `intake_paths`; the `datasource` path delegates to `brainds-source-explorer` instead.

---

## generate-brd

**Trigger**: `/generate-brd` or `/generate-brd --save` (explicit slash command only).
**Inputs**: domain entities stored in SQLite for the resolved org graph; optional `--org <name|slug>` and `--save` flags.
**Outputs**: a deterministic 14-section Business Requirements Document (Header, Executive Summary, Current State Analysis, Requirements, Data Sources & Dependencies, Stakeholder Impact, Solution Options, ADR Log, Data Provenance, Risk Register, Cross-Dept Overlap Map, Project Portfolio, KPI Dashboard, Improvement Roadmap); an ADR persisted to engram on every run; optional BRD persist to engram on `--save`.
**MCP tools**: `list_nodes` (typed per entity family), `search_graph`.

This skill retrieves the full org domain from SQLite using typed `list_nodes` calls (never Engram for domain data) and assembles the BRD in strict section order. Empty sections get `[NEEDS DATA: <entity type> entities missing]` markers — no section is ever omitted. The BRD Header includes Status (EMPTY/PARTIAL/COMPLETE), version, org name, and a Dataset Fingerprint with entity counts.

---

## map-connections

**Trigger**: `/map-connections`, `/map-connections --graph`, `/map-connections --save`, `/map-connections --graph-json`, `/map-connections --graph-ui` (explicit slash command only).
**Inputs**: domain entities stored in SQLite for the resolved org graph; optional `--org`, `--graph`, `--graph-json`, `--graph-ui`, and `--save` flags.
**Outputs**: a 7-section Markdown relationship map (Entity Table, Information Flows, Overlaps, Broken Links, Missing Knowledge, DS Intervention Opportunities, Provenance Table); optional Mermaid graph (`--graph`); optional v2 JSON export (`--graph-json`); optional graph viewer launch (`--graph-ui`).
**MCP tools**: `list_nodes`, `search_graph`, `suggest_connections`, `add_edge` (when --save with new links), `update_node`.

This skill builds a deterministic connection map across all entity types using token-overlap scoring and ontology-backed relationship labels. It uses `suggest_connections` for new-node linking (Connection RAG) and `list_nodes` for full-report retrieval. Cross-department edges are rendered as dashed arrows in Mermaid output. Graphs with more than 24 nodes or 40 edges are condensed into an Overview Graph plus per-department Detail Graphs.

---

## share-brainds

**Trigger**: after creating/modifying any brain_ds skill, or `/share-brainds`.
**Inputs**: all `skills/*/SKILL.md` files in the project root.
**Outputs**: regenerated `skills/SHARED_CONTEXT.md` with one-paragraph summary per skill (name, trigger, inputs, outputs, MCP tools used); reminder to sync `.opencode/skills/` mirrors.
**MCP tools**: none (file authoring skill).

This skill maintains a cheap, always-current index of every brain_ds skill so agents and collaborators can understand each skill's purpose without reading full SKILL.md files. It scans all skill directories, extracts key metadata, and writes alphabetically ordered summaries to `skills/SHARED_CONTEXT.md`. It must be run after any skill is created, modified, or removed to keep the index accurate.

---

_Mirror reminder: `.opencode/skills/` must mirror `skills/` byte-identically. Copy any new or changed SKILL.md files after regenerating this index._
