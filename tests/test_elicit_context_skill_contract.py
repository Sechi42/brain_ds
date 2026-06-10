from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL_PATHS = [
    p
    for p in [
        PROJECT_ROOT / "skills" / "elicit-context" / "SKILL.md",
        PROJECT_ROOT / ".opencode" / "skills" / "elicit-context" / "SKILL.md",
    ]
    if p.exists()
]


class TestElicitContextSkillContract(unittest.TestCase):
    def test_skill_contract_mentions_sqlite_write_tools(self) -> None:
        required_markers = [
            '"tool": "create_graph"',
            '"tool": "update_node"',
            '"tool": "add_edge"',
            'If it reports the graph already exists, continue',
            'Persist domain entities through MCP SQLite tools, not `mem_save`.',
        ]
        self.assertTrue(SKILL_PATHS, "No SKILL.md files found to test")
        for path in SKILL_PATHS:
            content = path.read_text(encoding="utf-8")
            for marker in required_markers:
                with self.subTest(path=path.name, marker=marker):
                    self.assertIn(marker, content)

    def test_skill_question_bank_prioritizes_data_source(self) -> None:
        self.assertTrue(SKILL_PATHS, "No SKILL.md files found to test")
        for path in SKILL_PATHS:
            content = path.read_text(encoding="utf-8")
            question_bank = content.split("## Question Bank", 1)[1].split(
                "Default behavior:", 1
            )[0]
            data_source_index = question_bank.index("| Data Source |")
            department_index = question_bank.index("| Department |")
            role_index = question_bank.index("| Role |")
            with self.subTest(path=path.name):
                self.assertLess(data_source_index, department_index)
                self.assertLess(data_source_index, role_index)

    def test_skill_data_source_completeness_rule_present(self) -> None:
        required_markers = [
            "Data Source completeness rule",
            "Kind of source",
            "System name",
            "Database name",
            "Table name",
            "Key columns/fields",
            "Purpose",
            "Owner",
            "Underspecified",
        ]
        self.assertTrue(SKILL_PATHS, "No SKILL.md files found to test")
        for path in SKILL_PATHS:
            content = path.read_text(encoding="utf-8")
            for marker in required_markers:
                with self.subTest(path=path.name, marker=marker):
                    self.assertIn(marker, content)

    def test_skill_data_source_question_bank_covers_structure(self) -> None:
        required_topics = [
            "database and tables",
            "workbook and sheets",
            "columns/fields",
            "used for",
            "owns or manages",
            "refreshed or updated",
        ]
        self.assertTrue(SKILL_PATHS, "No SKILL.md files found to test")
        for path in SKILL_PATHS:
            content = path.read_text(encoding="utf-8")
            question_bank = content.split("## Question Bank", 1)[1].split(
                "Default behavior:", 1
            )[0]
            data_source_row = [
                line
                for line in question_bank.splitlines()
                if "| Data Source |" in line
            ][0]
            for topic in required_topics:
                with self.subTest(path=path.name, topic=topic):
                    self.assertIn(topic, data_source_row)

    def test_skill_copies_are_in_sync(self) -> None:
        if len(SKILL_PATHS) < 2:
            self.skipTest("Fewer than 2 SKILL.md copies found; nothing to sync-check")
        contents = [p.read_text(encoding="utf-8") for p in SKILL_PATHS]
        self.assertEqual(
            contents[0],
            contents[1],
            f"SKILL.md copies are out of sync: {SKILL_PATHS[0]} vs {SKILL_PATHS[1]}",
        )


if __name__ == "__main__":
    unittest.main()
