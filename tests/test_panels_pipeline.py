from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = ROOT / "brain_ds" / "ui"
PANELS_DIR = UI_ROOT / "src" / "panels"
GRAPH_VIEWER = UI_ROOT / "templates" / "graph_viewer.html"


class TestPipelinePanelModule(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.path = PANELS_DIR / "pipeline-panel.ts"
        cls.exists = cls.path.exists()
        cls.text = cls.path.read_text(encoding="utf-8") if cls.exists else ""

    def _require(self) -> None:
        if not self.exists:
            self.fail(f"pipeline-panel.ts not found at {self.path}")

    def test_renders_all_six_stages_in_order(self) -> None:
        self._require()
        self.assertRegex(self.text, r"PIPELINE_STAGES")
        ordered = ["setup", "intake", "map", "brd", "verify", "archive"]
        cursor = -1
        for stage in ordered:
            next_cursor = self.text.find(stage, cursor + 1)
            self.assertGreater(next_cursor, cursor, f"{stage} must appear after the previous stage")
            cursor = next_cursor

    def test_exports_mount_unmount_and_stays_read_only(self) -> None:
        self._require()
        self.assertRegex(self.text, r"export\s+(?:async\s+)?function\s+mount")
        self.assertRegex(self.text, r"export\s+function\s+unmount")
        self.assertNotRegex(
            self.text,
            r"createElement\(\s*['\"]button['\"]|<button|type=\s*['\"]button['\"]",
            "pipeline panel must not expose mutation controls",
        )


class TestPipelinePanelDefaultStatuses(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.path = PANELS_DIR / "pipeline-panel.ts"
        cls.exists = cls.path.exists()
        cls.text = cls.path.read_text(encoding="utf-8") if cls.exists else ""

    def _require(self) -> None:
        if not self.exists:
            self.fail(f"pipeline-panel.ts not found at {self.path}")

    def test_no_live_data_defaults_to_pending(self) -> None:
        self._require()
        self.assertRegex(self.text, r"pending", msg="pipeline panel must default to pending/neutral status")
        self.assertRegex(self.text, r"pipeline-stage-chip", msg="pipeline stages must render status chips")


class TestPipelinePanelRailWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.exists = GRAPH_VIEWER.exists()
        cls.text = GRAPH_VIEWER.read_text(encoding="utf-8") if cls.exists else ""

    def _require(self) -> None:
        if not self.exists:
            self.fail(f"graph_viewer.html not found at {GRAPH_VIEWER}")

    def test_pipeline_panel_uses_single_active_panel_dispatcher(self) -> None:
        self._require()
        self.assertIn("const setActiveRightPanel", self.text)
        self.assertRegex(self.text, r"setActiveRightPanel\(['\"]pipeline['\"]\)")
        self.assertRegex(self.text, r"data-rail-icon=\"pipeline\"")
        self.assertRegex(self.text, r"pipelinePanel\.mount")
        self.assertRegex(
            self.text,
            r"active\s*===\s*'pipeline'|showPipelinePanel",
            msg="pipeline must flow through the existing active-panel dispatcher",
        )
