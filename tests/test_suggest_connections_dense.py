"""Tests for tools.py dense-embedding wiring (TDD RED phase — PR-2 / T6).

Covers:
  - EMB-S1 (tool layer): update_node producer hook writes embedding row
  - EMB-S2 (degradation): model=None => update_node success, no embedding row
  - SUG-S5: CorruptVectorError => lexical-only fallback, no error surfaced
  - SUG-S6: rank map built from nearest_embeddings hits
  - LE-2: k multiplier (limit * 3 floored at 30)
  - Full pipeline: dense candidate surfaces in suggest_connections result
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from brain_ds.mcp.tools import suggest_connections, update_node
from brain_ds.scoring import similarity
from brain_ds.store.errors import CorruptVectorError
from brain_ds.store.graph_store import GraphStore
from brain_ds.store.models import NearestHit


# ---------------------------------------------------------------------------
# Helpers / Fake embedder
# ---------------------------------------------------------------------------


class FakeEmbeddingModel:
    """Deterministic fake that satisfies EmbeddingModel protocol."""

    def __init__(self, name: str = "fake-test") -> None:
        self._name = name
        self.embed_calls: list[str] = []

    @property
    def name(self) -> str:
        return self._name

    def embed(self, text: str) -> list[float]:
        self.embed_calls.append(text)
        # Fixed 3-dim vector for any text
        return [0.1, 0.2, 0.3]


def _make_store() -> tuple[GraphStore, tempfile.TemporaryDirectory]:
    tmp = tempfile.TemporaryDirectory()
    db_path = Path(tmp.name) / "store.db"
    store = GraphStore(str(db_path))
    store.meta_repo.save_graph_meta(
        graph_id="g1",
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
    return store, tmp


def _upsert_node(store: GraphStore, graph_id: str, node_id: str, label: str,
                 type_: str = "Role", details: dict | None = None) -> None:
    store.upsert_node(graph_id, {
        "id": node_id,
        "label": label,
        "type": type_,
        "supertype": None,
        "parent_id": "ROOT",
        "details": details or {"where": "somewhere"},
    })


# ---------------------------------------------------------------------------
# EMB-S1: Producer hook writes embedding on update_node
# ---------------------------------------------------------------------------


class TestUpdateNodeProducerHook(unittest.TestCase):
    """update_node calls upsert_embedding when EmbeddingModel is available."""

    def setUp(self) -> None:
        self.store, self.tmp = _make_store()
        self.graph_id = "g1"
        self.fake_model = FakeEmbeddingModel()

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_embedding_row_written_after_update_node(self) -> None:
        """EMB-S1: update_node calls store.upsert_embedding with the fake model's vector."""
        with patch(
            "brain_ds.mcp.tools.get_default_model", return_value=self.fake_model
        ):
            result = update_node(self.store, {
                "graph_id": self.graph_id,
                "node_id": "n1",
                "label": "Test Node",
                "type": "Role",
                "details": {"where": "test location"},
            })

        # update_node should succeed (no error key)
        self.assertNotIn("code", result, f"Expected success, got: {result}")

        # Embedding row must exist for (g1, node, n1, fake-test)
        has_row = self.store.embedding_repo.has_embedding(
            self.graph_id, "node", "n1", "fake-test"
        )
        self.assertTrue(has_row, "Expected embedding row for n1 in embeddings table")

    def test_embed_called_with_node_text(self) -> None:
        """update_node calls model.embed() with the node's assembled text."""
        with patch(
            "brain_ds.mcp.tools.get_default_model", return_value=self.fake_model
        ):
            update_node(self.store, {
                "graph_id": self.graph_id,
                "node_id": "n1",
                "label": "Test Node",
                "type": "Role",
                "details": {"where": "test location"},
            })

        self.assertEqual(len(self.fake_model.embed_calls), 1,
                         "model.embed() should be called exactly once")

    def test_update_node_returns_success_result(self) -> None:
        """update_node still returns a valid node dict even with embedding."""
        with patch(
            "brain_ds.mcp.tools.get_default_model", return_value=self.fake_model
        ):
            result = update_node(self.store, {
                "graph_id": self.graph_id,
                "node_id": "n1",
                "label": "Test Node",
                "type": "Role",
                "details": {"where": "somewhere"},
            })

        self.assertNotIn("code", result)
        self.assertEqual(result.get("id"), "n1")


# ---------------------------------------------------------------------------
# EMB-S2: Degradation — model=None => success, no embedding written
# ---------------------------------------------------------------------------


class TestUpdateNodeDegradation(unittest.TestCase):
    """update_node degrades gracefully when EmbeddingModel is None."""

    def setUp(self) -> None:
        self.store, self.tmp = _make_store()
        self.graph_id = "g1"

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_no_embedding_when_model_is_none(self) -> None:
        """EMB-S2: get_default_model()=None => update_node succeeds, no row written."""
        with patch("brain_ds.mcp.tools.get_default_model", return_value=None):
            result = update_node(self.store, {
                "graph_id": self.graph_id,
                "node_id": "n1",
                "label": "Test Node",
                "type": "Role",
                "details": {"where": "somewhere"},
            })

        self.assertNotIn("code", result, "update_node should succeed even without model")

        has_row = self.store.embedding_repo.has_embedding(
            self.graph_id, "node", "n1", "fake-test"
        )
        self.assertFalse(has_row, "No embedding row should be written when model is None")

    def test_update_node_returns_success_even_without_model(self) -> None:
        """update_node returns the node dict even when embedding is skipped."""
        with patch("brain_ds.mcp.tools.get_default_model", return_value=None):
            result = update_node(self.store, {
                "graph_id": self.graph_id,
                "node_id": "n2",
                "label": "Another Node",
                "type": "KPI",
                "details": {"where": "dashboard"},
            })

        self.assertEqual(result.get("id"), "n2")


# ---------------------------------------------------------------------------
# SUG-S5: CorruptVectorError => lexical-only fallback, no error surfaced
# ---------------------------------------------------------------------------


class TestCorruptVectorFallback(unittest.TestCase):
    """suggest_connections catches CorruptVectorError and falls back to lexical-only."""

    def setUp(self) -> None:
        self.store, self.tmp = _make_store()
        self.graph_id = "g1"
        # Add two nodes so suggest_connections has candidates
        _upsert_node(self.store, self.graph_id, "focus",
                     "Ventas Mensuales", "KPI",
                     {"where": "Dashboard comercial ventas", "learned": "CRM ventas"})
        _upsert_node(self.store, self.graph_id, "ds-crm",
                     "CRM Salesforce ventas", "Data Source",
                     {"where": "Salesforce cloud"})

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_corrupt_vector_falls_back_to_lexical(self) -> None:
        """SUG-S5: CorruptVectorError from nearest_embeddings => lexical-only, no tool error."""
        with patch.object(
            self.store, "nearest_embeddings",
            side_effect=CorruptVectorError("focus has no embedding")
        ):
            result = suggest_connections(self.store, {
                "graph_id": self.graph_id,
                "node_id": "focus",
            })

        # Must NOT return an error
        self.assertNotIn("code", result, f"Expected success, got: {result}")
        # Must still return suggestions (lexical path)
        self.assertIn("suggestions", result)

    def test_corrupt_vector_no_error_raised_to_caller(self) -> None:
        """CorruptVectorError is caught silently; caller sees a normal response."""
        with patch.object(
            self.store, "nearest_embeddings",
            side_effect=CorruptVectorError("no vector for focus")
        ):
            result = suggest_connections(self.store, {
                "graph_id": self.graph_id,
                "node_id": "focus",
            })

        self.assertIsInstance(result, dict)
        self.assertNotIn("code", result)


# ---------------------------------------------------------------------------
# SUG-S6: Rank map built from NearestHit list
# ---------------------------------------------------------------------------


class TestRankMapConstruction(unittest.TestCase):
    """tools.suggest_connections builds a 1-based rank dict from NearestHit results."""

    def setUp(self) -> None:
        self.store, self.tmp = _make_store()
        self.graph_id = "g1"
        _upsert_node(self.store, self.graph_id, "focus",
                     "Ventas Mensuales", "KPI",
                     {"where": "Dashboard ventas comercial"})
        _upsert_node(self.store, self.graph_id, "n2",
                     "CRM Salesforce ventas", "Data Source",
                     {"where": "Salesforce cloud"})
        _upsert_node(self.store, self.graph_id, "n3",
                     "ERP datos ventas", "Data Source",
                     {"where": "ERP sistema"})

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_rank_map_is_1_based_and_ordered(self) -> None:
        """SUG-S6: nearest_embeddings [n2@0.9, n3@0.7] => dense_ranks={n2:1, n3:2}."""
        hits = [NearestHit(target_id="n2", score=0.9),
                NearestHit(target_id="n3", score=0.7)]

        # Capture the dense_ranks passed to suggest_connections_for_node
        captured: dict[str, Any] = {}

        import brain_ds.scoring.similarity as sim_module

        original_fn = sim_module.suggest_connections_for_node

        def capturing_suggest(*args: Any, **kwargs: Any) -> Any:
            captured["dense_ranks"] = kwargs.get("dense_ranks")
            captured["dense_scores"] = kwargs.get("dense_scores")
            return original_fn(*args, **kwargs)

        with patch.object(self.store, "nearest_embeddings", return_value=hits), \
             patch.object(sim_module, "suggest_connections_for_node", side_effect=capturing_suggest):
            suggest_connections(self.store, {
                "graph_id": self.graph_id,
                "node_id": "focus",
            })

        self.assertIn("dense_ranks", captured, "dense_ranks must be passed to suggest_connections_for_node")
        dr = captured["dense_ranks"]
        self.assertIsNotNone(dr)
        self.assertEqual(dr.get("n2"), 1)
        self.assertEqual(dr.get("n3"), 2)
        ds = captured.get("dense_scores")
        self.assertIsNotNone(ds)
        self.assertEqual(ds.get("n2"), 0.9)
        self.assertEqual(ds.get("n3"), 0.7)


# ---------------------------------------------------------------------------
# LE-2: k multiplier — k = max(limit * 3, 30)
# ---------------------------------------------------------------------------


class TestKMultiplier(unittest.TestCase):
    """tools.suggest_connections calls nearest_embeddings with k=max(limit*3, 30)."""

    def setUp(self) -> None:
        self.store, self.tmp = _make_store()
        self.graph_id = "g1"
        _upsert_node(self.store, self.graph_id, "focus",
                     "Ventas Mensuales", "KPI",
                     {"where": "Dashboard ventas"})
        _upsert_node(self.store, self.graph_id, "n2",
                     "CRM datos ventas", "Data Source",
                     {"where": "Salesforce"})

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_k_floor_at_30_for_small_limit(self) -> None:
        """LE-2: limit=5 => k=max(15, 30)=30."""
        captured_k: list[int] = []

        def capturing_nearest(graph_id: str, node_id: str, *, k: int = 10, **kwargs: Any) -> list:
            captured_k.append(k)
            return []  # empty hits => lexical-only fallback

        with patch.object(self.store, "nearest_embeddings", side_effect=capturing_nearest):
            suggest_connections(self.store, {
                "graph_id": self.graph_id,
                "node_id": "focus",
                "limit": 5,
            })

        self.assertEqual(len(captured_k), 1, "nearest_embeddings should be called once")
        self.assertEqual(captured_k[0], 30, f"Expected k=30, got k={captured_k[0]}")

    def test_k_multiplier_for_large_limit(self) -> None:
        """LE-2: limit=20 => k=max(60, 30)=60."""
        captured_k: list[int] = []

        def capturing_nearest(graph_id: str, node_id: str, *, k: int = 10, **kwargs: Any) -> list:
            captured_k.append(k)
            return []

        with patch.object(self.store, "nearest_embeddings", side_effect=capturing_nearest):
            suggest_connections(self.store, {
                "graph_id": self.graph_id,
                "node_id": "focus",
                "limit": 20,
            })

        self.assertEqual(len(captured_k), 1)
        self.assertEqual(captured_k[0], 60, f"Expected k=60, got k={captured_k[0]}")


# ---------------------------------------------------------------------------
# Full pipeline: dense candidate surfaces in result
# ---------------------------------------------------------------------------


class TestFullPipelineDenseCandidate(unittest.TestCase):
    """End-to-end: a semantically close but lexically distant node surfaces via dense."""

    def setUp(self) -> None:
        self.store, self.tmp = _make_store()
        self.graph_id = "g1"
        # Focus: KPI about "ventas"
        _upsert_node(self.store, self.graph_id, "focus",
                     "Indicador Comercial Trimestral", "KPI",
                     {"where": "Dashboard comercial"})
        # Dense candidate: Data Source with completely different vocabulary
        # (zero token overlap with focus, but semantically close in embedding space)
        _upsert_node(self.store, self.graph_id, "dense-ds",
                     "Repositorio Tecnico Alpha", "Data Source",
                     {"where": "Sistema tecnico alpha"})
        # A regular lexical candidate so the function has something to work with
        _upsert_node(self.store, self.graph_id, "lexical-ds",
                     "Dashboard comercial metricas", "Data Source",
                     {"where": "Sistema comercial"})

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_dense_only_candidate_surfaces_in_result(self) -> None:
        """Dense candidate (zero tokens with focus) appears when given high dense rank."""
        # nearest_embeddings returns dense-ds as the top hit
        hits = [NearestHit(target_id="dense-ds", score=0.95)]

        with patch.object(self.store, "nearest_embeddings", return_value=hits):
            result = suggest_connections(self.store, {
                "graph_id": self.graph_id,
                "node_id": "focus",
                "threshold": 0.35,  # lower threshold so type-affinity alone clears gate
            })

        self.assertNotIn("code", result)
        ids = [s["node_id"] for s in result["suggestions"]]
        self.assertIn("dense-ds", ids,
                      "Dense-only candidate must appear when given high dense rank")


class TestDenseAdmissionFix(unittest.TestCase):
    def setUp(self) -> None:
        self.store, self.tmp = _make_store()
        self.graph_id = "g1"

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def _add(self, node_id: str, label: str, type_: str, details: dict[str, Any]) -> None:
        _upsert_node(self.store, self.graph_id, node_id, label, type_, details)

    def _suggest_with_hits(self, hits: list[NearestHit], *, threshold: float | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"graph_id": self.graph_id, "node_id": "focus"}
        if threshold is not None:
            params["threshold"] = threshold
        with patch.object(self.store, "nearest_embeddings", return_value=hits):
            return suggest_connections(self.store, params)

    def test_strong_cosine_weak_lexical_candidate_surfaces_at_default_threshold(self) -> None:
        self._add("focus", "Revenue Forecast", "KPI", {"where": "finance dashboard monthly"})
        self._add("candidate", "Revenue Archive", "Data Source", {"where": "systems back office"})

        result = self._suggest_with_hits([NearestHit(target_id="candidate", score=0.91)])

        ids = [item["node_id"] for item in result["suggestions"]]
        self.assertIn("candidate", ids)

    def test_weak_cosine_zero_token_unmapped_candidate_does_not_appear(self) -> None:
        self._add("focus", "Revenue Forecast", "KPI", {"where": "finance dashboard monthly"})
        self._add("noise", "Legal Audit Trail", "Risk", {"where": "governance office"})

        result = self._suggest_with_hits([NearestHit(target_id="noise", score=0.12)])

        ids = [item["node_id"] for item in result["suggestions"]]
        self.assertNotIn("noise", ids)

    def test_min_dense_similarity_boundary_admits_just_above_and_drops_just_below(self) -> None:
        self._add("focus", "Revenue Forecast", "KPI", {"where": "finance dashboard monthly"})
        self._add("above", "Legal Audit Trail", "Risk", {"where": "governance office"})
        self._add("below", "Compliance Ledger", "Risk", {"where": "policy archive"})

        min_dense = getattr(similarity, "MIN_DENSE_SIMILARITY", 0.58)
        result = self._suggest_with_hits(
            [
                NearestHit(target_id="above", score=min_dense + 0.01),
                NearestHit(target_id="below", score=min_dense - 0.01),
            ]
        )

        ids = [item["node_id"] for item in result["suggestions"]]
        self.assertIn("above", ids)
        self.assertNotIn("below", ids)

    def test_dense_admitted_sparse_focus_still_gets_review_needed(self) -> None:
        self._add("focus", "Revenue Forecast", "KPI", {"where": "", "learned": "Underspecified: pending input"})
        self._add("candidate", "Revenue Archive", "Data Source", {"where": "systems back office"})

        result = self._suggest_with_hits([NearestHit(target_id="candidate", score=0.93)])

        suggestion = next((item for item in result["suggestions"] if item["node_id"] == "candidate"), None)
        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion["suggested_edge"]["label"], "review-needed")

    def test_dense_admitted_candidate_preserves_type_affinity_label(self) -> None:
        self._add("focus", "Revenue Forecast", "KPI", {"where": "finance dashboard monthly"})
        self._add("role", "Revenue Steward", "Role", {"where": "business ops"})

        result = self._suggest_with_hits([NearestHit(target_id="role", score=0.94)])

        suggestion = next((item for item in result["suggestions"] if item["node_id"] == "role"), None)
        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion["suggested_edge"], {"source": "role", "target": "focus", "label": "accountable"})

    def test_dense_ranks_and_scores_none_keep_legacy_output_byte_identical(self) -> None:
        self._add("focus", "Ventas Mensuales", "KPI", {"where": "Dashboard comercial ventas", "learned": "CRM ventas"})
        self._add("ds-crm", "CRM Salesforce ventas", "Data Source", {"where": "Salesforce cloud"})
        self._add("risk-legal", "Riesgo Regulatorio", "Risk", {"where": "Legal"})

        nodes = self.store.query_nodes(self.graph_id)
        edges = self.store.query_edges(self.graph_id)
        legacy = similarity.suggest_connections_for_node(nodes, edges, "focus")
        current = similarity.suggest_connections_for_node(
            nodes,
            edges,
            "focus",
            dense_ranks=None,
            dense_scores=None,
        )

        self.assertEqual(current, legacy)


if __name__ == "__main__":
    unittest.main()
