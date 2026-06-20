from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


class AppGenerationWorkflowTests(unittest.TestCase):
    def _workflow(self, name: str) -> str:
        path = WORKFLOWS / name
        self.assertTrue(path.exists(), f"{path} must exist")
        return path.read_text(encoding="utf-8")

    def test_windows_workflow_rebuilds_and_verifies_ui_before_packaging_current_commit(self) -> None:
        content = self._workflow("build-windows-exe.yml")

        checkout = content.index("uses: actions/checkout@")
        guard = content.index("name: Rebuild and verify fresh UI bundle")
        clean = content.index("name: Force fresh Tauri bundle")
        package = content.index("name: Build Windows installer")

        self.assertLess(checkout, guard)
        self.assertLess(guard, clean)
        self.assertLess(clean, package)
        self.assertIn("pnpm --dir brain_ds/ui install --frozen-lockfile", content)
        self.assertIn("pnpm --dir brain_ds/ui run build", content)
        self.assertIn("uv run python -m brain_ds.ui.bundle_freshness --ui-root brain_ds/ui", content)
        self.assertIn("git diff --exit-code -- brain_ds/ui/assets/viewer.bundle.js brain_ds/ui/assets/viewer.bundle.css", content)
        self.assertIn("cargo clean --release -p brain_ds_desktop --manifest-path src-tauri/Cargo.toml", content)
        self.assertIn("Remove-Item -Recurse -Force src-tauri/target/release/bundle", content)
        self.assertNotIn("actions/download-artifact", content)

    def test_macos_workflow_rebuilds_and_verifies_ui_before_packaging_current_commit(self) -> None:
        content = self._workflow("build-macos-exe.yml")

        checkout = content.index("uses: actions/checkout@")
        guard = content.index("name: Rebuild and verify fresh UI bundle")
        clean = content.index("name: Force fresh Tauri bundle")
        package = content.index("name: Build macOS bundle")

        self.assertLess(checkout, guard)
        self.assertLess(guard, clean)
        self.assertLess(clean, package)
        self.assertIn("pnpm --dir brain_ds/ui install --frozen-lockfile", content)
        self.assertIn("pnpm --dir brain_ds/ui run build", content)
        self.assertIn("uv run python -m brain_ds.ui.bundle_freshness --ui-root brain_ds/ui", content)
        self.assertIn("git diff --exit-code -- brain_ds/ui/assets/viewer.bundle.js brain_ds/ui/assets/viewer.bundle.css", content)
        self.assertIn("cargo clean --release -p brain_ds_desktop --manifest-path src-tauri/Cargo.toml", content)
        self.assertIn("rm -rf src-tauri/target/release/bundle", content)
        self.assertIn("brain_ds-macos-", content)
        self.assertNotIn("actions/download-artifact", content)


if __name__ == "__main__":
    unittest.main()
