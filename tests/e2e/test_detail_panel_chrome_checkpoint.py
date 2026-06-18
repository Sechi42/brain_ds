from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
UI_ROOT = REPO_ROOT / "brain_ds" / "ui"


class TestDetailPanelChromeCheckpoint(unittest.TestCase):
    def test_playwright_checkpoint_runs_detail_panel_chrome_spec(self) -> None:
        result = subprocess.run(
            ["pnpm", "exec", "playwright", "test", "e2e/detail-panel-chrome.spec.ts"],
            cwd=UI_ROOT,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )

        if result.returncode != 0:
            self.fail(
                "Playwright checkpoint failed.\n"
                f"STDOUT:\n{result.stdout}\n"
                f"STDERR:\n{result.stderr}"
            )
