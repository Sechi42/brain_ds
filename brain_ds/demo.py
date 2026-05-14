"""Deterministic demo graph builders for smoke testing."""

from __future__ import annotations

from brain_ds.ontology import Edge, EntityType, Graph, Node, RelationshipType


def build_logitrans_graph() -> Graph:
    """Build a realistic deterministic LogiTrans organization graph."""
    nodes = [
        Node(
            id="org/logitrans/domain/department/logistics",
            label="[Department] Logistics",
            type=EntityType.DEPARTMENT,
            details={
                "what": "Coordinates warehousing and last-mile operations.",
                "why": "Reduce lead time and missed delivery windows.",
                "where": "org/logitrans/domain/department/logistics",
                "learned": "Operational bottlenecks concentrate in handoff points.",
            },
        ),
        Node(
            id="org/logitrans/domain/role/operations-manager",
            label="[Role] Operations Manager",
            type=EntityType.ROLE,
            details={
                "what": "Owns delivery execution and dispatch governance.",
                "why": "Aligns daily execution with service-level objectives.",
                "where": "org/logitrans/domain/role/operations-manager",
                "learned": "Escalation quality improves with explicit ownership.",
            },
        ),
        Node(
            id="org/logitrans/domain/kpi/delivery-time",
            label="[KPI] Delivery Time",
            type=EntityType.KPI,
            details={
                "what": "Average elapsed time from order confirmation to delivery.",
                "why": "Primary customer experience metric for logistics quality.",
                "where": "org/logitrans/domain/kpi/delivery-time",
                "learned": "Transit variability predicts complaint volume.",
            },
        ),
        Node(
            id="org/logitrans/domain/decision/reroute-policy",
            label="[Decision] Dynamic Reroute Policy",
            type=EntityType.DECISION,
            details={
                "what": "Defines rerouting thresholds for delayed shipments.",
                "why": "Mitigates cascading delays during route disruptions.",
                "where": "org/logitrans/domain/decision/reroute-policy",
                "learned": "Early reroute triggers outperform late manual intervention.",
            },
        ),
        Node(
            id="org/logitrans/domain/data-source/fleet-telemetry",
            label="[Data Source] Fleet Telemetry",
            type=EntityType.DATA_SOURCE,
            details={
                "what": "Vehicle GPS pings and driver status events.",
                "why": "Provides near-real-time signal for delay detection.",
                "where": "org/logitrans/domain/data-source/fleet-telemetry",
                "learned": "Ping cadence under 60 seconds improves anomaly precision.",
            },
        ),
        Node(
            id="org/logitrans/domain/heuristic/congestion-risk",
            label="[Heuristic] Congestion Risk Rule",
            type=EntityType.HEURISTIC,
            details={
                "what": "Flags routes with congestion and weather overlap.",
                "why": "Supports proactive dispatch interventions.",
                "where": "org/logitrans/domain/heuristic/congestion-risk",
                "learned": "Combining weather and congestion lowers false positives.",
            },
        ),
    ]

    edges = [
        Edge(
            source="org/logitrans/domain/department/logistics",
            target="org/logitrans/domain/role/operations-manager",
            label=RelationshipType.OWNS,
            weight=0.72,
            reasons=["Department accountability charter."],
            evidence_ids=["ev-logitrans-001"],
        ),
        Edge(
            source="org/logitrans/domain/department/logistics",
            target="org/logitrans/domain/kpi/delivery-time",
            label=RelationshipType.MEASURED_BY,
            weight=0.83,
            reasons=["Service level objective review cadence."],
            evidence_ids=["ev-logitrans-002"],
        ),
        Edge(
            source="org/logitrans/domain/role/operations-manager",
            target="org/logitrans/domain/data-source/fleet-telemetry",
            label=RelationshipType.USES,
            weight=0.78,
            reasons=["Dispatch standups consume telemetry dashboards."],
            evidence_ids=["ev-logitrans-003"],
        ),
        Edge(
            source="org/logitrans/domain/decision/reroute-policy",
            target="org/logitrans/domain/heuristic/congestion-risk",
            label=RelationshipType.DEPENDS_ON,
            weight=0.69,
            reasons=["Policy trigger references heuristic score threshold."],
            evidence_ids=["ev-logitrans-004"],
        ),
    ]

    return Graph(org="logitrans", nodes=nodes, edges=edges)
