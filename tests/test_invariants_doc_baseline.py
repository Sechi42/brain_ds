"""Tests for the verify-rubric helper assert_doc_matches_baseline (Work-Unit E).

E-REQ-10 / E-S10: when a documented Data Source node's stored baseline column
count differs from the live schema, the verify phase flags a WARNING by default.
It only escalates to CRITICAL when an explicit threshold is configured and the
drift magnitude exceeds it.
"""

from __future__ import annotations

import unittest

from brain_ds.pipeline.invariants import assert_doc_matches_baseline


def _baseline(columns_per_table: dict[str, int]) -> dict:
    tables = {
        name: {"columns": [{"name": f"c{i}", "type": "int"} for i in range(n)]}
        for name, n in columns_per_table.items()
    }
    return {
        "schema_hash": "x",
        "documented_schema_snapshot": {"tables": tables},
        "last_documented_at": "2026-01-01T00:00:00Z",
    }


def _live(columns_per_table: dict[str, int]) -> dict:
    return {
        "tables": {
            name: {"columns": [{"name": f"c{i}", "type": "int"} for i in range(n)]}
            for name, n in columns_per_table.items()
        }
    }


class DocMatchesBaselineTests(unittest.TestCase):
    def test_matching_counts_no_finding(self) -> None:
        result = assert_doc_matches_baseline(_baseline({"T": 5}), _live({"T": 5}))
        self.assertIsNone(result["severity"])
        self.assertEqual(result["findings"], [])

    def test_column_count_mismatch_is_warning_by_default(self) -> None:
        # E-S10: documented 5 columns, live now 7 -> WARNING (threshold None).
        result = assert_doc_matches_baseline(_baseline({"T": 5}), _live({"T": 7}))
        self.assertEqual(result["severity"], "WARNING")
        self.assertTrue(any("T" in f for f in result["findings"]))
        self.assertTrue(any("5" in f and "7" in f for f in result["findings"]))

    def test_mismatch_under_threshold_is_warning(self) -> None:
        # explicit threshold of 5; drift of 2 -> still WARNING.
        result = assert_doc_matches_baseline(_baseline({"T": 5}), _live({"T": 7}), threshold=5)
        self.assertEqual(result["severity"], "WARNING")

    def test_mismatch_over_threshold_is_critical(self) -> None:
        # explicit threshold of 1; drift of 4 -> CRITICAL.
        result = assert_doc_matches_baseline(_baseline({"T": 5}), _live({"T": 9}), threshold=1)
        self.assertEqual(result["severity"], "CRITICAL")

    def test_default_threshold_never_critical_even_for_large_drift(self) -> None:
        result = assert_doc_matches_baseline(_baseline({"T": 5}), _live({"T": 99}))
        self.assertEqual(result["severity"], "WARNING")

    def test_missing_baseline_yields_no_finding(self) -> None:
        # None-safe: no baseline snapshot -> nothing to compare, no crash.
        result = assert_doc_matches_baseline(None, _live({"T": 5}))
        self.assertIsNone(result["severity"])
        self.assertEqual(result["findings"], [])

    def test_added_and_removed_table_flagged_as_warning(self) -> None:
        result = assert_doc_matches_baseline(_baseline({"T1": 3}), _live({"T2": 3}))
        self.assertEqual(result["severity"], "WARNING")


if __name__ == "__main__":
    unittest.main()
