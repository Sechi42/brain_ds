"""Tests for brain_ds.verify.semantic_verify.

Strict TDD: every test was written before the corresponding implementation.
Deterministic tests (no LLM) run in the standard `uv run pytest` suite.
LLM-gated tests require RUN_LIVE_LLM env var and a real injected JudgeModel.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from brain_ds.store.graph_store import GraphStore


# ---------------------------------------------------------------------------
# T-01: Data model scaffolding
# ---------------------------------------------------------------------------

class TestDataModelFields(unittest.TestCase):
    """T-01: Verify all dataclasses exist and have the required fields."""

    def test_data_model_fields_present(self) -> None:
        from brain_ds.verify.semantic_verify import (
            ReferenceFinding,
            FaithfulnessResult,
            CoherenceResult,
            SemanticFinding,
            SemanticReport,
            FAITHFULNESS_WARN_THRESHOLD,
            COHERENCE_MIN_SCORE,
            NEEDS_DATA_SUGGEST_DENSITY,
            SUPPORTED_DOCUMENTATION_LANGUAGES,
        )

        # ReferenceFinding
        rf = ReferenceFinding(
            raw_text="Entity A",
            matched_node_id="n-1",
            matched_label="Entity A",
            via="wikilink",
            resolved=True,
        )
        self.assertEqual(rf.raw_text, "Entity A")
        self.assertEqual(rf.matched_node_id, "n-1")
        self.assertEqual(rf.matched_label, "Entity A")
        self.assertEqual(rf.via, "wikilink")
        self.assertTrue(rf.resolved)

        # FaithfulnessResult
        fr = FaithfulnessResult(
            graph_id="g-1",
            total_references=0,
            resolved_references=0,
            ratio=1.0,
            references=(),
            wikilink_coverage=1.0,
            needs_data_density=0.0,
        )
        self.assertEqual(fr.graph_id, "g-1")
        self.assertEqual(fr.ratio, 1.0)
        self.assertIsInstance(fr.references, tuple)

        # CoherenceResult
        cr = CoherenceResult(
            ran=False,
            language="es",
            section_scores=(),
            consistency_pass=None,
            rationales=(),
        )
        self.assertFalse(cr.ran)
        self.assertIsNone(cr.consistency_pass)

        # SemanticFinding
        sf = SemanticFinding(
            severity="CRITICAL",
            dimension="faithfulness",
            message="Ghost entity not resolved",
            locator="Ghost Corp",
        )
        self.assertEqual(sf.severity, "CRITICAL")
        self.assertEqual(sf.dimension, "faithfulness")

        # SemanticReport
        report = SemanticReport(
            graph_id="g-1",
            faithfulness=fr,
            coherence=cr,
            findings=(),
        )
        self.assertEqual(report.graph_id, "g-1")
        self.assertIsInstance(report.findings, tuple)

        # Module-level constants
        self.assertEqual(FAITHFULNESS_WARN_THRESHOLD, 0.85)
        self.assertEqual(COHERENCE_MIN_SCORE, 3)
        self.assertEqual(NEEDS_DATA_SUGGEST_DENSITY, 0.30)
        self.assertIn("en", SUPPORTED_DOCUMENTATION_LANGUAGES)
        self.assertIn("es", SUPPORTED_DOCUMENTATION_LANGUAGES)


# ---------------------------------------------------------------------------
# T-02: _normalize_label parity guard
# ---------------------------------------------------------------------------

class TestNormalizeLabelParity(unittest.TestCase):
    """T-02: _normalize_label must stay byte-identical to the FTS normalization path.

    This is NOT an EntityType-based guard. The faithfulness extractor uses node
    labels (built dynamically from query_nodes), so a new EntityType does NOT
    cause scorer drift. The real drift risk is label normalization diverging from
    what search_nodes_fts would find — that is what this test guards against.

    The FTS contract (graph_store.py:313-314): NFD normalize, strip Mn-category
    chars, lowercase. After that, tokens are split on whitespace. We replicate
    this contract via _fold_accents (NFKD + combining-char strip) + lower() +
    whitespace collapse, which must produce the same output for the labels we care
    about.
    """

    def test_normalize_label_parity_with_fts(self) -> None:
        from brain_ds.verify.semantic_verify import _normalize_label
        from brain_ds.scoring.factors import _fold_accents

        test_cases = [
            "Empresa Logística",
            "PROVEEDOR",
            "  Área de Ventas  ",
            "Sistema ERP",
            "DataGhost",
            "Área Técnica",
            "Información General",
        ]

        for s in test_cases:
            expected = " ".join(_fold_accents(s).lower().split())
            actual = _normalize_label(s)
            self.assertEqual(
                actual,
                expected,
                msg=f"_normalize_label({s!r}) = {actual!r}, expected {expected!r}",
            )


# ---------------------------------------------------------------------------
# Shared fixture helper
# ---------------------------------------------------------------------------

def _make_store(tmp_path: Path) -> tuple[GraphStore, str]:
    """Create a GraphStore in tmp_path with a test graph. Returns (store, graph_id)."""
    db_path = str(tmp_path / "store.db")
    store = GraphStore(db_path)
    graph_id = "test-graph"
    store.create_graph(graph_id, name="Test Graph", workspace_root=str(tmp_path), workspace_path=str(tmp_path))
    return store, graph_id


def _add_node(store: GraphStore, graph_id: str, node_id: str, label: str) -> None:
    store.upsert_node(graph_id, {"id": node_id, "label": label, "type": "Unknown"})


# ---------------------------------------------------------------------------
# T-03: score_graph_faithfulness — wikilink-only path
# ---------------------------------------------------------------------------

class TestFaithfulnessWikilinkPath(unittest.TestCase):
    """T-03: Pass A — wikilink extraction and resolution."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.store, self.graph_id = _make_store(self.tmp_path)
        _add_node(self.store, self.graph_id, "n-1", "Entity A")
        _add_node(self.store, self.graph_id, "n-2", "Entity B")
        _add_node(self.store, self.graph_id, "n-3", "Entity C")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_faithfulness_all_wikilinks_resolve(self) -> None:
        from brain_ds.verify.semantic_verify import score_graph_faithfulness

        brd = "The BRD covers [[Entity A]], [[Entity B]], and [[Entity C]]."
        result = score_graph_faithfulness(brd, self.graph_id, self.store)

        self.assertAlmostEqual(result.ratio, 1.0)
        self.assertEqual(result.total_references, 3)
        self.assertEqual(result.resolved_references, 3)
        for ref in result.references:
            self.assertTrue(ref.resolved, msg=f"{ref.raw_text!r} not resolved")

    def test_faithfulness_one_hallucinated(self) -> None:
        from brain_ds.verify.semantic_verify import score_graph_faithfulness

        brd = "See [[Entity A]] and [[Ghost Entity]] for details."
        result = score_graph_faithfulness(brd, self.graph_id, self.store)

        self.assertAlmostEqual(result.ratio, 0.5)
        ghost = next(r for r in result.references if r.raw_text == "Ghost Entity")
        self.assertFalse(ghost.resolved)
        self.assertIsNone(ghost.matched_node_id)

    def test_faithfulness_zero_references(self) -> None:
        from brain_ds.verify.semantic_verify import score_graph_faithfulness

        brd = "This document has no entity references."
        result = score_graph_faithfulness(brd, self.graph_id, self.store)

        self.assertAlmostEqual(result.ratio, 1.0)
        self.assertEqual(result.references, ())


# ---------------------------------------------------------------------------
# T-04: score_graph_faithfulness — sub-metrics and Pass B
# ---------------------------------------------------------------------------

class TestFaithfulnessSubMetrics(unittest.TestCase):
    """T-04: Pass B — plain-text label matching; wikilink_coverage; needs_data_density."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.store, self.graph_id = _make_store(self.tmp_path)
        _add_node(self.store, self.graph_id, "n-1", "Entity A")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_wikilink_coverage_unwikilinked_mention(self) -> None:
        from brain_ds.verify.semantic_verify import score_graph_faithfulness

        # "Entity A" appears as plain text, not wikilinked
        brd = "The BRD covers Entity A in detail."
        result = score_graph_faithfulness(brd, self.graph_id, self.store)

        self.assertLess(result.wikilink_coverage, 1.0)

    def test_needs_data_density(self) -> None:
        from brain_ds.verify.semantic_verify import score_graph_faithfulness

        # Build a BRD with 3 sections and 10 [NEEDS DATA] markers
        brd = (
            "## Section One\n"
            + " ".join(["word"] * 50)
            + " [NEEDS DATA] [NEEDS DATA] [NEEDS DATA]\n"
            "## Section Two\n"
            + " ".join(["word"] * 50)
            + " [NEEDS DATA] [NEEDS DATA] [NEEDS DATA]\n"
            "## Section Three\n"
            + " ".join(["word"] * 50)
            + " [NEEDS DATA] [NEEDS DATA] [NEEDS DATA] [NEEDS DATA]\n"
        )
        result = score_graph_faithfulness(brd, self.graph_id, self.store)

        # density = markers / section count = 10 / 3
        self.assertAlmostEqual(result.needs_data_density, 10 / 3, places=5)


# ---------------------------------------------------------------------------
# T-05: score_brd_coherence — gating and language validation
# ---------------------------------------------------------------------------

class TestCoherenceGating(unittest.TestCase):
    """T-05: Coherence gate — skipped when RUN_LIVE_LLM unset; ValueError on bad language."""

    def test_coherence_skipped_when_no_env(self) -> None:
        from brain_ds.verify.semantic_verify import score_brd_coherence

        env_backup = os.environ.pop("RUN_LIVE_LLM", None)
        try:
            result = score_brd_coherence("Any BRD text", "g-1", language="es")
            self.assertFalse(result.ran)
        finally:
            if env_backup is not None:
                os.environ["RUN_LIVE_LLM"] = env_backup

    def test_coherence_invalid_language_raises(self) -> None:
        from brain_ds.verify.semantic_verify import score_brd_coherence

        with self.assertRaises(ValueError):
            score_brd_coherence("Any BRD text", "g-1", language="fr")


# ---------------------------------------------------------------------------
# T-06: Tiered finding classification and build_semantic_report
# ---------------------------------------------------------------------------

class TestTieringAndReport(unittest.TestCase):
    """T-06: build_semantic_report — tier mapping for all deterministic rules."""

    def _make_faithfulness(self, *, ratio=1.0, refs=(), wikilink_coverage=1.0, needs_data_density=0.0):
        from brain_ds.verify.semantic_verify import FaithfulnessResult
        return FaithfulnessResult(
            graph_id="g-1",
            total_references=len(refs),
            resolved_references=sum(1 for r in refs if r.resolved),
            ratio=ratio,
            references=tuple(refs),
            wikilink_coverage=wikilink_coverage,
            needs_data_density=needs_data_density,
        )

    def _make_coherence(self, *, ran=False, language="es", section_scores=(), consistency_pass=None, rationales=()):
        from brain_ds.verify.semantic_verify import CoherenceResult
        return CoherenceResult(
            ran=ran,
            language=language,
            section_scores=section_scores,
            consistency_pass=consistency_pass,
            rationales=rationales,
        )

    def _make_ref(self, *, raw_text, resolved, node_id=None):
        from brain_ds.verify.semantic_verify import ReferenceFinding
        return ReferenceFinding(
            raw_text=raw_text,
            matched_node_id=node_id,
            matched_label=raw_text if resolved else None,
            via="wikilink",
            resolved=resolved,
        )

    def test_tier_critical_on_unresolved_reference(self) -> None:
        from brain_ds.verify.semantic_verify import build_semantic_report

        refs = [self._make_ref(raw_text="Ghost Co.", resolved=False)]
        faith = self._make_faithfulness(ratio=0.0, refs=refs)
        coherence = self._make_coherence()
        report = build_semantic_report(faith, coherence)

        criticals = [f for f in report.findings if f.severity == "CRITICAL"]
        self.assertEqual(len(criticals), 1)
        self.assertEqual(criticals[0].dimension, "faithfulness")
        self.assertIn("Ghost Co.", criticals[0].locator)

    def test_tier_warning_low_ratio_all_resolve(self) -> None:
        from brain_ds.verify.semantic_verify import build_semantic_report

        refs = [
            self._make_ref(raw_text=f"Entity {i}", resolved=True, node_id=f"n-{i}")
            for i in range(4)
        ]
        # ratio = 0.80 < 0.85 but all resolved
        faith = self._make_faithfulness(ratio=0.80, refs=refs)
        coherence = self._make_coherence()
        report = build_semantic_report(faith, coherence)

        criticals = [f for f in report.findings if f.severity == "CRITICAL"]
        warnings = [f for f in report.findings if f.severity == "WARNING"]
        self.assertEqual(len(criticals), 0)
        self.assertGreaterEqual(len(warnings), 1)

    def test_tier_suggestion_unwikilinked(self) -> None:
        from brain_ds.verify.semantic_verify import build_semantic_report

        faith = self._make_faithfulness(wikilink_coverage=0.5)
        coherence = self._make_coherence()
        report = build_semantic_report(faith, coherence)

        suggestions = [f for f in report.findings if f.severity == "SUGGESTION"]
        self.assertGreaterEqual(len(suggestions), 1)

    def test_tier_suggestion_needs_data_density(self) -> None:
        from brain_ds.verify.semantic_verify import build_semantic_report, NEEDS_DATA_SUGGEST_DENSITY

        faith = self._make_faithfulness(needs_data_density=NEEDS_DATA_SUGGEST_DENSITY + 0.01)
        coherence = self._make_coherence()
        report = build_semantic_report(faith, coherence)

        suggestions = [f for f in report.findings if f.severity == "SUGGESTION"]
        self.assertGreaterEqual(len(suggestions), 1)

    def test_report_no_block_flag(self) -> None:
        """SemanticReport must not have a 'blocked' or 'gate' field — advisory only."""
        from brain_ds.verify.semantic_verify import SemanticReport
        import dataclasses

        field_names = {f.name for f in dataclasses.fields(SemanticReport)}
        self.assertNotIn("blocked", field_names)
        self.assertNotIn("gate", field_names)

    def test_schema_complete_on_clean_brd(self) -> None:
        from brain_ds.verify.semantic_verify import build_semantic_report

        faith = self._make_faithfulness()
        coherence = self._make_coherence()
        report = build_semantic_report(faith, coherence)

        self.assertEqual(report.findings, ())
        self.assertFalse(report.has_critical)
        self.assertFalse(report.has_warning)

    def test_schema_llm_skipped(self) -> None:
        from brain_ds.verify.semantic_verify import build_semantic_report

        faith = self._make_faithfulness()
        coherence = self._make_coherence(ran=False)
        report = build_semantic_report(faith, coherence)

        self.assertFalse(report.coherence.ran)


# ---------------------------------------------------------------------------
# T-07: LLM-tier tiering (ungated, synthetic CoherenceResult)
# ---------------------------------------------------------------------------

class TestLLMTieringSynthetic(unittest.TestCase):
    """T-07: Verify the LLM-dimension tiering branches in build_semantic_report
    using synthetic CoherenceResult(ran=True) — no real model needed.
    """

    def _make_faithfulness(self):
        from brain_ds.verify.semantic_verify import FaithfulnessResult
        return FaithfulnessResult(
            graph_id="g-1",
            total_references=0,
            resolved_references=0,
            ratio=1.0,
            references=(),
            wikilink_coverage=1.0,
            needs_data_density=0.0,
        )

    def _make_coherence(self, **kwargs):
        from brain_ds.verify.semantic_verify import CoherenceResult
        defaults = dict(ran=True, language="es", section_scores=(), consistency_pass=True, rationales=())
        defaults.update(kwargs)
        return CoherenceResult(**defaults)

    def test_tier_warning_cross_section_inconsistency(self) -> None:
        from brain_ds.verify.semantic_verify import build_semantic_report

        coherence = self._make_coherence(consistency_pass=False)
        report = build_semantic_report(self._make_faithfulness(), coherence)

        warnings = [f for f in report.findings if f.severity == "WARNING" and f.dimension == "consistency"]
        self.assertGreaterEqual(len(warnings), 1)

    def test_tier_warning_section_score_below_min(self) -> None:
        from brain_ds.verify.semantic_verify import build_semantic_report

        coherence = self._make_coherence(section_scores=(("Problems", 2),))
        report = build_semantic_report(self._make_faithfulness(), coherence)

        warnings = [f for f in report.findings if f.severity == "WARNING" and f.dimension == "coherence"]
        self.assertGreaterEqual(len(warnings), 1)

    def test_tier_suggestion_section_score_borderline(self) -> None:
        from brain_ds.verify.semantic_verify import build_semantic_report

        # Score exactly at COHERENCE_MIN_SCORE (3) → SUGGESTION (3-4 range)
        coherence = self._make_coherence(section_scores=(("Problems", 3),))
        report = build_semantic_report(self._make_faithfulness(), coherence)

        suggestions = [f for f in report.findings if f.severity == "SUGGESTION" and f.dimension == "coherence"]
        self.assertGreaterEqual(len(suggestions), 1)


# ---------------------------------------------------------------------------
# T-08: Golden-run regression test
# ---------------------------------------------------------------------------

CLEAN_BRD = """## Contexto
Este BRD cubre [[Empresa ABC]], [[Sistema ERP]], y [[Área de Ventas]].
Todos los activos están referenciados en el grafo.
"""

POISONED_BRD = """## Contexto
Este BRD cubre [[Empresa ABC]], [[Sistema ERP]], y [[Área de Ventas]].
También menciona [[Ghost Corp]] que no existe en el grafo.
"""


def _make_fixture_store(tmp_path: Path) -> tuple[GraphStore, str]:
    """Create a fixture store with 4 nodes; Ghost Corp is NOT included."""
    store = GraphStore(str(tmp_path / "fixture.db"))
    graph_id = "fixture-graph"
    store.create_graph(graph_id, name="Fixture Graph", workspace_root=str(tmp_path), workspace_path=str(tmp_path))
    for node_id, label in [
        ("n-1", "Empresa ABC"),
        ("n-2", "Sistema ERP"),
        ("n-3", "Área de Ventas"),
        # "DataGhost" is NOT added — it's the purposely absent entity
    ]:
        store.upsert_node(graph_id, {"id": node_id, "label": label, "type": "Unknown"})
    return store, graph_id


class TestGoldenRun(unittest.TestCase):
    """T-08: Golden-run regression tests using fixture graph."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.store, self.graph_id = _make_fixture_store(self.tmp_path)

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_golden_clean_no_critical(self) -> None:
        from brain_ds.verify.semantic_verify import score_graph_faithfulness, build_semantic_report, CoherenceResult

        faith = score_graph_faithfulness(CLEAN_BRD, self.graph_id, self.store)
        coherence = CoherenceResult(ran=False, language="es", section_scores=(), consistency_pass=None, rationales=())
        report = build_semantic_report(faith, coherence)

        self.assertFalse(report.has_critical, msg=f"Unexpected CRITICAL findings: {report.findings}")

    def test_golden_poisoned_exactly_one_critical(self) -> None:
        from brain_ds.verify.semantic_verify import score_graph_faithfulness, build_semantic_report, CoherenceResult

        faith = score_graph_faithfulness(POISONED_BRD, self.graph_id, self.store)
        coherence = CoherenceResult(ran=False, language="es", section_scores=(), consistency_pass=None, rationales=())
        report = build_semantic_report(faith, coherence)

        criticals = [f for f in report.findings if f.severity == "CRITICAL"]
        self.assertEqual(len(criticals), 1, msg=f"Expected 1 CRITICAL, got: {criticals}")

    @unittest.skipUnless(os.environ.get("RUN_LIVE_LLM"), "RUN_LIVE_LLM not set")
    def test_golden_llm_gated(self) -> None:
        """Gated seam for future real chat-client wiring. Inject a JudgeModel stub
        that returns a low consistency score and assert at least one WARNING."""
        from brain_ds.verify.semantic_verify import score_brd_coherence, build_semantic_report, score_graph_faithfulness

        class _StubJudge:
            def complete(self, prompt: str) -> str:
                # Return a JSON-like response simulating low consistency
                return '{"score": 1, "rationale": "Solutions do not address stated Problems."}'

        faith = score_graph_faithfulness(POISONED_BRD, self.graph_id, self.store)
        coherence = score_brd_coherence(POISONED_BRD, self.graph_id, language="es", model=_StubJudge())
        report = build_semantic_report(faith, coherence)

        consistency_warnings = [
            f for f in report.findings
            if f.severity == "WARNING" and f.dimension == "consistency"
        ]
        self.assertGreaterEqual(len(consistency_warnings), 1)


# ---------------------------------------------------------------------------
# T-09: brain_ds/verify/__init__.py export extension
# ---------------------------------------------------------------------------

class TestVerifyPackageExports(unittest.TestCase):
    """T-09: All new public symbols must be importable from brain_ds.verify."""

    def test_verify_package_exports(self) -> None:
        from brain_ds.verify import (
            build_semantic_report,
            SemanticReport,
            SemanticFinding,
            FaithfulnessResult,
            CoherenceResult,
            ReferenceFinding,
            score_graph_faithfulness,
            score_brd_coherence,
        )
        # All imports succeeded — package exports are correct
        self.assertIsNotNone(build_semantic_report)
        self.assertIsNotNone(SemanticReport)


if __name__ == "__main__":
    unittest.main()
