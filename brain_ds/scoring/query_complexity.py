"""Deterministic query complexity classifier for the cognitive router.

Single source of truth for all numeric thresholds. A pure, side-effect-free
helper consumed by agent prose — NOT wired into any MCP tool response payload.
"""

from __future__ import annotations

from typing import TypedDict

from brain_ds.ontology.relationship_types import RelationshipType
from brain_ds.scoring.factors import _tokens


# ---------------------------------------------------------------------------
# Ontology-derived relational keyword set (computed once at import time)
# ---------------------------------------------------------------------------

def _relational_keywords_from_ontology() -> frozenset[str]:
    """Derive relational keywords from RelationshipType enum values.

    rt.value examples: "depends-on", "owned-by", "creates-risk"
    Split on "-", keep parts with len > 1 so the set auto-tracks enum changes.
    """
    kws: set[str] = set()
    for rt in RelationshipType:
        for part in rt.value.replace("-", " ").split():
            if len(part) > 1:
                kws.add(part)
    return frozenset(kws)


# ---------------------------------------------------------------------------
# Module-level constants — SINGLE SOURCE OF TRUTH
# These values are mirrored verbatim in .claude/agents/brainds-query-consultant.md
# ---------------------------------------------------------------------------

# Token-count signal
TOKEN_COUNT_CUTOFF: int = 5          # >=5 meaningful tokens => multi-hop indicator
TOKEN_SIGNAL_WEIGHT: float = 0.35

# Result-type diversity signal (from first search_graph pass)
RESULT_TYPE_DIVERSITY_CUTOFF: int = 3   # >=3 distinct types => spans entity classes
DIVERSITY_SIGNAL_WEIGHT: float = 0.30

# Comparative / aggregation keyword signal (literal, language-agnostic core)
COMPARATIVE_SIGNAL_WEIGHT: float = 0.30
COMPARATIVE_KEYWORDS: frozenset[str] = frozenset({
    "compare", "comparison", "between", "across", "all", "every", "each",
    "which", "when", "trend", "most", "least", "ranked", "rank", "top",
    "vs", "versus", "difference", "total", "count", "average", "sum",
})

# Relational / path keyword signal — DERIVED at import time from RelationshipType
RELATIONAL_SIGNAL_WEIGHT: float = 0.30
RELATIONAL_KEYWORDS: frozenset[str] = _relational_keywords_from_ontology()
# Small literal augmentation set for natural-language path phrasing:
RELATIONAL_EXTRA_KEYWORDS: frozenset[str] = frozenset({
    "who", "owner", "owns", "path", "connected", "links", "via", "through",
})

# Decision boundary — score >= boundary => "complex"; >= means tie-break to complex
COMPLEX_SCORE_BOUNDARY: float = 0.30


# ---------------------------------------------------------------------------
# Public type
# ---------------------------------------------------------------------------

class QueryComplexity(TypedDict):
    level: str          # "simple" | "complex"
    score: float        # 0.0 .. ~1.0, monotonic in complexity
    signals: list[str]  # human-readable signal names that fired, always sorted


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_query(
    query: str,
    result_types: list[str] | set[str] | None = None,
) -> QueryComplexity:
    """Classify a query as 'simple' or 'complex' using four cheap LLM-free signals.

    Parameters
    ----------
    query:
        Raw user query string.
    result_types:
        Distinct entity ``type`` strings from the FIRST ``search_graph`` pass
        (caller passes ``[r["type"] for r in results]`` or the set).
        ``None`` / empty => diversity signal contributes 0; classifier still
        works pre-search.

    Returns
    -------
    QueryComplexity dict with keys ``level``, ``score``, ``signals``.
    ``signals`` is always sorted for deterministic output.
    """
    score: float = 0.0
    signals: list[str] = []

    tokens = _tokens(query)

    # 1. Token-count signal
    if len(tokens) >= TOKEN_COUNT_CUTOFF:
        score += TOKEN_SIGNAL_WEIGHT
        signals.append(f"token_count>={TOKEN_COUNT_CUTOFF}")

    # 2. Comparative / aggregation keyword signal
    matched_comparative = tokens & COMPARATIVE_KEYWORDS
    if matched_comparative:
        score += COMPARATIVE_SIGNAL_WEIGHT
        # Report the first (alphabetically) matched keyword for determinism
        signals.append(f"comparative_keyword:{min(matched_comparative)}")

    # 3. Relational keyword signal (ontology-derived + extra NL phrasing)
    matched_relational = tokens & (RELATIONAL_KEYWORDS | RELATIONAL_EXTRA_KEYWORDS)
    if matched_relational:
        score += RELATIONAL_SIGNAL_WEIGHT
        signals.append(f"relational_keyword:{min(matched_relational)}")

    # 4. Result-type diversity signal
    distinct_types = set(result_types or ())
    if len(distinct_types) >= RESULT_TYPE_DIVERSITY_CUTOFF:
        score += DIVERSITY_SIGNAL_WEIGHT
        signals.append(f"result_type_diversity>={RESULT_TYPE_DIVERSITY_CUTOFF}")

    # Decision: bias-to-complex via >= (tie-break lands on complex)
    level = "complex" if score >= COMPLEX_SCORE_BOUNDARY else "simple"

    return QueryComplexity(
        level=level,
        score=round(score, 3),
        signals=sorted(signals),
    )
