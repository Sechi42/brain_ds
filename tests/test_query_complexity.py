"""Tests for brain_ds.scoring.query_complexity — strict TDD, RED-first."""

from __future__ import annotations

import unittest
from pathlib import Path

from brain_ds.scoring.query_complexity import (
    COMPLEX_SCORE_BOUNDARY,
    COMPARATIVE_KEYWORDS,
    DIVERSITY_SIGNAL_WEIGHT,
    RELATIONAL_KEYWORDS,
    RESULT_TYPE_DIVERSITY_CUTOFF,
    TOKEN_COUNT_CUTOFF,
    TOKEN_SIGNAL_WEIGHT,
    classify_query,
)


class TestQueryComplexityImport(unittest.TestCase):
    """Phase 1.1 — guard: module and public API must be importable."""

    def test_classify_query_is_callable(self):
        self.assertTrue(callable(classify_query))

    def test_constants_are_present(self):
        self.assertIsInstance(TOKEN_COUNT_CUTOFF, int)
        self.assertIsInstance(TOKEN_SIGNAL_WEIGHT, float)
        self.assertIsInstance(RESULT_TYPE_DIVERSITY_CUTOFF, int)
        self.assertIsInstance(DIVERSITY_SIGNAL_WEIGHT, float)
        self.assertIsInstance(COMPLEX_SCORE_BOUNDARY, float)
        self.assertIsInstance(COMPARATIVE_KEYWORDS, frozenset)


class TestOntologyDerivedRelationalKeywords(unittest.TestCase):
    """Phase 1.3 — RELATIONAL_KEYWORDS derived from RelationshipType enum."""

    def test_relational_keywords_is_nonempty_frozenset(self):
        self.assertIsInstance(RELATIONAL_KEYWORDS, frozenset)
        self.assertGreater(len(RELATIONAL_KEYWORDS), 0)

    def test_relational_keywords_covers_enum_parts(self):
        from brain_ds.ontology.relationship_types import RelationshipType

        for rt in RelationshipType:
            parts = [
                part
                for part in rt.value.replace("-", " ").split()
                if len(part) > 1
            ]
            for part in parts:
                self.assertIn(
                    part,
                    RELATIONAL_KEYWORDS,
                    msg=f"Part '{part}' from RelationshipType.{rt.name} "
                    f"(value={rt.value!r}) not found in RELATIONAL_KEYWORDS",
                )


class TestClassifyQuerySimple(unittest.TestCase):
    """Phase 2.1 — QC-SIMPLE: short query, no keywords."""

    def test_qc_simple(self):
        result = classify_query("deliveries table")
        self.assertEqual(result["level"], "simple")
        self.assertLess(result["score"], COMPLEX_SCORE_BOUNDARY)
        self.assertEqual(result["signals"], [])


class TestClassifyQueryComplexKeyword(unittest.TestCase):
    """Phase 2.2 — QC-COMPLEX-KEYWORD: comparative/aggregation keyword."""

    def test_qc_complex_keyword(self):
        result = classify_query("compare revenue across all regions")
        self.assertEqual(result["level"], "complex")
        signals_str = " ".join(result["signals"])
        self.assertIn("comparative_keyword", signals_str)


class TestClassifyQueryComplexRelational(unittest.TestCase):
    """Phase 2.3 — QC-COMPLEX-RELATIONAL: ontology-derived relational keyword."""

    def test_qc_complex_relational(self):
        result = classify_query("who owns the deliveries table")
        self.assertEqual(result["level"], "complex")
        self.assertTrue(
            any(s.startswith("relational_keyword:") for s in result["signals"]),
            msg=f"No relational_keyword signal in {result['signals']}",
        )


class TestClassifyQueryComplexDiversity(unittest.TestCase):
    """Phase 2.4 — QC-COMPLEX-DIVERSITY: high result-type diversity."""

    def test_qc_complex_diversity(self):
        result = classify_query("table", result_types=["KPI", "Role", "Data Source", "Risk"])
        self.assertEqual(result["level"], "complex")
        self.assertIn("result_type_diversity>=3", result["signals"])


class TestClassifyQueryAmbiguousBias(unittest.TestCase):
    """Phase 2.5 — QC-AMBIGUOUS-BIAS (reconciled): single token-count signal => complex."""

    def test_qc_ambiguous_bias(self):
        # A query with >= 5 meaningful tokens but no comparative/relational keywords.
        # "the" / "is" / "now" are stopwords; meaningful tokens: deliveries, table, large, today
        # We need exactly >= 5 meaningful tokens to fire token_count signal.
        # "large data deliveries table today present active" => 7 tokens (all meaningful)
        query = "large data deliveries table today present active"
        result = classify_query(query)
        self.assertEqual(result["level"], "complex")
        self.assertAlmostEqual(result["score"], TOKEN_SIGNAL_WEIGHT, places=5)
        self.assertIn("token_count>=5", result["signals"])
        self.assertNotIn("ambiguous_bias", result["signals"])


class TestClassifyQueryDeterminism(unittest.TestCase):
    """Phase 2.6 — QC-DETERMINISM: identical inputs => identical outputs."""

    def test_qc_determinism(self):
        query = "compare revenue across all regions"
        r1 = classify_query(query)
        r2 = classify_query(query)
        r3 = classify_query(query)
        self.assertEqual(r1, r2)
        self.assertEqual(r2, r3)

    def test_signals_are_sorted(self):
        # A query that fires multiple signals
        result = classify_query(
            "compare who owns all the data sources tables",
            result_types=["KPI", "Role", "Data Source", "Risk"],
        )
        self.assertEqual(result["signals"], sorted(result["signals"]))


class TestClassifyQuerySignals(unittest.TestCase):
    """Phase 2.7 — QC-SIGNALS: signals list names every fired signal."""

    def test_qc_signals_multi(self):
        # compare (comparative) + owns (relational) + result_types diversity
        result = classify_query(
            "compare who owns the data sources",
            result_types=["KPI", "Role", "Data Source", "Risk"],
        )
        self.assertGreaterEqual(len(result["signals"]), 2)
        for sig in result["signals"]:
            self.assertIsInstance(sig, str)


class TestProseContractMirror(unittest.TestCase):
    """Phase 3.1/3.2 — QC-PROSE-MIRROR and QC-PROSE-ROUTING."""

    _AGENT_PATH = Path(__file__).parent.parent / ".claude" / "agents" / "brainds-query-consultant.md"

    def _agent_text(self) -> str:
        # The query-consultant agent file is a per-client installed artifact
        # (gitignored, no tracked prompts/ mirror — by design, see
        # harness_check.py "query-consultant prompt mirror → always SKIP").
        # It is absent on a fresh clone / CI / an OpenCode-only environment, so
        # SKIP rather than hard-fail to keep dual-client (Claude + OpenCode)
        # support intact. Where the file IS installed, the guard still enforces
        # that the Python thresholds are mirrored in the prose.
        if not self._AGENT_PATH.is_file():
            self.skipTest(
                f"agent prose file absent ({self._AGENT_PATH.name}) — "
                "installed per-client artifact, mirror not verified here"
            )
        return self._AGENT_PATH.read_text(encoding="utf-8")

    def test_qc_prose_mirror_token_cutoff(self):
        # Anchor on the unique constant-binding string, not the bare "5".
        # A bare digit can appear incidentally elsewhere in the prose, which
        # would let the guard pass even if the Complexity Routing block were
        # deleted. The "TOKEN_COUNT_CUTOFF=<n>" form only exists in that block.
        text = self._agent_text()
        anchor = f"TOKEN_COUNT_CUTOFF={TOKEN_COUNT_CUTOFF}"
        self.assertIn(
            anchor,
            text,
            msg=f"{anchor!r} not found in agent prose (Complexity Routing block missing or drifted)",
        )

    def test_qc_prose_mirror_diversity_cutoff(self):
        # Anchor on the unique constant-binding string. The bare "3" already
        # occurs elsewhere in this file ("1-3 candidates"), so str(cutoff)
        # alone would pass even with the routing block deleted.
        text = self._agent_text()
        anchor = f"RESULT_TYPE_DIVERSITY_CUTOFF={RESULT_TYPE_DIVERSITY_CUTOFF}"
        self.assertIn(
            anchor,
            text,
            msg=f"{anchor!r} not found in agent prose (Complexity Routing block missing or drifted)",
        )

    def test_qc_prose_mirror_score_boundary(self):
        # S-2: the third declared threshold. Anchor on the exact prose phrase
        # "score < 0.30" so the guard fails if the boundary drifts or the
        # routing block is removed.
        text = self._agent_text()
        anchor = f"score < {COMPLEX_SCORE_BOUNDARY:.2f}"
        self.assertIn(
            anchor,
            text,
            msg=f"{anchor!r} not found in agent prose (boundary drifted or routing block missing)",
        )

    def test_qc_prose_routing_search_graph(self):
        text = self._agent_text()
        self.assertIn("search_graph", text)

    def test_qc_prose_routing_suggest_connections(self):
        text = self._agent_text()
        self.assertIn("suggest_connections", text)


class TestNoClassifyQueryMcpToolAdded(unittest.TestCase):
    """Phase 4.1 — QC-NO-MCP-TOOL: classify_query must not add another MCP tool."""

    def test_tool_registry_count(self):
        from brain_ds.harness_check import EXPECTED_MCP_TOOL_COUNT
        from brain_ds.mcp.tools import TOOL_REGISTRY

        self.assertEqual(
            len(TOOL_REGISTRY),
            EXPECTED_MCP_TOOL_COUNT,
            msg=f"TOOL_REGISTRY has {len(TOOL_REGISTRY)} tools; expected {EXPECTED_MCP_TOOL_COUNT}. "
            "Do NOT register classify_query as an MCP tool.",
        )


if __name__ == "__main__":
    unittest.main()
