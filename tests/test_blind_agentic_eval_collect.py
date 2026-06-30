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
from tests.eval.blind_agentic.trace_schema import TraceSchemaError, parse_opencode_export
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

    def test_opencode_export_parser_normalizes_real_opencode_envelopes_and_stderr_agent(self) -> None:
        export_root = Path("tmp") / "blind-agentic-eval-test" / "opencode-real-envelopes"
        export_root.mkdir(parents=True, exist_ok=True)
        session_id = "ses_real_001"
        (export_root / "opencode-stderr.log").write_text(
            "\n".join(
                [
                    f"timestamp=2026-06-29T01:37:37.942Z level=INFO message=stream session.id={session_id} agent=brain-ds-orchestrator mode=primary",
                    f"timestamp=2026-06-29T01:37:42.945Z level=INFO message=stream session.id={session_id} agent=brain-ds-source-explorer mode=subagent",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (export_root / "opencode-stdout.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "type": "step_start",
                            "timestamp": 1782697058984,
                            "sessionID": session_id,
                            "part": {"type": "step-start", "messageID": "msg_1"},
                        }
                    ),
                    json.dumps(
                        {
                            "type": "text",
                            "timestamp": 1782697085951,
                            "sessionID": session_id,
                            "part": {
                                "type": "text",
                                "messageID": "msg_1",
                                "text": "I will document the source through BrainDS.",
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "tool_use",
                            "timestamp": 1782697061687,
                            "sessionID": session_id,
                            "part": {
                                "type": "tool",
                                "tool": "brain_ds_list_graphs",
                                "state": {"status": "completed", "input": {}, "output": "[]"},
                            },
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
            run_id="trace-real-opencode",
            pathway_id="datasource_documentation",
            model_provider="opencode",
            model="test-model",
        )

        self.assertEqual(omissions, [])
        self.assertEqual(trace.events[0].role, "orchestrator")
        self.assertEqual(trace.events[0].agent_name, "brain-ds-orchestrator")
        self.assertEqual(trace.events[0].session_id, session_id)
        self.assertTrue(
            any(
                event.role == "subagent" and event.agent_name == "brain-ds-source-explorer"
                for event in trace.events
            )
        )
        orchestrator_messages = [
            event
            for event in trace.events
            if event.role == "orchestrator" and event.action == "message"
        ]
        self.assertEqual(len(orchestrator_messages), 1)
        self.assertTrue(orchestrator_messages[0].text_hash)
        tool_events = [event for event in trace.events if event.role == "tool"]
        self.assertEqual(len(tool_events), 1)
        self.assertEqual(tool_events[0].tool_name, "brain_ds_list_graphs")
        self.assertEqual(tool_events[0].action, "tool_call")

    def test_opencode_export_parser_marks_created_subagent_sessions_as_orchestrator_delegated(self) -> None:
        export_root = Path("tmp") / "blind-agentic-eval-test" / "opencode-subagent-created"
        export_root.mkdir(parents=True, exist_ok=True)
        orchestrator_session = "ses_orchestrator_001"
        subagent_session = "ses_subagent_001"
        (export_root / "opencode-stderr.log").write_text(
            "\n".join(
                [
                    f"timestamp=2026-06-29T03:45:07.022Z level=INFO message=stream session.id={orchestrator_session} agent=brain-ds-orchestrator mode=primary",
                    f"timestamp=2026-06-29T03:45:21.575Z level=INFO message=created id={subagent_session}",
                    f"parentID={orchestrator_session} title=\"Run connection mapping phase (@brainds-connection-mapper subagent)\"",
                    "agent=brainds-connection-mapper model=undefined metadata=undefined",
                    f"timestamp=2026-06-29T03:45:22.099Z level=INFO message=stream session.id={subagent_session} agent=brainds-connection-mapper mode=subagent",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        trace, omissions = parse_opencode_export(
            export_root,
            scenario="datasource_documentation",
            run_id="trace-subagent-created",
            pathway_id="datasource_documentation",
            model_provider="opencode",
        )

        self.assertEqual(omissions, [])
        delegated_subagents = [event for event in trace.events if event.role == "subagent"]
        self.assertGreaterEqual(len(delegated_subagents), 2)
        self.assertTrue(
            all(event.delegated_by == "brain-ds-orchestrator" for event in delegated_subagents)
        )
        self.assertEqual(delegated_subagents[0].action, "session_created")
        self.assertEqual(delegated_subagents[0].session_id, subagent_session)

    def test_opencode_export_parser_treats_title_stream_as_metadata_and_binds_text_to_orchestrator(self) -> None:
        export_root = Path("tmp") / "blind-agentic-eval-test" / "opencode-title-metadata"
        export_root.mkdir(parents=True, exist_ok=True)
        session_id = "ses_title_then_orchestrator"
        (export_root / "opencode-stderr.log").write_text(
            "\n".join(
                [
                    f"timestamp=2026-06-29T03:05:16.651Z level=INFO message=stream session.id={session_id} small=true agent=title mode=primary",
                    f"timestamp=2026-06-29T03:05:23.369Z level=INFO message=stream session.id={session_id} small=false agent=brain-ds-orchestrator mode=primary",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (export_root / "opencode-stdout.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "type": "text",
                            "timestamp": 1782702326650,
                            "sessionID": session_id,
                            "part": {"type": "text", "text": "I will document this datasource."},
                        }
                    ),
                    json.dumps(
                        {
                            "type": "tool_use",
                            "timestamp": 1782702326766,
                            "sessionID": session_id,
                            "part": {
                                "type": "tool",
                                "tool": "brain_ds_list_graphs",
                                "state": {"status": "completed", "input": {}, "output": "[]"},
                            },
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
            run_id="trace-title-metadata",
            pathway_id="datasource_documentation",
            model_provider="opencode",
        )

        self.assertEqual(omissions, [])
        self.assertEqual([event.agent_name for event in trace.events], ["brain-ds-orchestrator", "brain-ds-orchestrator", "brain-ds-orchestrator"])
        self.assertEqual(trace.events[0].action, "agent_stream")
        self.assertEqual(trace.events[1].role, "orchestrator")
        self.assertIsNotNone(trace.events[1].content_ref)
        self.assertEqual(str(trace.events[1].content_ref)[:14], "opencode:text-")
        self.assertEqual(trace.events[2].role, "tool")

    def test_opencode_export_parser_binds_stdout_only_step_agent_to_later_text(self) -> None:
        export_root = Path("tmp") / "blind-agentic-eval-test" / "opencode-stdout-step-agent"
        export_root.mkdir(parents=True, exist_ok=True)
        session_id = "ses_stdout_only_orchestrator"
        (export_root / "opencode-stdout.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "type": "step_start",
                            "timestamp": 1782702326000,
                            "sessionID": session_id,
                            "agent": "brain-ds-orchestrator",
                            "part": {"type": "step-start"},
                        }
                    ),
                    json.dumps(
                        {
                            "type": "text",
                            "timestamp": 1782702326650,
                            "sessionID": session_id,
                            "part": {
                                "type": "text",
                                "text": "I will document this datasource from stdout only.",
                            },
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
            run_id="trace-stdout-step-agent",
            pathway_id="datasource_documentation",
            model_provider="opencode",
        )

        self.assertEqual(omissions, [])
        self.assertEqual(len(trace.events), 1)
        self.assertEqual(trace.events[0].role, "orchestrator")
        self.assertEqual(trace.events[0].agent_name, "brain-ds-orchestrator")
        self.assertEqual(trace.events[0].action, "message")

    def test_opencode_export_parser_normalizes_session_id_and_parent_aliases(self) -> None:
        parent_aliases = (
            "ParentSessionID",
            "parentSessionID",
            "parent_session_id",
            "parentID",
            "parent_id",
        )

        for alias in parent_aliases:
            with self.subTest(parent_alias=alias):
                export_root = Path("tmp") / "blind-agentic-eval-test" / f"opencode-aliases-{alias}"
                export_root.mkdir(parents=True, exist_ok=True)
                orchestrator_session = f"ses_orchestrator_{alias}"
                subagent_session = f"ses_subagent_{alias}"
                (export_root / "session.json").write_text(
                    json.dumps(
                        {
                            "events": [
                                {
                                    "type": "text",
                                    "timestamp": 1,
                                    "session_id": orchestrator_session,
                                    "agent": "brain-ds-orchestrator",
                                    "part": {"type": "text", "text": "I will document the source."},
                                },
                                {
                                    "type": "opencode_session",
                                    "timestamp": 2,
                                    "id": subagent_session,
                                    alias: orchestrator_session,
                                    "agent_name": "brainds-source-explorer",
                                    "action": "session_created",
                                },
                                {
                                    "type": "text",
                                    "timestamp": 3,
                                    "sessionID": subagent_session,
                                    "part": {"type": "text", "text": "I profiled the source."},
                                },
                            ]
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )

                trace, omissions = parse_opencode_export(
                    export_root,
                    scenario="datasource_documentation",
                    run_id="trace-aliases",
                    pathway_id="datasource_documentation",
                    model_provider="opencode",
                )

                self.assertEqual(omissions, [])
                self.assertEqual(trace.events[0].session_id, orchestrator_session)
                self.assertEqual(trace.events[1].session_id, subagent_session)
                self.assertEqual(trace.events[1].delegated_by, "brain-ds-orchestrator")
                self.assertEqual(trace.events[2].agent_name, "brainds-source-explorer")
                self.assertEqual(trace.events[2].delegated_by, "brain-ds-orchestrator")

    def test_opencode_export_parser_rejects_unknown_export_schema_before_undefined_agent(self) -> None:
        export_root = Path("tmp") / "blind-agentic-eval-test" / "opencode-unknown-schema"
        export_root.mkdir(parents=True, exist_ok=True)
        (export_root / "session.json").write_text(
            json.dumps(
                {
                    "events": [
                        {
                            "kind": "assistant_output",
                            "actor": "undefined",
                            "payload": {"message": "This schema is not recognized."},
                        }
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(TraceSchemaError, "unknown OpenCode export schema"):
            parse_opencode_export(
                export_root,
                scenario="datasource_documentation",
                run_id="trace-unknown-schema",
                pathway_id="datasource_documentation",
                model_provider="opencode",
            )

    def test_opencode_export_parser_rejects_mixed_unknown_record_shapes(self) -> None:
        export_root = Path("tmp") / "blind-agentic-eval-test" / "opencode-mixed-unknown-schema"
        export_root.mkdir(parents=True, exist_ok=True)
        (export_root / "session.json").write_text(
            json.dumps(
                {
                    "events": [
                        {
                            "type": "text",
                            "timestamp": 1,
                            "sessionID": "ses_valid",
                            "agent_name": "brain-ds-orchestrator",
                            "part": {"type": "text", "text": "Valid exported text."},
                        },
                        {
                            "kind": "assistant_output",
                            "actor": "brain-ds-orchestrator",
                            "payload": {"message": "Unknown export shape must fail fast."},
                        },
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(TraceSchemaError, "unknown OpenCode export schema"):
            parse_opencode_export(
                export_root,
                scenario="datasource_documentation",
                run_id="trace-mixed-unknown-schema",
                pathway_id="datasource_documentation",
                model_provider="opencode",
            )

    def test_opencode_export_parser_rejects_unsupported_typed_record_shapes(self) -> None:
        export_root = Path("tmp") / "blind-agentic-eval-test" / "opencode-unsupported-type"
        export_root.mkdir(parents=True, exist_ok=True)
        (export_root / "session.json").write_text(
            json.dumps(
                {
                    "events": [
                        {
                            "type": "assistant_output",
                            "timestamp": 1,
                            "sessionID": "ses_unsupported",
                            "agent_name": "brain-ds-orchestrator",
                            "part": {"type": "text", "text": "Unsupported typed record."},
                        }
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(TraceSchemaError, "unsupported OpenCode export record type"):
            parse_opencode_export(
                export_root,
                scenario="datasource_documentation",
                run_id="trace-unsupported-type",
                pathway_id="datasource_documentation",
                model_provider="opencode",
            )

    def test_opencode_export_parser_replaces_unknown_session_agent_with_orchestrator(self) -> None:
        export_root = Path("tmp") / "blind-agentic-eval-test" / "opencode-unknown-placeholder"
        export_root.mkdir(parents=True, exist_ok=True)
        session_id = "ses_unknown_then_orchestrator"
        (export_root / "opencode-stderr.log").write_text(
            "\n".join(
                [
                    f"timestamp=2026-06-29T03:05:16.651Z level=INFO message=stream session.id={session_id} agent=unknown mode=primary",
                    f"timestamp=2026-06-29T03:05:23.369Z level=INFO message=stream session.id={session_id} agent=brain-ds-orchestrator mode=primary",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (export_root / "opencode-stdout.jsonl").write_text(
            json.dumps(
                {
                    "type": "text",
                    "timestamp": 1782702326650,
                    "sessionID": session_id,
                    "part": {"type": "text", "text": "Unknown placeholder must not own this message."},
                }
            )
            + "\n",
            encoding="utf-8",
        )

        trace, omissions = parse_opencode_export(
            export_root,
            scenario="datasource_documentation",
            run_id="trace-unknown-placeholder",
            pathway_id="datasource_documentation",
            model_provider="opencode",
        )

        self.assertEqual(omissions, [])
        self.assertEqual([event.agent_name for event in trace.events], ["brain-ds-orchestrator", "brain-ds-orchestrator"])
        self.assertEqual(trace.events[0].action, "agent_stream")
        self.assertEqual(trace.events[1].role, "orchestrator")

    def test_opencode_export_parser_adds_user_prompt_event_from_subject_prompt_read(self) -> None:
        export_root = Path("tmp") / "blind-agentic-eval-test" / "opencode-prompt-read"
        export_root.mkdir(parents=True, exist_ok=True)
        session_id = "ses_prompt_read"
        (export_root / "opencode-stderr.log").write_text(
            f"timestamp=2026-06-29T03:05:23.369Z level=INFO message=stream session.id={session_id} agent=brain-ds-orchestrator mode=primary\n",
            encoding="utf-8",
        )
        (export_root / "opencode-stdout.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "type": "tool_use",
                            "timestamp": 1782702339008,
                            "sessionID": session_id,
                            "part": {
                                "type": "tool",
                                "tool": "read",
                                "state": {
                                    "status": "completed",
                                    "input": {"filePath": "C:/subject/PROMPT.md"},
                                    "output": "1: Document the Helios datasource.\n2: Produce stakeholder documentation.",
                                },
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "text",
                            "timestamp": 1782702339725,
                            "sessionID": session_id,
                            "part": {"type": "text", "text": "I will produce source documentation."},
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
            run_id="trace-prompt-read",
            pathway_id="datasource_documentation",
            model_provider="opencode",
        )

        self.assertEqual(omissions, [])
        self.assertEqual([event.role for event in trace.events], ["orchestrator", "tool", "user", "orchestrator"])
        self.assertEqual(trace.events[2].action, "message")
        self.assertEqual(trace.events[2].agent_name, None)
        self.assertTrue(trace.events[2].content_ref)
        self.assertTrue(trace.events[2].text_hash)

    def test_opencode_export_parser_ignores_unrelated_prompt_template_reads(self) -> None:
        export_root = Path("tmp") / "blind-agentic-eval-test" / "opencode-template-prompt-read"
        export_root.mkdir(parents=True, exist_ok=True)
        session_id = "ses_template_prompt_read"
        (export_root / "opencode-stderr.log").write_text(
            f"timestamp=2026-06-29T03:05:23.369Z level=INFO message=stream session.id={session_id} agent=brain-ds-orchestrator mode=primary\n",
            encoding="utf-8",
        )
        (export_root / "opencode-stdout.jsonl").write_text(
            json.dumps(
                {
                    "type": "tool_use",
                    "timestamp": 1782702339008,
                    "sessionID": session_id,
                    "part": {
                        "type": "tool",
                        "tool": "read",
                        "state": {
                            "status": "completed",
                            "input": {"filePath": "C:/repo/templates/PROMPT.md"},
                            "output": "1: Generic template prompt.",
                        },
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

        trace, omissions = parse_opencode_export(
            export_root,
            scenario="datasource_documentation",
            run_id="trace-template-prompt-read",
            pathway_id="datasource_documentation",
            model_provider="opencode",
        )

        self.assertEqual(omissions, [])
        self.assertEqual([event.role for event in trace.events], ["orchestrator", "tool"])
        self.assertFalse(any(event.role == "user" for event in trace.events))

    def test_opencode_export_parser_ignores_bare_prompt_basename_reads(self) -> None:
        export_root = Path("tmp") / "blind-agentic-eval-test" / "opencode-bare-prompt-read"
        export_root.mkdir(parents=True, exist_ok=True)
        session_id = "ses_bare_prompt_read"
        (export_root / "opencode-stderr.log").write_text(
            f"timestamp=2026-06-29T03:05:23.369Z level=INFO message=stream session.id={session_id} agent=brain-ds-orchestrator mode=primary\n",
            encoding="utf-8",
        )
        (export_root / "opencode-stdout.jsonl").write_text(
            json.dumps(
                {
                    "type": "tool_use",
                    "timestamp": 1782702339008,
                    "sessionID": session_id,
                    "part": {
                        "type": "tool",
                        "tool": "read",
                        "state": {
                            "status": "completed",
                            "input": {"filePath": "PROMPT.md"},
                            "output": "1: Ambiguous prompt basename without subject path.",
                        },
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

        trace, omissions = parse_opencode_export(
            export_root,
            scenario="datasource_documentation",
            run_id="trace-bare-prompt-read",
            pathway_id="datasource_documentation",
            model_provider="opencode",
        )

        self.assertEqual(omissions, [])
        self.assertEqual([event.role for event in trace.events], ["orchestrator", "tool"])
        self.assertFalse(any(event.role == "user" for event in trace.events))

    def test_collect_copies_only_transcript_artifacts_and_avoids_recursive_json_noise(self) -> None:
        subject = prepare_subject(
            scenario="datasource_documentation",
            run_id="datasource-transcript-allowlist-001",
            output_root=Path("tmp") / "blind-agentic-eval-test",
        )
        self._write_core_subject_outputs(subject.subject_path)
        opencode_dir = subject.subject_path.parent / "opencode-artifacts"
        opencode_dir.mkdir(parents=True)
        (opencode_dir / "opencode-stderr.log").write_text(
            "timestamp=2026-06-29T01:37:37.942Z level=INFO message=stream session.id=ses_1 agent=brain-ds-orchestrator mode=primary\n",
            encoding="utf-8",
        )
        (opencode_dir / "opencode-stdout.jsonl").write_text(
            json.dumps({"type": "text", "timestamp": 1782697085951, "sessionID": "ses_1", "part": {"type": "text", "text": "Documenting the datasource."}}) + "\n",
            encoding="utf-8",
        )
        (opencode_dir / "evidence").mkdir()
        (opencode_dir / "evidence" / "manifest.json").write_text("[]\n", encoding="utf-8")
        (opencode_dir / "subject").mkdir()
        (opencode_dir / "subject" / "PROMPT.md").write_text("subject prompt", encoding="utf-8")
        self._write_datasource_export(subject.subject_path.parent, session_id="ses_1")

        bundle = collect_evidence(
            scenario="datasource_documentation",
            run_id="datasource-transcript-allowlist-001",
            subject_path=subject.subject_path,
            evidence_path=subject.subject_path.parent / "evidence",
            repo_root=Path.cwd(),
            opencode_artifacts_path=opencode_dir,
        )

        manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["captured"]["opencode_export"],
            "opencode/session.json",
        )
        self.assertFalse((bundle.evidence_path / "opencode" / "evidence" / "manifest.json").exists())
        self.assertFalse((bundle.evidence_path / "opencode" / "opencode-stdout.jsonl").exists())
        self.assertNotIn("record 0 is not an object", json.dumps(manifest["omissions"]))

    def test_datasource_collect_does_not_synthesize_source_documentation_from_export_text(self) -> None:
        subject = prepare_subject(
            scenario="datasource_documentation",
            run_id="datasource-final-text-output-001",
            output_root=Path("tmp") / "blind-agentic-eval-test",
        )
        self._write_subject_graph_only(subject.subject_path)
        opencode_dir = subject.subject_path.parent / "opencode-artifacts"
        opencode_dir.mkdir(parents=True)
        (opencode_dir / "opencode-stderr.log").write_text(
            "timestamp=2026-06-29T03:05:23.369Z level=INFO message=stream session.id=ses_final agent=brain-ds-orchestrator mode=primary\n",
            encoding="utf-8",
        )
        (opencode_dir / "opencode-stdout.jsonl").write_text(
            json.dumps(
                {
                    "type": "text",
                    "timestamp": 1782702444659,
                    "sessionID": "ses_final",
                    "part": {
                        "type": "text",
                        "text": "# Source Documentation\n\nOwner: Revenue Operations. Freshness: daily. Data gaps: amount is text.",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self._write_datasource_export(subject.subject_path.parent, session_id="ses_final")

        bundle = collect_evidence(
            scenario="datasource_documentation",
            run_id="datasource-final-text-output-001",
            subject_path=subject.subject_path,
            evidence_path=subject.subject_path.parent / "evidence",
            repo_root=Path.cwd(),
            opencode_artifacts_path=opencode_dir,
        )

        manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
        generated = subject.subject_path / "generated" / "source_documentation.md"
        self.assertFalse(generated.exists())
        self.assertNotIn("generated_outputs", manifest["captured"])
        self.assertEqual(manifest["freshness_checks"]["generated_outputs"]["status"], "missing")

    def test_datasource_collect_does_not_materialize_final_text_after_title_metadata_agent(self) -> None:
        subject = prepare_subject(
            scenario="datasource_documentation",
            run_id="datasource-title-before-orchestrator-final-text-001",
            output_root=Path("tmp") / "blind-agentic-eval-test",
        )
        self._write_subject_graph_only(subject.subject_path)
        opencode_dir = subject.subject_path.parent / "opencode-artifacts"
        opencode_dir.mkdir(parents=True)
        (opencode_dir / "opencode-stderr.log").write_text(
            "\n".join(
                [
                    "timestamp=2026-06-29T03:05:16.651Z level=INFO message=stream session.id=ses_title_final agent=title mode=primary",
                    "timestamp=2026-06-29T03:05:23.369Z level=INFO message=stream session.id=ses_title_final agent=brain-ds-orchestrator mode=primary",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (opencode_dir / "opencode-stdout.jsonl").write_text(
            json.dumps(
                {
                    "type": "text",
                    "timestamp": 1782702444659,
                    "sessionID": "ses_title_final",
                    "part": {
                        "type": "text",
                        "text": "# Source Documentation\n\nTitle metadata must not block final materialization.",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self._write_datasource_export(subject.subject_path.parent, session_id="ses_title_final")

        collect_evidence(
            scenario="datasource_documentation",
            run_id="datasource-title-before-orchestrator-final-text-001",
            subject_path=subject.subject_path,
            evidence_path=subject.subject_path.parent / "evidence",
            repo_root=Path.cwd(),
            opencode_artifacts_path=opencode_dir,
        )

        generated = subject.subject_path / "generated" / "source_documentation.md"
        self.assertFalse(generated.exists())

    def test_datasource_collect_does_not_materialize_final_text_after_unknown_session_agent(self) -> None:
        subject = prepare_subject(
            scenario="datasource_documentation",
            run_id="datasource-unknown-before-orchestrator-final-text-001",
            output_root=Path("tmp") / "blind-agentic-eval-test",
        )
        self._write_subject_graph_only(subject.subject_path)
        opencode_dir = subject.subject_path.parent / "opencode-artifacts"
        opencode_dir.mkdir(parents=True)
        (opencode_dir / "opencode-stdout.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "type": "step_start",
                            "sessionID": "ses_unknown_final",
                            "agent": "unknown",
                            "part": {"type": "step-start"},
                        }
                    ),
                    json.dumps(
                        {
                            "type": "step_start",
                            "sessionID": "ses_unknown_final",
                            "agent": "brain-ds-orchestrator",
                            "part": {"type": "step-start"},
                        }
                    ),
                    json.dumps(
                        {
                            "type": "text",
                            "timestamp": 1782702444659,
                            "sessionID": "ses_unknown_final",
                            "part": {
                                "type": "text",
                                "text": "# Source Documentation\n\nUnknown session agent must be replaced by the orchestrator.",
                            },
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        self._write_datasource_export(subject.subject_path.parent, session_id="ses_unknown_final")

        collect_evidence(
            scenario="datasource_documentation",
            run_id="datasource-unknown-before-orchestrator-final-text-001",
            subject_path=subject.subject_path,
            evidence_path=subject.subject_path.parent / "evidence",
            repo_root=Path.cwd(),
            opencode_artifacts_path=opencode_dir,
        )

        generated = subject.subject_path / "generated" / "source_documentation.md"
        self.assertFalse(generated.exists())

    def test_datasource_collect_does_not_materialize_incomplete_orchestrator_source_documentation(self) -> None:
        subject = prepare_subject(
            scenario="datasource_documentation",
            run_id="datasource-incomplete-final-text-output-001",
            output_root=Path("tmp") / "blind-agentic-eval-test",
        )
        self._write_subject_graph_only(subject.subject_path)
        opencode_dir = subject.subject_path.parent / "opencode-artifacts"
        opencode_dir.mkdir(parents=True)
        (opencode_dir / "opencode-stderr.log").write_text(
            "timestamp=2026-06-29T03:05:23.369Z level=INFO message=stream session.id=ses_incomplete agent=brain-ds-orchestrator mode=primary\n",
            encoding="utf-8",
        )
        (opencode_dir / "opencode-stdout.jsonl").write_text(
            json.dumps(
                {
                    "type": "text",
                    "timestamp": 1782702444659,
                    "sessionID": "ses_incomplete",
                    "part": {
                        "type": "text",
                        "text": "# Source Documentation\n\nThis datasource response is incomplete and still needs human follow-up.",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self._write_datasource_export(subject.subject_path.parent, session_id="ses_incomplete")

        bundle = collect_evidence(
            scenario="datasource_documentation",
            run_id="datasource-incomplete-final-text-output-001",
            subject_path=subject.subject_path,
            evidence_path=subject.subject_path.parent / "evidence",
            repo_root=Path.cwd(),
            opencode_artifacts_path=opencode_dir,
        )

        manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
        generated = subject.subject_path / "generated" / "source_documentation.md"
        self.assertFalse(generated.exists())
        self.assertNotIn("generated_outputs", manifest["captured"])
        self.assertEqual(manifest["freshness_checks"]["generated_outputs"]["status"], "missing")

    def test_datasource_collect_does_not_materialize_datasource_markdown_without_exact_heading(self) -> None:
        subject = prepare_subject(
            scenario="datasource_documentation",
            run_id="datasource-contract-markdown-output-001",
            output_root=Path("tmp") / "blind-agentic-eval-test",
        )
        self._write_subject_graph_only(subject.subject_path)
        opencode_dir = subject.subject_path.parent / "opencode-artifacts"
        opencode_dir.mkdir(parents=True)
        (opencode_dir / "opencode-stderr.log").write_text(
            "timestamp=2026-06-29T03:05:23.369Z level=INFO message=stream session.id=ses_contract agent=brain-ds-orchestrator mode=primary\n",
            encoding="utf-8",
        )
        (opencode_dir / "opencode-stdout.jsonl").write_text(
            json.dumps(
                {
                    "type": "text",
                    "timestamp": 1782702444659,
                    "sessionID": "ses_contract",
                    "part": {
                        "type": "text",
                        "text": "# Datasource Profile\n\nOwner: Revenue Operations. Freshness: daily. Columns: account_id, amount.",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self._write_datasource_export(subject.subject_path.parent, session_id="ses_contract")

        collect_evidence(
            scenario="datasource_documentation",
            run_id="datasource-contract-markdown-output-001",
            subject_path=subject.subject_path,
            evidence_path=subject.subject_path.parent / "evidence",
            repo_root=Path.cwd(),
            opencode_artifacts_path=opencode_dir,
        )

        generated = subject.subject_path / "generated" / "source_documentation.md"
        self.assertFalse(generated.exists())

    def test_datasource_collect_does_not_materialize_generic_datasource_chat(self) -> None:
        subject = prepare_subject(
            scenario="datasource_documentation",
            run_id="datasource-generic-chat-output-001",
            output_root=Path("tmp") / "blind-agentic-eval-test",
        )
        self._write_subject_graph_only(subject.subject_path)
        opencode_dir = subject.subject_path.parent / "opencode-artifacts"
        opencode_dir.mkdir(parents=True)
        (opencode_dir / "opencode-stderr.log").write_text(
            "timestamp=2026-06-29T03:05:23.369Z level=INFO message=stream session.id=ses_chat agent=brain-ds-orchestrator mode=primary\n",
            encoding="utf-8",
        )
        (opencode_dir / "opencode-stdout.jsonl").write_text(
            json.dumps(
                {
                    "type": "text",
                    "timestamp": 1782702444659,
                    "sessionID": "ses_chat",
                    "part": {
                        "type": "text",
                        "text": "I can help with this datasource, but I need more context first.",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self._write_datasource_export(subject.subject_path.parent, session_id="ses_chat")

        collect_evidence(
            scenario="datasource_documentation",
            run_id="datasource-generic-chat-output-001",
            subject_path=subject.subject_path,
            evidence_path=subject.subject_path.parent / "evidence",
            repo_root=Path.cwd(),
            opencode_artifacts_path=opencode_dir,
        )

        generated = subject.subject_path / "generated" / "source_documentation.md"
        self.assertFalse(generated.exists())

    def test_datasource_collect_does_not_materialize_chronological_final_orchestrator_text(self) -> None:
        subject = prepare_subject(
            scenario="datasource_documentation",
            run_id="datasource-chronological-final-text-output-001",
            output_root=Path("tmp") / "blind-agentic-eval-test",
        )
        self._write_subject_graph_only(subject.subject_path)
        opencode_dir = subject.subject_path.parent / "opencode-artifacts"
        opencode_dir.mkdir(parents=True)
        (opencode_dir / "opencode-stderr.log").write_text(
            "timestamp=2026-06-29T03:05:23.369Z level=INFO message=stream session.id=ses_final agent=brain-ds-orchestrator mode=primary\n",
            encoding="utf-8",
        )
        (opencode_dir / "opencode-stdout-a-late.jsonl").write_text(
            json.dumps(
                {
                    "type": "text",
                    "timestamp": 1782702459999,
                    "sessionID": "ses_final",
                    "part": {
                        "type": "text",
                        "text": "# Source Documentation\n\nChronological final text selected across files.",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (opencode_dir / "opencode-stdout-z-earlier.jsonl").write_text(
            json.dumps(
                {
                    "type": "text",
                    "timestamp": 1782702444659,
                    "sessionID": "ses_final",
                    "part": {
                        "type": "text",
                        "text": "# Source Documentation\n\nEarlier draft chosen only by filename traversal.",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self._write_datasource_export(subject.subject_path.parent, session_id="ses_final")

        collect_evidence(
            scenario="datasource_documentation",
            run_id="datasource-chronological-final-text-output-001",
            subject_path=subject.subject_path,
            evidence_path=subject.subject_path.parent / "evidence",
            repo_root=Path.cwd(),
            opencode_artifacts_path=opencode_dir,
        )

        generated = subject.subject_path / "generated" / "source_documentation.md"
        self.assertFalse(generated.exists())

    def test_datasource_collect_does_not_materialize_equal_timestamp_final_text_ties(self) -> None:
        subject = prepare_subject(
            scenario="datasource_documentation",
            run_id="datasource-equal-timestamp-sequence-final-text-001",
            output_root=Path("tmp") / "blind-agentic-eval-test",
        )
        self._write_subject_graph_only(subject.subject_path)
        opencode_dir = subject.subject_path.parent / "opencode-artifacts"
        opencode_dir.mkdir(parents=True)
        (opencode_dir / "opencode-stderr.log").write_text(
            "timestamp=2026-06-29T03:05:23.369Z level=INFO message=stream session.id=ses_final agent=brain-ds-orchestrator mode=primary\n",
            encoding="utf-8",
        )
        (opencode_dir / "opencode-stdout-a-late.jsonl").write_text(
            json.dumps(
                {
                    "type": "text",
                    "timestamp": 1782702459999,
                    "sequence": 2,
                    "sessionID": "ses_final",
                    "part": {
                        "type": "text",
                        "text": "# Source Documentation\n\nSequence-late final text selected across files.",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (opencode_dir / "opencode-stdout-z-earlier.jsonl").write_text(
            json.dumps(
                {
                    "type": "text",
                    "timestamp": 1782702459999,
                    "sequence": 1,
                    "sessionID": "ses_final",
                    "part": {
                        "type": "text",
                        "text": "# Source Documentation\n\nTraversal-late draft must not win equal timestamps.",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self._write_datasource_export(subject.subject_path.parent, session_id="ses_final")

        collect_evidence(
            scenario="datasource_documentation",
            run_id="datasource-equal-timestamp-sequence-final-text-001",
            subject_path=subject.subject_path,
            evidence_path=subject.subject_path.parent / "evidence",
            repo_root=Path.cwd(),
            opencode_artifacts_path=opencode_dir,
        )

        generated = subject.subject_path / "generated" / "source_documentation.md"
        self.assertFalse(generated.exists())

    def test_datasource_collect_does_not_materialize_source_documentation_from_json_transcript(self) -> None:
        subject = prepare_subject(
            scenario="datasource_documentation",
            run_id="datasource-json-transcript-final-text-001",
            output_root=Path("tmp") / "blind-agentic-eval-test",
        )
        self._write_subject_graph_only(subject.subject_path)
        opencode_dir = subject.subject_path.parent / "opencode-artifacts"
        opencode_dir.mkdir(parents=True)
        (opencode_dir / "opencode-stderr.log").write_text(
            "timestamp=2026-06-29T03:05:23.369Z level=INFO message=stream session.id=ses_json agent=brain-ds-orchestrator mode=primary\n",
            encoding="utf-8",
        )
        (opencode_dir / "transcript.json").write_text(
            json.dumps(
                [
                    {
                        "type": "text",
                        "timestamp": 1782702459999,
                        "sequence": 1,
                        "sessionID": "ses_json",
                        "part": {
                            "type": "text",
                            "text": "# Source Documentation\n\nJSON transcript final text is materialized.",
                        },
                    }
                ]
            ),
            encoding="utf-8",
        )
        self._write_datasource_export(subject.subject_path.parent, session_id="ses_json")

        collect_evidence(
            scenario="datasource_documentation",
            run_id="datasource-json-transcript-final-text-001",
            subject_path=subject.subject_path,
            evidence_path=subject.subject_path.parent / "evidence",
            repo_root=Path.cwd(),
            opencode_artifacts_path=opencode_dir,
        )

        generated = subject.subject_path / "generated" / "source_documentation.md"
        self.assertFalse(generated.exists())

    def test_datasource_collect_does_not_materialize_subagent_only_source_documentation(self) -> None:
        subject = prepare_subject(
            scenario="datasource_documentation",
            run_id="datasource-subagent-only-output-001",
            output_root=Path("tmp") / "blind-agentic-eval-test",
        )
        self._write_subject_graph_only(subject.subject_path)
        opencode_dir = subject.subject_path.parent / "opencode-artifacts"
        opencode_dir.mkdir(parents=True)
        (opencode_dir / "opencode-stderr.log").write_text(
            "timestamp=2026-06-29T03:05:23.369Z level=INFO message=stream session.id=ses_child agent=brain-ds-source-explorer mode=primary\n",
            encoding="utf-8",
        )
        (opencode_dir / "opencode-stdout.jsonl").write_text(
            json.dumps(
                {
                    "type": "text",
                    "timestamp": 1782702444659,
                    "sessionID": "ses_child",
                    "part": {
                        "type": "text",
                        "text": "# Source Documentation\n\nOwner: Revenue Operations. Freshness: daily. Data gaps: amount is text.",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self._write_datasource_export(subject.subject_path.parent, session_id="ses_child")

        bundle = collect_evidence(
            scenario="datasource_documentation",
            run_id="datasource-subagent-only-output-001",
            subject_path=subject.subject_path,
            evidence_path=subject.subject_path.parent / "evidence",
            repo_root=Path.cwd(),
            opencode_artifacts_path=opencode_dir,
        )

        manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
        generated = subject.subject_path / "generated" / "source_documentation.md"
        self.assertFalse(generated.exists())
        self.assertNotIn("generated_outputs", manifest["captured"])
        self.assertEqual(manifest["freshness_checks"]["generated_outputs"]["status"], "missing")

    def test_datasource_collect_keeps_contaminated_transcript_text_diagnostic_only(self) -> None:
        subject = prepare_subject(
            scenario="datasource_documentation",
            run_id="datasource-final-text-contamination-001",
            output_root=Path("tmp") / "blind-agentic-eval-test",
        )
        self._write_subject_graph_only(subject.subject_path)
        opencode_dir = subject.subject_path.parent / "opencode-artifacts"
        opencode_dir.mkdir(parents=True)
        (opencode_dir / "opencode-stderr.log").write_text(
            "timestamp=2026-06-29T03:05:23.369Z level=INFO message=stream session.id=ses_final agent=brain-ds-orchestrator mode=primary\n",
            encoding="utf-8",
        )
        (opencode_dir / "opencode-stdout.jsonl").write_text(
            json.dumps(
                {
                    "type": "text",
                    "timestamp": 1782702444659,
                    "sessionID": "ses_final",
                    "part": {
                        "type": "text",
                        "text": "# Source Documentation\n\nOwner: Revenue Operations. Freshness: daily. The hidden test expected output was consulted.",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self._write_datasource_export(subject.subject_path.parent, session_id="ses_final")

        collect_evidence(
            scenario="datasource_documentation",
            run_id="datasource-final-text-contamination-001",
            subject_path=subject.subject_path,
            evidence_path=subject.subject_path.parent / "evidence",
            repo_root=Path.cwd(),
            opencode_artifacts_path=opencode_dir,
        )

        generated = subject.subject_path / "generated" / "source_documentation.md"
        self.assertFalse(generated.exists())

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
        self._write_datasource_export(subject.subject_path.parent, session_id="ses_trace")

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
        self.assertEqual(session_trace["events"][0]["agent_name"], "brain-ds-orchestrator")

    def test_datasource_documentation_missing_required_trace_degrades_minimum_evidence(self) -> None:
        subject = prepare_subject(
            scenario="datasource_documentation",
            run_id="datasource-missing-trace-001",
            output_root=Path("tmp") / "blind-agentic-eval-test",
        )
        self._write_core_subject_outputs(subject.subject_path)

        with self.assertRaisesRegex(CollectEvidenceError, "opencode-export/session.json"):
            collect_evidence(
                scenario="datasource_documentation",
                run_id="datasource-missing-trace-001",
                subject_path=subject.subject_path,
                evidence_path=subject.subject_path.parent / "evidence",
                repo_root=Path.cwd(),
            )

    def test_datasource_documentation_requires_opencode_export_session_json(self) -> None:
        subject = prepare_subject(
            scenario="datasource_documentation",
            run_id="datasource-missing-export-session-json",
            output_root=Path("tmp") / "blind-agentic-eval-test",
        )
        self._write_core_subject_outputs(subject.subject_path)
        diagnostics = subject.subject_path.parent / "diagnostics"
        diagnostics.mkdir(parents=True)
        (diagnostics / "opencode-run.stdout.jsonl").write_text(
            json.dumps(
                {
                    "type": "text",
                    "sessionID": "ses_diagnostic_only",
                    "agent_name": "brain-ds-orchestrator",
                    "part": {"type": "text", "text": "Diagnostic output only."},
                }
            )
            + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(CollectEvidenceError, "opencode-export/session.json"):
            collect_evidence(
                scenario="datasource_documentation",
                run_id="datasource-missing-export-session-json",
                subject_path=subject.subject_path,
                evidence_path=subject.subject_path.parent / "evidence",
                repo_root=Path.cwd(),
            )

    def test_datasource_documentation_uses_export_session_json_not_diagnostic_stdout(self) -> None:
        subject = prepare_subject(
            scenario="datasource_documentation",
            run_id="datasource-export-first-trace",
            output_root=Path("tmp") / "blind-agentic-eval-test",
        )
        self._write_core_subject_outputs(subject.subject_path)
        run_root = subject.subject_path.parent
        export_dir = run_root / "opencode-export"
        export_dir.mkdir(parents=True)
        (export_dir / "session.json").write_text(
            json.dumps(
                {
                    "events": [
                        {
                            "type": "text",
                            "timestamp": 1,
                            "sessionID": "ses_export",
                            "agent_name": "brain-ds-orchestrator",
                            "part": {"type": "text", "text": "Exported orchestrator text."},
                        }
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )
        diagnostics = run_root / "diagnostics"
        diagnostics.mkdir()
        (diagnostics / "opencode-run.stdout.jsonl").write_text(
            json.dumps(
                {
                    "type": "text",
                    "sessionID": "ses_diagnostic",
                    "agent_name": "build",
                    "part": {"type": "text", "text": "Diagnostic fallback must be ignored."},
                }
            )
            + "\n",
            encoding="utf-8",
        )

        bundle = collect_evidence(
            scenario="datasource_documentation",
            run_id="datasource-export-first-trace",
            subject_path=subject.subject_path,
            evidence_path=run_root / "evidence",
            repo_root=Path.cwd(),
        )

        manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
        session_trace = json.loads((bundle.evidence_path / "trace" / "session_trace.json").read_text())

        self.assertEqual(manifest["captured"]["opencode_export"], "opencode/session.json")
        self.assertEqual(manifest["trace"]["event_count"], 1)
        self.assertEqual(session_trace["events"][0]["session_id"], "ses_export")
        self.assertEqual(session_trace["events"][0]["agent_name"], "brain-ds-orchestrator")
        self.assertFalse((bundle.evidence_path / "opencode" / "opencode-run.stdout.jsonl").exists())

    def test_datasource_documentation_prefers_canonical_export_over_legacy_session_json(self) -> None:
        subject = prepare_subject(
            scenario="datasource_documentation",
            run_id="datasource-export-canonical-wins",
            output_root=Path("tmp") / "blind-agentic-eval-test",
        )
        self._write_core_subject_outputs(subject.subject_path)
        run_root = subject.subject_path.parent
        self._write_datasource_export(run_root, session_id="ses_canonical_export")
        legacy_dir = run_root / "opencode-artifacts"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "session.json").write_text(
            json.dumps(
                {
                    "events": [
                        {
                            "type": "text",
                            "timestamp": 1,
                            "sessionID": "ses_legacy_artifact",
                            "agent_name": "brain-ds-orchestrator",
                            "part": {"type": "text", "text": "Legacy artifacts are diagnostics only."},
                        }
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )
        bundle = collect_evidence(
            scenario="datasource_documentation",
            run_id="datasource-export-canonical-wins",
            subject_path=subject.subject_path,
            evidence_path=run_root / "evidence",
            repo_root=Path.cwd(),
            opencode_artifacts_path=legacy_dir,
        )

        manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
        session_trace = json.loads((bundle.evidence_path / "trace" / "session_trace.json").read_text())

        self.assertEqual(manifest["captured"]["opencode_export"], "opencode/session.json")
        self.assertEqual(session_trace["events"][0]["session_id"], "ses_canonical_export")
        self.assertNotEqual(session_trace["events"][0]["session_id"], "ses_legacy_artifact")

    def test_datasource_documentation_rejects_legacy_session_json_without_canonical_export(self) -> None:
        subject = prepare_subject(
            scenario="datasource_documentation",
            run_id="datasource-legacy-session-json-rejected",
            output_root=Path("tmp") / "blind-agentic-eval-test",
        )
        self._write_core_subject_outputs(subject.subject_path)
        legacy_dir = subject.subject_path.parent / "opencode-artifacts"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "session.json").write_text(
            json.dumps(
                {
                    "events": [
                        {
                            "type": "text",
                            "timestamp": 1,
                            "sessionID": "ses_legacy_only",
                            "agent_name": "brain-ds-orchestrator",
                            "part": {"type": "text", "text": "This is not canonical export evidence."},
                        }
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(CollectEvidenceError, "opencode-export/session.json"):
            collect_evidence(
                scenario="datasource_documentation",
                run_id="datasource-legacy-session-json-rejected",
                subject_path=subject.subject_path,
                evidence_path=subject.subject_path.parent / "evidence",
                repo_root=Path.cwd(),
                opencode_artifacts_path=legacy_dir,
            )

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
        self._write_datasource_export(subject.subject_path.parent, session_id="ses_stable_trace")

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

    def test_opencode_export_parser_rejects_mixed_shape_drifted_text_record(self) -> None:
        export_root = Path("tmp") / "blind-agentic-eval-test" / "opencode-export-shape-drift"
        export_root.mkdir(parents=True, exist_ok=True)
        (export_root / "session.json").write_text(
            json.dumps(
                {
                    "events": [
                        {
                            "type": "text",
                            "timestamp": 1,
                            "sessionID": "ses_valid",
                            "agent_name": "brain-ds-orchestrator",
                            "part": {"type": "text", "text": "Valid exported text."},
                        },
                        {
                            "type": "text",
                            "timestamp": 2,
                            "part": {"type": "text", "text": "Shape drift lacks session and attribution."},
                        },
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(TraceSchemaError, "valid attribution/session"):
            parse_opencode_export(
                export_root,
                scenario="datasource_documentation",
                run_id="trace-shape-drift",
                pathway_id="datasource_documentation",
                model_provider="opencode",
            )

    def test_opencode_export_parser_rejects_session_alias_only_unknown_shape(self) -> None:
        export_root = Path("tmp") / "blind-agentic-eval-test" / "opencode-export-session-alias-only"
        export_root.mkdir(parents=True, exist_ok=True)
        (export_root / "session.json").write_text(
            json.dumps(
                {
                    "kind": "assistant_output",
                    "sessionID": "ses_unknown",
                    "actor": "brain-ds-orchestrator",
                    "payload": {"message": "Unknown export shape"},
                }
            )
            + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(TraceSchemaError, "unknown OpenCode export schema"):
            parse_opencode_export(
                export_root,
                scenario="datasource_documentation",
                run_id="trace-session-alias-only",
                pathway_id="datasource_documentation",
                model_provider="opencode",
            )

    def test_datasource_documentation_manifest_uses_datasource_run_metadata(self) -> None:
        subject = prepare_subject(
            scenario="datasource_documentation",
            run_id="datasource-metadata-001",
            output_root=Path("tmp") / "blind-agentic-eval-test",
        )
        self._write_core_subject_outputs(subject.subject_path)
        self._write_datasource_export(subject.subject_path.parent, session_id="ses_metadata")

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
        self._write_datasource_export(subject.subject_path.parent, session_id="ses_freshness_local")

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
        self._write_datasource_export(subject.subject_path.parent, session_id="ses_external_graph")
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
        self._write_datasource_export(subject.subject_path.parent, session_id="ses_freshness_stale")

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

    def _write_datasource_export(self, run_root: Path, *, session_id: str = "ses_export") -> None:
        export_dir = run_root / "opencode-export"
        export_dir.mkdir(parents=True, exist_ok=True)
        (export_dir / "session.json").write_text(
            json.dumps(
                {
                    "events": [
                        {
                            "type": "text",
                            "timestamp": 1,
                            "sessionID": session_id,
                            "agent_name": "brain-ds-orchestrator",
                            "part": {"type": "text", "text": "Exported datasource documentation trace."},
                        }
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def _write_subject_graph_only(self, subject_path: Path) -> None:
        brain_ds = subject_path / ".brain_ds"
        brain_ds.mkdir(parents=True, exist_ok=True)
        (brain_ds / "store.db").write_bytes(b"sqlite graph snapshot")
