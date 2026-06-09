from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL_PATHS = [
    PROJECT_ROOT / "skills" / "elicit-context" / "SKILL.md",
    PROJECT_ROOT / ".opencode" / "skills" / "elicit-context" / "SKILL.md",
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
        for path in SKILL_PATHS:
            content = path.read_text(encoding="utf-8")
            for marker in required_markers:
                with self.subTest(path=path.name, marker=marker):
                    self.assertIn(marker, content)

    def test_skill_question_bank_prioritizes_data_source(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
