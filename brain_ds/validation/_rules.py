from __future__ import annotations

import copy
from difflib import get_close_matches

from brain_ds.ontology.entity_types import EntityType
from brain_ds.ontology.relationship_types import RelationshipType

from ._result import ValidationError, ValidationResult


def validate_graph(data: dict) -> ValidationResult:
    normalized = copy.deepcopy(data)
    errors: list[ValidationError] = []
    warnings: list[str] = []

    _check_required_top_level(normalized, errors)
    _check_schema_version(normalized, errors)
    _check_node_fields_and_types(normalized, errors)
    _check_edge_fields_and_types(normalized, errors)
    _check_duplicates(normalized, errors)
    _check_cross_references(normalized, errors)
    _check_evidence_integrity(normalized, errors)
    _check_empty_graph_warning(normalized, warnings)

    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        normalized=normalized,
    )


def _add_missing_field_error(errors: list[ValidationError], path: str) -> None:
    errors.append(ValidationError(path=path, message=f"Missing required field: {path}"))


def _check_required_top_level(data: dict, errors: list[ValidationError]) -> None:
    for field in ("schema_version", "org", "nodes", "edges"):
        if field not in data:
            _add_missing_field_error(errors, field)


def _check_schema_version(data: dict, errors: list[ValidationError]) -> None:
    if "schema_version" in data and not str(data["schema_version"]).strip():
        errors.append(ValidationError(path="schema_version", message="schema_version cannot be empty"))


def _check_node_fields_and_types(data: dict, errors: list[ValidationError]) -> None:
    nodes = data.get("nodes", [])
    valid_types = {item.value for item in EntityType}
    lowered = {item.value.lower(): item.value for item in EntityType}

    for idx, node in enumerate(nodes):
        for field in ("id", "label", "type"):
            if field not in node:
                _add_missing_field_error(errors, f"nodes[{idx}].{field}")

        raw_type = node.get("type")
        if raw_type is None:
            continue

        type_str = str(raw_type)
        if type_str in valid_types:
            continue

        normalized = lowered.get(type_str.lower())
        if normalized:
            node["type"] = normalized
            continue

        suggestion = _suggest(type_str, list(valid_types))
        errors.append(
            ValidationError(
                path=f"nodes[{idx}].type",
                message=f"Unsupported entity type: {type_str}",
                suggestion=suggestion,
            )
        )


def _check_edge_fields_and_types(data: dict, errors: list[ValidationError]) -> None:
    edges = data.get("edges", [])
    valid_labels = {item.value for item in RelationshipType}

    for idx, edge in enumerate(edges):
        for field in ("source", "target", "label"):
            if field not in edge:
                _add_missing_field_error(errors, f"edges[{idx}].{field}")

        label = edge.get("label")
        if label is None:
            continue
        if str(label) not in valid_labels:
            errors.append(
                ValidationError(
                    path=f"edges[{idx}].label",
                    message=f"Unsupported relationship type: {label}",
                )
            )


def _check_duplicates(data: dict, errors: list[ValidationError]) -> None:
    seen_nodes: set[str] = set()
    for idx, node in enumerate(data.get("nodes", [])):
        node_id = str(node.get("id", ""))
        if not node_id:
            continue
        if node_id in seen_nodes:
            errors.append(ValidationError(path=f"nodes[{idx}].id", message=f"Duplicate node id: {node_id}"))
        seen_nodes.add(node_id)

    seen_edges: set[str] = set()
    for idx, edge in enumerate(data.get("edges", [])):
        edge_id = edge.get("edge_id")
        if edge_id is None:
            continue
        edge_key = str(edge_id)
        if edge_key in seen_edges:
            errors.append(
                ValidationError(path=f"edges[{idx}].edge_id", message=f"Duplicate edge id: {edge_key}")
            )
        seen_edges.add(edge_key)


def _check_cross_references(data: dict, errors: list[ValidationError]) -> None:
    node_ids = {str(node.get("id", "")) for node in data.get("nodes", []) if node.get("id") is not None}
    for idx, edge in enumerate(data.get("edges", [])):
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        if source and source not in node_ids:
            errors.append(
                ValidationError(
                    path=f"edges[{idx}].source",
                    message=f"Broken cross-reference: source node '{source}' does not exist",
                )
            )
        if target and target not in node_ids:
            errors.append(
                ValidationError(
                    path=f"edges[{idx}].target",
                    message=f"Broken cross-reference: target node '{target}' does not exist",
                )
            )


def _check_evidence_integrity(data: dict, errors: list[ValidationError]) -> None:
    evidence_ids = {str(item.get("id", "")) for item in data.get("evidence", []) if item.get("id") is not None}

    for idx, node in enumerate(data.get("nodes", [])):
        for evidence_idx, evidence_id in enumerate(node.get("evidence_ids", []) or []):
            if str(evidence_id) not in evidence_ids:
                errors.append(
                    ValidationError(
                        path=f"nodes[{idx}].evidence_ids[{evidence_idx}]",
                        message=f"Unknown evidence id: {evidence_id}",
                    )
                )

    for idx, edge in enumerate(data.get("edges", [])):
        for evidence_idx, evidence_id in enumerate(edge.get("evidence_ids", []) or []):
            if str(evidence_id) not in evidence_ids:
                errors.append(
                    ValidationError(
                        path=f"edges[{idx}].evidence_ids[{evidence_idx}]",
                        message=f"Unknown evidence id: {evidence_id}",
                    )
                )


def _check_empty_graph_warning(data: dict, warnings: list[str]) -> None:
    if len(data.get("nodes", [])) == 0 and len(data.get("edges", [])) == 0:
        warnings.append("Graph has no nodes or edges")


def _suggest(value: str, candidates: list[str]) -> str | None:
    alias_suggestions = {
        "company": "Organization",
        "business": "Organization",
    }
    alias = alias_suggestions.get(value.strip().lower())
    if alias in candidates:
        return f"Did you mean '{alias}'?"

    matches = get_close_matches(value.lower(), [item.lower() for item in candidates], n=1, cutoff=0.6)
    if not matches:
        return None
    lower_to_actual = {item.lower(): item for item in candidates}
    return f"Did you mean '{lower_to_actual[matches[0]]}'?"
