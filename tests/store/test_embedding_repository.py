"""RED tests for embedding repository and GraphStore embedding API."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest

from brain_ds.store.errors import CorruptVectorError
from brain_ds.store.graph_store import GraphStore
from brain_ds.store.migrations import apply_pending, configure_connection
from brain_ds.store.repository import EmbeddingRepository, GraphMetaRepository


class EmbeddingRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        configure_connection(self.conn)
        apply_pending(self.conn)
        self.meta = GraphMetaRepository(self.conn)
        self.repo = EmbeddingRepository(self.conn)
        self.meta.save_graph_meta(
            graph_id="graph-emb",
            workspace_root="/tmp/ws",
            workspace_path="/tmp/ws/project-emb",
            project="project-emb",
            org="org-emb",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at="",
        )

    def tearDown(self) -> None:
        self.conn.close()

    def test_upsert_embedding_is_idempotent(self) -> None:
        self.repo.upsert_embedding("graph-emb", "node", "n-1", "m-1", [1.0, 0.0, 0.0])
        self.repo.upsert_embedding("graph-emb", "node", "n-1", "m-1", [0.0, 1.0, 0.0])

        rows = self.conn.execute(
            """
            SELECT graph_id, target_type, target_id, model, dimensions
              FROM embeddings
             WHERE graph_id = ? AND target_id = ?
            """,
            ("graph-emb", "n-1"),
        ).fetchall()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][4], 3)

    def test_upsert_embedding_mixed_dim_raises(self) -> None:
        self.repo.upsert_embedding("graph-emb", "node", "n-1", "m-1", [1.0, 0.0, 0.0])

        with self.assertRaises(CorruptVectorError):
            self.repo.upsert_embedding("graph-emb", "node", "n-2", "m-1", [1.0, 0.0])

    def test_nearest_embeddings_orders_by_cosine(self) -> None:
        self.repo.upsert_embedding("graph-emb", "node", "q", "m-1", [1.0, 0.0, 0.0])
        self.repo.upsert_embedding("graph-emb", "node", "a", "m-1", [1.0, 0.0, 0.0])
        self.repo.upsert_embedding("graph-emb", "node", "b", "m-1", [0.0, 1.0, 0.0])
        self.repo.upsert_embedding("graph-emb", "node", "c", "m-1", [-1.0, 0.0, 0.0])

        hits = self.repo.nearest_embeddings("graph-emb", "q", k=3)
        self.assertEqual([hit.target_id for hit in hits], ["a", "b", "c"])
        self.assertAlmostEqual(hits[0].score, 1.0)
        self.assertAlmostEqual(hits[1].score, 0.0)
        self.assertAlmostEqual(hits[2].score, -1.0)

    def test_nearest_embeddings_excludes_self(self) -> None:
        self.repo.upsert_embedding("graph-emb", "node", "q", "m-1", [1.0, 0.0, 0.0])
        self.repo.upsert_embedding("graph-emb", "node", "a", "m-1", [1.0, 0.0, 0.0])

        hits = self.repo.nearest_embeddings("graph-emb", "q", k=10)
        self.assertEqual([hit.target_id for hit in hits], ["a"])

    def test_nearest_embeddings_filters_by_model(self) -> None:
        self.repo.upsert_embedding("graph-emb", "node", "q", "model-a", [1.0, 0.0, 0.0])
        self.repo.upsert_embedding("graph-emb", "node", "a", "model-a", [1.0, 0.0, 0.0])
        self.repo.upsert_embedding("graph-emb", "node", "b", "model-b", [1.0, 0.0, 0.0])

        hits = self.repo.nearest_embeddings("graph-emb", "q", k=10, model="model-a")
        self.assertEqual([hit.target_id for hit in hits], ["a"])

    def test_nearest_embeddings_missing_target_raises(self) -> None:
        with self.assertRaises(CorruptVectorError):
            self.repo.nearest_embeddings("graph-emb", "missing", k=3)


class GraphStoreEmbeddingApiTests(unittest.TestCase):
    def test_graph_store_embedding_methods_delegate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with GraphStore(f"{tmp_dir}/graph.db") as store:
                graph_id = "graph-scope"
                store.meta_repo.save_graph_meta(
                    graph_id=graph_id,
                    workspace_root="",
                    workspace_path="",
                    project="",
                    org="org",
                    schema_version="2.0.0",
                    contract_version="1.0.0",
                    node_count=0,
                    edge_count=0,
                    imported_from=None,
                    generated_at="",
                )
                store.meta_repo.save_graph_meta(
                    graph_id="other-graph",
                    workspace_root="",
                    workspace_path="",
                    project="",
                    org="org",
                    schema_version="2.0.0",
                    contract_version="1.0.0",
                    node_count=0,
                    edge_count=0,
                    imported_from=None,
                    generated_at="",
                )
                store.upsert_embedding(graph_id, "node", "q", "m-1", [1.0, 0.0, 0.0])
                store.upsert_embedding(graph_id, "node", "a", "m-1", [1.0, 0.0, 0.0])
                store.upsert_embedding("other-graph", "node", "a", "m-1", [-1.0, 0.0, 0.0])

                hits = store.nearest_embeddings(graph_id, "q", k=5)

                self.assertEqual([hit.target_id for hit in hits], ["a"])
