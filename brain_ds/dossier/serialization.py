"""Serialization helpers for KPI dossiers."""

from __future__ import annotations

from typing import Any

from brain_ds.dossier._serialization_utils import MAX_PAYLOAD_BYTES, TRUNCATED_DETAIL_BYTES, TRUNCATED_TEXT_BYTES, payload_size, truncate_text
from brain_ds.dossier.models import KpiDossier

_MAX_PAYLOAD_BYTES = MAX_PAYLOAD_BYTES
_TRUNCATED_TEXT_BYTES = TRUNCATED_TEXT_BYTES
_TRUNCATED_DETAIL_BYTES = TRUNCATED_DETAIL_BYTES


def serialize_dossier(dossier: KpiDossier) -> dict[str, Any]:
    payload = _payload(dossier)
    if payload_size(payload) <= _MAX_PAYLOAD_BYTES:
        return payload
    return _truncate_payload(payload)


def build_summary(dossier: KpiDossier) -> str:
    parts = [f"KPI {dossier.kpi.label}"]
    if dossier.summary:
        parts.append(dossier.summary)
    if dossier.data_sources:
        source_bits: list[str] = []
        for source in dossier.data_sources:
            container_bits = []
            for container in source.containers:
                field_labels = [field.label for field in container.fields]
                container_bits.append(f"{container.node.label}" + (f" fields {', '.join(field_labels)}" if field_labels else ""))
            source_bits.append(f"{source.node.label}" + (f" ({'; '.join(container_bits)})" if container_bits else ""))
        parts.append("Data sources: " + "; ".join(source_bits))
    else:
        parts.append("No mapped data sources or support are currently known")
    if dossier.actors:
        parts.append("Actors: " + ", ".join(actor.node.label for actor in dossier.actors))
    if dossier.processes:
        parts.append("Processes: " + ", ".join(process.node.label for process in dossier.processes))
    limitation_text = _limitation_summary(dossier.limitations)
    if limitation_text:
        parts.append("Limitations: " + limitation_text)
    return ". ".join(parts) + "."


def _payload(dossier: KpiDossier) -> dict[str, Any]:
    return {
        "kpi": _node_dict(dossier.kpi),
        "data_sources": [
            {
                "id": source.node.id,
                "label": source.node.label,
                "details": _description(source.node),
                "containers": [
                    {
                        "id": container.node.id,
                        "label": container.node.label,
                        "description": _description(container.node),
                        "fields": [
                            {"id": field.id, "label": field.label, "description": _description(field)}
                            for field in container.fields
                        ],
                    }
                    for container in source.containers
                ],
            }
            for source in dossier.data_sources
        ],
        "actors": [_node_dict(actor.node) for actor in dossier.actors],
        "processes": [_node_dict(process.node) for process in dossier.processes],
        "limitations": _limitations_dict(dossier),
        "serialized_for_llm": build_summary(dossier),
    }


def _node_dict(node: Any) -> dict[str, Any]:
    return {"id": node.id, "label": node.label, "details": _description(node), "entity_type": node.type}


def _limitations_dict(dossier: KpiDossier) -> dict[str, Any]:
    limitations = dossier.limitations
    return {
        "unmapped_sources": limitations.unmapped_sources,
        "unconfirmed_lineage": limitations.unconfirmed_lineage,
        "weak_edges": limitations.weak_edges,
        "currency_gaps": limitations.currency,
        "completeness": limitations.completeness,
        "missing_ownership": limitations.missing_ownership,
        "missing_process": limitations.missing_process,
        "truncated": limitations.truncated,
        "truncation_reason": limitations.truncation_reason,
    }


def _truncate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    dropped_fields = 0
    payload["limitations"]["truncated"] = True
    payload["limitations"]["truncation_reason"] = "Dossier was truncated to keep payload under 256 KiB"
    for source in payload["data_sources"]:
        for container in source["containers"]:
            while container["fields"] and payload_size(payload) > _MAX_PAYLOAD_BYTES:
                container["fields"].pop()
                dropped_fields += 1
    dropped_containers = 0
    for source in payload["data_sources"]:
        while source["containers"] and payload_size(payload) > _MAX_PAYLOAD_BYTES:
            source["containers"].pop()
            dropped_containers += 1
    payload["limitations"]["truncated"] = True
    payload["limitations"]["truncation_reason"] = (
        f"Dropped {dropped_fields} field(s) and {dropped_containers} container(s) to keep dossier under 256 KiB"
    )
    _truncate_large_text_sections(payload)
    for section in ("actors", "processes"):
        while payload[section] and payload_size(payload) > _MAX_PAYLOAD_BYTES:
            payload[section].pop()
    for key in ("unmapped_sources", "unconfirmed_lineage", "weak_edges", "currency_gaps", "completeness"):
        while payload["limitations"].get(key) and payload_size(payload) > _MAX_PAYLOAD_BYTES:
            payload["limitations"][key].pop()
    if payload_size(payload) > _MAX_PAYLOAD_BYTES:
        _truncate_all_strings(payload)
    return payload


def _truncate_large_text_sections(payload: dict[str, Any]) -> None:
    payload["serialized_for_llm"] = truncate_text(payload.get("serialized_for_llm", ""), _TRUNCATED_TEXT_BYTES)
    payload["kpi"]["details"] = truncate_text(payload["kpi"].get("details", ""), _TRUNCATED_DETAIL_BYTES)
    for section in ("actors", "processes"):
        for item in payload[section]:
            item["details"] = truncate_text(item.get("details", ""), _TRUNCATED_DETAIL_BYTES)
    for source in payload["data_sources"]:
        source["details"] = truncate_text(source.get("details", ""), _TRUNCATED_DETAIL_BYTES)
        for container in source["containers"]:
            container["description"] = truncate_text(container.get("description", ""), _TRUNCATED_DETAIL_BYTES)
    for values in payload["limitations"].values():
        if isinstance(values, list):
            for item in values:
                if isinstance(item, dict):
                    for key, value in list(item.items()):
                        if isinstance(value, str):
                            item[key] = truncate_text(value, _TRUNCATED_DETAIL_BYTES)


def _truncate_all_strings(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in list(value.items()):
            if isinstance(item, str):
                value[key] = truncate_text(item, 64)
            else:
                _truncate_all_strings(item)
    elif isinstance(value, list):
        for item in value:
            _truncate_all_strings(item)


def _description(node: Any) -> str:
    details = getattr(node, "details", None) or {}
    if isinstance(details, dict):
        value = details.get("description") or details.get("summary") or details.get("meaning")
        if value is not None:
            return str(value)
    return ""


def _limitation_summary(limitations: Any) -> str:
    items: list[str] = []
    for gap in limitations.unmapped_sources[:2]:
        items.append(str(gap.get("description") or gap))
    for gap in limitations.unconfirmed_lineage[:2]:
        items.append(f"Pending confirmation for {gap.get('to_node')}")
    for gap in limitations.weak_edges[:2]:
        items.append(f"Weak edge {gap.get('from_node')}→{gap.get('to_node')}")
    for gap in limitations.currency[:2]:
        items.append(str(gap.get("description") or gap))
    if limitations.missing_ownership:
        items.append("ownership is not mapped")
    if limitations.missing_process:
        items.append("supporting process is not mapped")
    return "; ".join(items)
