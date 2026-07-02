from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = REPO_ROOT / "skills" / "blind-agentic-path-evaluator" / "SKILL.md"
OPENCODE_SKILL_PATH = REPO_ROOT / ".opencode" / "skills" / "blind-agentic-path-evaluator" / "SKILL.md"
AGENT_PATH = REPO_ROOT / ".claude" / "agents" / "blind-agentic-path-evaluator.md"


class BlindAgenticPathEvaluatorContractTests(unittest.TestCase):
    def test_skill_declares_required_launch_questions_and_context_packet(self) -> None:
        content = SKILL_PATH.read_text(encoding="utf-8")

        for required in (
            "path",
            "OpenCode Go model",
            "report destination",
            "run label",
            "context packet",
            "orchestrator",
        ):
            with self.subTest(required=required):
                self.assertIn(required, content)

    def test_skill_declares_one_path_only_and_rejects_multi_path_contexts(self) -> None:
        content = SKILL_PATH.read_text(encoding="utf-8")

        self.assertIn("exactly one path", content)
        self.assertIn("Do not evaluate multiple paths", content)
        self.assertIn("reject", content)

    def test_skill_requires_evidence_grounded_behavioral_report_sections(self) -> None:
        content = SKILL_PATH.read_text(encoding="utf-8")

        for required in (
            "good",
            "bad",
            "learned",
            "improvable",
            "non-improvable constraints",
            "improvement plan",
            "evidence references",
            "visibility limits",
            "omissions",
        ):
            with self.subTest(required=required):
                self.assertIn(required, content)

    def test_skill_declares_user_selected_file_engram_or_both_destination(self) -> None:
        content = SKILL_PATH.read_text(encoding="utf-8")

        self.assertIn("file", content)
        self.assertIn("Engram", content)
        self.assertIn("both", content)
        self.assertIn("user-selected", content)

    def test_skill_requires_engram_key_points_for_every_completed_evaluation(self) -> None:
        content = SKILL_PATH.read_text(encoding="utf-8")

        self.assertIn("MUST save concise key points to Engram for every completed evaluation", content)
        self.assertNotIn("when requested by the protocol", content)

    def test_skill_requires_cognitive_benchmark_before_behavioral_judgment(self) -> None:
        content = SKILL_PATH.read_text(encoding="utf-8")

        self.assertIn("Cognitive benchmark first", content)
        self.assertIn("read and understand the selected target flow", content)
        self.assertIn("before judging behavior", content)
        self.assertIn("Use that benchmark as the basis for behavioral analysis", content)

    def test_opencode_skill_mirror_is_byte_identical(self) -> None:
        self.assertEqual(
            SKILL_PATH.read_text(encoding="utf-8"),
            OPENCODE_SKILL_PATH.read_text(encoding="utf-8"),
        )

    def test_local_agent_uses_skill_and_declares_single_path_protocol(self) -> None:
        content = AGENT_PATH.read_text(encoding="utf-8")

        self.assertIn("blind-agentic-path-evaluator", content)
        self.assertIn("skills/blind-agentic-path-evaluator/SKILL.md", content)
        self.assertIn("exactly one path", content)
        self.assertIn("context packet", content)
        self.assertIn("MUST save concise key points to Engram", content)
        self.assertIn("cognitive benchmark", content)


if __name__ == "__main__":
    unittest.main()
