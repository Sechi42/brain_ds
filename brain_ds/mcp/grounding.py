"""MCP grounding context module.

Provides three categories of context for the B1 context-return tools:
- Category-1: derived at runtime from ontology enums (zero drift).
- Category-2: hand-maintained Python constants (skill workflow prose for
  non-Claude clients that do not ship skills/*.md files).
- Category-3: live workspace scoping (build_workspace_context) — reads the
  active store metadata and the global workspace registry so agents always
  know WHICH vault they are touching before reading or writing.

The Category-1/2 composers stay pure (no store queries, no I/O); only the
Category-3 builder touches the store and the registry.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import brain_ds.workspaces as workspace_registry
from brain_ds.ontology.entity_types import EntityType
from brain_ds.ontology.relationship_types import BASE_WEIGHTS, RelationshipType
from brain_ds.scoring.engine import ScoringEngine
from brain_ds.verify.edge_calibration import EdgeCalibrationReport, calibrate_edges, load_gold_set
from brain_ds.verify.edge_rollout import evaluate_rollout_gates

SUPPORTED_DOCUMENTATION_LANGUAGES = {"en", "es"}
SEED_GOLD_SET_PATH = Path(__file__).resolve().parents[2] / "tests" / "gold" / "edge_gold_set.jsonl"


@dataclass(frozen=True)
class _CalibrationGroundingCache:
    report: EdgeCalibrationReport
    status: str
    thresholds: dict[str, dict[str, float]]


_calibration_grounding_cache: _CalibrationGroundingCache | None = None

DOCUMENTATION_LANGUAGE: dict[str, dict[str, object]] = {
    "en": {
        "label": "Documentation language",
        "directives": [
            "Write all user-facing documentation, card sections, and grounding deliverables in English.",
            "Keep entity identifiers, tool names, graph ids, and code-like values unchanged.",
        ],
    },
    "es": {
        "label": "Idioma de documentación",
        "directives": [
            "Redactá toda la documentación visible, card_sections y entregables de grounding en español.",
            "Mantené sin traducir identificadores de entidades, nombres de herramientas, graph ids y valores de código.",
        ],
    },
}

# ---------------------------------------------------------------------------
# Category-1 builders — derived from live ontology enums
# ---------------------------------------------------------------------------


def build_entity_types() -> list[dict[str, object]]:
    """Return all EntityType members as dicts with value/supertype/expected_sections."""
    return [
        {
            "value": e.value,
            "supertype": e.supertype,
            "expected_sections": e.expected_sections,
        }
        for e in EntityType
    ]


def build_supertypes() -> list[str]:
    """Return sorted unique supertype strings derived from EntityType."""
    return sorted({e.supertype for e in EntityType})


def build_expected_sections() -> dict[str, list[str]]:
    """Return mapping of entity-type value → expected section list."""
    return {e.value: e.expected_sections for e in EntityType}


def build_relationship_types() -> list[dict[str, str]]:
    """Return all RelationshipType members as dicts with value/description."""
    return [{"value": r.value, "description": r.description} for r in RelationshipType]


def build_base_weights() -> dict[str, float]:
    """Return BASE_WEIGHTS as a string-keyed dict (value → weight)."""
    return {r.value: BASE_WEIGHTS[r] for r in RelationshipType}


def build_relationship_labels() -> list[str]:
    """Return all RelationshipType values as a flat list."""
    return [r.value for r in RelationshipType]


def build_scoring_factors() -> dict[str, float]:
    """Return a copy of ScoringEngine factor_weights dict."""
    return dict(ScoringEngine().factor_weights)


def build_calibration_grounding() -> dict[str, object]:
    """Return cached calibration rollout status and per-label thresholds.

    The seed gold records are parsed lazily at call time, never import time, so
    tests can patch the calibration helpers without import-order side effects.
    """
    global _calibration_grounding_cache
    if _calibration_grounding_cache is None:
        records = load_gold_set(SEED_GOLD_SET_PATH, min_examples_per_type=5)
        report = calibrate_edges(records, run_id="seed-20260623")
        rollout = evaluate_rollout_gates(report, records)
        thresholds = {
            label: {
                "accept": float(metrics.accept_threshold),
                "reject": float(metrics.reject_threshold),
            }
            for label, metrics in sorted(report.classes.items())
        }
        _calibration_grounding_cache = _CalibrationGroundingCache(
            report=report,
            status=rollout.status,
            thresholds=thresholds,
        )
    return {
        "status": _calibration_grounding_cache.status,
        "thresholds": _calibration_grounding_cache.thresholds,
    }


def get_calibration_report() -> EdgeCalibrationReport:
    """Return the cached calibration report, initializing grounding if needed."""
    build_calibration_grounding()
    if _calibration_grounding_cache is None:  # defensive: build either sets cache or raises.
        raise RuntimeError("calibration grounding cache failed to initialize")
    return _calibration_grounding_cache.report


# ---------------------------------------------------------------------------
# Category-2 constants — hand-maintained, lifted from frozen SKILL.md prose.
# Each constant carries a source-pointer comment for future sync.
# ---------------------------------------------------------------------------

# Source: skills/elicit-context/SKILL.md "Question Bank"
QUESTION_BANK: dict[str, list[str]] = {
    "Organization": [
        "What is the organization name?",
        "What industry and region should we register for this org?",
    ],
    "Data Source": [
        "What systems/files/APIs feed this process?",
        "What kind of source is it (relational DB, NoSQL, Excel/CSV, API, SaaS)?",
        "For a database: which database and tables? For Excel/CSV: which workbook and sheets?",
        "Which key columns/fields matter, and what does each one mean?",
        "What is this source used for, and which decisions depend on it?",
        "Who owns or manages it day-to-day?",
        "How often is it refreshed or updated (real-time, daily, weekly, manual)?",
        "Which data source is least trusted and why?",
    ],
    "Department": [
        "Which departments participate in this workflow?",
        "Which department owns final accountability for the outcome?",
    ],
    "Role": [
        "Who makes the key decisions day-to-day?",
        "Which role is blocked most often and why?",
    ],
    "Heuristic": [
        "What manual rules do people apply when data is incomplete?",
        "Which shortcut is used to decide faster under pressure?",
    ],
    "Tacit Knowledge": [
        "What critical knowledge exists only in people's heads?",
        "What do experienced teammates know that new hires usually miss?",
    ],
    "Problem / Improvement Area": [
        "What problem or improvement area is slowing the workflow or creating risk?",
        "What workaround appears most frequently?",
    ],
    "KPI": [
        "What KPI should we track?",
        "What are current vs target values and unit?",
        "How often is it measured, by whom, and from which data source?",
    ],
    "Solution": [
        "What operational improvement are we proposing or implementing?",
        "Which KPI does it improve or which problem/improvement area does it resolve?",
        "What are status and effort (low/med/high)?",
    ],
    "Decision": [
        "What key decision was made and why?",
        "Which alternatives were considered, and what does this decision supersede or authorize?",
    ],
}

# Source: skills/elicit-context/SKILL.md "Organization Resolution Contract" — keep in sync (skills frozen this change).
ORG_SLUG_RULES: dict[str, object] = {
    "rules": [
        "lowercase kebab-case",
        "& -> and",
        "spaces, _, / -> -",
        "strip chars outside [a-z0-9-]",
        "collapse repeated -",
    ],
    "collision_handling": (
        "If create_graph reports that the slug already belongs to a different "
        "organization name, STOP and request explicit slug/name correction before saving."
    ),
}

# Source: skills/elicit-context/SKILL.md "SQLite node id rules" — keep in sync.
NODE_ID_FORMAT: str = (
    "Domain node id: <org-slug>-<entity-type-slug>-<short-name-slug>\n"
    "Org node id: <org-slug>-organization-<org-slug>"
)

# Source: skills/elicit-context/SKILL.md "SQLite MCP write contracts" — keep in sync.
SOURCE_KIND_ALIASES: dict[str, str] = {
    "sqlite": "relational-db",
    "postgres": "relational-db",
    "postgresql": "relational-db",
    "mysql": "relational-db",
    "sqlserver": "relational-db",
    "mssql": "relational-db",
    "relational-db": "relational-db",
    "xlsx": "excel",
    "xls": "excel",
    "excel": "excel",
    "sheets": "google-sheets",
    "google-sheets": "google-sheets",
    "aws-google-sheets": "google-sheets",
    "flat-file": "csv",
    "csv": "csv",
    "tsv": "csv",
    "api": "api",
    "rest": "api",
    "graphql": "api",
    "webhook": "event-stream",
    "event-stream": "event-stream",
    "stream": "event-stream",
}

SOURCE_KIND_HIERARCHY_TEMPLATES: dict[str, list[dict[str, object]]] = {
    "relational-db": [
        {"kind": "schema", "children": ["table", "view"]},
        {"kind": "table", "children": [{"kind": "column", "children": ["column"]}]},
        {"kind": "view", "children": [{"kind": "column", "children": ["column"]}]},
    ],
    "excel": [
        {"kind": "workbook", "children": ["worksheet"]},
        {"kind": "worksheet", "children": ["table", "range"]},
        {"kind": "table", "children": [{"kind": "column", "children": ["column"]}]},
        {"kind": "range", "children": [{"kind": "column", "children": ["column"]}]},
    ],
    "google-sheets": [
        {"kind": "spreadsheet", "children": ["worksheet"]},
        {"kind": "worksheet", "children": ["range", "table"]},
        {"kind": "range", "children": [{"kind": "column", "children": ["column"]}]},
        {"kind": "table", "children": [{"kind": "column", "children": ["column"]}]},
    ],
    "csv": [
        {"kind": "file", "children": ["column"]},
        {"kind": "column", "children": []},
    ],
    "api": [
        {"kind": "endpoint", "children": ["field"]},
        {"kind": "field", "children": []},
    ],
    "event-stream": [
        {"kind": "stream", "children": ["field"]},
        {"kind": "field", "children": []},
    ],
}


def normalize_source_kind(kind: str | None) -> str:
    normalized = (kind or "").strip().lower()
    return SOURCE_KIND_ALIASES.get(normalized, normalized or "relational-db")


def source_kind_hierarchy_template(kind: str | None) -> dict[str, object]:
    source_kind = normalize_source_kind(kind)
    template = SOURCE_KIND_HIERARCHY_TEMPLATES.get(source_kind, SOURCE_KIND_HIERARCHY_TEMPLATES["relational-db"])
    return {"source_kind": source_kind, "shape": template}


def build_source_kind_hierarchy_prose() -> str:
    lines = ["## Data Source Hierarchy Documentation", ""]
    for source_kind, shape in SOURCE_KIND_HIERARCHY_TEMPLATES.items():
        paths = []
        for item in shape:
            children = item.get("children") or []
            child_labels = [child.get("kind") if isinstance(child, dict) else str(child) for child in children]
            paths.append(f"{item['kind']} -> {', '.join(child_labels) if child_labels else 'leaf'}")
        lines.append(f"### {source_kind}")
        lines.extend(f"- {path}" for path in paths)
        lines.append("")
    lines.append("Capture each internal element as DataContainer/DataField with parent_id, depth, and details.kind.")
    return "\n".join(lines)


NODE_WRITE_TEMPLATES: dict[str, object] = {
    "generic": {
        "create_graph": {
            "graph_id": "<org-slug>",
            "name": "<org-name>",
            "project": "brain_ds",
            "note": "If the graph already exists, continue with node writes instead of aborting.",
        },
        "update_node": {
            "graph_id": "<org-slug>",
            "node_id": "<org-slug>-<entity-type-slug>-<short-name-slug>",
            "label": "<short-name>",
            "type": "<EntityType value>",
            "supertype": "<EntityType supertype>",
            "details": {
                "what": "<fact captured>",
                "why": "<business motivation / impact>",
                "where": "<org/process/system location>",
                "learned": "<non-obvious nuance, heuristic, problem, or improvement area>",
            },
        },
        "add_edge": {
            "graph_id": "<org-slug>",
            "source": "<source-node-id>",
            "target": "<target-node-id>",
            "label": "<RelationshipType value>",
        },
        "delete_node": {
            "graph_id": "<org-slug>",
            "node_id": "<existing-node-id>",
        },
        "delete_edge": {
            "graph_id": "<org-slug>",
            "source": "<source-node-id>",
            "target": "<target-node-id>",
        },
        "session_state": (
            "Persist session/active-org in Engram only; org domain entities now live in SQLite."
        ),
    },
    "Data Source": {
        "details": {
            "what": "<system/file/API description — exact product and identifiers>",
            "why": "<what this source is used for and which decisions depend on it>",
            "where": "<exact location: server/database, workbook path, API endpoint>",
            "learned": (
                "Kind: <relational-db|nosql|excel|csv|api|saas|other>; System: <exact product>; "
                "Database: <name or n/a>; Tables/Sheets: <names>; "
                "Key Columns/Fields: <name: meaning; name: meaning>; "
                "Purpose: <what it serves>; Owner: <dept/role>; Refresh: <cadence>; "
                "Trust: <high|medium|low — why>"
            ),
        },
        "structure_note": (
            "When column/table/sheet documentation exists, capture it as a markdown table "
            "in a 'Columns / Fields' card section: | Column/Field | Type | Meaning | Notes |. "
            "The viewer renders markdown tables in the reader."
        ),
        "hierarchy_template": build_source_kind_hierarchy_prose(),
        "connection_descriptor_note": (
            "To enable read-only exploration via explore_source / query_source, add a "
            "'connection' key to this node's details. Supported kinds:\n"
            "  sqlite/csv (file-path): "
            "{\"kind\": \"sqlite\"|\"csv\", \"path\": \"<project-relative path>\"}. "
            "The path must be within the project root (same sandbox as import_graph).\n"
            "  aws-postgres (Aurora/RDS via AWS Secrets Manager): "
            "{\"kind\": \"aws-postgres\", \"secret_handle\": \"<handle-name>\", \"database\": \"<db-name>\"}. "
            "secret_handle references a registered aws-postgres secret; database is handle metadata "
            "(not fetched from AWS). The server resolves credentials at connect time.\n"
            "  aws-google-sheets (Google Sheets via AWS Secrets Manager service account): "
            "{\"kind\": \"aws-google-sheets\", \"secret_handle\": \"<handle-name>\", "
            "\"spreadsheet_id\": \"<spreadsheet-id>\", \"sheet_range\": \"<range>\"}. "
            "secret_handle carries a service-account JSON secret; the server resolves it at connect time."
        ),
    },
    "KPI": {
        "details": {
            "what": "<KPI description>",
            "why": "<business impact of improving this KPI>",
            "where": "<team/process/system context>",
            "learned": "Target: <value>; Current: <value>; Unit: <unit>; Frequency: <cadence>; Owner: <dept/role>; Data Source: <source>; Related Problems / Improvement Areas: <names>; Related Solutions: <names>",
        },
    },
    "Solution": {
        "details": {
            "what": "<operational improvement proposed/implemented>",
            "why": "<problem being solved and expected impact>",
            "where": "<workflow/process location>",
            "learned": "Status: <proposed|in-progress|completed|deprecated> (default: proposed when omitted); Effort: <low|med|high>; Owner: <dept/role>; Related KPIs: <names>; Related Problems / Improvement Areas: <names>; Related Decisions: <names>",
        },
    },
    "Decision": {
        "details": {
            "what": "<decision summary>",
            "why": "<rationale for choosing this option>",
            "where": "<domain/product/architecture area impacted>",
            "learned": "Alternatives: <list>; Supersedes: <decision or none>; Version: <n>; Date: <ISO date>; Impacts KPIs: <names>; Authorizes Solutions: <names>",
        },
    },
}

# Source: skills/elicit-context/SKILL.md "Persistence Workflow (Mandatory)" — keep in sync.
ELICIT_WORKFLOW: dict[str, object] = {
    "steps": [
        "1. Resolve the org graph first: list_graphs, then create_graph only if the org slug is missing.",
        "2. Ask questions from question_bank (max 5 per session), prioritizing Data Source coverage.",
        (
            "3. Apply the completeness gate: if the user's answer is partial, vague, or leaves gaps, stay "
            "on the SAME question and ask focused follow-ups until the answer is complete. Never advance "
            "to the next question with a half-answered one."
        ),
        (
            "4. Once the user confirms the save, persist EVERY captured entity to SQLite via update_node "
            "(and add_edge for relationships the user stated) in that same turn. Never defer, skip, or "
            "partially persist."
        ),
        (
            "5. Mirror session-level findings to Engram via mem_save. Engram keeps session narrative and "
            "decisions; SQLite keeps the org graph. Both are mandatory."
        ),
        (
            "6. After each node is persisted, call suggest_connections(graph_id, node_id) and evaluate the "
            "candidates so new information gets linked while it is fresh."
        ),
    ],
    "completeness_gate": (
        "A question is answered only when it is complete for the entity being captured: every required "
        "field in the matching node_write_template has real content (no placeholders, no 'I guess', no "
        "unnamed systems or roles). When something is missing, ask one focused follow-up at a time about "
        "the SAME topic — do not move to the next question-bank question until there are no gaps."
    ),
    "dual_persistence": (
        "SQLite via brain_ds MCP (update_node/add_edge) is the single source of truth for org domain "
        "nodes and edges; Engram (mem_save) stores session context. Saving to only one store is a "
        "workflow violation."
    ),
    "anti_drift": (
        "Never represent the org graph in local files, markdown notes, or chat-only summaries. "
        "If a brain_ds MCP call fails, surface the error and retry — do not silently fall back to "
        "another storage mechanism."
    ),
}

# Source: skills/map-connections/SKILL.md "Retrieval Workflow (Mandatory)" — keep in sync.
MAP_RETRIEVAL_CONTRACT: str = (
    "Use suggest_connections(graph_id=<slug>, node_id=<id>) as the primary linking retrieval; "
    "use list_nodes(graph_id=<slug>, type=<EntityType>) for complete typed retrieval and "
    "search_graph(graph_id=<slug>, query=<text>) for substring lookups inside the resolved org graph. "
    "typed SQL filters are not equivalent to Engram substring search, so validate retrieval changes on a seeded vault "
    "before assuming parity."
)

# Source: skills/map-connections/SKILL.md "Connection RAG Workflow (Mandatory)" — keep in sync.
MAP_RAG_WORKFLOW: dict[str, object] = {
    "steps": [
        (
            "1. Immediately after creating or updating a node via update_node, call "
            "suggest_connections(graph_id, node_id) for that node."
        ),
        (
            "2. Evaluate each candidate with your own knowledge of the org: accept, reject, or defer. "
            "Suggestions are candidates, not commands."
        ),
        (
            "3. For accepted candidates call add_edge with the returned suggested_edge "
            "(source, target, label); adjust the label only when you have better evidence."
        ),
        (
            "4. Use get_node only on top candidates that need more detail before deciding. "
            "Never bulk-read the whole graph to find link targets."
        ),
        (
            "5. As the graph grows, raise threshold (default 0.3) or lower limit to keep responses small."
        ),
    ],
    "scaling_contract": (
        "suggest_connections computes compatibility server-side (type rules + token overlap + shared "
        "neighbors) and excludes already-connected nodes, so agent context stays small even at "
        "thousands of nodes."
    ),
}


# Source: skills/map-connections/SKILL.md "Deterministic Connection Rules" — keep in sync.
CONNECTION_RULES: dict[str, object] = {
    "rules": [
        {"connection": "Department ↔ Role", "rule": "Shared substring/token in Where"},
        {"connection": "Role ↔ Data Source", "rule": "Overlap between Role Where/Why and Data Source Where"},
        {"connection": "Heuristic ↔ Department", "rule": "Heuristic Where overlaps Department Where"},
        {"connection": "Heuristic ↔ Role", "rule": "Heuristic mentions Role domain or decision point"},
        {"connection": "Tacit Knowledge ↔ Role", "rule": "Tacit Where maps to Role area"},
        {"connection": "Problem / Improvement Area ↔ Data Source", "rule": "Problem or improvement area references Data Source name/system"},
        {"connection": "Problem / Improvement Area ↔ Role", "rule": "Problem or improvement area Where overlaps Role Where"},
        {"connection": "Project ↔ Department", "rule": "Project departments overlap with Department names/tokens"},
        {"connection": "Project ↔ Risk", "rule": "Project risk_ids or textual overlap links to Risk entities"},
        {"connection": "Decision ↔ Project/Risk", "rule": "Decision affects[]/supersedes or contextual overlap"},
        {"connection": "KPI ↔ Department", "rule": "KPI owner dept maps to Department (owned-by)"},
        {"connection": "KPI ↔ Role", "rule": "KPI owner role maps to Role (accountable)"},
        {"connection": "KPI ↔ Data Source", "rule": "KPI measurement source maps to Data Source (measured-by)"},
        {"connection": "KPI ↔ Problem / Improvement Area", "rule": "KPI degraded by linked problems or improvement areas (degraded-by)"},
        {"connection": "Solution ↔ KPI", "rule": "Solution expected impact references KPI (improves)"},
        {"connection": "Solution ↔ Problem / Improvement Area", "rule": "Solution resolves linked problems or improvement areas (resolves)"},
        {"connection": "Decision ↔ KPI", "rule": "Decision rationale references KPI (targets)"},
        {"connection": "Decision ↔ Solution", "rule": "Solution links to decision context (decided-by)"},
        {"connection": "Organization ↔ Role/Data Source/Project/KPI", "rule": "Organization owns its top-level entities (owns)"},
        {"connection": "Data Source ↔ Data Source", "rule": "Lineage/pipeline overlap between sources (depends-on)"},
        {"connection": "Risk ↔ Data Source", "rule": "Risk references the data source it threatens (creates-risk)"},
        {"connection": "Project ↔ Solution", "rule": "Solution emerges from project decision context (decided-by)"},
        {"connection": "Heuristic ↔ Data Source", "rule": "Heuristic inputs reference the data source (uses)"},
        {"connection": "Tacit Knowledge ↔ Data Source", "rule": "Tacit knowledge references the data source (uses)"},
        {"connection": "Role ↔ Role", "rule": "Same Where plus >=3 meaningful shared tokens (shared-with)"},
    ],
    "strength_labels": {
        "weak": "<=1 shared token",
        "strong": ">=3 shared tokens",
    },
}

# Secret connection rules — flat 6-step recipe for non-admin agents to connect to
# typed data sources (aws-postgres, aws-google-sheets) using only non-admin tools.
# Design: concrete + example-driven so the simplest model (DeepSeek Flash) follows
# correctly without clarification. Must NOT require list_secret_handles (admin-only).
# Mirrors brainds-source-explorer agent docs and skills/brainds-docs/SKILL.md prose.
SECRET_CONNECTION_RULES: str = """\
How to connect to a data source that uses a secret (aws-postgres, aws-google-sheets)
— grounding-first: Call a grounding context tool first, follow this recipe exactly,
and do NOT deviate or call admin-only tools.

1. Call list_source_connections(graph_id) to discover which Data Source nodes
   have explorable connection descriptors. Each result includes a "connection"
   dict with at minimum {"kind": "<kind>", "secret_handle": "<handle-name>"}.
   This call requires NO admin permission.

2. Read the "kind" and "secret_handle" fields from the descriptor.
   - kind tells you which connector to use (e.g. "aws-postgres").
   - secret_handle is a name (not a credential) that references a registered
     secret in the workspace vault.
   You do NOT need the raw secret value. The server resolves it for you.

3. Call explore_source(graph_id=<graph_id>, node_id=<node_id>) to inspect the
   source. The server internally resolves secret_handle → adapter → connector.
   You never see or need the ARN or password.
   - No additional args → describe + containers.
   - Add container=<name> → tables in that schema.
   - Add container=<name>, table=<table> → schema + preview.

4. For SQL queries on aws-postgres sources, call query_source(graph_id, node_id,
   query="SELECT ...") — SELECT only, max 200 rows. Never write.

5. NEVER call list_secret_handles. That tool requires workspace_admin and will
   return MCP error -32001 for non-admin agents. You do NOT need it: the bound
   secret_handle in the connection descriptor is sufficient for explore_source
   and query_source to connect.

6. If list_source_connections returns a source with no connection descriptor (or
   an empty/null "connection"), the source is not yet bound to a secret. Report
   it as "not explorable — no connection descriptor" and do NOT guess credentials.

--- Worked example: aws-postgres (Aurora PostgreSQL via AWS Secrets Manager) ---

  # Step 1 — discover
  list_source_connections(graph_id="grupo-topete")
  # → [{node_id: "gt-ds-sit-aurora", connection: {kind: "aws-postgres",
  #      secret_handle: "grupo-topete/sit-aurora", database: "sit_prod"}}]

  # Step 3 — explore (server resolves the secret)
  explore_source(graph_id="grupo-topete", node_id="gt-ds-sit-aurora")
  # → {describe: {...}, containers: ["public", "reporting"]}

  explore_source(graph_id="grupo-topete", node_id="gt-ds-sit-aurora",
                 container="public")
  # → {tables: ["orders", "customers", "deliveries"]}

  explore_source(graph_id="grupo-topete", node_id="gt-ds-sit-aurora",
                 container="public", table="orders")
  # → {schema: [{name: "order_id", type: "integer"}, ...], preview: [...]}

--- Worked example: aws-google-sheets (via AWS Secrets Manager service account) ---

  # Step 1 — discover
  list_source_connections(graph_id="grupo-topete")
  # → [{node_id: "gt-ds-erp-dvc", connection: {kind: "aws-google-sheets",
  #      secret_handle: "grupo-topete/erp-dvc",
  #      spreadsheet_id: "1AbC...", sheet_range: "Hoja1!A1:Z"}}]

  # Step 3 — explore (server resolves the service-account JSON from AWS)
  explore_source(graph_id="grupo-topete", node_id="gt-ds-erp-dvc")
  # → {describe: {title: "ERP DVC", url: "..."}, containers: ["ERP DVC"]}

  explore_source(graph_id="grupo-topete", node_id="gt-ds-erp-dvc",
                 container="ERP DVC")
  # → {tables: ["Hoja1", "Hoja2", "Resumen"]}

  explore_source(graph_id="grupo-topete", node_id="gt-ds-erp-dvc",
                 container="ERP DVC", table="Hoja1")
  # → {schema: [{name: "Fecha", type: "string"}, ...], preview: [...]}
"""

# Two-phase mapping — structural skeleton first, cross-cutting semantics second.
# Mirrored as "Two-Phase Mapping (Mandatory)" in skills/map-connections/SKILL.md
# (+ .opencode mirror) — keep in sync.
TWO_PHASE_MAPPING: dict[str, object] = {
    "why": (
        "The domain graph has a natural hierarchy (Organization -> Department -> Role -> "
        "Data Source) and cross-cutting semantics (KPI/Problem/Solution/Decision/Risk). "
        "Scoring both in one pass is what produces noise edges."
    ),
    "phase_1_structural": {
        "types": ["Organization", "Department", "Role", "Data Source"],
        "labels": ["owns", "uses", "depends-on"],
        "rule": (
            "Auto-executable: accept owns/uses edges between structural types when the "
            "parent exists or is derivable. Run this pass first and report it separately."
        ),
    },
    "phase_2_cross_cutting": {
        "types": [
            "Heuristic",
            "Tacit Knowledge",
            "Problem / Improvement Area",
            "Project",
            "Risk",
            "Decision",
            "KPI",
            "Solution",
        ],
        "rule": (
            "Requires prior elicitation or explicit user confirmation: KPI<->Role<->Data "
            "Source, Solution<->Problem, Decision<->Project<->Risk and similar pairs are "
            "only mapped after Phase 1 completes, never mixed into the same pass."
        ),
    },
    "report_rule": (
        "The mapping report MUST list structural_edges and cross_cutting_edges as separate "
        "sections — never merge the two phases into one edge list."
    ),
}


# Pre-mapping completeness gate — the mapping agent MUST run this before any
# add_edge. Mirrored as "Completeness Gate (Mandatory)" in
# skills/map-connections/SKILL.md (+ .opencode mirror) — keep in sync.
COMPLETENESS_GATE: dict[str, object] = {
    "tool": "assess_completeness",
    "when": "BEFORE the first add_edge of any mapping pass (once per graph per session)",
    "rules": [
        (
            "If pre_mapping_recommendation is 'elicit' (3+ entity types missing): do NOT map. "
            "Return the gap report to the orchestrator/user and wait for an explicit decision "
            "('elicit first' vs 'map with what we have, accepting a PARTIAL BRD')."
        ),
        (
            "If pre_mapping_recommendation is 'document': underspecified nodes (empty 'where' or "
            "learned starting with 'Underspecified') are blocked from automatic edges — "
            "suggest_connections marks them 'review-needed'. Document them before mapping them."
        ),
        (
            "Suggestions labeled 'review-needed' are NEVER written as edges. They exist so the "
            "human can see the candidate; promoting one requires explicit user confirmation and "
            "a real relationship label."
        ),
        "Start every first mapping pass of a session with a visible gap report, not with add_edge.",
    ],
}

# Source: skills/generate-brd/SKILL.md "Retrieval Workflow (Mandatory)" — keep in sync.
BRD_RETRIEVAL_CONTRACT: str = (
    "Use list_nodes(graph_id=<slug>, type=<EntityType>) to assemble deterministic typed datasets and "
    "search_graph(graph_id=<slug>, query=<text>) only for targeted substring expansion inside the same org graph. "
    "typed SQL filters are not equivalent to Engram substring search; validate retrieval changes on a seeded vault "
    "before assuming parity."
)


# Source: skills/generate-brd/SKILL.md "BRD Output Contract" — keep in sync.
BRD_SECTION_ORDER: list[str] = [
    "Header",
    "Executive Summary",
    "Current State Analysis",
    "Requirements",
    "Data Sources & Dependencies",
    "Stakeholder Impact",
    "Solution Options",
    "ADR Log",
    "Data Provenance",
    "Risk Register",
    "Cross-Dept Overlap Map",
    "Project Portfolio",
    "KPI Dashboard",
    "Improvement Roadmap",
]

# Source: skills/generate-brd/SKILL.md "Section Rules for KPI/Solution" and "Empty/Partial/Complete" — keep in sync (skills frozen this change).
SECTION_RULES: dict[str, object] = {
    "KPI_Dashboard": {
        "columns": [
            "KPI",
            "Target/Current",
            "Unit",
            "Frequency",
            "Owner",
            "Data Source",
            "Linked Problems / Improvement Areas",
            "Linked Solutions",
            "Decision Impact",
        ],
        "rules": [
            "If no KPI entities: [NEEDS DATA: KPI entities missing]",
            "If partial KPI fields: render row and fill unknown cells with Unknown",
            "Trend cue from target/current: ↑ improvement target, ↓ reduction target, → no-change",
        ],
    },
    "Improvement_Roadmap": {
        "columns": [
            "Solution",
            "Expected Impact",
            "Status",
            "Effort",
            "Owner",
            "Improves KPI",
            "Resolves Problem / Improvement Area",
            "Authorized By Decision",
        ],
        "rules": [
            "If no Solution entities: [NEEDS DATA: Solution entities missing]",
            "Render available rows even when KPI table is empty",
        ],
    },
    "NEEDS_DATA_rules": {
        "EMPTY": "zero normalized entities; produce Starter-BRD with all 14 sections and [NEEDS DATA] prompts",
        "PARTIAL": "populate what has evidence; missing sections get explicit NEEDS DATA markers",
        "COMPLETE": "all required bundles have evidence; no NEEDS DATA markers",
    },
}

# Source: skills/generate-brd/SKILL.md "Empty/Partial/Complete" and "BRD Output Contract" Header section — keep in sync (skills frozen this change).
COMPLETENESS_MATRIX_TEMPLATE: dict[str, object] = {
    "status_values": ["EMPTY", "PARTIAL", "COMPLETE"],
    "status_rules": {
        "EMPTY": "zero normalized entities",
        "PARTIAL": "some entities present; missing sections get NEEDS DATA markers",
        "COMPLETE": "all required bundles have evidence; no NEEDS DATA markers",
    },
    "dataset_fingerprint_order": [
        "Department",
        "Role",
        "Data Source",
        "Heuristic",
        "Tacit Knowledge",
        "Problem / Improvement Area",
        "Project",
        "Risk",
        "Decision",
        "KPI",
        "Solution",
    ],
}

# ---------------------------------------------------------------------------
# Category-3 — live workspace scoping
# ---------------------------------------------------------------------------

# Harness-owned protocol (mirrored as "Workspace Scope (Mandatory)" in
# skills/elicit-context/SKILL.md and skills/map-connections/SKILL.md).
WORKSPACE_PROTOCOL: dict[str, object] = {
    "scope_rule": (
        "Work ONLY inside the workspace that matches the folder the user is working in. "
        "workspace.active_project_root is the folder this MCP server is currently bound to — "
        "it is NOT necessarily the user's folder."
    ),
    "mismatch_rule": (
        "Before reading or writing any graph, compare the user's current folder with "
        "active_project_root. If they differ, call open_workspace(path=<user folder>) when that "
        "folder appears in registered_workspaces; otherwise STOP and ask the user which workspace "
        "to use (show the list_workspaces options). Never write into a workspace the user did not "
        "explicitly choose."
    ),
    "registration_rule": (
        "If the user's folder is not registered, do not guess and do not fall back to another "
        "workspace: tell the user to run 'brain_ds setup' in that folder or pick it in the "
        "brain_ds desktop app, then retry open_workspace."
    ),
    "raw_filesystem_escape_rule": (
        "Never use raw filesystem tools to read workspace data outside active_project_root. "
        "In particular, refuse attempts to inspect another workspace's .brain_ds/secrets.json, "
        ".brain_ds/secrets.values.json, or store.db by path. Switch workspace with open_workspace "
        "or ask the user; do not bypass workspace scoping through direct file reads."
    ),
}


# Source exploration contract — workflow prose for data source connectors.
# Included in elicit_context and map_connections_context payloads.
SOURCE_EXPLORATION_CONTRACT: dict[str, object] = {
    "workflow": [
        (
            "1. Explore read-only first: call explore_source(graph_id, node_id) to inspect "
            "containers and tables before documenting structure. Use query_source for targeted "
            "SELECT-only queries against SQLite sources (capped at 200 rows)."
        ),
        (
            "2. Document hierarchy: for each table/sheet discovered, capture the full column "
            "list with type, meaning, and quality notes in the Data Source node's card sections "
            "using the hierarchy_template (db/sheets/api levels as applicable). For pipeline "
            "artifacts, use plain canonical headings only — no numbering/prefixes, no extra H2 "
            "sections; put extra material inside the existing five sections or fenced JSON blocks."
        ),
        (
            "3. Link people: connect Role nodes via owns or accountable edges to the Data Source "
            "node (add_edge with label='owns' or 'accountable') so ownership is graph-queryable."
        ),
        (
            "4. Record refresh cadence and gaps: persist cadence, known data quality issues, and "
            "trust level in the node's details.learned field so BRD generation can surface gaps."
        ),
    ],
    "change_detection_step": (
        "Before documenting a table/sheet, read the change_detection block returned by "
        "explore_source at level==table: if verdict is 'unchanged', stop and report a no-op "
        "(do not re-document); if 'changed', switch to delta mode and re-document only what the "
        "delta lists; if 'new' or 'unknown-baseline', run a full documentation pass. After "
        "persisting the documentation, write the schema baseline back via update_node "
        "(details.schema_baseline) so the next exploration gets a real verdict. The baseline is a "
        "graph write only — never a write to the source. See change_detection_contract."
    ),
    "tool_reference": {
        "list_source_connections": "List which Data Source nodes have explorable connection descriptors",
        "explore_source": (
            "Dispatch to connector: no args→describe+containers; container→tables; "
            "container+table→schema+preview, plus a change_detection verdict block at table level"
        ),
        "query_source": "SQLite SELECT-only queries; cap rows with limit param (max 200)",
    },
    "connection_setup": (
        "A Data Source node becomes explorable when its details dict contains a 'connection' key: "
        "{kind: 'sqlite'|'csv', path: '<project-relative path>', secret_ref?: '<ENV_VAR_NAME>'}. "
        "If secret_ref is present, the connector resolves it from os.environ only at open time; "
        "store the reference name, never the credential value. The resolved secret is never stored "
        "in graph nodes, card_sections, or .elicit artifacts. Missing secret_ref values fail closed "
        "with a clear error naming the missing environment variable. "
        "Google Sheets: delegate to MCP Google Drive read tools or export to CSV first."
    ),
}


# Data Source schema change-detection contract — documents the auditable verdict
# surface explore_source emits at level==table. Mirrors the pure helper in
# brain_ds/connectors/change_detection.py and the documenter decision branch in
# the brainds-source-explorer agent prompt + skill prose. Category-2 (must sweep
# clean — references only the literal entity value "Data Source").
SOURCE_CHANGE_DETECTION_CONTRACT: dict[str, object] = {
    "purpose": (
        "Decide whether a Data Source needs (re-)documentation by comparing a freshly computed "
        "canonical schema hash against the baseline stored on the node. Change detection is an "
        "auditable transactional decision, never a silent overwrite."
    ),
    "emitted_at": "explore_source level==table only (never at the source or container levels)",
    "verdicts": {
        "new": "No baseline and no prior documentation — run a full first-time documentation pass.",
        "unchanged": "Baseline hash equals the live hash — skip re-documentation; report a no-op.",
        "changed": "Baseline existed and hashes differ — re-document using the returned delta only.",
        "unknown-baseline": (
            "Prior documentation exists but no baseline (node predates this feature) — run a full "
            "pass, then write the baseline. Self-healing; no migration script."
        ),
    },
    "baseline_fields": {
        "schema_hash": "hex sha256 over the canonical schema (columns sorted, types normalized).",
        "documented_schema_snapshot": "the canonical schema object the hash was computed from.",
        "last_documented_at": "ISO8601 UTC timestamp, distinct from the node-level modified_at.",
    },
    "baseline_shape": (
        "explore_source hashes ONE table at a time, so a multi-table source stores schema_baseline "
        "as a per-table map: {<table_name>: {schema_hash, documented_schema_snapshot, "
        "last_documented_at}, ...} — one entry per documented table. A single-table source may use "
        "the flat shape {schema_hash, documented_schema_snapshot, last_documented_at} directly; the "
        "reader accepts both (flat passes through, per-table is keyed by the explored table name, "
        "case-insensitive). When documenting a multi-table source, write/refresh ONLY the entry for "
        "each table you (re-)documented and preserve the others."
    ),
    "baseline_location": (
        "Stored on the Data Source node's details.schema_baseline via update_node. This is a graph "
        "write only — the change-detection path never writes to the external source."
    ),
    "canonicalization": (
        "Column order, name whitespace/case, varchar widening, and type synonyms are normalized "
        "away so they never produce a false 'changed'. Added/removed columns, type-class changes, "
        "and added/removed tables DO produce 'changed'."
    ),
    "delta_shape": {
        "added_columns": "[{table, name, type}] — present only when verdict==changed.",
        "removed_columns": "[{table, name, type}]",
        "altered_columns": "[{table, name, from_type, to_type}]",
        "added_tables": "[table_name]",
        "removed_tables": "[table_name]",
    },
    "governance": (
        "The delta is the Reflexion-style critique surface: the documenter emits incremental "
        "re-documentation from it rather than blindly rewriting. The verdict and baseline make the "
        "decision auditable in the graph."
    ),
}


# Source-type classification for recon / source-docs pipeline slices.
RECON_SOURCE_TYPES: dict[str, tuple[str, ...]] = {
    "supported": ("sqlite", "postgres", "sqlserver", "csv", "google-sheets"),
    "unsupported": ("unsupported-json-api", "unsupported-unstructured", "unsupported-other"),
}
UNSUPPORTED_RECOMMENDED_NEXT: str = "manual contract required"


# Harness-owned BRD graph persistence contract — mirrors the UI convention in
# brain_ds/ui/src/panels/brd-panel.ts (BRD node id "brd-{graphId}"). Keep both
# sides in sync: the panel reads card_sections[0] of that node.
BRD_GRAPH_PERSISTENCE_CONTRACT: dict[str, object] = {
    "purpose": (
        "Make the finished BRD visible in the brain_ds UI BRD panel. The UI reads one graph "
        "node per organization; persisting only to Engram does NOT surface the BRD in the UI."
    ),
    "when": (
        "On /generate-brd --save — or whenever the user asks to save/persist the BRD or to see "
        "it in the UI — write the BRD node via update_node IN ADDITION to the Engram mem_save "
        "mirror. Without this write the BRD exists only in chat/Engram and the UI panel stays empty."
    ),
    "update_node_template": {
        "graph_id": "<org-slug>",
        "node_id": "brd-<org-slug>",
        "label": "BRD",
        "type": "Unknown",
        "card_sections": [
            {
                "title": "Contenido",
                "content": "<full markdown BRD with 14 sections>",
                "order": 0,
                "icon": "",
            }
        ],
    },
    "rules": [
        "node_id MUST be exactly 'brd-<graph-id>' — the UI BRD panel looks up that id.",
        "card_sections[0] MUST keep title 'Contenido' and order 0; the panel reads that section.",
        "update_node is upsert-safe: re-running --save replaces the previous BRD content.",
        "The write emits a live node event, so a running UI refreshes without restart.",
        (
            "Every mention of a graph entity in the BRD markdown MUST be written as a wikilink "
            "[[<node label>]] (or [[<node label>|<display text>]] for inline phrasing). The UI "
            "renders these as Obsidian-style navigable links to the node; plain-text mentions "
            "leave the BRD disconnected from the graph."
        ),
    ],
}


# BRD strict mode — mirrored as "Strict Mode (--strict)" in
# skills/generate-brd/SKILL.md (+ .opencode mirror) — keep in sync.
BRD_STRICT_MODE: dict[str, object] = {
    "flag": "--strict",
    "gate_tool": "assess_completeness",
    "rules": [
        (
            "ALWAYS (strict or not): before composing, call assess_completeness(graph_id) and "
            "show a 'Gaps Detectados' section first — entity counts per type, missing types, "
            "and the [NEEDS DATA] sections the BRD will contain."
        ),
        (
            "--strict: if the completeness matrix is not COMPLETE (any missing type or "
            "underspecified node), REFUSE to generate/persist the BRD. Return an actionable "
            "error listing each gap and the elicitation prompt that closes it."
        ),
        (
            "--save without --strict stays permissive (current behavior): persist the PARTIAL "
            "BRD with explicit NEEDS DATA markers. '--strict --save' demands COMPLETE."
        ),
    ],
}


# Source: skills/elicit-context/SKILL.md "Pipeline Stages (Mandatory)" — keep in sync.
# Flat ordered list of pipeline stages for the full agentic brain_ds cycle.
# intake carries nested intake_paths describing how each input path is handled.
PIPELINE_STAGES: list[dict[str, object]] = [
    {
        "stage": "setup",
        "description": "resolve the org graph, choose the artifact store, and confirm workspace",
        "agents": ["brainds-orchestrator"],
    },
    {
        "stage": "intake",
        "description": "ingest and document all data sources feeding the workflow",
        "agents": ["brainds-source-explorer", "brainds-graph-mapper"],
        "intake_paths": {
            "datasource": ["brainds-source-explorer", "brainds-graph-mapper"],
            "human_org": ["brainds-orchestrator", "brainds-graph-mapper"],
        },
    },
    {
        "stage": "map",
        "description": "map connections between nodes using the two-phase structural and cross-cutting workflow",
        "agents": ["brainds-connection-mapper"],
    },
    {
        "stage": "brd",
        "description": "compose and persist the business requirements document from the org graph",
        "agents": ["brainds-brd-writer"],
    },
    {
        "stage": "verify",
        "description": (
            "run the compliance gate on all elicit artifacts and write the verify report, "
            "then delegate the advisory semantic coherence judge to brainds-semantic-verifier"
        ),
        "agents": ["brainds-orchestrator", "brainds-semantic-verifier"],
    },
    {
        "stage": "archive",
        "description": "move completed cycle artifacts to the archive folder if the verify gate passes",
        "agents": ["brainds-orchestrator"],
    },
]


# Harness-owned orchestration protocol — how an orchestrator agent stays thin,
# delegates context-heavy work to sub-agents, and where artifacts are stored.
# Mirrored in .claude/agents/brainds-orchestrator.md and prompts/brain-ds-orchestrator.md.
DELEGATION_PROTOCOL: dict[str, object] = {
    "role": (
        "The orchestrator is the MIND: it coordinates phases, interviews the user, and makes "
        "decisions. It delegates context-heavy work (source exploration, bulk documentation, "
        "connection mapping, BRD composition) to sub-agents and consumes only their summaries."
    ),
    "session_setup": (
        "At the start of a session that will produce artifacts, ask the user ONCE how to store "
        "intermediate artifacts: 'engram' (persistent memory), '.elicit' (project-local .elicit/ "
        "folder), or 'both'. Default to 'engram' when available, otherwise '.elicit'. Cache the "
        "choice for the whole session — do not ask again."
    ),
    "artifact_keys": {
        "engram_topic_key": "org/<slug>/<phase>/<ISO-date-or-section-slug>",
        "elicit_file": ".elicit/<phase>-<slug>-<ISO-date>.md",
        "phases": [
            "elicit",
            "recon",
            "plan",
            "source-exploration",
            "source-docs",
            "map",
            "brd",
            "verify",
            "archive",
        ],
    },
    "pipeline_stages": PIPELINE_STAGES,
    "intake_paths": PIPELINE_STAGES[1]["intake_paths"],
    "handoff_rule": (
        "Pass artifact references (topic keys or file paths) to sub-agents, never full content. "
        "Each sub-agent reads its inputs itself and returns a result contract: status, "
        "executive_summary, artifacts (keys/paths written), next_recommended, risks."
    ),
    "source_exploration_flow": [
        (
            "1. recon: delegate a read-only magnitude scan of the data source (containers, "
            "tables/sheets, row estimates) to size the documentation work. unsupported objects "
            "carry recommended_next='manual contract required'. no graph writes."
        ),
        (
            "2. plan: split documentation into non-overlapping slices (by table/sheet/endpoint). "
            "one documenter agent for small sources; several agents with disjoint slice "
            "assignments for large ones so they never overlap. unsupported items are recorded as "
            "skip — unsupported source type."
        ),
        (
            "3. document: each documenter explores ONLY its assigned slice and saves structured "
            "findings (hierarchy_template format) to the configured artifact store."
        ),
        (
            "4. consolidate + push: a mapper agent reads every saved finding and persists the "
            "consolidated documentation to the graph via update_node (card_sections) and add_edge "
            "so the documented source is visible in the ui. Pipeline artifacts must already satisfy "
            "assert_deliverable_shape because the mapper actually ran the helper against the artifact "
            "text or file; eyeballing prose is not enough. unsupported-* counts as skipped-by-design, "
            "not a gap."
        ),
    ],
    "dry_run": {
        "trigger_phrase": "dry-run the source intake",
        "steps": [
            "run brainds-source-explorer mode a (recon) — no graph writes",
            "produce plan artifact: slice→agent assignment",
            "verify completeness invariant: union(plan slices) == recon inventory",
            "optionally run one documentation slice if user requests a sample",
            "surface invariant result and sample deliverable to user for review",
        ],
        "no_graph_writes_guard": "suppress all update_node and add_edge calls during dry-run",
        "persistence_responsibility": (
            "brainds-graph-mapper has no Write tool, so it cannot materialize the consolidation "
            "report to .elicit by itself. In dry-run the orchestrator MUST re-delegate writing the "
            "consolidation/dry-run report to an agent that has Write (brainds-source-explorer), or "
            "fail. Never report a .elicit artifact as written unless a Write call actually produced "
            "the file. This is a persistence-responsibility guard, not a domain check: the "
            "substantive pass can succeed while the artifact trail stays incomplete."
        ),
    },
    "skill_scope": (
        "Use ONLY brain_ds-owned skills and commands (elicit-context, map-connections, "
        "generate-brd, and project-local helpers shipped with brain_ds). Never invoke skills, "
        "agents, or commands that belong to other projects installed on the same machine, even "
        "when they look relevant."
    ),
}


# Source: workspace secret catalog contract — provider kinds, manifest paths, and
# redaction rules for the secret handle surface. Kept lowercase to stay clean
# under the Category-2 drift sweep.
SECRET_CATALOG_CONTRACT: dict[str, object] = {
    "manifest_path": ".brain_ds/secrets.json",
    "values_path": ".brain_ds/secrets.values.json",
    "schema_version": "1.0",
    "provider_kinds": [
        "sqlite",
        "postgres",
        "sqlserver",
        "aws-secrets",
        "iam-role",
        "iam-credential",
        "google-sheets-json",
    ],
    "security_invariants": [
        "raw secret values never appear in the manifest, MCP responses, UI views, or logs",
        "manual manifest edits are schema-validated; failure closes the secret surface",
        "raw values are stored in .brain_ds/secrets.values.json with 0o600 permissions",
        "agents receive only handles, kinds, and redacted metadata",
    ],
}

# Source: SI-6 redaction pattern — case-insensitive substring match against keys.
SECRET_REDACTION_TOKENS: list[str] = [
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "access_key",
    "private_key",
    "client_secret",
    "service_account.private_key",
]

# Source: .elicit artifact canonical contract — human markdown + ONE canonical
# fenced JSON block per .elicit artifact. Injected into all 3 grounding composers
# under key "artifact_contract" so every MCP client receives the same contract.
# Guarded by the drift sweep (no CamelCase-compound entity tokens in values).
DELIVERABLE_CONTRACT: dict[str, object] = {
    "sections": (
        "outcome_title",
        "quick_path",
        "details_table",
        "checklist",
        "next_step",
    ),
    "rules": (
        "lead-with-outcome",
        "progressive-disclosure",
        "chunking",
        "signposting",
        "recognition-over-recall",
    ),
    "applies_to": ("recon", "plan", "source-docs", "consolidation", "dry-run"),
}

CONTRACT_APPLICABILITY: dict[str, str] = {
    "recon": "deliverable_contract",
    "plan": "deliverable_contract",
    "source-docs": "deliverable_contract",
    "consolidation": "deliverable_contract",
    "dry-run": "deliverable_contract",
    "brd": "brd_section_order",
    "map": "map_retrieval_contract",
    "query": "query_consultant_contract",
}

ARTIFACT_CONTRACT: dict[str, dict[str, object]] = {
    "source-docs": {
        "artifact_type": "source-docs",
        "required_keys": (
            "artifact_type",
            "graph_id",
            "documented_nodes",
            "slice_id",
            "assigned_objects",
        ),
        "validator": "check_documented_nodes",
        "schema_notes": (
            "documented_nodes is a list of node objects each with node_id, label, type, "
            "card_sections. slice_id and assigned_objects echo the plan assignment. "
            "coverage_status_values=('documented', 'skipped') and source_type_values include "
            "supported + unsupported markers. Non-BRD nodes: order >= 1, non-empty icon. "
            "BRD carve-out (type=='Unknown' and node_id starts 'brd-'): order=0, icon=''."
        ),
        "coverage_status_values": ("documented", "skipped"),
        "source_type_values": RECON_SOURCE_TYPES["supported"] + RECON_SOURCE_TYPES["unsupported"],
        "type_fields_notes": (
            "SQL type_fields cover schema, columns, keys, and sample rows; sheet/CSV type_fields "
            "cover tabs, headers, row_count_estimate, and inferred_types."
        ),
        "skip_reason_notes": (
            "When coverage_status is skipped, skip_reason must be a non-empty string explaining the gap."
        ),
    },
    "map": {
        "artifact_type": "map",
        "required_keys": ("artifact_type", "graph_id", "documented_nodes", "edges", "completeness_gate"),
        "validator": "check_documented_nodes",
        "schema_notes": (
            "Same documented_nodes rules as source-docs. "
            "completeness_gate from assess_completeness (pre_mapping_recommendation required). "
            "map is the canonical completeness_gate owner."
        ),
    },
    "brd": {
        "artifact_type": "brd",
        "required_keys": ("artifact_type", "graph_id", "markdown", "brd_node"),
        "validator": "check_brd_payload",
        "schema_notes": (
            "brd_node: node_id='brd-<graph_id>', label='BRD', type='Unknown', "
            "card_sections[0]: title='Contenido', order=0, icon=''. "
            "markdown must contain wikilinks ([[...]])."
        ),
    },
    "verify": {
        "artifact_type": "verify",
        "required_keys": (
            "artifact_type",
            "graph_id",
            "stage",
            "status",
            "critical_count",
            "findings",
            "gate",
        ),
        "validator": "check_verify_payload",
        "schema_notes": (
            "gate must be 'PASS' (zero findings) for archive to be allowed. "
            "gate='BLOCKED' or non-empty findings raises CRITICAL in compliance check."
        ),
    },
    "dual_contract_rule": (
        "Every .elicit artifact is human-readable markdown PLUS exactly ONE canonical "
        "fenced JSON block. The verifier selects the LAST ```json...``` block in the file "
        "(positional selection; earlier example blocks are ignored). "
        "A <!-- canonical-payload --> comment above the block is advisory, not required."
    ),
    "canonical_sentinel": "<!-- canonical-payload -->",
    "selection_rule": (
        "LAST fenced JSON block wins. Place the canonical payload at the end of the file, "
        "after any human-readable sections or example blocks."
    ),
}


def build_workspace_context(store: Any) -> dict[str, object]:
    """Live workspace scoping payload attached to every grounding tool response."""
    active_root = workspace_registry.project_root_from_store_path(store.path).resolve()
    workspace_entry = workspace_registry.find_workspace(active_root) or {}
    language = _resolve_documentation_language(workspace_entry)
    graphs = [
        {
            "id": meta.id,
            "name": meta.org or meta.id,
            "node_count": meta.node_count,
            "edge_count": meta.edge_count,
        }
        for meta in store.list_graphs()
    ]
    result: dict[str, object] = {
        "active_project_root": str(active_root),
        "documentation_language": language,
        "documentation_language_contract": DOCUMENTATION_LANGUAGE[language],
        "active_graphs": graphs,
        "registered_workspaces": workspace_registry.list_workspaces(),
        "protocol": WORKSPACE_PROTOCOL,
    }
    return result


def _resolve_documentation_language(workspace_entry: dict[str, Any]) -> str:
    configured = workspace_entry.get("documentation_language")
    if isinstance(configured, str):
        normalized = configured.strip().lower()
        if normalized in SUPPORTED_DOCUMENTATION_LANGUAGES:
            return normalized
    return "en"


def apply_documentation_language(
    payload: dict[str, object], workspace_context: Mapping[str, object]
) -> dict[str, object]:
    """Inject the resolved workspace documentation-language contract into a payload."""
    language = str(workspace_context.get("documentation_language") or "en").strip().lower()
    if language not in SUPPORTED_DOCUMENTATION_LANGUAGES:
        language = "en"
    payload["documentation_language"] = language
    payload["documentation_language_contract"] = DOCUMENTATION_LANGUAGE[language]
    return payload


# Source: skills/brainds-docs/SKILL.md "Data Source documentation bundle" — keep in sync.
# Category-2 constant: DDS-7 spec requirement. Must sweep clean (no stale entity-name tokens).
SOURCE_DOCUMENTATION_BUNDLE_CONTRACT: dict[str, object] = {
    "description": (
        "Single MCP call that returns a joined documentation bundle for a Data Source node. "
        "Use this to answer 'what columns does table T have?' in one call — no raw filesystem "
        "access, no chain of node lookups."
    ),
    "mcp_call": {
        "tool": "explore_source",
        "params": {
            "graph_id": "<graph-id>",
            "node_id": "<datasource-node-id>",
            "level": "documentation",
        },
        "note": (
            "No connector required. Reads child table nodes from the graph store only. "
            "Tool count stayed unchanged for level='documentation'; the current MCP inventory has 25 tools after snapshot_edges."
        ),
    },
    "response_shape": {
        "level": "documentation",
        "graph_id": "<graph-id>",
        "source": {
            "node_id": "<datasource-node-id>",
            "label": "<label>",
            "schema_baseline": "<baseline-dict-or-null>",
        },
        "tables": [
            {
                "node_id": "<table-node-id>",
                "label": "<table-label>",
                "sections": [{"title": "<section-title>", "content": "<markdown-content>"}],
                "columns_markdown": "<pipe-table-markdown-or-empty>",
                "purpose": "<from details.what>",
                "owner": "<from details.where>",
                "refresh": "<from details.learned>",
                "schema_baseline_status": "baseline-present | no-baseline",
            }
        ],
        "relationships": [
            {
                "edge_label": "<relationship-type>",
                "source_id": "<source-node-id>",
                "target_id": "<target-node-id>",
                "other_id": "<other-end-node-id>",
                "other_label": "<other-end-label>",
            }
        ],
    },
    "agent_answerability": (
        "The question 'what columns does table T have?' MUST be answered from "
        "tables[].columns_markdown in this single response. Do NOT read raw "
        "filesystem files and do NOT chain multiple get_node calls."
    ),
}


# ---------------------------------------------------------------------------
# Composers — assemble grounding context payloads for each tool
# ---------------------------------------------------------------------------


def elicit_context() -> dict[str, object]:
    """Return the 18-key grounding context payload for run_elicit.

    Keys: entity_types, supertypes, expected_sections, relationship_types,
          base_weights, question_bank, org_slug_rules, node_id_format,
          node_write_templates, workflow, source_exploration_contract,
          delegation_protocol, pipeline_stages, intake_paths, artifact_contract,
          deliverable_contract, secret_connection_rules,
          source_documentation_bundle_contract.
    """
    return {
        "entity_types": build_entity_types(),
        "supertypes": build_supertypes(),
        "expected_sections": build_expected_sections(),
        "relationship_types": build_relationship_types(),
        "base_weights": build_base_weights(),
        "question_bank": QUESTION_BANK,
        "org_slug_rules": ORG_SLUG_RULES,
        "node_id_format": NODE_ID_FORMAT,
        "node_write_templates": NODE_WRITE_TEMPLATES,
        "workflow": ELICIT_WORKFLOW,
        "source_exploration_contract": SOURCE_EXPLORATION_CONTRACT,
        "delegation_protocol": DELEGATION_PROTOCOL,
        "pipeline_stages": PIPELINE_STAGES,
        "intake_paths": PIPELINE_STAGES[1]["intake_paths"],
        "artifact_contract": ARTIFACT_CONTRACT,
        "deliverable_contract": DELIVERABLE_CONTRACT,
        "secret_connection_rules": SECRET_CONNECTION_RULES,
        "source_documentation_bundle_contract": SOURCE_DOCUMENTATION_BUNDLE_CONTRACT,
    }


def map_connections_context() -> dict[str, object]:
    """Return the 16-key grounding context payload for map_connections.

    Keys: entity_types, connection_rules, completeness_gate, two_phase_mapping,
          relationship_labels, scoring_factors, retrieval_contract, rag_workflow,
          source_exploration_contract, delegation_protocol, pipeline_stages,
          intake_paths, artifact_contract, secret_connection_rules,
          source_documentation_bundle_contract, calibration.
    scoring_factors comes from ScoringEngine (distinct from connection_rules
    strength heuristics — the skill's own weak/strong labels live in connection_rules).
    """
    return {
        "entity_types": build_entity_types(),
        "connection_rules": CONNECTION_RULES,
        "completeness_gate": COMPLETENESS_GATE,
        "two_phase_mapping": TWO_PHASE_MAPPING,
        "relationship_labels": build_relationship_labels(),
        "scoring_factors": build_scoring_factors(),
        "retrieval_contract": MAP_RETRIEVAL_CONTRACT,
        "rag_workflow": MAP_RAG_WORKFLOW,
        "source_exploration_contract": SOURCE_EXPLORATION_CONTRACT,
        "delegation_protocol": DELEGATION_PROTOCOL,
        "pipeline_stages": PIPELINE_STAGES,
        "intake_paths": PIPELINE_STAGES[1]["intake_paths"],
        "artifact_contract": ARTIFACT_CONTRACT,
        "secret_connection_rules": SECRET_CONNECTION_RULES,
        "source_documentation_bundle_contract": SOURCE_DOCUMENTATION_BUNDLE_CONTRACT,
        "calibration": build_calibration_grounding(),
    }


def generate_brd_context() -> dict[str, object]:
    """Return the 12-key grounding context payload for generate_brd.

    Keys: entity_types, brd_section_order, section_rules,
          completeness_matrix_template, retrieval_contract,
          brd_graph_persistence_contract, strict_mode, delegation_protocol,
          pipeline_stages, intake_paths, artifact_contract, secret_connection_rules.
    """
    return {
        "entity_types": build_entity_types(),
        "brd_section_order": BRD_SECTION_ORDER,
        "section_rules": SECTION_RULES,
        "completeness_matrix_template": COMPLETENESS_MATRIX_TEMPLATE,
        "retrieval_contract": BRD_RETRIEVAL_CONTRACT,
        "brd_graph_persistence_contract": BRD_GRAPH_PERSISTENCE_CONTRACT,
        "strict_mode": BRD_STRICT_MODE,
        "delegation_protocol": DELEGATION_PROTOCOL,
        "pipeline_stages": PIPELINE_STAGES,
        "intake_paths": PIPELINE_STAGES[1]["intake_paths"],
        "artifact_contract": ARTIFACT_CONTRACT,
        "secret_connection_rules": SECRET_CONNECTION_RULES,
    }
