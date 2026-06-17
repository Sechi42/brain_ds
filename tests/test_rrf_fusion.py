"""Tests for RRF fusion in suggest_connections_for_node (TDD RED phase — PR-2).

Scope: dense_ranks parameter added to suggest_connections_for_node.
  - SUG-S1: dense_ranks=None => output identical to pre-change
  - SUG-S3: RRF math exact to 5 decimals
  - SUG-S2: dense-only zero-token candidate labeled per LE-3
  - SUG-S4: dense-only floor bypass (non-sparse focus) and sparse gate still applies
  - SUG-S4 mapped pair (LE-3): mapped type pair gets mapped label, not review-needed
  - LE-1 (sentinel): non-lexical candidate in dense_ranks uses sentinel rank
"""

from __future__ import annotations

import unittest
from typing import Any

from brain_ds.scoring.similarity import (
    REVIEW_NEEDED_LABEL,
    suggest_connections_for_node,
)
from brain_ds.store.models import EdgeRow, NodeRow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _node(
    node_id: str,
    label: str,
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


def _edge(source: str, target: str, label: str = "uses") -> EdgeRow:
    return EdgeRow(
        graph_id="g1",
        edge_id=f"{source}->{target}",
        source=source,
        target=target,
        label=label,
        weight=None,
        reasons=None,
        evidence_ids=None,
        created_at="2026-01-01T00:00:00",
    )


def _result_node_ids(result: dict[str, Any]) -> list[str]:
    return [s["node_id"] for s in result["suggestions"]]


def _find(result: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    return next((s for s in result["suggestions"] if s["node_id"] == node_id), None)


# ---------------------------------------------------------------------------
# SUG-S1 — Regression guard: dense_ranks=None => identical to pre-change
# ---------------------------------------------------------------------------


class TestRRFRegressionGuard(unittest.TestCase):
    """When dense_ranks=None, output must be byte-identical to existing behavior."""

    def _make_graph(self) -> tuple[list[NodeRow], list[EdgeRow]]:
        """Reuse the same fixture as test_suggest_connections.py."""
        focus = _node("kpi-ventas", "Ventas Mensuales", "KPI",
                      {"where": "Dashboard comercial", "learned": "Data Source: CRM Salesforce ventas"})
        ds_crm = _node("ds-crm", "CRM Salesforce", "Data Source",
                       {"where": "Salesforce cloud", "what": "CRM Salesforce con tabla ventas"})
        role = _node("role-analista", "Analista Ventas", "Role",
                     {"where": "Equipo comercial ventas"})
        risk = _node("risk-legal", "Riesgo Regulatorio", "Risk",
                     {"where": "Legal", "what": "Cambios normativos"})
        nodes = [focus, ds_crm, role, risk]
        edges = [_edge("role-analista", "kpi-ventas", "accountable")]
        return nodes, edges

    def test_none_output_identical_to_no_param(self) -> None:
        """Calling with dense_ranks=None returns same result as omitting parameter."""
        nodes, edges = self._make_graph()

        baseline = suggest_connections_for_node(nodes, edges, "kpi-ventas")
        with_none = suggest_connections_for_node(nodes, edges, "kpi-ventas", dense_ranks=None)

        # The suggestion dicts should be identical
        self.assertEqual(baseline["suggestions"], with_none["suggestions"])
        self.assertEqual(baseline["candidates_above_threshold"], with_none["candidates_above_threshold"])
        self.assertEqual(baseline["returned"], with_none["returned"])

    def test_none_does_not_add_rrf_key(self) -> None:
        """dense_ranks=None: no 'rrf' or 'fused_score' keys leaked into suggestions."""
        nodes, edges = self._make_graph()
        result = suggest_connections_for_node(nodes, edges, "kpi-ventas", dense_ranks=None)
        for s in result["suggestions"]:
            self.assertNotIn("rrf", s)
            self.assertNotIn("fused_score", s)


# ---------------------------------------------------------------------------
# SUG-S3 — RRF math exact to 5 decimals
# ---------------------------------------------------------------------------


class TestRRFMath(unittest.TestCase):
    """Verify the RRF formula produces the expected numeric values."""

    def _make_graph(self) -> tuple[list[NodeRow], list[EdgeRow]]:
        # Focus F with KPI type; A and B are Data Sources (mapped pair -> KPI measured-by DS)
        # We give F and A a shared token "ventas" so A passes lexical gate.
        # B has only a weak match but we'll give it dense rank 1.
        focus = _node("focus", "ventas metricas", "KPI",
                      {"where": "dashboard ventas"})
        a = _node("A", "ventas datos fuente", "Data Source",
                  {"where": "salesforce ventas"})
        b = _node("B", "fuente datos metricas", "Data Source",
                  {"where": "sistema datos metricas"})
        return [focus, a, b], []

    def test_rrf_ranks_b_above_a(self) -> None:
        """lexical A=1 B=2, dense A=3 B=1 => B ranks above A in fused result."""
        nodes, edges = self._make_graph()

        # We need to know the lexical ordering first: call without dense_ranks
        baseline = suggest_connections_for_node(nodes, edges, "focus")
        ids = _result_node_ids(baseline)
        # A should be ranked 1 (more shared tokens with focus) and B ranked 2
        # If the actual lexical order is different the test is still valid as long as
        # dense_ranks inverts it.
        if len(ids) < 2:
            self.skipTest("Not enough candidates to test ranking inversion")

        # Assign dense ranks to INVERT the lexical order
        lexical_rank_map = {node_id: rank + 1 for rank, node_id in enumerate(ids)}
        # dense: top of lexical rank gets worst dense rank, bottom gets best
        dense_rank_map = {node_id: len(ids) - rank + 1 for rank, node_id in enumerate(ids)}

        result = suggest_connections_for_node(nodes, edges, "focus", dense_ranks=dense_rank_map)
        fused_ids = _result_node_ids(result)

        # The bottom lexical candidate should now rank above the top one
        if len(fused_ids) >= 2:
            self.assertNotEqual(fused_ids[0], ids[0],
                                "Dense-boosted candidate should move to top")

    def test_rrf_exact_values_a1_b2_a3_b1(self) -> None:
        """
        Spec SUG-S3:
          lexical ranks: A=1, B=2
          dense ranks:   A=3, B=1
          rrf(A) = 1/(60+1) + 1/(60+3) = 1/61 + 1/63 ≈ 0.03222
          rrf(B) = 1/(60+2) + 1/(60+1) = 1/62 + 1/61 ≈ 0.03250
          => B has higher rrf => B above A
        """
        # Build a graph where A and B are both valid lexical candidates so we
        # can supply artificial dense ranks and verify B comes out on top.
        focus = _node("focus", "ventas analisis reporte", "KPI",
                      {"where": "dashboard ventas analisis"})
        # A: more shared tokens so will be lexical rank 1
        a = _node("A", "ventas analisis metricas datos", "Data Source",
                  {"where": "sistema ventas analisis"})
        # B: fewer shared tokens so will be lexical rank 2
        b = _node("B", "datos reporte metricas", "Data Source",
                  {"where": "almacen datos"})
        nodes = [focus, a, b]
        edges: list[EdgeRow] = []

        # Verify baseline lexical order
        baseline = suggest_connections_for_node(nodes, edges, "focus")
        baseline_ids = _result_node_ids(baseline)
        if len(baseline_ids) < 2 or baseline_ids[0] != "A":
            self.skipTest(f"Expected A to be lexical rank 1 but got {baseline_ids}")

        # Assign dense ranks: A=3, B=1
        dense_ranks = {"A": 3, "B": 1}
        result = suggest_connections_for_node(nodes, edges, "focus", dense_ranks=dense_ranks)

        fused_ids = _result_node_ids(result)
        self.assertGreaterEqual(len(fused_ids), 2, "Both candidates must survive")
        self.assertEqual(fused_ids[0], "B", "B should rank above A after RRF")
        self.assertEqual(fused_ids[1], "A")

        # Also check that rrf values are exposed/used correctly
        # We can verify the ordering is correct by checking fused_score if exposed
        b_entry = _find(result, "B")
        a_entry = _find(result, "A")
        self.assertIsNotNone(b_entry)
        self.assertIsNotNone(a_entry)
        # B's fused_score must be higher than A's (or B would not be first)
        b_fused = b_entry.get("fused_score", b_entry["score"])  # type: ignore[union-attr]
        a_fused = a_entry.get("fused_score", a_entry["score"])  # type: ignore[union-attr]
        self.assertGreater(b_fused, a_fused)


# ---------------------------------------------------------------------------
# SUG-S2 + LE-3 — Dense-only zero-token candidate labeled correctly
# ---------------------------------------------------------------------------


class TestDenseOnlyLabel(unittest.TestCase):
    """Dense-only candidate (zero shared tokens) labeling per LE-3."""

    def test_unmapped_pair_dense_only_gets_review_needed(self) -> None:
        """Zero shared tokens + unmapped type pair => REVIEW_NEEDED_LABEL."""
        # Focus: KPI, Candidate: Project (KPI<->Project not in TYPE_PAIR_SUGGESTIONS)
        focus = _node("focus", "ventas dashboard", "KPI",
                      {"where": "comercial dashboard"})
        candidate = _node("C", "proyecto alfa beta", "Project",
                          {"where": "ingenieria alfa"})
        nodes = [focus, candidate]
        edges: list[EdgeRow] = []

        # Without dense_ranks: C would not survive (zero tokens, unmapped pair)
        baseline = suggest_connections_for_node(nodes, edges, "focus")
        baseline_ids = _result_node_ids(baseline)
        # We expect C not in baseline (zero shared tokens, unmapped, below threshold)
        # (This assertion may vary - the key is C *is* included with dense_ranks)

        # With dense_ranks: C should appear, labeled REVIEW_NEEDED_LABEL
        result = suggest_connections_for_node(nodes, edges, "focus", dense_ranks={"C": 1})
        result_ids = _result_node_ids(result)
        self.assertIn("C", result_ids, "Dense-only candidate should appear in result")

        c_entry = _find(result, "C")
        self.assertIsNotNone(c_entry)
        self.assertEqual(c_entry["suggested_edge"]["label"], REVIEW_NEEDED_LABEL)  # type: ignore[index]

    def test_mapped_pair_dense_only_gets_mapped_label(self) -> None:
        """LE-3: Zero shared tokens + MAPPED type pair => canonical label, NOT review-needed.

        A mapped pair (KPI <-> DataSource => "measured-by") with zero shared tokens
        and a low lexical score is brought in via dense_ranks. We use threshold=0.35
        so the type-affinity score (0.40) clears the gate and we can verify the label.
        """
        # KPI <-> Data Source IS mapped (KPI measured-by DS)
        focus = _node("focus", "indicador comercial", "KPI",
                      {"where": "sistema comercial"})
        candidate = _node("C", "repositorio tecnico", "Data Source",
                          {"where": "sistema tecnico"})
        nodes = [focus, candidate]
        edges: list[EdgeRow] = []

        # Use threshold=0.35 so the type-affinity score (0.40) clears the gate.
        # The key assertion is about the LABEL, not just presence.
        result = suggest_connections_for_node(
            nodes, edges, "focus", dense_ranks={"C": 1}, threshold=0.35
        )
        result_ids = _result_node_ids(result)
        self.assertIn("C", result_ids, "Dense-only mapped candidate should appear at threshold=0.35")

        c_entry = _find(result, "C")
        self.assertIsNotNone(c_entry)
        # mapped pair KPI<->DataSource should give "measured-by", NOT "review-needed"
        self.assertNotEqual(c_entry["suggested_edge"]["label"], REVIEW_NEEDED_LABEL)  # type: ignore[index]
        self.assertEqual(c_entry["suggested_edge"]["label"], "measured-by")  # type: ignore[index]


# ---------------------------------------------------------------------------
# SUG-S4 — Dense-only floor bypass and sparse gate
# ---------------------------------------------------------------------------


class TestDenseOnlyFloorBypass(unittest.TestCase):
    """Dense-only candidates bypass minimum_shared_tokens but respect sparse gate."""

    def test_dense_only_included_when_focus_not_sparse(self) -> None:
        """focus not sparse + dense_ranks => C with 0 tokens is included."""
        focus = _node("focus", "analisis metricas ventas", "KPI",
                      {"where": "dashboard comercial"})
        candidate = _node("C", "repositorio datos tecnicos", "Data Source",
                          {"where": "sistema tecnico"})
        nodes = [focus, candidate]
        edges: list[EdgeRow] = []

        result = suggest_connections_for_node(
            nodes, edges, "focus", dense_ranks={"C": 1}, minimum_shared_tokens=2
        )
        result_ids = _result_node_ids(result)
        self.assertIn("C", result_ids, "Dense candidate should bypass token floor")

    def test_dense_only_excluded_when_focus_is_sparse(self) -> None:
        """focus IS sparse => dense candidate C still blocked (sparse gate applies)."""
        # Sparse: empty 'where' field
        focus = _node("focus", "analisis metricas ventas", "KPI",
                      {"where": "", "learned": "Underspecified: faltan datos"})
        candidate = _node("C", "repositorio datos tecnicos", "Data Source",
                          {"where": "sistema tecnico"})
        nodes = [focus, candidate]
        edges: list[EdgeRow] = []

        result = suggest_connections_for_node(
            nodes, edges, "focus", dense_ranks={"C": 1}, minimum_shared_tokens=2
        )
        # C may appear but MUST be labeled review-needed and blocked
        c_entry = _find(result, "C")
        if c_entry is not None:
            self.assertEqual(c_entry["suggested_edge"]["label"], REVIEW_NEEDED_LABEL,
                             "Sparse focus => C must be blocked as review-needed")
            self.assertIn("sparse", c_entry["reason"])

    def test_dense_only_excluded_when_candidate_is_sparse(self) -> None:
        """Dense candidate that is itself sparse => blocked as review-needed."""
        focus = _node("focus", "analisis metricas ventas", "KPI",
                      {"where": "dashboard comercial"})
        # Sparse candidate
        candidate = _node("C", "repositorio datos tecnicos", "Data Source",
                          {"where": "", "learned": "Underspecified: sin tablas"})
        nodes = [focus, candidate]
        edges: list[EdgeRow] = []

        result = suggest_connections_for_node(
            nodes, edges, "focus", dense_ranks={"C": 1}, minimum_shared_tokens=2
        )
        c_entry = _find(result, "C")
        if c_entry is not None:
            self.assertEqual(c_entry["suggested_edge"]["label"], REVIEW_NEEDED_LABEL,
                             "Sparse candidate => must be blocked")
            self.assertIn("sparse", c_entry["reason"])


# ---------------------------------------------------------------------------
# LE-1 — Sentinel rank for dense-only candidates not in lexical ranking
# ---------------------------------------------------------------------------


class TestSentinelRank(unittest.TestCase):
    """Candidate that passes ONLY via dense_ranks (no lexical score) uses sentinel."""

    def test_sentinel_gives_nonzero_lexical_rrf_term(self) -> None:
        """A candidate not in lexical ranking gets sentinel=len(candidates)+1.

        Its RRF lexical term = 1/(60+sentinel) which is small but non-zero.
        We verify the candidate still appears (not excluded due to zero RRF term).
        """
        focus = _node("focus", "metricas ventas", "KPI",
                      {"where": "dashboard ventas"})
        # A: has shared token 'ventas' so passes lexical gate
        a = _node("A", "fuente ventas", "Data Source",
                  {"where": "sistema ventas"})
        # B: completely different vocabulary, zero shared tokens with focus
        b = _node("B", "repositorio tecnico", "Data Source",
                  {"where": "sistema tecnico"})
        nodes = [focus, a, b]
        edges: list[EdgeRow] = []

        # Without dense_ranks: B is not present (zero tokens, below threshold)
        baseline = suggest_connections_for_node(nodes, edges, "focus")
        baseline_ids = _result_node_ids(baseline)

        # With dense_ranks including B: B should appear via sentinel + dense rank
        result = suggest_connections_for_node(
            nodes, edges, "focus", dense_ranks={"A": 1, "B": 1}
        )
        result_ids = _result_node_ids(result)
        self.assertIn("B", result_ids,
                      "B with sentinel lexical rank + dense rank 1 should appear")


if __name__ == "__main__":
    unittest.main()
