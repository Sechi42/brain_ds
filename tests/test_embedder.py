"""Tests for brain_ds/scoring/embedder.py (TDD RED phase — PR-1 / Foundation).

Scope: EmbeddingModel protocol, FastEmbedModel lazy singleton (via
get_default_model monkeypatch), node_text, node_text_tokens refactor,
embed_graph_nodes backfill helper.

OUT OF SCOPE HERE (PR-2 / T7):
  - tools.update_node calling upsert_embedding (tests in test_suggest_connections_dense.py)

PR-2 deferred items are noted with # PR-2 comments.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from brain_ds.scoring.embedder import (
    EmbeddingModel,
    get_default_model,
    embed_graph_nodes,
    node_text,
)
from brain_ds.scoring.factors import _tokens
from brain_ds.scoring.similarity import node_text_tokens
from brain_ds.store.models import NodeRow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_node(
    node_id: str,
    label: str = "Test Node",
    type_: str = "Role",
    details: dict | None = None,
) -> NodeRow:
    return NodeRow(
        graph_id="g1",
        id=node_id,
        label=label,
        type=type_,
        supertype=None,
        details=details or {"where": "somewhere"},
        card_sections=None,
        editable_fields=None,
        evidence_ids=None,
        layout_hint=None,
        parent_id=None,
        depth=0,
        created_at="2026-01-01T00:00:00",
        modified_at="2026-01-01T00:00:00",
    )


class FakeEmbeddingModel:
    """Deterministic fake that satisfies EmbeddingModel protocol."""

    _instance_count = 0

    def __init__(self) -> None:
        FakeEmbeddingModel._instance_count += 1
        self._name = "fake-test"

    @property
    def name(self) -> str:
        return self._name

    def embed(self, text: str) -> list[float]:
        # Return a deterministic 3-dim vector based on text length.
        n = len(text) % 10 + 1
        return [float(n), 0.0, 0.0]


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------

class TestEmbeddingModelProtocol(unittest.TestCase):
    """FakeEmbeddingModel must satisfy the EmbeddingModel Protocol."""

    def test_fake_satisfies_protocol(self) -> None:
        fake = FakeEmbeddingModel()
        # EmbeddingModel is a Protocol — isinstance check works at runtime
        # if runtime_checkable; otherwise, duck-type check via hasattr.
        self.assertTrue(hasattr(fake, "name"))
        self.assertTrue(hasattr(fake, "embed"))
        self.assertIsInstance(fake.name, str)
        result = fake.embed("hello world")
        self.assertIsInstance(result, list)
        self.assertTrue(all(isinstance(v, float) for v in result))

    def test_fake_name_property_returns_string(self) -> None:
        fake = FakeEmbeddingModel()
        self.assertEqual(fake.name, "fake-test")

    def test_fake_embed_returns_nonempty_list_of_floats(self) -> None:
        fake = FakeEmbeddingModel()
        vec = fake.embed("rotación de personal")
        self.assertGreater(len(vec), 0)
        self.assertIsInstance(vec[0], float)


# ---------------------------------------------------------------------------
# get_default_model — None path (graceful degradation)
# ---------------------------------------------------------------------------

class TestGetDefaultModelNone(unittest.TestCase):
    """When get_default_model is patched to return None, callers must handle it."""

    def test_get_default_model_returns_none_when_patched(self) -> None:
        with patch("brain_ds.scoring.embedder.get_default_model", return_value=None):
            from brain_ds.scoring import embedder
            result = embedder.get_default_model()
        self.assertIsNone(result)

    def test_get_default_model_signature(self) -> None:
        # The function must exist and be callable with no args.
        result = get_default_model()
        # When fastembed is not installed this MUST be None (graceful degradation).
        # When installed it returns an EmbeddingModel — both are valid here.
        self.assertTrue(result is None or hasattr(result, "embed"))


# ---------------------------------------------------------------------------
# Lazy singleton — instantiated exactly once across N calls
# ---------------------------------------------------------------------------

class TestLazySingleton(unittest.TestCase):
    """get_default_model() must instantiate the underlying model at most once."""

    def test_singleton_instantiates_once(self) -> None:
        import brain_ds.scoring.embedder as embedder_mod

        FakeEmbeddingModel._instance_count = 0
        fake_instance = FakeEmbeddingModel()
        FakeEmbeddingModel._instance_count = 0  # reset after setup construction

        # Patch _INSTANCE and the factory so we can count constructions.
        call_count = {"n": 0}

        def _fake_factory() -> FakeEmbeddingModel:
            call_count["n"] += 1
            return fake_instance

        # Reset the module singleton so we start fresh.
        original_instance = embedder_mod._INSTANCE
        embedder_mod._INSTANCE = None

        with patch.object(embedder_mod, "_build_model", side_effect=_fake_factory):
            for _ in range(5):
                model = embedder_mod.get_default_model()

        embedder_mod._INSTANCE = original_instance  # restore

        # _build_model must have been called exactly once.
        self.assertEqual(call_count["n"], 1)
        self.assertIs(model, fake_instance)


# ---------------------------------------------------------------------------
# node_text
# ---------------------------------------------------------------------------

class TestNodeText(unittest.TestCase):
    """node_text(node) must return a non-empty string for a grounded node."""

    def test_node_text_nonempty(self) -> None:
        node = _make_node(
            "n1",
            label="rotación de personal",
            type_="Role",
            details={"where": "HR department", "learned": "High turnover"},
        )
        text = node_text(node)
        self.assertIsInstance(text, str)
        self.assertGreater(len(text.strip()), 0)

    def test_node_text_contains_label_and_type(self) -> None:
        node = _make_node(
            "n2",
            label="CRM Salesforce",
            type_="Data Source",
            details={"where": "Salesforce cloud"},
        )
        text = node_text(node)
        self.assertIn("CRM Salesforce", text)
        self.assertIn("Data Source", text)


# ---------------------------------------------------------------------------
# node_text_tokens refactor: must equal _tokens(node_text(node))
# ---------------------------------------------------------------------------

class TestNodeTextTokensRefactor(unittest.TestCase):
    """node_text_tokens must return exactly _tokens(node_text(node)) — no behavior change."""

    def _check(self, node: NodeRow) -> None:
        expected = _tokens(node_text(node))
        actual = node_text_tokens(node)
        self.assertEqual(
            actual,
            expected,
            f"node_text_tokens diverged from _tokens(node_text(node)) for node {node.id}",
        )

    def test_basic_node(self) -> None:
        self._check(_make_node("n1", label="Ventas Mensuales", type_="KPI"))

    def test_node_with_details(self) -> None:
        self._check(
            _make_node(
                "n2",
                label="CRM Salesforce",
                type_="Data Source",
                details={"where": "Salesforce cloud", "what": "CRM con tabla ventas"},
            )
        )

    def test_node_with_no_details(self) -> None:
        node = _make_node("n3", label="Solo Label", type_="Role", details={})
        self._check(node)

    def test_node_with_low_signal_details(self) -> None:
        node = _make_node("n4", label="Label", type_="KPI", details={"where": "n/a"})
        self._check(node)


# ---------------------------------------------------------------------------
# embed_graph_nodes — backfill
# ---------------------------------------------------------------------------

class TestEmbedGraphNodes(unittest.TestCase):
    """Unit tests for the backfill helper using a fake store."""

    def _make_store(
        self,
        nodes: list[NodeRow],
        existing_embeddings: set[tuple[str, str]] | None = None,
    ) -> Any:
        """Build a minimal mock store for embed_graph_nodes."""
        store = MagicMock()
        store.query_nodes.return_value = nodes

        _existing = existing_embeddings or set()

        def _has_embedding(graph_id: str, target_type: str, target_id: str, model: str) -> bool:
            return (target_id, model) in _existing

        store.embedding_repo.has_embedding.side_effect = _has_embedding

        return store

    def test_backfill_skips_already_embedded(self) -> None:
        """EMB-S3: n1 already has embedding; only n2 and n3 are embedded."""
        nodes = [
            _make_node("n1", label="Node One", type_="Role"),
            _make_node("n2", label="Node Two", type_="KPI"),
            _make_node("n3", label="Node Three", type_="Data Source"),
        ]
        store = self._make_store(nodes, existing_embeddings={("n1", "fake-test")})
        model = FakeEmbeddingModel()

        result = embed_graph_nodes(store, "g1", model)

        # upsert_embedding must have been called for n2 and n3 only.
        called_ids = {call.args[2] for call in store.upsert_embedding.call_args_list}
        self.assertIn("n2", called_ids)
        self.assertIn("n3", called_ids)
        self.assertNotIn("n1", called_ids)
        self.assertEqual(result["embedded"], 2)
        self.assertEqual(result["skipped"], 1)
        self.assertFalse(result["dry_run"])

    def test_backfill_dry_run_no_writes(self) -> None:
        """EMB-S4: dry_run=True → 0 writes, returns count=2."""
        nodes = [
            _make_node("n1", label="Node One", type_="Role"),
            _make_node("n2", label="Node Two", type_="KPI"),
        ]
        store = self._make_store(nodes)
        model = FakeEmbeddingModel()

        result = embed_graph_nodes(store, "g1", model, dry_run=True)

        store.upsert_embedding.assert_not_called()
        self.assertEqual(result["embedded"], 0)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result.get("would_embed"), 2)
        self.assertTrue(result["dry_run"])

    def test_backfill_idempotent_all_embedded(self) -> None:
        """All nodes already embedded → embedded=0, skipped=3."""
        nodes = [
            _make_node("n1", label="A", type_="Role"),
            _make_node("n2", label="B", type_="Role"),
            _make_node("n3", label="C", type_="Role"),
        ]
        store = self._make_store(
            nodes,
            existing_embeddings={("n1", "fake-test"), ("n2", "fake-test"), ("n3", "fake-test")},
        )
        model = FakeEmbeddingModel()

        result = embed_graph_nodes(store, "g1", model)

        store.upsert_embedding.assert_not_called()
        self.assertEqual(result["embedded"], 0)
        self.assertEqual(result["skipped"], 3)


if __name__ == "__main__":
    unittest.main()
