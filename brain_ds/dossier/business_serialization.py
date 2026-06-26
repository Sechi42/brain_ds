"""Serialization helpers for query-first business dossiers."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from brain_ds.dossier._serialization_utils import MAX_PAYLOAD_BYTES, payload_size, truncate_text
from brain_ds.dossier.business_models import BusinessDossier

_MAX_PAYLOAD_BYTES = MAX_PAYLOAD_BYTES
_TRUNCATED_DETAIL_BYTES = 512
_TRUNCATED_SUMMARY_BYTES = 1024


def serialize_business_dossier(dossier: BusinessDossier) -> dict[str, Any]:
    payload = _payload(dossier)
    if payload_size(payload) > _MAX_PAYLOAD_BYTES:
        payload = _truncate_payload(payload)
    payload["serialized_for_llm"] = build_business_summary(payload)
    if payload_size(payload) > _MAX_PAYLOAD_BYTES:
        payload = _truncate_payload(payload)
        payload["serialized_for_llm"] = truncate_text(build_business_summary(payload), _TRUNCATED_SUMMARY_BYTES)
    return payload


def build_business_summary(payload: dict[str, Any]) -> str:
    selected_id = payload.get("selected_interpretation_id") or "none"
    parts = [f"Business dossier for query '{payload.get('query', '')}'", f"Selected interpretation: {selected_id}"]
    section_bits: list[str] = []
    for section in ("kpis", "problems", "departments", "processes", "actors"):
        labels = [str(item.get("label")) for item in payload.get("dossier", {}).get(section, [])[:3]]
        if labels:
            section_bits.append(f"{section}: {', '.join(labels)}")
    if section_bits:
        parts.append("Business sections: " + "; ".join(section_bits))
    if payload.get("evidence_sources"):
        labels = [str(item.get("label")) for item in payload["evidence_sources"][:3]]
        parts.append("Evidence sources: " + ", ".join(labels))
    uncertainty = payload.get("uncertainty", {})
    uncertainty_bits = []
    for key in ("completeness", "currency", "weak_edges"):
        if uncertainty.get(key):
            uncertainty_bits.append(key)
    if uncertainty.get("source_heavy"):
        uncertainty_bits.append("source-heavy")
    if uncertainty.get("business_light"):
        uncertainty_bits.append("business-light")
    if uncertainty.get("truncated"):
        uncertainty_bits.append("truncated")
    if uncertainty_bits:
        parts.append("Uncertainty: " + ", ".join(uncertainty_bits))
    return ". ".join(parts) + "."


def _payload(dossier: BusinessDossier) -> dict[str, Any]:
    return {
        "query": dossier.query,
        "selected_interpretation_id": dossier.selected_interpretation_id,
        "interpretations": [_interpretation_dict(item) for item in dossier.interpretations],
        "dossier": dossier.dossier,
        "evidence_sources": dossier.evidence_sources,
        "uncertainty": asdict(dossier.uncertainty),
        "pending_question_proposals": [asdict(item) for item in dossier.pending_question_proposals],
        "pending_questions_created": dossier.pending_questions_created,
        "serialized_for_llm": dossier.serialized_for_llm,
    }


def _interpretation_dict(value: Any) -> dict[str, Any]:
    item = asdict(value)
    item["entity_ids"] = list(value.entity_ids)
    item["evidence_ids"] = list(value.evidence_ids)
    return item


def _truncate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    dropped = 0
    for section in ("evidence_sources", "actors", "processes", "departments", "problems", "kpis"):
        values = payload["dossier"].get(section, []) if section in payload.get("dossier", {}) else payload.get(section, [])
        while values and payload_size(payload) > _MAX_PAYLOAD_BYTES:
            values.pop()
            dropped += 1
    _truncate_large_text(payload)
    for key in ("pending_question_proposals", "interpretations"):
        while payload.get(key) and payload_size(payload) > _MAX_PAYLOAD_BYTES:
            payload[key].pop()
            dropped += 1
    if payload_size(payload) > _MAX_PAYLOAD_BYTES:
        _truncate_all_strings(payload)
    payload["uncertainty"]["truncated"] = True
    payload["uncertainty"]["truncation_reason"] = f"Dropped {dropped} item(s) to keep dossier under 256 KiB"
    return payload


def _truncate_large_text(payload: dict[str, Any]) -> None:
    payload["serialized_for_llm"] = truncate_text(payload.get("serialized_for_llm", ""), _TRUNCATED_SUMMARY_BYTES)
    for section in payload.get("dossier", {}).values():
        for item in section:
            if isinstance(item, dict) and isinstance(item.get("details"), str):
                item["details"] = truncate_text(item["details"], _TRUNCATED_DETAIL_BYTES)
    for item in payload.get("evidence_sources", []):
        if isinstance(item, dict) and isinstance(item.get("details"), str):
            item["details"] = truncate_text(item["details"], _TRUNCATED_DETAIL_BYTES)


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
