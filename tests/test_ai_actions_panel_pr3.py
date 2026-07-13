from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AI_ACTIONS_PANEL = ROOT / "brain_ds" / "ui" / "src" / "panels" / "ai-actions-panel.ts"
GRAPH_VIEWER = ROOT / "brain_ds" / "ui" / "templates" / "graph_viewer.html"


class TestAiActionsLifecyclePr3(unittest.TestCase):
    def test_panel_renders_selected_node_header_on_reveal_and_live_update(self) -> None:
        text = AI_ACTIONS_PANEL.read_text(encoding="utf-8")

        self.assertIn("ai-actions-node-intel__selected-context", text)
        self.assertIn("Nodo seleccionado", text)
        self.assertRegex(text, r"_renderSelectedNodeHeader\([^)]*nodeId")
        self.assertRegex(text, r"setSelectedNodeId[\s\S]*_renderSelectedNodeHeader")
        self.assertRegex(text, r"onReveal\(\)[\s\S]*_renderSelectedNodeHeader")

    def test_ai_actions_and_pipeline_are_distinct_rail_groups(self) -> None:
        html = GRAPH_VIEWER.read_text(encoding="utf-8")

        self.assertIn('class="rail-section-group rail-section-group--ai-actions"', html)
        self.assertIn('class="rail-section-group rail-section-group--pipeline"', html)
        self.assertIn("Acciones IA", html)
        self.assertIn("Pipeline stage", html)
        self.assertRegex(html, r"rail-section-divider")
        self.assertLess(
            html.index('rail-section-group rail-section-group--ai-actions'),
            html.index('rail-section-group rail-section-group--pipeline'),
        )


if __name__ == "__main__":
    unittest.main()
