"""Composite deterministic relationship scoring engine."""

from __future__ import annotations

from dataclasses import dataclass, field

from brain_ds.ontology.relationship_types import BASE_WEIGHTS

from .factors import (
    directionality,
    evidence_count,
    explicit_reference,
    process_cooccurrence,
    relationship_base,
    token_overlap,
)
from .models import ScoringContext, StrengthResult


@dataclass
class ScoringEngine:
    factor_weights: dict[str, float] = field(
        default_factory=lambda: {
            "token_overlap": 0.25,
            "relationship_base": 0.20,
            "directionality": 0.10,
            "evidence_count": 0.15,
            "process_cooccurrence": 0.15,
            "explicit_reference": 0.15,
        }
    )

    def score(self, ctx: ScoringContext) -> StrengthResult:
        evidence_items = ctx.evidence_items or []
        edge = {"source": ctx.edge_source, "target": ctx.edge_target}

        factor_outputs = {
            "token_overlap": token_overlap(ctx.edge_source, ctx.edge_target),
            "relationship_base": relationship_base(ctx.relation_type, BASE_WEIGHTS),
            "directionality": directionality(edge, evidence_items),
            "evidence_count": evidence_count(evidence_items),
            "process_cooccurrence": process_cooccurrence(edge, evidence_items),
            "explicit_reference": explicit_reference(edge, evidence_items),
        }

        raw_weight = 0.0
        reasons: list[str] = []
        for name, (score_value, reason) in factor_outputs.items():
            raw_weight += max(0.0, score_value) * self.factor_weights.get(name, 0.0)
            if reason:
                reasons.append(reason)

        weight = max(0.0, min(raw_weight, 1.0))
        dedup_reasons = list(dict.fromkeys(reasons))
        dedup_evidence_ids = list(
            dict.fromkeys(
                str(item.get("id") or item.get("evidence_id"))
                for item in evidence_items
                if item.get("id") or item.get("evidence_id")
            )
        )

        return StrengthResult(
            weight=weight,
            reasons=dedup_reasons,
            evidence_ids=dedup_evidence_ids,
        )
