from __future__ import annotations

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
        self.assertIn("hiddenimports=[", content)
        self.assertIn("uvicorn.loops.auto", content)
        self.assertIn("brain_ds.ui", content)
        self.assertIn("onefile", content.lower())
        self.assertIn('"brain_ds" / "__main__.py"', content)
        self.assertNotIn('"brain_ds" / "ui" / "__main__.py"', content)

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
        content = script.read_text(encoding="utf-8").lower()

        self.assertNotIn("npm ", content)
        self.assertNotIn("pnpm ", content)
        self.assertIn("--locked", content)

    def test_build_script_pins_uv_python_to_3_13_for_pyinstaller_compatibility(self) -> None:
        script = ROOT / "scripts" / "build-windows-exe.ps1"
        content = script.read_text(encoding="utf-8")

        self.assertIn('uv venv --python 3.13', content)
        self.assertIn('pyinstaller==6.11.1', content)
        self.assertIn('uv pip install --python $venvPath -e .', content)

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

    def test_nsis_license_file_path_resolves_from_tauri_config(self) -> None:
        tauri_config = TAURI_ROOT / "tauri.conf.json"
        content = tauri_config.read_text(encoding="utf-8")

        self.assertIn('"licenseFile": "../LICENSE"', content)
        self.assertTrue((ROOT / "LICENSE").exists(), "Root LICENSE file must exist for NSIS bundling")


if __name__ == "__main__":
    unittest.main()
