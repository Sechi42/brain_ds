from __future__ import annotations

import unittest
from pathlib import Path


class McpNoShellTests(unittest.TestCase):
    def test_mcp_package_has_no_shell_or_dynamic_exec_calls(self) -> None:
        root = Path(__file__).resolve().parents[1]
        mcp_dir = root / "brain_ds" / "mcp"
        forbidden = ("subprocess", "os.system", "eval(", "exec(", "__import__")

        offenders: list[str] = []
        if not mcp_dir.exists():
            self.assertEqual(offenders, [])
            return

        for file_path in mcp_dir.rglob("*.py"):
            content = file_path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in content:
                    offenders.append(f"{file_path.relative_to(root)} contains '{token}'")

        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
