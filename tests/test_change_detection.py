"""Unit tests for the data-source change-detection pure helpers (Work-Unit E).

Covers:
- E-T1: canonicalize_schema + compute_schema_hash cosmetic invariance (E-S6/S7/S8)
- E-T2: change_detection block emitted ONLY at level==table (no-emit guard)
- E-T3: verdict resolution — new / unchanged / changed / unknown-baseline (E-S1/S2/S9/S11)
- E-T4: Reflexion-style delta — added/removed/altered columns, added/removed tables (E-S3/S4/S5/S12/S13)

All tests are pure: no network, no live connector, in-memory schema dicts only.
"""

from __future__ import annotations

import unittest

from brain_ds.connectors.change_detection import (
    canonicalize_schema,
    compute_schema_hash,
    compute_schema_delta,
    resolve_verdict,
    build_change_detection,
)


def _schema(tables: dict[str, list[dict[str, str]]]) -> dict:
    """Build a multi-table live-schema dict in the shape the helper consumes.

    {"tables": {table_name: {"columns": [{"name":..,"type":..}, ...]}}}
    """
    return {"tables": {name: {"columns": cols} for name, cols in tables.items()}}


# ---------------------------------------------------------------------------
# E-T1 — canonicalization + hash cosmetic invariance
# ---------------------------------------------------------------------------
class CanonicalizeSchemaTests(unittest.TestCase):
    def test_column_reorder_yields_same_hash(self) -> None:
        # E-S6: column order is canonicalized away.
        a = _schema({"T": [
            {"name": "A", "type": "int"},
            {"name": "B", "type": "text"},
            {"name": "C", "type": "real"},
        ]})
        b = _schema({"T": [
            {"name": "C", "type": "real"},
            {"name": "A", "type": "int"},
            {"name": "B", "type": "text"},
        ]})
        self.assertEqual(compute_schema_hash(a), compute_schema_hash(b))

    def test_varchar_widening_yields_same_hash(self) -> None:
        # E-S7: varchar(100) -> varchar(255), both canonicalize to type class text.
        a = _schema({"T": [{"name": "A", "type": "varchar(100)"}]})
        b = _schema({"T": [{"name": "A", "type": "varchar(255)"}]})
        self.assertEqual(compute_schema_hash(a), compute_schema_hash(b))

    def test_type_synonyms_yield_same_hash(self) -> None:
        # E-S8: integer / int / int4 all canonicalize to int.
        for syn in ("integer", "int4", "INT", " integer "):
            with self.subTest(syn=syn):
                a = _schema({"T": [{"name": "A", "type": "int"}]})
                b = _schema({"T": [{"name": "A", "type": syn}]})
                self.assertEqual(compute_schema_hash(a), compute_schema_hash(b))

    def test_column_name_whitespace_and_case_normalized(self) -> None:
        a = _schema({"T": [{"name": "Amount", "type": "real"}]})
        b = _schema({"T": [{"name": " amount ", "type": "real"}]})
        self.assertEqual(compute_schema_hash(a), compute_schema_hash(b))

    def test_hash_is_hex_sha256(self) -> None:
        h = compute_schema_hash(_schema({"T": [{"name": "A", "type": "int"}]}))
        self.assertEqual(len(h), 64)
        int(h, 16)  # raises ValueError if not hex

    def test_canonical_is_stable_and_sorted(self) -> None:
        canon = canonicalize_schema(_schema({
            "Z": [{"name": "b", "type": "int"}, {"name": "a", "type": "text"}],
            "A": [{"name": "x", "type": "int"}],
        }))
        # tables sorted by name
        self.assertEqual(list(canon["tables"].keys()), ["A", "Z"])
        # columns within a table sorted by name
        self.assertEqual([c["name"] for c in canon["tables"]["Z"]["columns"]], ["a", "b"])


# ---------------------------------------------------------------------------
# E-T2 — emission guard: change_detection only at level==table
# ---------------------------------------------------------------------------
class EmissionLevelGuardTests(unittest.TestCase):
    def test_build_change_detection_returns_block_for_table_level(self) -> None:
        live = _schema({"T": [{"name": "A", "type": "int"}]})
        block = build_change_detection(live_schema=live, baseline=None, has_prior_doc=False)
        self.assertIsNotNone(block)
        self.assertIn("verdict", block)

    def test_describe_and_container_levels_never_emit(self) -> None:
        # The explore_source wiring guard: helper is only invoked at table level.
        # We assert the contract by checking that the result dict for non-table
        # levels does not contain a change_detection key. This mirrors the
        # explore_source structure used by the integration wiring.
        from brain_ds.connectors.change_detection import should_emit_change_detection

        self.assertTrue(should_emit_change_detection(level="table"))
        self.assertFalse(should_emit_change_detection(level="source"))
        self.assertFalse(should_emit_change_detection(level="container"))


# ---------------------------------------------------------------------------
# E-T3 — verdict resolution
# ---------------------------------------------------------------------------
class VerdictResolutionTests(unittest.TestCase):
    def test_never_documented_is_new(self) -> None:
        # E-S1: no baseline, no prior doc -> new
        verdict = resolve_verdict(live_hash="abc", baseline=None, has_prior_doc=False)
        self.assertEqual(verdict, "new")

    def test_matching_baseline_is_unchanged(self) -> None:
        # E-S2: baseline hash == live hash -> unchanged
        baseline = {"schema_hash": "abc", "documented_schema_snapshot": {}, "last_documented_at": "x"}
        verdict = resolve_verdict(live_hash="abc", baseline=baseline, has_prior_doc=True)
        self.assertEqual(verdict, "unchanged")

    def test_differing_baseline_is_changed(self) -> None:
        baseline = {"schema_hash": "abc", "documented_schema_snapshot": {}, "last_documented_at": "x"}
        verdict = resolve_verdict(live_hash="def", baseline=baseline, has_prior_doc=True)
        self.assertEqual(verdict, "changed")

    def test_prior_doc_no_baseline_is_unknown_baseline(self) -> None:
        # E-S9: documented pre-feature, no baseline -> unknown-baseline
        verdict = resolve_verdict(live_hash="abc", baseline=None, has_prior_doc=True)
        self.assertEqual(verdict, "unknown-baseline")

    def test_none_safe_missing_keys_never_raise(self) -> None:
        # E-S11: baseline dict without schema_hash key must not raise.
        baseline = {}  # no schema_hash key
        verdict = resolve_verdict(live_hash="abc", baseline=baseline, has_prior_doc=True)
        # absent hash inside baseline dict behaves like unknown-baseline
        self.assertEqual(verdict, "unknown-baseline")


# ---------------------------------------------------------------------------
# E-T4 — Reflexion-style delta
# ---------------------------------------------------------------------------
class SchemaDeltaTests(unittest.TestCase):
    def test_added_column(self) -> None:
        # E-S3
        baseline_snap = canonicalize_schema(_schema({"T": [
            {"name": "A", "type": "int"}, {"name": "B", "type": "int"}]}))
        live = _schema({"T": [
            {"name": "A", "type": "int"}, {"name": "B", "type": "int"}, {"name": "C", "type": "int"}]})
        delta = compute_schema_delta(baseline_snap, canonicalize_schema(live))
        self.assertEqual(
            [(c["table"], c["name"]) for c in delta["added_columns"]],
            [("T", "c")],
        )
        self.assertEqual(delta["removed_columns"], [])

    def test_removed_column(self) -> None:
        # E-S4
        baseline_snap = canonicalize_schema(_schema({"T": [
            {"name": "A", "type": "int"}, {"name": "B", "type": "int"}]}))
        live = _schema({"T": [{"name": "A", "type": "int"}]})
        delta = compute_schema_delta(baseline_snap, canonicalize_schema(live))
        self.assertEqual(
            [(c["table"], c["name"]) for c in delta["removed_columns"]],
            [("T", "b")],
        )

    def test_altered_column_type_class(self) -> None:
        # E-S5
        baseline_snap = canonicalize_schema(_schema({"T": [{"name": "A", "type": "int"}]}))
        live = _schema({"T": [{"name": "A", "type": "text"}]})
        delta = compute_schema_delta(baseline_snap, canonicalize_schema(live))
        altered = delta["altered_columns"]
        self.assertEqual(len(altered), 1)
        self.assertEqual(altered[0]["table"], "T")
        self.assertEqual(altered[0]["name"], "a")
        self.assertEqual(altered[0]["from_type"], "int")
        self.assertEqual(altered[0]["to_type"], "text")

    def test_added_table(self) -> None:
        # E-S12
        baseline_snap = canonicalize_schema(_schema({"T1": [{"name": "A", "type": "int"}]}))
        live = _schema({"T1": [{"name": "A", "type": "int"}], "T2": [{"name": "X", "type": "int"}]})
        delta = compute_schema_delta(baseline_snap, canonicalize_schema(live))
        self.assertIn("T2", delta["added_tables"])
        self.assertEqual(delta["removed_tables"], [])

    def test_removed_table(self) -> None:
        # E-S13
        baseline_snap = canonicalize_schema(
            _schema({"T1": [{"name": "A", "type": "int"}], "T2": [{"name": "X", "type": "int"}]}))
        live = _schema({"T1": [{"name": "A", "type": "int"}]})
        delta = compute_schema_delta(baseline_snap, canonicalize_schema(live))
        self.assertIn("T2", delta["removed_tables"])

    def test_delta_present_only_when_changed(self) -> None:
        live = _schema({"T": [{"name": "A", "type": "int"}, {"name": "C", "type": "text"}]})
        baseline_snap = canonicalize_schema(_schema({"T": [{"name": "A", "type": "int"}]}))
        baseline = {
            "schema_hash": compute_schema_hash({"tables": {"T": {"columns": [{"name": "A", "type": "int"}]}}}),
            "documented_schema_snapshot": baseline_snap,
            "last_documented_at": "2026-01-01T00:00:00Z",
        }
        block = build_change_detection(live_schema=live, baseline=baseline, has_prior_doc=True)
        self.assertEqual(block["verdict"], "changed")
        self.assertIsNotNone(block["delta"])
        self.assertEqual([(c["table"], c["name"]) for c in block["delta"]["added_columns"]], [("T", "c")])

    def test_delta_is_omitted_when_unchanged(self) -> None:
        live = _schema({"T": [{"name": "A", "type": "int"}]})
        snap = canonicalize_schema(live)
        baseline = {
            "schema_hash": compute_schema_hash(live),
            "documented_schema_snapshot": snap,
            "last_documented_at": "2026-01-01T00:00:00Z",
        }
        block = build_change_detection(live_schema=live, baseline=baseline, has_prior_doc=True)
        self.assertEqual(block["verdict"], "unchanged")
        self.assertNotIn("delta", block)

    def test_delta_is_omitted_when_new(self) -> None:
        live = _schema({"T": [{"name": "A", "type": "int"}]})
        block = build_change_detection(live_schema=live, baseline=None, has_prior_doc=False)
        self.assertEqual(block["verdict"], "new")
        self.assertNotIn("delta", block)


# ---------------------------------------------------------------------------
# Delta robustness — a documenter may persist documented_schema_snapshot in a
# NON-canonical shape (flat {columns:[...]}, raw "name TYPE" strings, no table
# name). The delta must still diff columns correctly, not report the whole
# table as added. (Found in live validation of andes-blind-e.)
# ---------------------------------------------------------------------------
class DeltaRobustnessTests(unittest.TestCase):
    def test_canonicalize_parses_raw_string_columns(self) -> None:
        canon = canonicalize_schema({"columns": ["id INTEGER", "nombre TEXT"]})
        cols = canon["tables"]["data"]["columns"]
        self.assertEqual(cols, [{"name": "id", "type": "int"}, {"name": "nombre", "type": "text"}])

    def test_delta_robust_to_flat_rawstring_snapshot_single_table(self) -> None:
        # Mirrors the real andes-blind baseline: flat {columns:[raw strings]},
        # no `tables` key — and live is a single scoped table with one new column.
        live = _schema({"clientes": [
            {"name": "id", "type": "INTEGER"},
            {"name": "nombre", "type": "TEXT"},
            {"name": "email", "type": "TEXT"},
            {"name": "ciudad", "type": "TEXT"},
            {"name": "telefono", "type": "TEXT"},
        ]})
        baseline = {
            "schema_hash": "deadbeef",  # differs from live -> changed
            "documented_schema_snapshot": {
                "columns": ["id INTEGER", "nombre TEXT", "email TEXT", "ciudad TEXT"]
            },
            "last_documented_at": "2026-06-16",
        }
        block = build_change_detection(live_schema=live, baseline=baseline, has_prior_doc=True)
        self.assertEqual(block["verdict"], "changed")
        self.assertEqual(
            [(c["table"], c["name"]) for c in block["delta"]["added_columns"]],
            [("clientes", "telefono")],
        )
        self.assertEqual(block["delta"]["added_tables"], [])
        self.assertEqual(block["delta"]["removed_tables"], [])


if __name__ == "__main__":
    unittest.main()
