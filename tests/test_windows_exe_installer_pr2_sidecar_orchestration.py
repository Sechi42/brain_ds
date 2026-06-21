from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TAURI_ROOT = ROOT / "src-tauri"


class WindowsExeInstallerPr2SidecarOrchestrationTests(unittest.TestCase):
    def test_tauri_reqwest_enables_blocking_feature_for_readiness_probe(self) -> None:
        cargo_toml = TAURI_ROOT / "Cargo.toml"
        content = cargo_toml.read_text(encoding="utf-8")

        self.assertIn('reqwest = { version = "0.12.12"', content)
        self.assertIn('"blocking"', content)

    def test_cli_supports_probe_mode_for_sidecar_smoke_checks(self) -> None:
        cli_py = ROOT / "brain_ds" / "ui" / "cli.py"
        content = cli_py.read_text(encoding="utf-8")

        self.assertIn("--probe", content)
        self.assertIn("READY", content)
        self.assertIn('"127.0.0.1", 0', content)

    def test_desktop_rs_declares_dev_vs_bundled_cfg_split(self) -> None:
        desktop_rs = TAURI_ROOT / "src" / "desktop.rs"
        content = desktop_rs.read_text(encoding="utf-8")

        self.assertIn('#[cfg(not(feature = "bundled"))]', content)
        self.assertIn('#[cfg(feature = "bundled")]', content)
        self.assertIn('sidecar("brain_ds")', content)
        self.assertIn('Command::new("uv")', content)

    def test_desktop_rs_uses_ephemeral_port_and_runtime_url_building(self) -> None:
        desktop_rs = TAURI_ROOT / "src" / "desktop.rs"
        content = desktop_rs.read_text(encoding="utf-8")

        self.assertIn('TcpListener::bind("127.0.0.1:0")', content)
        self.assertIn("local_addr()", content)
        self.assertIn('format!("http://{DESKTOP_SERVER_HOST}:{port}")', content)

    def test_pyinstaller_spec_exists_with_onefile_and_hidden_imports(self) -> None:
        spec_file = ROOT / "scripts" / "pyinstaller" / "brain_ds.spec"
        self.assertTrue(spec_file.exists(), "scripts/pyinstaller/brain_ds.spec must exist")

        content = spec_file.read_text(encoding="utf-8")
        self.assertIn("name='brain_ds'", content)
        self.assertIn("hiddenimports", content)
        self.assertIn("uvicorn.loops.auto", content)
        self.assertIn("brain_ds.ui", content)
        self.assertIn("onefile", content.lower())
        self.assertIn('"brain_ds" / "__main__.py"', content)
        self.assertNotIn('"brain_ds" / "ui" / "__main__.py"', content)
        # Optional connection backends are lazy-imported, so the spec must
        # collect them explicitly or the frozen exe raises "boto3 is not
        # installed" at secret-validation time.
        self.assertIn("collect_all", content)
        for pkg in ("boto3", "psycopg", "gspread"):
            self.assertIn(pkg, content, f"spec must bundle optional backend {pkg!r}")

    def test_build_script_has_preflight_and_bundled_build_contract(self) -> None:
        script = ROOT / "scripts" / "build-windows-exe.ps1"
        self.assertTrue(script.exists(), "scripts/build-windows-exe.ps1 must exist")

        content = script.read_text(encoding="utf-8")
        self.assertIn("cargo", content)
        self.assertIn("rustc", content)
        self.assertIn("uv", content)
        self.assertIn("cargo tauri --version", content)
        self.assertIn("PyInstaller failed", content)
        self.assertIn("Tauri build failed", content)
        self.assertIn("cargo tauri build --features bundled --bundles nsis", content)
        self.assertIn("dist", content)

    def test_build_script_enforces_security_constraints_for_package_tools(self) -> None:
        script = ROOT / "scripts" / "build-windows-exe.ps1"
        content = script.read_text(encoding="utf-8")

        self.assertIn('Require-Command "pnpm"', content)
        self.assertIn('$env:PNPM_CONFIG_IGNORE_SCRIPTS = "true"', content)
        self.assertIn('pnpm install --frozen-lockfile', content)
        self.assertIn('pnpm audit --audit-level high', content)
        self.assertIn('pnpm run build', content)
        self.assertIn('pnpm run bundle-size', content)
        self.assertIn("--locked", content)

    def test_build_script_rebuilds_bundle_before_tauri_and_checks_freshness(self) -> None:
        script = ROOT / "scripts" / "build-windows-exe.ps1"
        content = script.read_text(encoding="utf-8")

        self.assertIn('viewer.bundle.js', content)
        self.assertIn('pnpm run build', content)
        self.assertIn('pnpm run bundle-size', content)
        self.assertIn('brain_ds.ui.bundle_freshness', content)
        self.assertIn('cargo tauri build --features bundled --bundles nsis', content)
        self.assertLess(content.index('pnpm run build'), content.index('cargo tauri build --features bundled --bundles nsis'))
        self.assertLess(content.index('brain_ds.ui.bundle_freshness'), content.index('cargo tauri build --features bundled --bundles nsis'))

    def test_workflow_pins_pnpm_before_running_windows_build(self) -> None:
        workflow = ROOT / '.github' / 'workflows' / 'build-windows-exe.yml'
        content = workflow.read_text(encoding='utf-8')

        self.assertIn('Install pnpm (exact pinned version)', content)
        self.assertIn('npm install -g pnpm@11.0.8', content)
        self.assertIn('pnpm --version', content)

    def test_ui_package_declares_exact_pnpm_package_manager(self) -> None:
        package_json = ROOT / 'brain_ds' / 'ui' / 'package.json'
        content = package_json.read_text(encoding='utf-8')

        self.assertIn('"packageManager": "pnpm@11.0.8"', content)

    def test_build_script_pins_uv_python_to_3_13_for_pyinstaller_compatibility(self) -> None:
        script = ROOT / "scripts" / "build-windows-exe.ps1"
        content = script.read_text(encoding="utf-8")

        self.assertIn('uv venv --python 3.13', content)
        self.assertIn('pyinstaller==6.11.1', content)
        # Editable install MUST include the connection extras so boto3/psycopg/
        # gspread land in the build venv and get bundled into the sidecar.
        self.assertIn('uv pip install --python $venvPath -e ".[aws,postgres,gsheets]"', content)

    def test_build_script_has_deterministic_preflight_for_incompatible_python(self) -> None:
        script = ROOT / "scripts" / "build-windows-exe.ps1"
        content = script.read_text(encoding="utf-8")

        self.assertIn('PyInstaller compatibility requires CPython 3.13.x', content)
        self.assertIn('Unsupported python version?', content)

    def test_icon_ico_has_valid_windows_ico_structure(self) -> None:
        icon_path = TAURI_ROOT / "icons" / "icon.ico"
        self.assertTrue(icon_path.exists(), "src-tauri/icons/icon.ico must exist")

        payload = icon_path.read_bytes()
        self.assertGreaterEqual(len(payload), 22, "ICO payload is too small")

        reserved = int.from_bytes(payload[0:2], "little")
        icon_type = int.from_bytes(payload[2:4], "little")
        image_count = int.from_bytes(payload[4:6], "little")

        self.assertEqual(0, reserved)
        self.assertEqual(1, icon_type)
        self.assertGreaterEqual(image_count, 3, "ICO should include multiple image sizes")

        dir_table_len = 6 + image_count * 16
        self.assertLessEqual(dir_table_len, len(payload), "ICO directory table is truncated")

        png_sig = b"\x89PNG\r\n\x1a\n"
        for i in range(image_count):
            entry = 6 + (i * 16)
            image_size = int.from_bytes(payload[entry + 8 : entry + 12], "little")
            image_offset = int.from_bytes(payload[entry + 12 : entry + 16], "little")

            self.assertGreater(image_size, 0, f"ICO image {i} has empty payload")
            self.assertLess(image_offset + image_size, len(payload) + 1, f"ICO image {i} exceeds file")

            image = payload[image_offset : image_offset + image_size]
            self.assertTrue(
                image.startswith(png_sig) or image.startswith(b"(\x00\x00\x00"),
                f"ICO image {i} is neither PNG nor BMP/DIB payload",
            )

    def test_nsis_installerHooks_configured_in_tauri_config(self) -> None:
        tauri_config = TAURI_ROOT / "tauri.conf.json"
        config = json.loads(tauri_config.read_text(encoding="utf-8"))

        nsis = config["bundle"]["windows"]["nsis"]
        self.assertIn(
            "installerHooks",
            nsis,
            "bundle.windows.nsis must declare installerHooks so the sidecar guard runs",
        )

        hook_rel = nsis["installerHooks"]
        hook_path = (TAURI_ROOT / hook_rel).resolve()
        self.assertTrue(
            hook_path.is_file(),
            f"installerHooks path must resolve to an existing file: {hook_path}",
        )

    def test_hooks_nsh_contains_sidecar_check_in_all_required_macros(self) -> None:
        hooks = TAURI_ROOT / "windows" / "hooks.nsh"
        self.assertTrue(hooks.exists(), "src-tauri/windows/hooks.nsh must exist")
        content = hooks.read_text(encoding="utf-8")

        for macro in ("NSIS_HOOK_PREINSTALL", "NSIS_HOOK_PREUNINSTALL"):
            body_match = re.search(
                rf"!macro\s+{macro}\b(.*?)!macroend", content, re.DOTALL
            )
            self.assertIsNotNone(
                body_match, f"hooks.nsh must define the {macro} macro"
            )
            body = body_match.group(1)
            self.assertIn(
                'CheckIfAppIsRunning "brain_ds.exe"',
                body,
                f"{macro} must guard the sidecar process brain_ds.exe",
            )

    def test_sidecar_name_drift_externalBin_matches_hooks_reference(self) -> None:
        tauri_config = TAURI_ROOT / "tauri.conf.json"
        config = json.loads(tauri_config.read_text(encoding="utf-8"))

        external_bins = config["bundle"]["externalBin"]
        sidecar_basename = Path(external_bins[0]).name  # "brain_ds"
        # Tauri strips the target triple and runs the sidecar as <name>.exe.
        sidecar_process = f"{sidecar_basename}.exe"

        content = (TAURI_ROOT / "windows" / "hooks.nsh").read_text(encoding="utf-8")
        calls = re.findall(
            r'CheckIfAppIsRunning\s+"([^"]+)"', content
        )
        self.assertEqual(
            2,
            len(calls),
            "Expected exactly two sidecar guard calls (PREINSTALL + PREUNINSTALL)",
        )
        for proc in calls:
            self.assertEqual(
                sidecar_process,
                proc,
                "hooks.nsh sidecar process name drifted from externalBin basename",
            )

    def test_nsis_license_file_path_resolves_from_tauri_config(self) -> None:
        tauri_config = TAURI_ROOT / "tauri.conf.json"
        content = tauri_config.read_text(encoding="utf-8")

        self.assertIn('"licenseFile": "../LICENSE"', content)
        self.assertTrue((ROOT / "LICENSE").exists(), "Root LICENSE file must exist for NSIS bundling")


if __name__ == "__main__":
    unittest.main()
