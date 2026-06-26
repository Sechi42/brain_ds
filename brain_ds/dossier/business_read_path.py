"""Pure read-path composition for business dossiers."""

from __future__ import annotations

from typing import Any

from brain_ds.dossier.business_assembler import assemble_business_dossier
from brain_ds.dossier.business_router import rank_business_interpretations
from brain_ds.dossier.business_serialization import serialize_business_dossier
from brain_ds.dossier.models import DossierGapInputs, DossierGraphView
from brain_ds.retrieval.models import RetrievalCandidate
from brain_ds.retrieval.neighborhood import ClusterRoute


def build_business_dossier_payload(
    *,
    graph_view: DossierGraphView,
    gaps: DossierGapInputs,
    query: str,
    candidates: list[RetrievalCandidate],
    cluster_routes: list[ClusterRoute] | None = None,
    max_alternatives: int = 3,
    depth: int = 2,
) -> dict[str, Any]:
    """Rank, assemble, and serialize a business dossier without side effects."""
    interpretations = rank_business_interpretations(
        query=query,
        candidates=candidates,
        cluster_routes=cluster_routes,
        max_alternatives=max_alternatives,
    )
    dossier = assemble_business_dossier(
        graph_view,
        gaps,
        query=query,
        interpretations=interpretations,
        depth=depth,
    )
    return serialize_business_dossier(dossier)
