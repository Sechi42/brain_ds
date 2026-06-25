from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest

import brain_ds.mcp.grounding as grounding
from brain_ds.mcp.tools import add_edge, resolve_confirmation, suggest_connections
from brain_ds.scoring import similarity
from brain_ds.store.graph_store import GraphStore
from brain_ds.store.models import EdgeRow, NodeRow
from brain_ds.verify.edge_calibration import EdgeCalibrationReport, EdgeClassMetrics


def _metrics(label: str, *, accept: float, reject: float) -> EdgeClassMetrics:
    return EdgeClassMetrics(
        label=label,
        examples=5,
        accept_threshold=accept,
        reject_threshold=reject,
        precision=1.0,
        recall=1.0,
        false_positive_rate=0.0,
        false_negative_rate=0.0,
        abstain_band_size=accept - reject,
        confusion_matrix={},
        abstain_actual_count=0,
        abstain_predicted_count=0,
        abstain_recall=0.0,
        abstain_coverage=0.0,
    )


def _report(classes: dict[str, EdgeClassMetrics]) -> EdgeCalibrationReport:
    return EdgeCalibrationReport(
        run_id="test-calibration",
        generated_at="2026-06-24T00:00:00Z",
        classes=classes,
        provenance_counts={"seed": 5, "hand_labeled": 0, "generated": 0},
    )


def _node(node_id: str, label: str, type_: str, details: dict | None = None) -> NodeRow:
    return NodeRow(
        graph_id="g1",
        id=node_id,
        label=label,
        type=type_,
        supertype=None,
        details=details or {"where": "fixture"},
        card_sections=None,
        editable_fields=None,
        evidence_ids=None,
        layout_hint=None,
        parent_id=None,
        depth=0,
        created_at="2026-06-24T00:00:00Z",
        modified_at="2026-06-24T00:00:00Z",
    )


def _make_minimal_store(graph_id: str = "g-test") -> GraphStore:
    """Create a fresh in-memory GraphStore with a graph and two nodes."""
    store = GraphStore(":memory:")
    store.create_graph(graph_id, name=graph_id, project="test")
    store.upsert_node(
        graph_id,
        {
            "id": "src",
            "label": "Source Node",
            "type": "KPI",
            "supertype": "metric",
            "parent_id": "ROOT",
            "details": {"where": "test fixture", "what": "source"},
        },
    )
    store.upsert_node(
        graph_id,
        {
            "id": "tgt",
            "label": "Target Node",
            "type": "Data Source",
            "supertype": "data",
            "parent_id": "ROOT",
            "details": {"where": "test fixture", "what": "target"},
        },
    )
    return store


# ---------------------------------------------------------------------------
# Task 1.1: Autouse fixture — clear per-graph calibration cache between tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_per_graph_calibration_cache():
    """Prevent cross-test state bleed in _per_graph_calibration_cache."""
    yield
    getattr(grounding, "_per_graph_calibration_cache", {}).clear()


def _edge(source: str, target: str, label: str = "owns") -> EdgeRow:
    return EdgeRow(
        graph_id="g1",
        edge_id=f"{source}->{target}",
        source=source,
        target=target,
        label=label,
        weight=None,
        reasons=None,
        evidence_ids=None,
        created_at="2026-06-24T00:00:00Z",
    )


class SuggestConnectionsToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "store.db"
        self.store = GraphStore(str(self.db_path))
        self.graph_id = "graph-suggest"
        self.store.meta_repo.save_graph_meta(
            graph_id=self.graph_id,
            workspace_root=self.temp_dir.name,
            workspace_path=self.temp_dir.name,
            project="project-suggest",
            org="org-suggest",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at="",
        )
        # Every fixture node carries a non-empty "where": the sparse gate marks
        # where-less nodes as review-needed, which is covered separately below.
        self._add_node("kpi-ventas", "Ventas Mensuales", "KPI", "metric", {"where": "Dashboard comercial", "learned": "Data Source: CRM Salesforce ventas"})
        self._add_node("ds-crm", "CRM Salesforce", "Data Source", "data", {"where": "Salesforce cloud", "what": "CRM Salesforce con tabla ventas"})
        self._add_node("role-analista", "Analista Ventas", "Role", "actor", {"where": "Equipo comercial ventas"})
        self._add_node("risk-legal", "Riesgo Regulatorio", "Risk", "risk", {"where": "Legal", "what": "Cambios normativos"})
        # KPI already accountable to the Role — must be excluded from suggestions.
        self.store.upsert_edge(self.graph_id, {"source": "role-analista", "target": "kpi-ventas", "label": "accountable"})

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def _add_node(self, node_id: str, label: str, type_: str, supertype: str, details: dict) -> None:
        self.store.upsert_node(
            self.graph_id,
            {
                "id": node_id,
                "label": label,
                "type": type_,
                "supertype": supertype,
                "parent_id": "ROOT",
                "details": details,
            },
        )

    def test_suggests_data_source_with_measured_by_direction(self) -> None:
        result = suggest_connections(self.store, {"graph_id": self.graph_id, "node_id": "kpi-ventas"})

        self.assertNotIn("code", result)
        ids = [item["node_id"] for item in result["suggestions"]]
        self.assertIn("ds-crm", ids)
        top = next(item for item in result["suggestions"] if item["node_id"] == "ds-crm")
        self.assertEqual(top["suggested_edge"], {"source": "kpi-ventas", "target": "ds-crm", "label": "measured-by"})
        self.assertGreaterEqual(top["score"], 0.45)

    def test_excludes_already_connected_and_self(self) -> None:
        result = suggest_connections(self.store, {"graph_id": self.graph_id, "node_id": "kpi-ventas"})

        ids = [item["node_id"] for item in result["suggestions"]]
        self.assertNotIn("kpi-ventas", ids)
        self.assertNotIn("role-analista", ids)
        self.assertIn("role-analista", result["already_connected"])

    def test_threshold_filters_weak_candidates(self) -> None:
        result = suggest_connections(
            self.store,
            {"graph_id": self.graph_id, "node_id": "kpi-ventas", "threshold": 0.5},
        )

        ids = [item["node_id"] for item in result["suggestions"]]
        # Risk has no type rule with KPI and no token overlap — must be filtered.
        self.assertNotIn("risk-legal", ids)

    def test_limit_caps_results_and_reports_effective_threshold(self) -> None:
        for index in range(15):
            self._add_node(f"ds-extra-{index}", f"Fuente ventas {index}", "Data Source", "data", {"where": "Almacén ventas", "what": "ventas"})

        result = suggest_connections(
            self.store,
            {"graph_id": self.graph_id, "node_id": "kpi-ventas", "limit": 5},
        )

        self.assertEqual(result["returned"], 5)
        self.assertGreater(result["candidates_above_threshold"], 5)
        self.assertGreaterEqual(result["effective_threshold"], result["threshold"])

    def test_missing_node_returns_validation_error(self) -> None:
        result = suggest_connections(self.store, {"graph_id": self.graph_id, "node_id": "nope"})

        self.assertEqual(result["code"], -32000)
        self.assertIn("not found", result["message"])

    def test_missing_graph_returns_validation_error(self) -> None:
        result = suggest_connections(self.store, {"graph_id": "ghost", "node_id": "kpi-ventas"})

        self.assertEqual(result["code"], -32000)

    def test_sparse_node_candidates_are_blocked_as_review_needed(self) -> None:
        self._add_node(
            "ds-sparse",
            "Fuente ventas mensuales dashboard comercial",
            "Data Source",
            "data",
            {"where": "", "learned": "Underspecified: faltan tablas"},
        )

        result = suggest_connections(self.store, {"graph_id": self.graph_id, "node_id": "kpi-ventas"})

        sparse = next((item for item in result["suggestions"] if item["node_id"] == "ds-sparse"), None)
        if sparse is not None:
            self.assertEqual(sparse["suggested_edge"]["label"], "review-needed")
            self.assertIn("sparse", sparse["reason"])

    def test_suggest_connections_tool_passes_calibration_report(self) -> None:
        calibration_report = _report({"measured-by": _metrics("measured-by", accept=0.8, reject=0.2)})

        with (
            patch("brain_ds.mcp.tools.grounding.get_graph_calibration_report", return_value=calibration_report) as get_report,
            patch("brain_ds.mcp.tools.similarity.suggest_connections_for_node") as suggest_for_node,
        ):
            suggest_for_node.return_value = {"suggestions": []}

            result = suggest_connections(self.store, {"graph_id": self.graph_id, "node_id": "kpi-ventas"})

        self.assertEqual(result, {"suggestions": []})
        get_report.assert_called_once_with(self.graph_id, self.store)
        self.assertIs(suggest_for_node.call_args.kwargs["calibration_report"], calibration_report)


class SimilarityAlgorithmTests(unittest.TestCase):
    def test_type_pair_suggestions_use_canonical_relationship_labels(self) -> None:
        from brain_ds.ontology.relationship_types import RelationshipType

        valid_labels = {item.value for item in RelationshipType}
        for source_type, target_type, label in similarity.TYPE_PAIR_SUGGESTIONS.values():
            self.assertIn(label, valid_labels, f"{source_type}->{target_type} uses unknown label {label}")

    def test_type_pair_keys_match_their_rule_types(self) -> None:
        for pair, (source_type, target_type, _label) in similarity.TYPE_PAIR_SUGGESTIONS.items():
            self.assertEqual(pair, frozenset({source_type, target_type}))

    def test_compute_calibration_verdict_accept_abstain_reject_and_missing_label(self) -> None:
        report = _report({"owns": _metrics("owns", accept=0.49, reject=0.41)})

        self.assertEqual(
            similarity._compute_calibration_verdict(0.50, "owns", report),
            "advisory_accept",
        )
        self.assertEqual(
            similarity._compute_calibration_verdict(0.45, "owns", report),
            "advisory_abstain",
        )
        self.assertEqual(
            similarity._compute_calibration_verdict(0.40, "owns", report),
            "advisory_reject",
        )
        self.assertEqual(
            similarity._compute_calibration_verdict(0.99, "not-in-report", report),
            "advisory_abstain",
        )

    def test_lexical_calibration_verdict_accept_abstain_reject(self) -> None:
        report = _report({"owns": _metrics("owns", accept=0.47, reject=0.44)})
        focus = _node("org", "sales analytics", "Organization")
        accept = _node("dept-accept", "sales analytics", "Department")
        abstain = _node("dept-abstain", "sales", "Department")
        reject = _node("dept-reject", "finance", "Department")

        result = similarity.suggest_connections_for_node(
            [focus, accept, abstain, reject],
            [],
            "org",
            threshold=0.0,
            calibration_report=report,
        )

        verdicts = {item["node_id"]: item["calibration_verdict"] for item in result["suggestions"]}
        self.assertEqual(verdicts["dept-accept"], "advisory_accept")
        self.assertEqual(verdicts["dept-abstain"], "advisory_abstain")
        self.assertEqual(verdicts["dept-reject"], "advisory_reject")


# ---------------------------------------------------------------------------
# Phase 2: grounding.py RED tests (tasks 2.1–2.5)
# ---------------------------------------------------------------------------


def test_cache_miss_computes_and_stores():
    """Cache miss must invoke calibrate_from_ledger exactly once; second call hits cache."""
    store = _make_minimal_store("g-calib-1")
    try:
        mock_report = _report({"owns": _metrics("owns", accept=0.7, reject=0.3)})
        with patch(
            "brain_ds.verify.ledger_calibration.calibrate_from_ledger",
            return_value=mock_report,
        ) as mock_calibrate:
            result1 = grounding.get_graph_calibration_report("g-calib-1", store)
            result2 = grounding.get_graph_calibration_report("g-calib-1", store)
        mock_calibrate.assert_called_once()
        assert result1 is result2
    finally:
        store.close()


def test_cache_hit_skips_recomputation():
    """Pre-warming cache must prevent calibrate_from_ledger from being called."""
    mock_report = _report({"owns": _metrics("owns", accept=0.7, reject=0.3)})
    grounding._per_graph_calibration_cache["g-calib-2"] = mock_report
    store = _make_minimal_store("g-calib-2")
    try:
        with patch(
            "brain_ds.verify.ledger_calibration.calibrate_from_ledger"
        ) as mock_calibrate:
            result = grounding.get_graph_calibration_report("g-calib-2", store)
        mock_calibrate.assert_not_called()
        assert result is mock_report
    finally:
        store.close()


def test_cold_start_equals_global():
    """Empty ledger must produce report field-for-field equal to get_calibration_report()."""
    store = _make_minimal_store("g-cold")
    try:
        per_graph = grounding.get_graph_calibration_report("g-cold", store)
        global_report = grounding.get_calibration_report()
        assert set(per_graph.classes.keys()) == set(global_report.classes.keys())
        for label in global_report.classes:
            pg_cls = per_graph.classes[label]
            gl_cls = global_report.classes[label]
            assert pg_cls.accept_threshold == gl_cls.accept_threshold, (
                f"accept mismatch for {label!r}: per-graph={pg_cls.accept_threshold} "
                f"global={gl_cls.accept_threshold}"
            )
            assert pg_cls.reject_threshold == gl_cls.reject_threshold, (
                f"reject mismatch for {label!r}: per-graph={pg_cls.reject_threshold} "
                f"global={gl_cls.reject_threshold}"
            )
    finally:
        store.close()


def test_cross_graph_isolation():
    """Invalidating G1 must not evict G2 from the per-graph cache."""
    mock_g1 = _report({"owns": _metrics("owns", accept=0.8, reject=0.2)})
    mock_g2 = _report({"owns": _metrics("owns", accept=0.6, reject=0.4)})
    grounding._per_graph_calibration_cache["G1-iso"] = mock_g1
    grounding._per_graph_calibration_cache["G2-iso"] = mock_g2
    store = _make_minimal_store("G2-iso")
    try:
        grounding.invalidate_graph_calibration("G1-iso")
        assert "G1-iso" not in grounding._per_graph_calibration_cache
        with patch(
            "brain_ds.verify.ledger_calibration.calibrate_from_ledger"
        ) as mock_calibrate:
            result = grounding.get_graph_calibration_report("G2-iso", store)
        mock_calibrate.assert_not_called()
        assert result is mock_g2
    finally:
        store.close()


def test_absolute_seed_path_no_file_error(tmp_path: Path, monkeypatch) -> None:
    """Non-repo cwd must not raise FileNotFoundError for the seed gold set."""
    monkeypatch.chdir(tmp_path)
    store = _make_minimal_store("g-abs")
    try:
        report = grounding.get_graph_calibration_report("g-abs", store)
        assert report is not None
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Phase 4: tools.py RED tests (tasks 4.1–4.3)
# ---------------------------------------------------------------------------


def test_successful_append_ledger_evicts_cache():
    """Successful add_edge must evict the per-graph calibration cache entry."""
    graph_id = "g-evict-ok"
    store = _make_minimal_store(graph_id)
    try:
        mock_report = _report({"owns": _metrics("owns", accept=0.7, reject=0.3)})
        grounding._per_graph_calibration_cache[graph_id] = mock_report

        add_edge(
            store,
            {
                "graph_id": graph_id,
                "source": "src",
                "target": "tgt",
                "label": "owns",
                "confidence": 0.9,
            },
        )

        assert graph_id not in grounding._per_graph_calibration_cache, (
            "Cache entry should have been evicted after successful add_edge"
        )
    finally:
        store.close()


def test_failed_append_ledger_does_not_evict():
    """Failed store.append_ledger must leave the per-graph cache entry intact."""
    graph_id = "g-evict-fail"
    store = _make_minimal_store(graph_id)
    try:
        mock_report = _report({"owns": _metrics("owns", accept=0.7, reject=0.3)})
        grounding._per_graph_calibration_cache[graph_id] = mock_report

        with patch.object(
            store,
            "append_ledger",
            side_effect=RuntimeError("simulated ledger write failure"),
        ):
            add_edge(
                store,
                {
                    "graph_id": graph_id,
                    "source": "src",
                    "target": "tgt",
                    "label": "owns",
                    "confidence": 0.9,
                },
            )

        assert graph_id in grounding._per_graph_calibration_cache, (
            "Cache entry must remain intact when append_ledger raises"
        )
    finally:
        store.close()


def test_resolve_confirmation_evicts_cache():
    """Successful resolve_confirmation must evict the per-graph calibration cache."""
    graph_id = "g-evict-resolve"
    store = _make_minimal_store(graph_id)
    try:
        now = datetime.now(timezone.utc).isoformat()
        store.append_ledger(
            graph_id=graph_id,
            target_id="edge-conf-1",
            target_type="edge",
            status="needs-confirmation",
            provenance="seed",
            captured_at=now,
            relationship_label="owns",
        )

        mock_report = _report({"owns": _metrics("owns", accept=0.7, reject=0.3)})
        grounding._per_graph_calibration_cache[graph_id] = mock_report

        resolve_confirmation(
            store,
            {
                "graph_id": graph_id,
                "target_type": "edge",
                "target_id": "edge-conf-1",
                "outcome": "confirmed",
                "resolved_by": "test-user",
                "gold_rationale": "Verified by automated test",
            },
        )

        assert graph_id not in grounding._per_graph_calibration_cache, (
            "Cache entry should have been evicted after resolve_confirmation"
        )
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Phase 6: Behavioral boundary tests (tasks 6.1–6.4)
# ---------------------------------------------------------------------------


def test_per_graph_differentiation():
    """Ledger with >=10 verdict-bearing 'owns' rows must yield thresholds different from global.

    'owns' IS in the seed gold set.  Seeding extreme per-graph scores (8 confirmed
    at 0.99, 2 invalidated at 0.10) produces an 'owns' distribution far from the
    global seed, so calibration must produce different thresholds.
    """
    graph_id = "g-differentiated"
    store = _make_minimal_store(graph_id)
    try:
        now = datetime.now(timezone.utc).isoformat()
        # 8 confirmed at very high confidence
        for i in range(8):
            store.append_ledger(
                graph_id=graph_id,
                target_id=f"edge-owns-valid-{i}",
                target_type="edge",
                status="confirmed",
                provenance="seed",
                captured_at=now,
                relationship_label="owns",
                initial_confidence=0.99,
                current_confidence=0.99,
                gold_rationale="high-confidence test fixture",
            )
        # 2 invalidated at very low confidence
        for i in range(2):
            store.append_ledger(
                graph_id=graph_id,
                target_id=f"edge-owns-invalid-{i}",
                target_type="edge",
                status="invalidated",
                provenance="seed",
                captured_at=now,
                relationship_label="owns",
                initial_confidence=0.10,
                current_confidence=0.10,
                gold_rationale="low-confidence test fixture",
            )

        per_graph = grounding.get_graph_calibration_report(graph_id, store)
        global_report = grounding.get_calibration_report()

        assert "owns" in per_graph.classes, "per-graph report must have 'owns' class"
        assert "owns" in global_report.classes, "global report must have 'owns' class"
        pg = per_graph.classes["owns"]
        gl = global_report.classes["owns"]
        assert pg.accept_threshold != gl.accept_threshold or pg.reject_threshold != gl.reject_threshold, (
            "per-graph thresholds must differ from global when ledger has 10+ verdict-bearing records"
        )
    finally:
        store.close()


def test_sparse_label_fallback_9_records():
    """9 non-verdict-bearing 'owns' ledger rows → seed fallback → thresholds equal to global.

    'owns' IS in the seed gold set.  status='inferred' rows are NOT verdict-bearing:
    ledger_to_gold_records filters them out, so the gold-records count for 'owns'
    stays at 0 (< 10 threshold) and _merge_global_seed supplies the same seed
    records as the global calibration uses, producing identical thresholds.
    """
    graph_id = "g-sparse-9"
    store = _make_minimal_store(graph_id)
    try:
        now = datetime.now(timezone.utc).isoformat()
        # status='inferred' is NOT verdict-bearing: excluded by ledger_to_gold_records
        for i in range(9):
            store.append_ledger(
                graph_id=graph_id,
                target_id=f"edge-owns-inferred-{i}",
                target_type="edge",
                status="inferred",
                provenance="seed",
                captured_at=now,
                relationship_label="owns",
            )

        per_graph = grounding.get_graph_calibration_report(graph_id, store)
        global_report = grounding.get_calibration_report()

        assert "owns" in per_graph.classes, "per-graph report must have 'owns' class (from seed)"
        assert "owns" in global_report.classes, "global report must have 'owns' class"
        pg = per_graph.classes["owns"]
        gl = global_report.classes["owns"]
        assert pg.accept_threshold == gl.accept_threshold, (
            f"'owns' accept_threshold must fall back to seed (0 verdict-bearing rows): "
            f"per-graph={pg.accept_threshold} global={gl.accept_threshold}"
        )
        assert pg.reject_threshold == gl.reject_threshold, (
            f"'owns' reject_threshold must fall back to seed (0 verdict-bearing rows): "
            f"per-graph={pg.reject_threshold} global={gl.reject_threshold}"
        )
    finally:
        store.close()


def test_sparse_label_fallback_9_verdict_bearing_records():
    """9 verdict-bearing 'owns' rows (< 10) → seed fallback → thresholds equal to global.

    'owns' IS in the seed gold set.  7 confirmed + 2 invalidated = 9 verdict-bearing rows.
    Because the threshold is < 10, _merge_global_seed fallback is engaged for 'owns',
    so per-graph thresholds must be identical to the global seed-derived thresholds.
    This covers the lower boundary of R-04 (exactly one record below the 10-record cutoff).
    """
    graph_id = "g-sparse-9-vb"
    store = _make_minimal_store(graph_id)
    try:
        now = datetime.now(timezone.utc).isoformat()
        for i in range(7):
            store.append_ledger(
                graph_id=graph_id,
                target_id=f"edge-owns-valid-{i}",
                target_type="edge",
                status="confirmed",
                provenance="seed",
                captured_at=now,
                relationship_label="owns",
                initial_confidence=0.99,
                current_confidence=0.99,
                gold_rationale="high-confidence test fixture",
            )
        for i in range(2):
            store.append_ledger(
                graph_id=graph_id,
                target_id=f"edge-owns-invalid-{i}",
                target_type="edge",
                status="invalidated",
                provenance="seed",
                captured_at=now,
                relationship_label="owns",
                initial_confidence=0.10,
                current_confidence=0.10,
                gold_rationale="low-confidence test fixture",
            )

        per_graph = grounding.get_graph_calibration_report(graph_id, store)
        global_report = grounding.get_calibration_report()

        assert "owns" in per_graph.classes, "per-graph report must have 'owns' class (from seed fallback)"
        assert "owns" in global_report.classes, "global report must have 'owns' class"
        pg = per_graph.classes["owns"]
        gl = global_report.classes["owns"]
        assert pg.accept_threshold == gl.accept_threshold, (
            f"'owns' accept_threshold must fall back to seed (9 verdict-bearing rows < 10): "
            f"per-graph={pg.accept_threshold} global={gl.accept_threshold}"
        )
        assert pg.reject_threshold == gl.reject_threshold, (
            f"'owns' reject_threshold must fall back to seed (9 verdict-bearing rows < 10): "
            f"per-graph={pg.reject_threshold} global={gl.reject_threshold}"
        )
    finally:
        store.close()


def test_sparse_label_boundary_10_records():
    """10 verdict-bearing 'owns' rows → no seed fallback → thresholds differ from global.

    'owns' IS in the seed gold set.  With exactly 10 verdict-bearing rows (8 confirmed
    at 0.99, 2 invalidated at 0.10), the label is NOT sparse (10 >= 10).  The seed
    fallback for 'owns' is skipped; thresholds are derived purely from ledger data
    and must differ from the global seed-derived thresholds.
    """
    graph_id = "g-sparse-10"
    store = _make_minimal_store(graph_id)
    try:
        now = datetime.now(timezone.utc).isoformat()
        for i in range(8):
            store.append_ledger(
                graph_id=graph_id,
                target_id=f"edge-owns-valid-{i}",
                target_type="edge",
                status="confirmed",
                provenance="seed",
                captured_at=now,
                relationship_label="owns",
                initial_confidence=0.99,
                current_confidence=0.99,
                gold_rationale="high-confidence test fixture",
            )
        for i in range(2):
            store.append_ledger(
                graph_id=graph_id,
                target_id=f"edge-owns-invalid-{i}",
                target_type="edge",
                status="invalidated",
                provenance="seed",
                captured_at=now,
                relationship_label="owns",
                initial_confidence=0.10,
                current_confidence=0.10,
                gold_rationale="low-confidence test fixture",
            )

        per_graph = grounding.get_graph_calibration_report(graph_id, store)
        global_report = grounding.get_calibration_report()

        assert "owns" in per_graph.classes, "per-graph report must have 'owns' class"
        assert "owns" in global_report.classes, "global report must have 'owns' class"
        pg = per_graph.classes["owns"]
        gl = global_report.classes["owns"]
        assert pg.accept_threshold != gl.accept_threshold or pg.reject_threshold != gl.reject_threshold, (
            "per-graph thresholds for 'owns' must differ from global when >= 10 verdict-bearing records"
        )
    finally:
        store.close()


def test_admission_gate_unchanged():
    """Different calibration reports must not change candidate ids or scores (admission gate invariant)."""
    graph_id = "g-gate"
    store = _make_minimal_store(graph_id)
    try:
        # Add extra nodes to ensure some suggestions appear
        for i in range(3):
            store.upsert_node(
                graph_id,
                {
                    "id": f"ds-extra-{i}",
                    "label": f"Data Source {i} test fixture",
                    "type": "Data Source",
                    "supertype": "data",
                    "parent_id": "ROOT",
                    "details": {"where": "fixture storage", "what": f"extra source {i}"},
                },
            )

        report_a = grounding.get_calibration_report()
        # report_b has dramatically different advisory thresholds
        report_b = _report({"owned-by": _metrics("owned-by", accept=0.99, reject=0.95)})

        with patch(
            "brain_ds.mcp.tools.grounding.get_graph_calibration_report",
            return_value=report_a,
        ):
            result_a = suggest_connections(store, {"graph_id": graph_id, "node_id": "src"})

        with patch(
            "brain_ds.mcp.tools.grounding.get_graph_calibration_report",
            return_value=report_b,
        ):
            result_b = suggest_connections(store, {"graph_id": graph_id, "node_id": "src"})

        ids_scores_a = [
            (item["node_id"], item["score"]) for item in result_a.get("suggestions", [])
        ]
        ids_scores_b = [
            (item["node_id"], item["score"]) for item in result_b.get("suggestions", [])
        ]
        assert ids_scores_a == ids_scores_b, (
            "Admission gate changed: candidate ids/scores differ between calibration reports"
        )
    finally:
        store.close()


if __name__ == "__main__":
    unittest.main()
