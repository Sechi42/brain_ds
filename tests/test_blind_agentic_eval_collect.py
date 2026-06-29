from __future__ import annotations

import json
import os
import shutil
import time
import unittest
from pathlib import Path

from tests.eval.blind_agentic.collect_evidence import (
    CollectEvidenceError,
    collect_evidence,
)
from tests.eval.blind_agentic.trace_schema import parse_opencode_export
from tests.eval.blind_agentic.prepare_subject import prepare_subject


class BlindAgenticCollectTests(unittest.TestCase):
    def setUp(self) -> None:
        shutil.rmtree(Path("tmp") / "blind-agentic-eval-test", ignore_errors=True)

    def test_collect_writes_manifest_with_core_evidence_and_missing_transcript(self) -> None:
        subject = self._prepared_subject("collect-run-001")
        self._write_core_subject_outputs(subject.subject_path)

        bundle = collect_evidence(
            scenario="revops_growth",
            run_id="collect-run-001",
            subject_path=subject.subject_path,
            evidence_path=subject.subject_path.parent / "evidence",
            repo_root=Path.cwd(),
        )

        manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["scenario"], "revops_growth")
        self.assertEqual(manifest["run_id"], "collect-run-001")
        self.assertEqual(manifest["minimum_evidence"]["status"], "accepted")
        self.assertEqual(manifest["session_transcript"]["status"], "missing")
        self.assertIn("graph_db", manifest["captured"])
        self.assertIn("generated_outputs", manifest["captured"])
        self.assertIn("git_diff", manifest["captured"])
        snapshot = manifest["immutable_evidence_snapshot"]
        self.assertEqual(snapshot["status"], "frozen")
        self.assertEqual(snapshot["algorithm"], "sha256")
        self.assertIn("evidence_hash", snapshot)
        self.assertEqual(
            [item["path"] for item in snapshot["files"]],
            ["generated/brd.md", "git_diff.patch", "graph/store.db"],
        )
        self.assertTrue(all(len(item["sha256"]) == 64 for item in snapshot["files"]))
        self.assertTrue((bundle.evidence_path / "graph" / "store.db").is_file())
        self.assertTrue((bundle.evidence_path / "generated" / "brd.md").is_file())
        self.assertTrue((bundle.evidence_path / "git_diff.patch").is_file())

    def test_collect_accepts_missing_transcript_when_required_evidence_exists(self) -> None:
        subject = self._prepared_subject("collect-run-002")
        self._write_core_subject_outputs(subject.subject_path)

        bundle = collect_evidence(
            scenario="revops_growth",
            run_id="collect-run-002",
            subject_path=subject.subject_path,
            evidence_path=subject.subject_path.parent / "evidence",
            repo_root=Path.cwd(),
        )

        manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["minimum_evidence"]["status"], "accepted")
        self.assertEqual(manifest["session_transcript"]["status"], "missing")
        self.assertEqual(manifest["session_transcript"]["required"], False)

    def test_collect_rejects_missing_graph_snapshot(self) -> None:
        subject = self._prepared_subject("collect-run-003")
        self._write_core_subject_outputs(subject.subject_path)
        (subject.subject_path / ".brain_ds" / "store.db").unlink()

        with self.assertRaisesRegex(CollectEvidenceError, "graph snapshot"):
            collect_evidence(
                scenario="revops_growth",
                run_id="collect-run-003",
                subject_path=subject.subject_path,
                evidence_path=subject.subject_path.parent / "evidence",
                repo_root=Path.cwd(),
            )

    def test_collect_rejects_subject_visible_contamination(self) -> None:
        subject = self._prepared_subject("collect-run-004")
        self._write_core_subject_outputs(subject.subject_path)
        (subject.subject_path / "generated" / "notes.md").write_text(
            "The hidden test expected output was consulted.", encoding="utf-8"
        )

        with self.assertRaisesRegex(CollectEvidenceError, "forbidden terms"):
            collect_evidence(
                scenario="revops_growth",
                run_id="collect-run-004",
                subject_path=subject.subject_path,
                evidence_path=subject.subject_path.parent / "evidence",
                repo_root=Path.cwd(),
            )

    def test_collect_ignores_agent_runtime_infrastructure_contamination_terms(self) -> None:
        subject = self._prepared_subject("collect-run-004-infra")
        self._write_core_subject_outputs(subject.subject_path)
        atl = subject.subject_path / ".atl"
        atl.mkdir()
        (atl / "skill-registry.md").write_text(
            "Registered skills for eval harness helpers live outside business content.",
            encoding="utf-8",
        )

        bundle = collect_evidence(
            scenario="revops_growth",
            run_id="collect-run-004-infra",
            subject_path=subject.subject_path,
            evidence_path=subject.subject_path.parent / "evidence",
            repo_root=Path.cwd(),
        )

        manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["anti_contamination"]["status"], "passed")

    def test_collect_captures_explicit_graph_db_override_outside_subject(self) -> None:
        subject = self._prepared_subject("collect-run-004-graph-override")
        self._write_core_subject_outputs(subject.subject_path)
        (subject.subject_path / ".brain_ds" / "store.db").unlink()
        external_graph = subject.subject_path.parent / "active-workspace" / ".brain_ds" / "store.db"
        external_graph.parent.mkdir(parents=True)
        external_graph.write_bytes(b"external sqlite graph snapshot")

        bundle = collect_evidence(
            scenario="revops_growth",
            run_id="collect-run-004-graph-override",
            subject_path=subject.subject_path,
            evidence_path=subject.subject_path.parent / "evidence",
            repo_root=Path.cwd(),
            graph_db_path=external_graph,
        )

        manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["captured"]["graph_db"], "graph/store.db")
        self.assertEqual(
            manifest["graph_db_source"],
            {"kind": "explicit_override", "path": external_graph.as_posix()},
        )
        self.assertEqual(
            (bundle.evidence_path / "graph" / "store.db").read_bytes(),
            b"external sqlite graph snapshot",
        )

    def test_collect_records_empty_opencode_artifact_directory_as_missing(self) -> None:
        subject = self._prepared_subject("collect-run-005")
        self._write_core_subject_outputs(subject.subject_path)
        empty_opencode_dir = subject.subject_path.parent / "empty-opencode-artifacts"
        empty_opencode_dir.mkdir()

        bundle = collect_evidence(
            scenario="revops_growth",
            run_id="collect-run-005",
            subject_path=subject.subject_path,
            evidence_path=subject.subject_path.parent / "evidence",
            repo_root=Path.cwd(),
            opencode_artifacts_path=empty_opencode_dir,
        )

        manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["session_transcript"]["status"], "missing")
        self.assertEqual(manifest["session_transcript"]["files"], [])
        self.assertNotIn("opencode_artifacts", manifest["captured"])

    def test_collect_captures_opencode_artifacts_when_files_exist(self) -> None:
        subject = self._prepared_subject("collect-run-006")
        self._write_core_subject_outputs(subject.subject_path)
        opencode_dir = subject.subject_path.parent / "opencode-artifacts"
        (opencode_dir / "sessions").mkdir(parents=True)
        (opencode_dir / "sessions" / "transcript.jsonl").write_text(
            '{"role":"assistant","content":"mapped lineage"}\n', encoding="utf-8"
        )

        bundle = collect_evidence(
            scenario="revops_growth",
            run_id="collect-run-006",
            subject_path=subject.subject_path,
            evidence_path=subject.subject_path.parent / "evidence",
            repo_root=Path.cwd(),
            opencode_artifacts_path=opencode_dir,
        )

        manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["session_transcript"]["status"], "captured")
        self.assertEqual(
            manifest["captured"]["opencode_artifacts"],
            ["opencode/sessions/transcript.jsonl"],
        )
        self.assertTrue((bundle.evidence_path / "opencode" / "sessions" / "transcript.jsonl").is_file())

    def test_opencode_export_parser_normalizes_roles_and_parent_links(self) -> None:
        export_root = Path("tmp") / "blind-agentic-eval-test" / "opencode-export-roles"
        (export_root / "sessions").mkdir(parents=True, exist_ok=True)
        (export_root / "sessions" / "session.jsonl").write_text(
            "\n".join(
                [
                    json.dumps({"role": "user", "content": "Document the datasource."}),
                    json.dumps(
                        {
                            "role": "assistant",
                            "agent_name": "brainds-orchestrator",
                            "content": "Delegating source exploration.",
                        }
                    ),
                    json.dumps(
                        {
                            "role": "assistant",
                            "agent_name": "brainds-source-explorer",
                            "delegated_by": "brainds-orchestrator",
                            "pathway_milestone": "explore_source",
                            "content": "Source profile drafted.",
                        }
                    ),
                    json.dumps(
                        {
                            "role": "tool",
                            "tool_name": "brain_ds_explore_source",
                            "agent_name": "brainds-source-explorer",
                            "delegated_by": "brainds-orchestrator",
                            "target": "sources/orders.csv",
                            "content": {"status": "ok"},
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        trace, omissions = parse_opencode_export(
            export_root,
            scenario="datasource_documentation",
            run_id="trace-run-001",
            pathway_id="datasource_documentation",
            model_provider="opencode",
            model="test-model",
        )

        self.assertEqual(omissions, [])
        self.assertEqual(trace.scenario, "datasource_documentation")
        self.assertEqual(trace.pathway_id, "datasource_documentation")
        self.assertEqual([event.role for event in trace.events], ["user", "orchestrator", "subagent", "tool"])
        self.assertEqual(trace.events[1].agent_name, "brainds-orchestrator")
        self.assertEqual(trace.events[2].delegated_by, "brainds-orchestrator")
        self.assertEqual(trace.events[2].pathway_milestone, "explore_source")
        self.assertEqual(trace.events[3].tool_name, "brain_ds_explore_source")
        self.assertEqual(trace.events[3].target, "sources/orders.csv")

    def test_collect_writes_normalized_session_trace_and_hash(self) -> None:
        subject = prepare_subject(
            scenario="datasource_documentation",
            run_id="collect-trace-001",
            output_root=Path("tmp") / "blind-agentic-eval-test",
        )
        self._write_core_subject_outputs(subject.subject_path)
        opencode_dir = subject.subject_path.parent / "opencode-artifacts"
        (opencode_dir / "sessions").mkdir(parents=True)
        (opencode_dir / "sessions" / "session.jsonl").write_text(
            json.dumps(
                {
                    "role": "assistant",
                    "agent_name": "brainds-orchestrator",
                    "content": "Starting datasource documentation.",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        bundle = collect_evidence(
            scenario="datasource_documentation",
            run_id="collect-trace-001",
            subject_path=subject.subject_path,
            evidence_path=subject.subject_path.parent / "evidence",
            repo_root=Path.cwd(),
            opencode_artifacts_path=opencode_dir,
        )

        manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
        session_trace = json.loads(
            (bundle.evidence_path / "trace" / "session_trace.json").read_text(encoding="utf-8")
        )

        self.assertEqual(manifest["captured"]["session_trace"], "trace/session_trace.json")
        self.assertEqual(manifest["trace"]["status"], "captured")
        self.assertEqual(len(manifest["trace"]["sha256"]), 64)
        self.assertEqual(session_trace["trace_version"], "2026-06-27.pr1")
        self.assertEqual(session_trace["events"][0]["role"], "orchestrator")
        self.assertEqual(session_trace["events"][0]["agent_name"], "brainds-orchestrator")

    def test_datasource_documentation_missing_required_trace_degrades_minimum_evidence(self) -> None:
        subject = prepare_subject(
            scenario="datasource_documentation",
            run_id="datasource-missing-trace-001",
            output_root=Path("tmp") / "blind-agentic-eval-test",
        )
        self._write_core_subject_outputs(subject.subject_path)

        bundle = collect_evidence(
            scenario="datasource_documentation",
            run_id="datasource-missing-trace-001",
            subject_path=subject.subject_path,
            evidence_path=subject.subject_path.parent / "evidence",
            repo_root=Path.cwd(),
        )

        manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["trace"]["status"], "missing")
        self.assertEqual(manifest["trace"]["required"], True)
        self.assertEqual(manifest["trace"]["required_for_scenarios"], ["datasource_documentation"])
        self.assertEqual(manifest["minimum_evidence"]["status"], "degraded")
        self.assertIn("required session trace", manifest["minimum_evidence"]["reason"])
        self.assertIn("session_trace", [item["artifact"] for item in manifest["omissions"]])
        self.assertNotIn("session_trace", manifest["captured"])
        self.assertFalse((bundle.evidence_path / "trace" / "session_trace.json").exists())

    def test_datasource_documentation_trace_hash_is_stable_for_same_opencode_export(self) -> None:
        subject = prepare_subject(
            scenario="datasource_documentation",
            run_id="datasource-stable-trace-001",
            output_root=Path("tmp") / "blind-agentic-eval-test",
        )
        self._write_core_subject_outputs(subject.subject_path)
        opencode_dir = subject.subject_path.parent / "opencode-artifacts"
        (opencode_dir / "sessions").mkdir(parents=True)
        (opencode_dir / "sessions" / "session.jsonl").write_text(
            json.dumps(
                {
                    "role": "assistant",
                    "agent_name": "brainds-orchestrator",
                    "content": "Starting datasource documentation.",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        first = collect_evidence(
            scenario="datasource_documentation",
            run_id="datasource-stable-trace-001",
            subject_path=subject.subject_path,
            evidence_path=subject.subject_path.parent / "evidence-first",
            repo_root=Path.cwd(),
            opencode_artifacts_path=opencode_dir,
        )
        time.sleep(0.01)
        second = collect_evidence(
            scenario="datasource_documentation",
            run_id="datasource-stable-trace-001",
            subject_path=subject.subject_path,
            evidence_path=subject.subject_path.parent / "evidence-second",
            repo_root=Path.cwd(),
            opencode_artifacts_path=opencode_dir,
        )

        first_manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
        second_manifest = json.loads(second.manifest_path.read_text(encoding="utf-8"))
        first_trace = json.loads((first.evidence_path / "trace" / "session_trace.json").read_text())
        second_trace = json.loads((second.evidence_path / "trace" / "session_trace.json").read_text())

        self.assertEqual(first_manifest["trace"]["sha256"], second_manifest["trace"]["sha256"])
        self.assertEqual(first_trace["created_at_utc"], second_trace["created_at_utc"])

    def test_opencode_export_parser_records_unknown_role_omission_without_crashing(self) -> None:
        export_root = Path("tmp") / "blind-agentic-eval-test" / "opencode-export-unknown-role"
        (export_root / "sessions").mkdir(parents=True, exist_ok=True)
        (export_root / "sessions" / "session.jsonl").write_text(
            "\n".join(
                [
                    json.dumps({"role": "alien", "content": "unsupported role"}),
                    json.dumps(
                        {
                            "role": "assistant",
                            "agent_name": "brainds-orchestrator",
                            "content": "Continuing after unsupported role.",
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        trace, omissions = parse_opencode_export(
            export_root,
            scenario="datasource_documentation",
            run_id="trace-run-unknown-role",
            pathway_id="datasource_documentation",
            model_provider="opencode",
            model="test-model",
        )

        self.assertEqual([event.role for event in trace.events], ["orchestrator"])
        self.assertEqual(omissions[0]["artifact"], "opencode_record")
        self.assertIn("unsupported role", omissions[0]["reason"])

    def test_datasource_documentation_manifest_uses_datasource_run_metadata(self) -> None:
        subject = prepare_subject(
            scenario="datasource_documentation",
            run_id="datasource-metadata-001",
            output_root=Path("tmp") / "blind-agentic-eval-test",
        )
        self._write_core_subject_outputs(subject.subject_path)

        bundle = collect_evidence(
            scenario="datasource_documentation",
            run_id="datasource-metadata-001",
            subject_path=subject.subject_path,
            evidence_path=subject.subject_path.parent / "evidence",
            repo_root=Path.cwd(),
        )

        manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(
            manifest["run_metadata"],
            {
                "prompt_version": "datasource-documentation-v1",
                "fixture_version": "datasource-documentation-fixture-v1",
            },
        )

    def test_datasource_documentation_records_subject_local_freshness_inputs(self) -> None:
        subject = prepare_subject(
            scenario="datasource_documentation",
            run_id="datasource-freshness-local-001",
            output_root=Path("tmp") / "blind-agentic-eval-test",
        )
        self._write_core_subject_outputs(subject.subject_path)
        opencode_dir = subject.subject_path.parent / "opencode-artifacts"
        (opencode_dir / "sessions").mkdir(parents=True)
        (opencode_dir / "sessions" / "session.jsonl").write_text(
            json.dumps({"role": "assistant", "agent_name": "brainds-orchestrator"}) + "\n",
            encoding="utf-8",
        )

        bundle = collect_evidence(
            scenario="datasource_documentation",
            run_id="datasource-freshness-local-001",
            subject_path=subject.subject_path,
            evidence_path=subject.subject_path.parent / "evidence",
            repo_root=Path.cwd(),
            opencode_artifacts_path=opencode_dir,
        )

        manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
        freshness = manifest["freshness_checks"]

        self.assertEqual(freshness["status"], "passed")
        self.assertEqual(freshness["report_schema_version"], "2026-06-27.pr2")
        self.assertEqual(freshness["trace_schema_version"], "2026-06-27.pr1")
        self.assertEqual(freshness["subject_local_graph"]["status"], "passed")
        self.assertEqual(freshness["generated_outputs"]["status"], "captured")
        self.assertEqual(freshness["trace"]["status"], "captured")
        self.assertEqual(len(freshness["artifact_hashes"]["graph/store.db"]), 64)

    def test_datasource_documentation_degrades_non_subject_local_graph_freshness(self) -> None:
        subject = prepare_subject(
            scenario="datasource_documentation",
            run_id="datasource-freshness-external-001",
            output_root=Path("tmp") / "blind-agentic-eval-test",
        )
        self._write_core_subject_outputs(subject.subject_path)
        (subject.subject_path / ".brain_ds" / "store.db").unlink()
        external_graph = subject.subject_path.parent / "active-workspace" / ".brain_ds" / "store.db"
        external_graph.parent.mkdir(parents=True)
        external_graph.write_bytes(b"external sqlite graph snapshot")

        bundle = collect_evidence(
            scenario="datasource_documentation",
            run_id="datasource-freshness-external-001",
            subject_path=subject.subject_path,
            evidence_path=subject.subject_path.parent / "evidence",
            repo_root=Path.cwd(),
            graph_db_path=external_graph,
        )

        manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
        freshness = manifest["freshness_checks"]

        self.assertEqual(freshness["status"], "degraded")
        self.assertEqual(freshness["subject_local_graph"]["status"], "failed")
        self.assertIn("subject workspace", freshness["subject_local_graph"]["reason"])
        self.assertEqual(manifest["minimum_evidence"]["status"], "degraded")

    def test_datasource_documentation_degrades_subject_local_stale_graph_freshness(self) -> None:
        subject = prepare_subject(
            scenario="datasource_documentation",
            run_id="datasource-freshness-stale-local-001",
            output_root=Path("tmp") / "blind-agentic-eval-test",
        )
        self._write_core_subject_outputs(subject.subject_path)
        graph_db = subject.subject_path / ".brain_ds" / "store.db"
        stale_epoch = 1_700_000_000
        os.utime(graph_db, (stale_epoch, stale_epoch))
        opencode_dir = subject.subject_path.parent / "opencode-artifacts"
        (opencode_dir / "sessions").mkdir(parents=True)
        (opencode_dir / "sessions" / "session.jsonl").write_text(
            json.dumps({"role": "assistant", "agent_name": "brainds-orchestrator"}) + "\n",
            encoding="utf-8",
        )

        bundle = collect_evidence(
            scenario="datasource_documentation",
            run_id="datasource-freshness-stale-local-001",
            subject_path=subject.subject_path,
            evidence_path=subject.subject_path.parent / "evidence",
            repo_root=Path.cwd(),
            opencode_artifacts_path=opencode_dir,
        )

        manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
        freshness = manifest["freshness_checks"]

        self.assertEqual(freshness["status"], "degraded")
        self.assertEqual(freshness["subject_local_graph"]["status"], "stale")
        self.assertIn("Regenerate the graph", freshness["subject_local_graph"]["action"])
        self.assertIn("subject_local_graph", freshness["failing_checks"])
        self.assertEqual(manifest["minimum_evidence"]["status"], "degraded")

    def test_collect_records_setup_and_generated_output_omissions(self) -> None:
        subject = self._prepared_subject("collect-run-007")
        brain_ds = subject.subject_path / ".brain_ds"
        brain_ds.mkdir(parents=True, exist_ok=True)
        (brain_ds / "store.db").write_bytes(b"sqlite graph snapshot")

        bundle = collect_evidence(
            scenario="revops_growth",
            run_id="collect-run-007",
            subject_path=subject.subject_path,
            evidence_path=subject.subject_path.parent / "evidence",
            repo_root=Path.cwd(),
        )

        manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["minimum_evidence"]["status"], "accepted")
        self.assertNotIn("setup_metadata", manifest["captured"])
        self.assertNotIn("generated_outputs", manifest["captured"])
        self.assertEqual(
            [item["artifact"] for item in manifest["omissions"]],
            ["setup_metadata", "generated_outputs"],
        )

    def test_collect_rerun_replaces_read_only_evidence_tree(self) -> None:
        subject = self._prepared_subject("collect-run-read-only-rerun")
        self._write_core_subject_outputs(subject.subject_path)
        evidence_path = subject.subject_path.parent / "evidence"

        first_bundle = collect_evidence(
            scenario="revops_growth",
            run_id="collect-run-read-only-rerun",
            subject_path=subject.subject_path,
            evidence_path=evidence_path,
            repo_root=Path.cwd(),
        )
        read_only_file = first_bundle.evidence_path / "stale" / "locked.txt"
        read_only_file.parent.mkdir(parents=True)
        read_only_file.write_text("old evidence", encoding="utf-8")
        read_only_file.chmod(0o444)

        try:
            second_bundle = collect_evidence(
                scenario="revops_growth",
                run_id="collect-run-read-only-rerun",
                subject_path=subject.subject_path,
                evidence_path=evidence_path,
                repo_root=Path.cwd(),
            )
        finally:
            if read_only_file.exists():
                read_only_file.chmod(0o666)

        self.assertTrue(second_bundle.manifest_path.is_file())
        self.assertFalse(read_only_file.exists())

    def _prepared_subject(self, run_id: str):
        return prepare_subject(
            scenario="revops_growth",
            run_id=run_id,
            output_root=Path("tmp") / "blind-agentic-eval-test",
        )

    def _write_core_subject_outputs(self, subject_path: Path) -> None:
        brain_ds = subject_path / ".brain_ds"
        brain_ds.mkdir(parents=True, exist_ok=True)
        (brain_ds / "store.db").write_bytes(b"sqlite graph snapshot")
        (brain_ds / "setup.json").write_text(
            json.dumps({"agents": ["opencode"], "workspace": "subject"}),
            encoding="utf-8",
        )
        generated = subject_path / "generated"
        generated.mkdir(parents=True, exist_ok=True)
        (generated / "brd.md").write_text(
            "# Revenue Operations Diagnosis\n\nPipeline and retention lineage mapped.",
            encoding="utf-8",
        )
