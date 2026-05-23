import re
import unittest
from pathlib import Path


class TestDomRendererContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parent.parent
        cls.renderer_dom_path = root / "brain_ds" / "ui" / "src" / "renderer-dom.ts"
        cls.popover_path = root / "brain_ds" / "ui" / "src" / "interactions" / "popover.ts"
        cls.template_path = root / "brain_ds" / "ui" / "templates" / "graph_viewer.html"
        cls.renderer_text = cls.renderer_dom_path.read_text(encoding="utf-8")
        cls.popover_text = cls.popover_path.read_text(encoding="utf-8")
        cls.template_text = cls.template_path.read_text(encoding="utf-8")

    def test_mount_unmount_and_subscribe_cleanup_contract_present(self):
        self.assertRegex(self.renderer_text, r"export\s+function\s+mount\s*\(")
        self.assertIn("deps.dataset._subscribe", self.renderer_text)
        self.assertIn("removeEventListener('keydown'", self.renderer_text)
        self.assertIn("if (typeof unsubscribe === 'function') unsubscribe()", self.renderer_text)
        self.assertIn("if (typeof unsubscribeEdges === 'function') unsubscribeEdges()", self.renderer_text)

    def test_css_vars_and_state_transitions_contract_present(self):
        for token in (
            "--node-color",
            "--node-color-muted",
            "selected-target",
            "selected-related",
            "hover-target",
            "hover-related",
            "default",
        ):
            self.assertIn(token, self.renderer_text)

    def test_svg_edge_contract_present(self):
        self.assertRegex(self.renderer_text, r"createElementNS\([^\n]*line")
        self.assertIn("line.setAttribute('x1'", self.renderer_text)
        self.assertIn("line.setAttribute('y1'", self.renderer_text)
        self.assertIn("line.setAttribute('x2'", self.renderer_text)
        self.assertIn("line.setAttribute('y2'", self.renderer_text)
        self.assertIn("line.dataset.related", self.renderer_text)

    def test_popover_lifecycle_contract_present(self):
        self.assertIn("deps.network.hoverDelayMs = 150", self.popover_text)
        self.assertIn("setPopoverContentFactory", self.popover_text)
        self.assertIn("export function unmount", self.popover_text)
        self.assertIn("_deps = null", self.popover_text)

    def test_reduced_motion_contract_present(self):
        self.assertIn("@media (prefers-reduced-motion: reduce)", self.template_text)
        self.assertRegex(
            self.template_text,
            r"@media\s*\(prefers-reduced-motion:\s*reduce\)[\s\S]*node-hover-breathe",
        )


class TestDomRendererIntegrationContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parent.parent
        cls.renderer_text = (root / "brain_ds" / "ui" / "src" / "renderer-dom.ts").read_text(encoding="utf-8")
        cls.popover_text = (root / "brain_ds" / "ui" / "src" / "interactions" / "popover.ts").read_text(encoding="utf-8")

    def test_selection_and_hover_flip_ego_dim_contract(self):
        self.assertIn("deps.container.dataset.hasHover", self.renderer_text)
        self.assertIn("deps.container.dataset.hasSelection", self.renderer_text)
        self.assertIn("setAttribute('data-has-hover'", self.renderer_text)
        self.assertIn("setAttribute('data-has-selection'", self.renderer_text)

    def test_keyboard_roving_tabindex_contract(self):
        self.assertRegex(self.renderer_text, r"ArrowLeft|ArrowRight|ArrowUp|ArrowDown")
        self.assertIn("node.tabIndex = i === 0 ? 0 : -1", self.renderer_text)
        self.assertIn("nodes[nextIndex].focus()", self.renderer_text)

    def test_hover_to_popover_integration_contract(self):
        self.assertIn("createContentFactory", self.popover_text)
        self.assertIn("setPopoverContentFactory", self.popover_text)
        self.assertIn("hoverDelayMs = 150", self.popover_text)
