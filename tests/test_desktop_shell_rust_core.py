from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TAURI_SRC = ROOT / "src-tauri" / "src"


class DesktopShellRustCoreStructureTests(unittest.TestCase):
    def test_desktop_rs_exists_with_lifecycle_contract(self) -> None:
        desktop_rs = TAURI_SRC / "desktop.rs"
        self.assertTrue(desktop_rs.exists(), "src-tauri/src/desktop.rs must exist")

        content = desktop_rs.read_text(encoding="utf-8")
        required_tokens = [
            "pub const DESKTOP_SERVER_PORT: u16 = 8765",
            'pub const DESKTOP_READINESS_PATH: &str = "/api/graphs"',
            "pub enum LaunchStatus",
            "pub struct LaunchResult",
            "pub struct DesktopState",
            "pub fn validate_project_root",
            "pub fn spawn_sidecar",
            "pub fn poll_for_server_ready",
            "pub fn terminate_sidecar",
        ]
        for token in required_tokens:
            self.assertIn(token, content)

    def test_commands_rs_exists_with_tauri_commands(self) -> None:
        commands_rs = TAURI_SRC / "commands.rs"
        self.assertTrue(commands_rs.exists(), "src-tauri/src/commands.rs must exist")

        content = commands_rs.read_text(encoding="utf-8")
        self.assertIn("#[tauri::command]", content)
        self.assertIn("pub fn pick_project_and_launch", content)
        self.assertIn("pub fn retry_launch", content)

    def test_main_rs_wires_state_and_commands(self) -> None:
        main_rs = TAURI_SRC / "main.rs"
        content = main_rs.read_text(encoding="utf-8")

        required_tokens = [
            "mod commands;",
            "mod desktop;",
            "desktop::DesktopState::new()",
            "tauri::generate_handler![",
            "commands::pick_project_and_launch",
            "commands::retry_launch",
        ]
        for token in required_tokens:
            self.assertIn(token, content)


if __name__ == "__main__":
    unittest.main()
