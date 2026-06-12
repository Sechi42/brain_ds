from __future__ import annotations

import json
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TAURI_ROOT = ROOT / "src-tauri"


class WindowsExeInstallerPr1FoundationTests(unittest.TestCase):
    def test_build_rs_exists_with_tauri_build_call(self) -> None:
        build_rs = TAURI_ROOT / "build.rs"
        self.assertTrue(build_rs.exists(), "src-tauri/build.rs must exist")

        normalized = "".join(build_rs.read_text(encoding="utf-8").split())
        self.assertIn("fnmain(){tauri_build::build()}", normalized)

    def test_cargo_toml_exposes_bundled_feature_and_unstable_tauri(self) -> None:
        cargo_toml = tomllib.loads((TAURI_ROOT / "Cargo.toml").read_text(encoding="utf-8"))

        features = cargo_toml["features"]
        self.assertIn("bundled", features)
        self.assertEqual([], features["bundled"])

        tauri_dep = cargo_toml["dependencies"]["tauri"]
        self.assertEqual("2.0.0", tauri_dep["version"])
        self.assertIn("unstable", tauri_dep["features"])

    def test_tauri_conf_includes_nsis_with_webview_bootstrapper_and_nsis_fields(self) -> None:
        config = json.loads((TAURI_ROOT / "tauri.conf.json").read_text(encoding="utf-8"))
        bundle = config["bundle"]

        self.assertIn("nsis", bundle["targets"])
        self.assertEqual(["binaries/brain_ds"], bundle["externalBin"])
        self.assertEqual({"type": "embedBootstrapper"}, bundle["windows"]["webviewInstallMode"])
        self.assertEqual("../LICENSE", bundle["licenseFile"])

        nsis = bundle["windows"]["nsis"]
        self.assertEqual("currentUser", nsis["installMode"])

    def test_capability_scopes_shell_execution_to_bundled_sidecar(self) -> None:
        capability = json.loads((TAURI_ROOT / "capabilities" / "default.json").read_text(encoding="utf-8"))
        shell_rule = next(
            permission for permission in capability["permissions"] if isinstance(permission, dict) and permission.get("identifier") == "shell:allow-execute"
        )

        allowed_names = [entry["name"] for entry in shell_rule["allow"]]
        self.assertIn("binaries/brain_ds", allowed_names)

    def test_binaries_placeholder_and_gitignore_exist(self) -> None:
        binaries_dir = TAURI_ROOT / "binaries"
        self.assertTrue((binaries_dir / ".gitkeep").exists())
        self.assertTrue((binaries_dir / ".gitignore").exists())
        gitignore = (binaries_dir / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("*.exe", gitignore)

    def test_root_gitignore_includes_windows_installer_build_artifacts(self) -> None:
        text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("dist/", text)
        self.assertIn(".build-venv/", text)
        self.assertIn("build/pyinstaller/", text)
        self.assertIn("src-tauri/binaries-stage/", text)

    def test_tauri_conf_frontend_dist_is_directory_and_global_tauri_enabled(self) -> None:
        """
        Two structural contracts required for the bootstrap UI to work in the installer:

        1. build.frontendDist must point at the bootstrap DIRECTORY (not index.html),
           so that bootstrap.js is bundled as a sibling asset and the <script> tag resolves.
        2. app.withGlobalTauri must be true so that window.__TAURI__ is injected and
           the invoke() call in bootstrap.js is available at runtime.
        """
        config = json.loads((TAURI_ROOT / "tauri.conf.json").read_text(encoding="utf-8"))

        self.assertEqual(
            "bootstrap",
            config["build"]["frontendDist"],
            "frontendDist must be the 'bootstrap' directory, not a specific file",
        )
        self.assertTrue(
            config["app"].get("withGlobalTauri"),
            "app.withGlobalTauri must be true so window.__TAURI__ is injected",
        )


if __name__ == "__main__":
    unittest.main()
