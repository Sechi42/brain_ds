from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TAURI_ROOT = ROOT / "src-tauri"


class MacOSPackagingTests(unittest.TestCase):
    def test_tauri_conf_includes_windows_and_macos_bundle_targets(self) -> None:
        config = json.loads((TAURI_ROOT / "tauri.conf.json").read_text(encoding="utf-8"))
        bundle = config["bundle"]

        self.assertIn("nsis", bundle["targets"])
        self.assertIn("dmg", bundle["targets"])
        self.assertIn("app", bundle["targets"])
        self.assertEqual("10.15", bundle["macOS"]["minimumSystemVersion"])

    def test_build_macos_sh_has_secure_gate_sequence(self) -> None:
        script = ROOT / "scripts" / "build-macos.sh"
        self.assertTrue(script.exists(), "scripts/build-macos.sh must exist")

        content = script.read_text(encoding="utf-8")
        self.assertIn("#!/usr/bin/env bash", content)
        self.assertIn("cargo", content)
        self.assertIn("rustc", content)
        self.assertIn("uv", content)
        self.assertIn("pnpm", content)
        self.assertIn("cargo tauri --version", content)
        self.assertIn("export PNPM_CONFIG_IGNORE_SCRIPTS=true", content)
        self.assertIn("pnpm install --frozen-lockfile", content)
        self.assertIn("pnpm audit --audit-level high", content)
        self.assertIn("pnpm run build", content)
        self.assertIn("pnpm run bundle-size", content)
        self.assertIn("brain_ds.ui.bundle_freshness", content)
        self.assertIn("viewer.bundle.js", content)
        self.assertIn("uv venv --python 3.13", content)
        self.assertIn("pyinstaller==6.11.1", content)
        self.assertIn("ui --probe", content)
        self.assertIn("READY", content)
        self.assertIn("cargo tauri build --features bundled --bundles dmg,app", content)
        self.assertLess(content.index("brain_ds.ui.bundle_freshness"), content.index("cargo tauri build --features bundled --bundles dmg,app"))

    def test_build_macos_sh_uses_unix_paths_and_darwin_sidecar_names(self) -> None:
        script = ROOT / "scripts" / "build-macos.sh"
        self.assertTrue(script.exists(), "scripts/build-macos.sh must exist")

        content = script.read_text(encoding="utf-8")
        self.assertIn('"$venv_path/bin/python"', content)
        self.assertIn("uname -m", content)
        self.assertIn("x86_64-apple-darwin", content)
        self.assertIn("aarch64-apple-darwin", content)
        self.assertIn("src-tauri/binaries/brain_ds-", content)

    def test_gitignore_covers_macos_sidecar(self) -> None:
        gitignore = (TAURI_ROOT / "binaries" / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("brain_ds-*-apple-darwin*", gitignore)

    def test_macos_ci_workflow_builds_on_macos_runner_with_secure_delivery(self) -> None:
        workflow = ROOT / ".github" / "workflows" / "build-macos-exe.yml"
        self.assertTrue(workflow.exists(), ".github/workflows/build-macos-exe.yml must exist")

        content = workflow.read_text(encoding="utf-8")
        # macOS runner, not Windows.
        self.assertIn("runs-on: macos-latest", content)
        self.assertNotIn("windows-latest", content)
        # Invokes the macOS build script and ships a .dmg.
        self.assertIn("scripts/build-macos.sh", content)
        self.assertIn(".dmg", content)
        # Same supply-chain / private-delivery posture as the Windows workflow.
        self.assertIn("npm install -g pnpm@11.0.8", content)
        self.assertIn("--locked", content)
        self.assertIn("--draft", content)
        self.assertIn("if: github.event_name != 'pull_request'", content)
        # Deterministic, arch-tagged artifact naming.
        self.assertIn("brain_ds-macos-", content)

    def test_install_doc_covers_macos_unsigned_build(self) -> None:
        install = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
        self.assertIn("./scripts/build-macos.sh", install)
        self.assertIn("Gatekeeper", install)
        self.assertIn("bundle-freshness", install)
        self.assertIn("pnpm --dir brain_ds/ui run build", install)


if __name__ == "__main__":
    unittest.main()
