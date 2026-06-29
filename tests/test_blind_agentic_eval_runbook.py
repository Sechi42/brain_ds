from __future__ import annotations

import unittest
from pathlib import Path


class BlindAgenticRunbookTests(unittest.TestCase):
    def test_runbook_documents_exact_manual_opencode_workflow(self) -> None:
        text = self._runbook_text()

        self.assertIn("C:\\Users\\sergi\\Documents\\brain_ds", text)
        self.assertIn(
            "uv run python -m tests.eval.blind_agentic.prepare_subject --scenario revops_growth --run-id <run_id>",
            text,
        )
        self.assertIn("cd tmp/blind-agentic-eval/<run_id>/subject", text)
        self.assertIn("opencode", text)
        self.assertIn("I run Revenue Operations for Northstar Analytics", text)
        self.assertIn(
            "uv run python -m tests.eval.blind_agentic.collect_evidence --scenario revops_growth --run-id <run_id>",
            text,
        )
        self.assertIn("uv run python -m tests.eval.blind_agentic.score_report", text)
        self.assertIn("uv run python -m tests.eval.blind_agentic.collect_and_score", text)
        self.assertIn("--graph-db-path <path-to-active-workspace/.brain_ds/store.db>", text)
        self.assertIn("--judge-packet-out tmp/blind-agentic-eval/<run_id>/judge_packet.json", text)
        self.assertIn("--judge-response tmp/blind-agentic-eval/<run_id>/judge_response.json", text)
        self.assertIn("OpenCode transcript/export is optional evidence", text)
        self.assertIn("tmp/blind-agentic-eval/<run_id>/evidence/manifest.json", text)

    def test_runbook_keeps_evaluator_assets_out_of_subject_workflow(self) -> None:
        text = self._runbook_text().lower()

        self.assertIn("do not copy evaluator-only files", text)
        self.assertIn("tests/gold/blind_agentic/revops_growth/", text)
        self.assertNotIn("copy tests/gold", text)
        self.assertNotIn("open tests/gold", text)

    def test_runbook_documents_non_blocking_advisory_lane_and_hash_binding(self) -> None:
        text = self._runbook_text().lower()

        self.assertIn("deterministic lane is authoritative", text)
        self.assertIn("advisory judge is non-blocking", text)
        self.assertIn("evidence_hash", text)
        self.assertIn("hash mismatch", text)
        self.assertIn("do not require api keys", text)

    def test_runbook_documents_datasource_gate_and_freshness_fields(self) -> None:
        text = self._runbook_text()

        self.assertIn("datasource_documentation", text)
        self.assertIn("brainds-orchestrator", text)
        self.assertIn("Any undelegated BrainDS subagent contact", text)
        self.assertIn("orchestrator_gate", text)
        self.assertIn("freshness_checks", text)
        self.assertIn("subject_local_graph", text)
        self.assertIn("artifact_hashes", text)

    def test_runbook_documents_pr4_comparison_audit_and_stacked_slice_workflow(self) -> None:
        text = self._runbook_text()

        self.assertIn("--model-run model-a=tmp/blind-agentic-eval/model-a/report.json", text)
        self.assertIn("model_matrix.json", text)
        self.assertIn("double_verifier", text)
        self.assertIn("--verifier-b-audit tmp/blind-agentic-eval/<run_id>/verifier_b_audit.json", text)
        self.assertIn("stacked-to-main", text)
        self.assertIn("PR4", text)

    def _runbook_text(self) -> str:
        return Path("docs/blind-agentic-eval.md").read_text(encoding="utf-8")
