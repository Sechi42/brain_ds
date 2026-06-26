"""RED tests for cluster repository behavior."""

from __future__ import annotations

import sqlite3
import unittest

from brain_ds.store.migrations import apply_pending, configure_connection
from brain_ds.store.models import ClusterMetadataV1
from brain_ds.store.graph_store import GraphStore
from brain_ds.store.repository import ClusterRepository, GraphMetaRepository, NodeRepository


class ClusterRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        configure_connection(self.conn)
        apply_pending(self.conn)
        self.meta = GraphMetaRepository(self.conn)
        self.nodes = NodeRepository(self.conn)
        self.repo = ClusterRepository(self.conn)
        self.meta.save_graph_meta(
            graph_id="graph-c",
            workspace_root="/tmp/ws",
            workspace_path="/tmp/ws/project-c",
            project="project-c",
            org="org-c",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at="",
        )
        self.nodes.save_nodes(
            "graph-c",
            [{"id": "node-1", "label": "N1", "type": "Task", "details": {}}],
        )

    def tearDown(self) -> None:
        self.conn.close()

    def test_save_cluster_and_member(self) -> None:
        self.repo.save_clusters(
            "graph-c",
            [{"id": "cluster-1", "name": "Main", "description": "desc"}],
        )
        self.repo.save_members(
            "graph-c",
            [{"cluster_id": "cluster-1", "node_id": "node-1", "weight": 0.5}],
        )

        clusters = self.repo.query_clusters("graph-c")
        members = self.repo.list_members("graph-c", cluster_id="cluster-1")

        self.assertEqual([cluster.id for cluster in clusters], ["cluster-1"])
        self.assertEqual([member.node_id for member in members], ["node-1"])

    def test_cluster_members_cascade_on_node_delete(self) -> None:
        self.repo.save_clusters("graph-c", [{"id": "cluster-2", "name": "Main"}])
        self.repo.save_members(
            "graph-c",
            [{"cluster_id": "cluster-2", "node_id": "node-1", "weight": None}],
        )

        self.nodes.delete_nodes("graph-c")

        members = self.repo.list_members("graph-c", cluster_id="cluster-2")
        self.assertEqual(members, [])

    def test_invalid_parent_cluster_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            self.repo.save_clusters(
                "graph-c",
                [{"id": "cluster-3", "name": "Child", "parent_id": "missing"}],
            )

    def test_cluster_metadata_round_trips_lifecycle_and_anchor_contract(self) -> None:
        metadata = ClusterMetadataV1(
            status="proposed",
            primary_anchor_id="kpi-revenue",
            primary_anchor_type="KPI",
            dominant_department_id="dept-finance",
            supporting_anchor_ids=["source-warehouse", "role-analyst"],
            needs_source=False,
            source_requirements={"tables": ["fact_revenue"], "fields": ["revenue"]},
            summary="Revenue performance cluster",
            quality_signals={"semantic_anchor": "kpi"},
        )

        self.repo.save_clusters(
            "graph-c",
            [{"id": "cluster-kpi", "name": "Revenue", "metadata": metadata.to_dict()}],
        )

        stored = self.repo.query_clusters("graph-c")[0]
        self.assertEqual(stored.metadata["status"], "proposed")
        self.assertEqual(stored.metadata["primary_anchor_id"], "kpi-revenue")
        self.assertEqual(stored.metadata["primary_anchor_type"], "KPI")
        self.assertEqual(stored.metadata["dominant_department_id"], "dept-finance")
        self.assertEqual(stored.metadata["supporting_anchor_ids"], ["source-warehouse", "role-analyst"])
        self.assertFalse(stored.metadata["needs_source"])
        self.assertEqual(stored.metadata["source_requirements"]["tables"], ["fact_revenue"])

    def test_update_cluster_lifecycle_preserves_anchor_metadata(self) -> None:
        self.repo.save_clusters(
            "graph-c",
            [
                {
                    "id": "cluster-lifecycle",
                    "name": "Revenue",
                    "metadata": ClusterMetadataV1(
                        status="proposed",
                        primary_anchor_id="kpi-revenue",
                        primary_anchor_type="KPI",
                        needs_source=True,
                    ).to_dict(),
                }
            ],
        )

        self.repo.update_cluster_lifecycle("graph-c", "cluster-lifecycle", "confirmed")
        confirmed = self.repo.query_clusters("graph-c")[0].metadata
        self.assertEqual(confirmed["status"], "confirmed")
        self.assertEqual(confirmed["primary_anchor_id"], "kpi-revenue")
        self.assertTrue(confirmed["needs_source"])

        self.repo.update_cluster_lifecycle(
            "graph-c", "cluster-lifecycle", "archived", reason="superseded by canonical KPI"
        )
        archived = self.repo.query_clusters("graph-c")[0].metadata
        self.assertEqual(archived["status"], "archived")
        self.assertEqual(archived["archived_reason"], "superseded by canonical KPI")

    def test_invalid_cluster_metadata_status_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ClusterMetadataV1(status="draft", primary_anchor_id="kpi", primary_anchor_type="KPI")


class GraphStoreClusterGovernanceTests(unittest.TestCase):
    def test_graph_store_exposes_cluster_lifecycle_pass_throughs(self) -> None:
        store = GraphStore(":memory:")
        try:
            store.create_graph("graph-store-c", name="Graph Store Cluster")
            store.save_clusters(
                "graph-store-c",
                [
                    {
                        "id": "cluster-store",
                        "name": "Store Cluster",
                        "metadata": ClusterMetadataV1(
                            status="proposed",
                            primary_anchor_id="kpi-store",
                            primary_anchor_type="KPI",
                        ).to_dict(),
                    }
                ],
            )

            store.update_cluster_lifecycle("graph-store-c", "cluster-store", "rejected")

            metadata = store.query_clusters("graph-store-c")[0].metadata
            self.assertEqual(metadata["status"], "rejected")
            self.assertEqual(metadata["primary_anchor_id"], "kpi-store")
        finally:
            store.close()
