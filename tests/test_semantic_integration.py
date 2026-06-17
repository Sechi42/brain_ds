"""Real-model semantic integration test (T10 — PR-3 / semantic-connections-slice1).

Uses ``pytest.importorskip("fastembed")`` so the test is SKIPPED cleanly when
fastembed is absent from the environment.  It is NEVER a failure when absent —
fastembed is an optional dependency.

Scenario SUG-S2 (full stack):
  - Seed two nodes with ZERO shared tokens but semantically close meanings:
      "rotación de personal" (employee turnover)
      "abandono de empleados" (employee attrition)
  - Use the real get_default_model() (requires fastembed installed).
  - Call tools.suggest_connections for each node.
  - Assert each node appears in the other's suggestion list.

Threshold note (from PR-2 design risk):
  Dense-only candidates with type affinity score=0.40 sit below the default
  threshold=0.55.  We use threshold=0.30 here so the dense candidate surfaces.
  This is correct per spec: "threshold applied to `score` not `fused_score`"
  and the integration test may use a lower threshold to expose the semantic hit.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

fastembed = pytest.importorskip("fastembed", reason="fastembed not installed — T10 skipped", exc_type=ImportError)

from brain_ds.mcp.tools import create_graph, search_graph, suggest_connections, update_node
from brain_ds.scoring.embedder import get_default_model
from brain_ds.store.graph_store import GraphStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_integration_store(tmp_dir: str) -> GraphStore:
    return GraphStore(str(Path(tmp_dir) / "store.db"))


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


class TestSemanticIntegration:
    """Real-model end-to-end: semantically close nodes surface in suggestions."""

    def test_semantically_close_nodes_suggest_each_other(self, tmp_path: Path) -> None:
        """SUG-S2 full stack: 'rotación de personal' vs 'abandono de empleados'."""
        store = _make_integration_store(str(tmp_path))

        create_graph(store, {"graph_id": "int-g1", "name": "Integration Graph", "project": "test"})

        # Node A: "workforce churn" — Process node, unique tokens
        # Node B: "talent exodus" — Solution node, zero token overlap with A
        # These are semantically close (both = people leaving an organization)
        # but share ZERO lexical tokens, so they only connect via dense/semantic path.
        update_node(
            store,
            {
                "graph_id": "int-g1",
                "node_id": "node-churn",
                "label": "workforce churn",
                "type": "Process",
                "details": {"context": "employees leaving the company unexpectedly"},
            },
        )

        update_node(
            store,
            {
                "graph_id": "int-g1",
                "node_id": "node-exodus",
                "label": "talent exodus",
                "type": "Solution",
                "details": {"context": "departure of skilled staff from the organization"},
            },
        )

        # Verify embeddings were written by the producer hook
        row_churn = store.embedding_repo.conn.execute(
            "SELECT model FROM embeddings WHERE target_id='node-churn' LIMIT 1"
        ).fetchone()
        row_exodus = store.embedding_repo.conn.execute(
            "SELECT model FROM embeddings WHERE target_id='node-exodus' LIMIT 1"
        ).fetchone()
        assert row_churn is not None, "embedding for node-churn should have been written by producer hook"
        assert row_exodus is not None, "embedding for node-exodus should have been written by producer hook"

        model_name = row_churn[0]
        assert store.embedding_repo.has_embedding("int-g1", "node", "node-churn", model_name)
        assert store.embedding_repo.has_embedding("int-g1", "node", "node-exodus", model_name)

        # suggest_connections for A — B should appear via semantic (dense-only) path
        # threshold=0.30 is generous enough to surface the dense-only candidate
        # (lexical score for unmapped pair with 0 shared tokens = ~0.14, bypassed by is_dense_only)
        result_a = suggest_connections(
            store,
            {
                "graph_id": "int-g1",
                "node_id": "node-churn",
                "limit": 10,
                "threshold": 0.30,
            },
        )
        suggestion_ids_a = [s.get("node_id") for s in result_a.get("suggestions", [])]
        assert "node-exodus" in suggestion_ids_a, (
            f"'talent exodus' (node-exodus) should appear in suggestions for 'workforce churn', "
            f"got: {result_a.get('suggestions', [])}"
        )

        # suggest_connections for B — A should appear
        result_b = suggest_connections(
            store,
            {
                "graph_id": "int-g1",
                "node_id": "node-exodus",
                "limit": 10,
                "threshold": 0.30,
            },
        )
        suggestion_ids_b = [s.get("node_id") for s in result_b.get("suggestions", [])]
        assert "node-churn" in suggestion_ids_b, (
            f"'workforce churn' (node-churn) should appear in suggestions for 'talent exodus', "
            f"got: {result_b.get('suggestions', [])}"
        )

        # Print evidence for the user (real model output)
        print(f"\n[T10 REAL MODEL] model={model_name}")
        print(f"[T10 REAL MODEL] Suggestions for 'workforce churn': {result_a.get('suggestions', [])}")
        print(f"[T10 REAL MODEL] Suggestions for 'talent exodus': {result_b.get('suggestions', [])}")

    def test_hybrid_search_recalls_semantic_hit_with_real_embeddings(self, tmp_path: Path) -> None:
        """PR-2 hybrid search proof: dense recall surfaces when lexical search is empty."""
        model = get_default_model()
        if model is None:
            pytest.skip("Embedding model unavailable — hybrid recall proof skipped")

        store = _make_integration_store(str(tmp_path))
        create_graph(store, {"graph_id": "int-g2", "name": "Integration Graph 2", "project": "test"})

        update_node(
            store,
            {
                "graph_id": "int-g2",
                "node_id": "node-churn",
                "label": "workforce churn",
                "type": "Process",
                "details": {"context": "employees leaving the company unexpectedly"},
            },
        )
        update_node(
            store,
            {
                "graph_id": "int-g2",
                "node_id": "node-exodus",
                "label": "talent exodus",
                "type": "Solution",
                "details": {"context": "departure of skilled staff from the organization"},
            },
        )

        result = search_graph(
            store,
            {
                "graph_id": "int-g2",
                "query": "employee attrition",
            },
        )

        assert isinstance(result, list)
        result_ids = [row["id"] for row in result]
        assert result_ids, f"Expected semantic recall, got: {result}"
        assert "node-churn" in result_ids or "node-exodus" in result_ids, (
            f"Expected a semantic hit for employee attrition, got: {result}"
        )

        print(f"\n[PR2 REAL MODEL] hybrid search results for 'employee attrition': {result}")
