from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch


class MCPOpenCodeConfigTests(unittest.TestCase):
    def test_generate_opencode_config_shape(self) -> None:
        from brain_ds.mcp.config import generate_opencode_config

        with patch("brain_ds.mcp.config.shutil.which", return_value="/fake/bin/brain_ds"):
            config = generate_opencode_config(Path("."))

        server = config["mcp"]["brain_ds"]
        self.assertEqual(server["type"], "local")
        self.assertTrue(server["enabled"])
        self.assertEqual(server["command"][1:], ["mcp", "--project-root", "."])
        self.assertEqual(server["environment"], {"BRAIN_DS_PROJECT_ROOT": "."})
        self.assertTrue(os.path.isabs(server["command"][0]))
        self.assertTrue(server["command"][0].replace("\\", "/").endswith("fake/bin/brain_ds"))

    def test_generate_opencode_config_absolute_flag(self) -> None:
        from brain_ds.mcp.config import generate_opencode_config

        with patch("brain_ds.mcp.config.shutil.which", return_value="/fake/bin/brain_ds"):
            config = generate_opencode_config(Path("."), absolute=True)

        server = config["mcp"]["brain_ds"]
        root_value = server["command"][3]
        self.assertTrue(os.path.isabs(root_value))
        self.assertEqual(server["environment"]["BRAIN_DS_PROJECT_ROOT"], root_value)

    def test_generate_opencode_config_raises_when_not_on_path(self) -> None:
        from brain_ds.mcp.config import generate_opencode_config

        with patch("brain_ds.mcp.config.shutil.which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "PATH"):
                generate_opencode_config(Path("."))

    def test_generate_opencode_config_json_roundtrip(self) -> None:
        from brain_ds.mcp.config import generate_opencode_config

        with patch("brain_ds.mcp.config.shutil.which", return_value="C:/tools/brain_ds.exe"):
            config = generate_opencode_config(Path("C:/Users/dev/project"))

        encoded = json.dumps(config)
        decoded = json.loads(encoded)
        self.assertEqual(decoded, config)

    def test_no_opencode_or_global_config_path_construction(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        targets = [
            project_root / "brain_ds" / "mcp" / "config.py",
            project_root / "brain_ds" / "ui" / "cli.py",
        ]
        forbidden = [
            "opencode.json",
            "opencode.jsonc",
            "~/.config/opencode",
            "~/.claude",
            "expanduser",
            "os.path.expanduser",
        ]

        for target in targets:
            content = target.read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, content)


if __name__ == "__main__":
    unittest.main()
