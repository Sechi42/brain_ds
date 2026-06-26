"""Pure DTOs for KPI dossier assembly."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class DossierGraphView:
    nodes_by_id: dict[str, Any] = field(default_factory=dict)
    adjacency: dict[str, set[str]] = field(default_factory=dict)
    children_by_parent: dict[str | None, list[Any]] = field(default_factory=dict)
    edges: list[Any] = field(default_factory=list)
    ledger_status_by_target: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DossierGapInputs:
    completeness: list[dict[str, Any]] = field(default_factory=list)
    currency: list[dict[str, Any]] = field(default_factory=list)
    weak_edges: list[dict[str, Any]] = field(default_factory=list)
    unconfirmed_lineage: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class KpiDossier:
    kpi: Any
    data_sources: list[DataSourceFacet] = field(default_factory=list)
    actors: list[ActorFacet] = field(default_factory=list)
    processes: list[ProcessFacet] = field(default_factory=list)
    limitations: LimitationsFacet = field(default_factory=lambda: LimitationsFacet())
    summary: str = ""


@dataclass(frozen=True, slots=True)
class DataSourceFacet:
    node: Any
    containers: list[DataContainerFacet] = field(default_factory=list)
    lineage_source: str = ""


@dataclass(frozen=True, slots=True)
class DataContainerFacet:
    node: Any
    fields: list[Any] = field(default_factory=list)
    lineage_source: str = ""


@dataclass(frozen=True, slots=True)
class ActorFacet:
    node: Any


@dataclass(frozen=True, slots=True)
class ProcessFacet:
    node: Any


@dataclass(frozen=True, slots=True)
class LimitationsFacet:
    unmapped_sources: list[dict[str, Any]] = field(default_factory=list)
    unconfirmed_lineage: list[dict[str, Any]] = field(default_factory=list)
    missing_ownership: bool = False
    missing_process: bool = False
    completeness: list[dict[str, Any]] = field(default_factory=list)
    currency: list[dict[str, Any]] = field(default_factory=list)
    weak_edges: list[dict[str, Any]] = field(default_factory=list)
    truncated: bool = False
    truncation_reason: str | None = None
