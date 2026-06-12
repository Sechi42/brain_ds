"""Deterministic factor scoring functions."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from brain_ds.ontology.relationship_types import BASE_WEIGHTS, RelationshipType
from brain_ds.scoring.stopwords import ALL_STOPWORDS as STOPWORDS


def _fold_accents(text: str) -> str:
    # "también" must tokenize as "tambien", not split into "tambi" + "n":
    # the ASCII-only regex below otherwise breaks words at accented chars and
    # leaks single-letter garbage tokens into the overlap scoring.
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _tokens(text: str) -> set[str]:
    parts = re.findall(r"[a-z0-9]+", _fold_accents(text or "").lower())
    return {token for token in parts if len(token) > 1 and token not in STOPWORDS}


def token_overlap(source_label: str, target_label: str) -> tuple[float, str]:
    source_tokens = _tokens(source_label)
    target_tokens = _tokens(target_label)
    if not source_tokens or not target_tokens:
        return 0.0, "No token overlap context available"
    union = source_tokens | target_tokens
    overlap = source_tokens & target_tokens
    score = len(overlap) / len(union) if union else 0.0
    if overlap:
        return score, f"Token overlap detected: {', '.join(sorted(overlap))}"
    return 0.0, "No meaningful token overlap"


def relationship_base(
    relation_type: RelationshipType | str,
    base_weights: dict[RelationshipType, float] | None = None,
) -> tuple[float, str]:
    weights = base_weights or BASE_WEIGHTS
    rel = relation_type
    if isinstance(rel, str):
        rel = RelationshipType.from_string(rel)
    score = weights.get(rel, 0.20)
    return score, f"Base relationship weight for {rel.value}: {score:.2f}"


def directionality(
    edge: tuple[str, str] | dict[str, str], evidence_items: list[dict[str, Any]]
) -> tuple[float, str]:
    if isinstance(edge, tuple):
        source, target = edge
    else:
        source = edge.get("source", "")
        target = edge.get("target", "")

    reciprocal = False
    for item in evidence_items or []:
        if item.get("reciprocal") is True:
            reciprocal = True
            break
        if item.get("source") == target and item.get("target") == source:
            reciprocal = True
            break

    if reciprocal:
        return 0.20, "Relationship appears reciprocal"
    return 0.80, "Asymmetric directionality supports stronger signal"


def evidence_count(evidence_items: list[dict[str, Any]]) -> tuple[float, str]:
    count = len(evidence_items or [])
    score = min(count / 5.0, 1.0)
    return score, f"Evidence count normalized from {count} source(s)"


def process_cooccurrence(
    edge: tuple[str, str] | dict[str, str], evidence_items: list[dict[str, Any]]
) -> tuple[float, str]:
    if isinstance(edge, tuple):
        source, target = edge
    else:
        source = edge.get("source", "")
        target = edge.get("target", "")

    source_tokens = _tokens(source)
    target_tokens = _tokens(target)
    for item in evidence_items or []:
        context = f"{item.get('where', '')} {item.get('process', '')}".lower()
        if context and any(tok in context for tok in source_tokens) and any(
            tok in context for tok in target_tokens
        ):
            return 1.0, "Source and target co-occur in process context"
    return 0.0, "No process co-occurrence found"


def explicit_reference(
    edge: tuple[str, str] | dict[str, str], evidence_items: list[dict[str, Any]]
) -> tuple[float, str]:
    if isinstance(edge, tuple):
        source, target = edge
    else:
        source = edge.get("source", "")
        target = edge.get("target", "")

    source_lower = source.lower()
    target_lower = target.lower()
    for item in evidence_items or []:
        refs = [str(ref).lower() for ref in item.get("explicit_refs", [])]
        text = str(item.get("text", "")).lower()
        if target_lower in refs or source_lower in refs:
            return 1.0, "Explicit reference found in evidence refs"
        if source_lower and target_lower and source_lower in text and target_lower in text:
            return 0.80, "Explicit source-target mention found in evidence text"
    return 0.0, "No explicit references found"
