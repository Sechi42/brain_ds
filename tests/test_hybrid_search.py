"""RED tests for vector nearest-neighbor lookup and hybrid graph search."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from brain_ds.mcp.tools import search_graph
from brain_ds.store.errors import CorruptVectorError, GraphNotFoundError
from brain_ds.store.graph_store import GraphStore
from brain_ds.store.migrations import apply_pending, configure_connection
from brain_ds.store.models import NearestHit
from brain_ds.store.repository import EmbeddingRepository, GraphMetaRepository


def _make_graph_store() -> tuple[GraphStore, tempfile.TemporaryDirectory, str]:
    tmp = tempfile.TemporaryDirectory()
    db_path = Path(tmp.name) / "store.db"
    store = GraphStore(str(db_path))
    graph_id = "graph-hybrid"
    store.meta_repo.save_graph_meta(
        graph_id=graph_id,
        workspace_root=tmp.name,
        workspace_path=tmp.name,
        project="proj",
        org="org",
        schema_version="2.0.0",
        contract_version="1.0.0",
        node_count=0,
        edge_count=0,
        imported_from=None,
        generated_at="",
    )
    return store, tmp, graph_id


class EmbeddingRepositoryNearestToVectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        configure_connection(self.conn)
        apply_pending(self.conn)
        self.meta = GraphMetaRepository(self.conn)
        self.repo = EmbeddingRepository(self.conn)
        self.graph_id = "graph-emb"
        self.meta.save_graph_meta(
            graph_id=self.graph_id,
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

    def test_nearest_to_vector_orders_by_cosine_and_honors_k(self) -> None:
        self.repo.upsert_embedding(self.graph_id, "node", "a", "m-1", [1.0, 0.0, 0.0])
        self.repo.upsert_embedding(self.graph_id, "node", "b", "m-1", [0.5, 0.5, 0.0])
        self.repo.upsert_embedding(self.graph_id, "node", "c", "m-1", [0.0, 1.0, 0.0])

        hits = self.repo.nearest_to_vector(self.graph_id, [1.0, 0.0, 0.0], k=2)

        self.assertEqual([hit.target_id for hit in hits], ["a", "b"])
        self.assertGreater(hits[0].score, hits[1].score)

    def test_nearest_to_vector_raises_on_zero_norm_query(self) -> None:
        self.repo.upsert_embedding(self.graph_id, "node", "a", "m-1", [1.0, 0.0, 0.0])

        with self.assertRaises(CorruptVectorError):
            self.repo.nearest_to_vector(self.graph_id, [0.0, 0.0, 0.0], k=3)

    def test_nearest_to_vector_returns_empty_when_graph_has_no_embeddings(self) -> None:
        hits = self.repo.nearest_to_vector(self.graph_id, [1.0, 0.0, 0.0], k=3)

        self.assertEqual(hits, [])


class GraphStoreNearestToVectorTests(unittest.TestCase):
    def test_delegate_and_missing_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = GraphStore(f"{tmp_dir}/graph.db")
            store.meta_repo.save_graph_meta(
                graph_id="graph-scope",
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
            store.upsert_embedding("graph-scope", "node", "q", "m-1", [1.0, 0.0, 0.0])
            store.upsert_embedding("graph-scope", "node", "a", "m-1", [1.0, 0.0, 0.0])

            try:
                with patch.object(
                    store.embedding_repo,
                    "nearest_to_vector",
                    return_value=[NearestHit(target_id="a", score=1.0)],
                    create=True,
                ) as nearest_mock:
                    hits = store.nearest_to_vector("graph-scope", [1.0, 0.0, 0.0], k=4)

                self.assertEqual([hit.target_id for hit in hits], ["a"])
                nearest_mock.assert_called_once_with("graph-scope", [1.0, 0.0, 0.0], k=4)

                with self.assertRaises(GraphNotFoundError):
                    store.nearest_to_vector("missing", [1.0, 0.0, 0.0], k=1)
            finally:
                store.close()


class HybridSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store, self.tmp, self.graph_id = _make_graph_store()

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def _upsert(self, node_id: str, label: str, details: dict[str, object]) -> None:
        self.store.upsert_node(
            self.graph_id,
            {
                "id": node_id,
                "label": label,
                "type": "Data Source",
                "supertype": "Knowledge",
                "details": details,
            },
        )

    def _ids(self, result: list[dict[str, object]] | dict[str, object]) -> list[str]:
        self.assertIsInstance(result, list)
        return [item["id"] for item in result]

    def test_model_none_returns_exact_lexical_baseline_and_skips_dense_path(self) -> None:
        self._upsert("n-1", "Alpha Source", {"what": "alpha facts"})
        self._upsert("n-2", "Beta Source", {"what": "beta facts"})

        with patch("brain_ds.mcp.tools.get_default_model", return_value=None) as model_mock, patch.object(
            self.store, "nearest_to_vector", create=True
        ) as nearest_mock:
            result = search_graph(self.store, {"graph_id": self.graph_id, "query": "alpha"})

        self.assertEqual(self._ids(result), ["n-1"])
        model_mock.assert_called_once()
        nearest_mock.assert_not_called()

    def test_embed_failure_returns_exact_lexical_baseline(self) -> None:
        self._upsert("n-1", "Alpha Source", {"what": "alpha facts"})
        self._upsert("n-2", "Beta Source", {"what": "beta facts"})

        fake_model = MagicMock()
        fake_model.embed.side_effect = RuntimeError("boom")

        with patch("brain_ds.mcp.tools.get_default_model", return_value=fake_model), patch.object(
            self.store, "nearest_to_vector", create=True
        ) as nearest_mock:
            result = search_graph(self.store, {"graph_id": self.graph_id, "query": "alpha"})

        self.assertEqual(self._ids(result), ["n-1"])
        fake_model.embed.assert_called_once_with("alpha")
        nearest_mock.assert_not_called()

    def test_nearest_failure_returns_exact_lexical_baseline(self) -> None:
        self._upsert("n-1", "Alpha Source", {"what": "alpha facts"})
        self._upsert("n-2", "Beta Source", {"what": "beta facts"})

        fake_model = MagicMock()
        fake_model.embed.return_value = [1.0, 0.0, 0.0]

        with patch("brain_ds.mcp.tools.get_default_model", return_value=fake_model), patch.object(
            self.store,
            "nearest_to_vector",
            create=True,
            side_effect=CorruptVectorError("no vector for graph"),
        ) as nearest_mock:
            result = search_graph(self.store, {"graph_id": self.graph_id, "query": "alpha"})

        self.assertEqual(self._ids(result), ["n-1"])
        fake_model.embed.assert_called_once_with("alpha")
        nearest_mock.assert_called_once()

    def test_no_embeddings_returns_exact_lexical_baseline(self) -> None:
        self._upsert("n-1", "Alpha Source", {"what": "alpha facts"})
        self._upsert("n-2", "Beta Source", {"what": "beta facts"})

        fake_model = MagicMock()
        fake_model.embed.return_value = [1.0, 0.0, 0.0]

        with patch("brain_ds.mcp.tools.get_default_model", return_value=fake_model), patch.object(
            self.store, "nearest_to_vector", return_value=[], create=True
        ) as nearest_mock:
            result = search_graph(self.store, {"graph_id": self.graph_id, "query": "alpha"})

        self.assertEqual(self._ids(result), ["n-1"])
        fake_model.embed.assert_called_once_with("alpha")
        nearest_mock.assert_called_once()

    def test_dense_only_recall_surfaces_when_lexical_search_is_empty(self) -> None:
        self._upsert("node-churn", "workforce churn", {"context": "employees leaving unexpectedly"})
        self._upsert("node-exodus", "talent exodus", {"context": "departure of skilled staff"})

        fake_model = MagicMock()
        fake_model.embed.return_value = [1.0, 0.0, 0.0]

        with patch("brain_ds.mcp.tools.get_default_model", return_value=fake_model), patch.object(
            self.store,
            "nearest_to_vector",
            create=True,
            return_value=[NearestHit(target_id="node-churn", score=0.97)],
        ):
            result = search_graph(
                self.store,
                {"graph_id": self.graph_id, "query": "employee attrition"},
            )

        self.assertEqual(self._ids(result), ["node-churn"])
        fake_model.embed.assert_called_once_with("employee attrition")

    def test_hybrid_rrf_dedupes_and_reorders_without_losing_lexical_hits(self) -> None:
        self._upsert("A", "alpha source", {"what": "alpha facts"})
        self._upsert("B", "alpha beta source", {"what": "alpha beta facts"})
        self._upsert("C", "gamma source", {"what": "gamma facts"})

        fake_model = MagicMock()
        fake_model.embed.return_value = [1.0, 0.0, 0.0]

        with patch("brain_ds.mcp.tools.get_default_model", return_value=fake_model), patch.object(
            self.store,
            "nearest_to_vector",
            create=True,
            return_value=[NearestHit(target_id="B", score=0.99), NearestHit(target_id="C", score=0.98)],
        ) as nearest_mock:
            result = search_graph(self.store, {"graph_id": self.graph_id, "query": "alpha"})

        ids = self._ids(result)
        self.assertEqual(ids, ["B", "C", "A"])
        self.assertEqual(ids.count("B"), 1)
        self.assertIn("A", ids)
        fake_model.embed.assert_called_once_with("alpha")
        nearest_mock.assert_called_once_with(self.graph_id, [1.0, 0.0, 0.0], k=30)
