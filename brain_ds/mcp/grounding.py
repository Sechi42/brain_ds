"""MCP grounding context module.

Provides two categories of context for the B1 context-return tools:
- Category-1: derived at runtime from ontology enums (zero drift).
- Category-2: hand-maintained Python constants (skill workflow prose for
  non-Claude clients that do not ship skills/*.md files).

This module is context-only: no store queries, no I/O, no side effects.
"""
from __future__ import annotations

from brain_ds.ontology.entity_types import EntityType
from brain_ds.ontology.relationship_types import BASE_WEIGHTS, RelationshipType
from brain_ds.scoring.engine import ScoringEngine

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
        "session_state": (
            "Persist session/active-org in Engram only; org domain entities now live in SQLite."
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

# Source: skills/map-connections/SKILL.md "Retrieval Workflow (Mandatory)" — keep in sync.
MAP_RETRIEVAL_CONTRACT: str = (
    "Use list_nodes(graph_id=<slug>, type=<EntityType>) for complete typed retrieval and "
    "search_graph(graph_id=<slug>, query=<text>) for substring lookups inside the resolved org graph. "
    "typed SQL filters are not equivalent to Engram substring search, so validate retrieval changes on a seeded vault "
    "before assuming parity."
)


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
    ],
    "strength_labels": {
        "weak": "<=1 shared token",
        "strong": ">=3 shared tokens",
    },
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
# Composers — assemble grounding context payloads for each tool
# ---------------------------------------------------------------------------


def elicit_context() -> dict[str, object]:
    """Return the 9-key grounding context payload for run_elicit.

    Keys: entity_types, supertypes, expected_sections, relationship_types,
          base_weights, question_bank, org_slug_rules, node_id_format,
          node_write_templates.
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
    }


def map_connections_context() -> dict[str, object]:
    """Return the 5-key grounding context payload for map_connections.

    Keys: entity_types, connection_rules, relationship_labels, scoring_factors,
          retrieval_contract.
    scoring_factors comes from ScoringEngine (distinct from connection_rules
    strength heuristics — the skill's own weak/strong labels live in connection_rules).
    """
    return {
        "entity_types": build_entity_types(),
        "connection_rules": CONNECTION_RULES,
        "relationship_labels": build_relationship_labels(),
        "scoring_factors": build_scoring_factors(),
        "retrieval_contract": MAP_RETRIEVAL_CONTRACT,
    }


def generate_brd_context() -> dict[str, object]:
    """Return the 5-key grounding context payload for generate_brd.

    Keys: entity_types, brd_section_order, section_rules,
          completeness_matrix_template, retrieval_contract.
    """
    return {
        "entity_types": build_entity_types(),
        "brd_section_order": BRD_SECTION_ORDER,
        "section_rules": SECTION_RULES,
        "completeness_matrix_template": COMPLETENESS_MATRIX_TEMPLATE,
        "retrieval_contract": BRD_RETRIEVAL_CONTRACT,
    }
