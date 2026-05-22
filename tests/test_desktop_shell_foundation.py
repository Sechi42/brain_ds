from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TAURI_ROOT = ROOT / "src-tauri"


class DesktopShellFoundationTests(unittest.TestCase):
    def test_tauri_foundation_files_exist(self) -> None:
        expected = [
            TAURI_ROOT / "Cargo.toml",
            TAURI_ROOT / "tauri.conf.json",
            TAURI_ROOT / "capabilities" / "default.json",
            TAURI_ROOT / "bootstrap" / "index.html",
            TAURI_ROOT / "bootstrap" / "bootstrap.js",
            TAURI_ROOT / "src" / "main.rs",
        ]
        missing = [str(path.relative_to(ROOT)) for path in expected if not path.exists()]
        self.assertEqual([], missing)

    def test_tauri_config_loads_bootstrap_html(self) -> None:
        config_path = TAURI_ROOT / "tauri.conf.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual("brain_ds", config["app"]["windows"][0]["title"])
        self.assertEqual("bootstrap", config["build"]["frontendDist"])

    def test_capabilities_include_dialog_and_shell_with_scoped_sidecar(self) -> None:
        capability_path = TAURI_ROOT / "capabilities" / "default.json"
        capability = json.loads(capability_path.read_text(encoding="utf-8"))

        permissions = capability["permissions"]
        self.assertIn("dialog:default", permissions)

        shell_entries = [
            permission
            for permission in permissions
            if isinstance(permission, dict) and "identifier" in permission
        ]
        self.assertEqual(1, len(shell_entries))
        self.assertEqual("shell:allow-execute", shell_entries[0]["identifier"])

        allow = shell_entries[0]["allow"][0]
        self.assertEqual("binaries/brain_ds", allow["name"])
        self.assertTrue(allow["sidecar"])
        self.assertTrue(allow["args"])

    def test_icons_present(self) -> None:
        icons = [
            "32x32.png",
            "128x128.png",
            "128x128@2x.png",
            "icon.ico",
            "icon.icns",
        ]
        missing = [name for name in icons if not (TAURI_ROOT / "icons" / name).exists()]
        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main()
