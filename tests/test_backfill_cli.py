"""Tests for the embed-backfill CLI subcommand (TDD RED phase — PR-3 / T8).

Scope: CLI dispatch, exit codes, summary output, idempotency via embed_graph_nodes.
These tests use a FakeEmbeddingModel via monkeypatch — fastembed is NOT required.

Scenarios:
  CLI-S1  happy path exits 0 and prints summary
  CLI-S2  --dry-run: writes 0 rows, prints dry-run summary
  CLI-S3  missing / unknown graph-id exits non-zero
  CLI-S4  idempotency: second call has embedded=0, skipped=N
  CLI-S5  model absent (get_default_model returns None) exits 1 with warning
"""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from brain_ds.store.graph_store import GraphStore
from brain_ds.ui import cli


# ---------------------------------------------------------------------------
# Fake embedding model — NO fastembed required
# ---------------------------------------------------------------------------

class _FakeModel:
    """Deterministic fake: returns a fixed 4-dim vector for any text."""

    name = "fake-test-v1"

    def embed(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3, 0.4]


# ---------------------------------------------------------------------------
# Helper — build a temp store with a graph and a few nodes
# ---------------------------------------------------------------------------

def _make_store_with_graph(tmp_dir: str, graph_id: str = "test-graph", n_nodes: int = 3) -> GraphStore:
    store = GraphStore(str(Path(tmp_dir) / "store.db"))
    from brain_ds.mcp.tools import create_graph, update_node
    create_graph(store, {"graph_id": graph_id, "name": "Test Graph", "project": "test"})
    for i in range(n_nodes):
        update_node(
            store,
            {
                "graph_id": graph_id,
                "node_id": f"node-{i}",
                "label": f"Node {i}",
                "type": "Role",
                "details": {"desc": f"description {i}"},
            },
        )
    return store


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBackfillCLI(unittest.TestCase):
    """CLI-S1 through CLI-S4: normal dispatch with FakeEmbeddingModel."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._store = _make_store_with_graph(self._tmpdir, graph_id="g1", n_nodes=3)

    # CLI-S1 — happy path exits 0 and prints summary
    def test_happy_path_exits_0_and_prints_summary(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch("brain_ds.ui.cli._resolve_backfill_store", return_value=self._store),
            patch("brain_ds.scoring.embedder.get_default_model", return_value=_FakeModel()),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            code = cli.main(["embed-backfill", "--graph-id", "g1", "--project-root", self._tmpdir])

        self.assertEqual(code, 0, msg=f"stderr: {stderr.getvalue()}")
        out = stdout.getvalue()
        # Summary must mention how many were embedded
        self.assertIn("embedded", out.lower())

    # CLI-S2 — --dry-run writes 0 rows, prints dry-run info
    def test_dry_run_writes_zero_rows(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch("brain_ds.ui.cli._resolve_backfill_store", return_value=self._store),
            patch("brain_ds.scoring.embedder.get_default_model", return_value=_FakeModel()),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            code = cli.main(["embed-backfill", "--graph-id", "g1", "--project-root", self._tmpdir, "--dry-run"])

        self.assertEqual(code, 0, msg=f"stderr: {stderr.getvalue()}")
        # Dry-run must NOT have written any embeddings (check each node individually)
        for i in range(3):
            has = self._store.embedding_repo.has_embedding("g1", "node", f"node-{i}", _FakeModel.name)
            self.assertFalse(has, f"dry-run must not write embedding for node-{i}")
        out = stdout.getvalue()
        # Output should mention dry-run or would-embed
        self.assertTrue(
            "dry" in out.lower() or "would" in out.lower(),
            f"dry-run output should mention dry or would: {out!r}",
        )

    # CLI-S3 — missing graph exits non-zero
    def test_missing_graph_exits_nonzero(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch("brain_ds.ui.cli._resolve_backfill_store", return_value=self._store),
            patch("brain_ds.scoring.embedder.get_default_model", return_value=_FakeModel()),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            code = cli.main(["embed-backfill", "--graph-id", "DOES-NOT-EXIST", "--project-root", self._tmpdir])

        self.assertNotEqual(code, 0, "non-existent graph-id should exit non-zero")

    # CLI-S4 — idempotency: second call skips all, embedded=0
    def test_idempotency_second_call_skips_all(self):
        stdout1 = io.StringIO()
        stdout2 = io.StringIO()
        stderr = io.StringIO()

        with (
            patch("brain_ds.ui.cli._resolve_backfill_store", return_value=self._store),
            patch("brain_ds.scoring.embedder.get_default_model", return_value=_FakeModel()),
            redirect_stdout(stdout1),
            redirect_stderr(stderr),
        ):
            code1 = cli.main(["embed-backfill", "--graph-id", "g1", "--project-root", self._tmpdir])

        self.assertEqual(code1, 0)

        with (
            patch("brain_ds.ui.cli._resolve_backfill_store", return_value=self._store),
            patch("brain_ds.scoring.embedder.get_default_model", return_value=_FakeModel()),
            redirect_stdout(stdout2),
            redirect_stderr(stderr),
        ):
            code2 = cli.main(["embed-backfill", "--graph-id", "g1", "--project-root", self._tmpdir])

        self.assertEqual(code2, 0)
        out2 = stdout2.getvalue()
        # Second run: embedded=0 (all skipped)
        self.assertIn("0", out2, f"second run should show 0 embedded; got: {out2!r}")


class TestBackfillCLINoModel(unittest.TestCase):
    """CLI-S5: get_default_model() returns None => exit 1 with warning."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._store = _make_store_with_graph(self._tmpdir, graph_id="g2", n_nodes=2)

    def test_no_model_exits_1_with_warning(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch("brain_ds.ui.cli._resolve_backfill_store", return_value=self._store),
            patch("brain_ds.scoring.embedder.get_default_model", return_value=None),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            code = cli.main(["embed-backfill", "--graph-id", "g2", "--project-root", self._tmpdir])

        self.assertEqual(code, 1, "absent model should exit 1")
        combined = stdout.getvalue() + stderr.getvalue()
        self.assertTrue(
            "fastembed" in combined.lower() or "not installed" in combined.lower() or "warning" in combined.lower(),
            f"should warn about missing model; got: {combined!r}",
        )
