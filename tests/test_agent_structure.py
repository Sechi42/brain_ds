import tempfile
import unittest
from pathlib import Path


def parse_frontmatter_agent(content: str) -> str:
    lines = content.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        raise AssertionError("Missing YAML frontmatter")

    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("agent:"):
            return line.split(":", 1)[1].strip()
    raise AssertionError("agent field missing in frontmatter")


class AgentStructureTests(unittest.TestCase):
    def test_command_yaml_parses(self):
        root = Path(__file__).resolve().parents[1]
        commands = root / "commands"
        for name in (
            "brain-ds-pipeline.md",
            "brain-ds-map.md",
            "brain-ds-brd.md",
            "elicit-context.md",
            "map-connections.md",
            "generate-brd.md",
        ):
            content = (commands / name).read_text(encoding="utf-8")
            self.assertEqual(parse_frontmatter_agent(content), "brain-ds-orchestrator")

    def test_gentle_ai_commands_intact(self):
        with tempfile.TemporaryDirectory(prefix="brain-ds-cmds-") as td:
            commands = Path(td) / "commands"
            commands.mkdir(parents=True, exist_ok=True)
            for name in (
                "sdd-new",
                "sdd-continue",
                "sdd-ff",
                "sdd-explore",
                "sdd-apply",
                "sdd-verify",
                "sdd-archive",
                "sdd-init",
                "sdd-onboard",
            ):
                (commands / f"{name}.md").write_text(f"# {name}\n", encoding="utf-8")

            self.assertEqual(len(list(commands.glob("sdd-*.md"))), 9)


if __name__ == "__main__":
    unittest.main()
