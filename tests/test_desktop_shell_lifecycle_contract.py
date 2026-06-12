from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TAURI_SRC = ROOT / "src-tauri" / "src"


class DesktopShellLifecycleContractTests(unittest.TestCase):
    def test_desktop_launch_flow_order_is_preserved(self) -> None:
        content = (TAURI_SRC / "desktop.rs").read_text(encoding="utf-8")

        launch_match = re.search(
            r"pub fn launch_with_project_root\([^)]*\) -> Result<LaunchResult, DesktopError> \{(?P<body>.*?)\n\}",
            content,
            re.DOTALL,
        )
        self.assertIsNotNone(launch_match, "launch_with_project_root contract must exist")
        assert launch_match is not None
        body = launch_match.group("body")

        ordered_calls = [
            "validate_project_root(project_root_raw)?",
            "self.shutdown_running_sidecar()?",
            "pick_ephemeral_port()?",
            "spawn_sidecar(app, &canonical_root, port)?",
            "poll_for_server_ready(",
            "Ok(LaunchResult {",
        ]
        cursor = -1
        for token in ordered_calls:
            idx = body.find(token)
            self.assertNotEqual(idx, -1, f"Missing launch flow token: {token}")
            self.assertGreater(idx, cursor, f"Launch flow out of order near token: {token}")
            cursor = idx

    def test_sidecar_spawn_contract_uses_uv_and_port_arg(self) -> None:
        content = (TAURI_SRC / "desktop.rs").read_text(encoding="utf-8")
        spawn_match = re.search(
            r"pub fn spawn_sidecar\([^)]*\) -> Result<SidecarChild, DesktopError> \{(?P<body>.*?)\n\}",
            content,
            re.DOTALL,
        )
        self.assertIsNotNone(spawn_match, "spawn_sidecar contract must exist")
        assert spawn_match is not None
        body = spawn_match.group("body")

        required_args = [
            'Command::new("uv")',
            '.arg("run")',
            '.arg("brain_ds")',
            '.arg("ui")',
            '.arg("serve")',
            '.arg("--project-root")',
            ".arg(project_root)",
            '.arg("--port")',
            ".arg(port.to_string())",
            ".stdout(Stdio::null())",
            ".stderr(Stdio::piped())",
        ]
        for token in required_args:
            self.assertIn(token, body)

        self.assertIn('#[cfg(feature = "bundled")]', content)
        self.assertIn('sidecar("brain_ds")', content)

    def test_main_wires_shutdown_hook_for_close_and_exit(self) -> None:
        content = (TAURI_SRC / "main.rs").read_text(encoding="utf-8")

        self.assertIn("WindowEvent::CloseRequested", content)
        self.assertIn("RunEvent::ExitRequested", content)
        self.assertEqual(
            content.count("shutdown_running_sidecar()"),
            2,
            "Shutdown hook should run for both window close and app exit",
        )


if __name__ == "__main__":
    unittest.main()
