from .elicit_compliance import Finding, check_elicit_compliance
from .semantic_verify import (
    CoherenceResult,
    FaithfulnessResult,
    ReferenceFinding,
    SemanticFinding,
    SemanticReport,
    build_semantic_report,
    score_brd_coherence,
    score_graph_faithfulness,
)

__all__ = [
    # Existing exports — UNCHANGED
    "Finding",
    "check_elicit_compliance",
    # New semantic verification exports — ADDITIVE
    "CoherenceResult",
    "FaithfulnessResult",
    "ReferenceFinding",
    "SemanticFinding",
    "SemanticReport",
    "build_semantic_report",
    "score_brd_coherence",
    "score_graph_faithfulness",
]
