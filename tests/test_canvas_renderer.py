import re
import unittest
from pathlib import Path

from test_viewer import FORBIDDEN_REMOTE_TOKENS


class TestCanvasRendererContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assets_dir = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "assets"
        cls.templates_dir = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "templates"
        cls.js_path = cls.assets_dir / "vis-offline-network.js"
        cls.css_path = cls.assets_dir / "vis-network.min.css"
        cls.template_path = cls.templates_dir / "graph_viewer.html"
        cls.js_text = cls.js_path.read_text(encoding="utf-8")
        cls.js_lower = cls.js_text.lower()
        cls.css_text = cls.css_path.read_text(encoding="utf-8")
        cls.template_text = cls.template_path.read_text(encoding="utf-8")

    def test_vis_offline_js_exists_and_is_replaced(self):
        self.assertTrue(self.js_path.exists())
        self.assertGreater(len(self.js_text.splitlines()), 158)
        self.assertNotIn("vis-fallback-list", self.js_text)
        self.assertRegex(self.js_text, r"class\s+Network|createElement\(['\"]canvas['\"]\)")

    def test_script_exposes_vis_Network_and_DataSet(self):
        self.assertRegex(
            self.js_text,
            r"window\.vis\s*=\s*\{[^}]*Network\s*:\s*Network[^}]*DataSet\s*:\s*DataSet[^}]*\}",
        )

    def test_renderer_uses_requestAnimationFrame(self):
        self.assertIn("requestAnimationFrame", self.js_text)

    def test_renderer_has_no_external_dependencies(self):
        self.assertNotRegex(self.js_text, r"\bimport\s+")
        self.assertNotRegex(self.js_text, r"\brequire\s*\(")
        self.assertNotRegex(self.js_text, r"\bfrom\s+['\"]")
        self.assertNotRegex(self.js_text, r"src\s*=\s*['\"]https?://")
        self.assertNotIn("fetch(", self.js_text)
        for token in FORBIDDEN_REMOTE_TOKENS:
            self.assertNotIn(token, self.js_lower)

    def test_canvas_element_created_in_container(self):
        self.assertRegex(self.js_text, r"createElement\(['\"]canvas['\"]\)")
        self.assertRegex(self.js_text, r"getContext\(['\"]2d['\"]\)")

    def test_dom_aria_companion_present(self):
        self.assertRegex(self.js_text, r"createElement\(['\"]ul['\"]\)")
        self.assertRegex(self.js_text, r"aria-label[\"']?\s*,\s*[\"']Graph nodes[\"']")
        self.assertRegex(self.js_text, r"role[\"']?\s*,\s*[\"']listbox[\"']")
        self.assertRegex(self.js_text, r"createElement\(['\"]li['\"]\)")
        self.assertRegex(self.js_text, r"role[\"']?\s*,\s*[\"']option[\"']")

    def test_aria_live_region_present(self):
        self.assertRegex(self.js_text, r"createElement\(['\"]div['\"]\)")
        self.assertRegex(self.js_text, r"aria-live[\"']?\s*,\s*[\"']polite[\"']")

    def test_keyboard_navigation_contract_present(self):
        self.assertIn("keydown", self.js_text)
        self.assertRegex(self.js_text, r"ArrowDown|ArrowUp")
        self.assertIn("Enter", self.js_text)
        self.assertRegex(self.js_text, r"['\"] ['\"]|Spacebar")

    def test_accessible_canvas_contract_present(self):
        self.assertRegex(self.js_text, r"setAttribute\(['\"]role['\"],\s*['\"]img['\"]\)")
        self.assertRegex(self.js_text, r"setAttribute\(['\"]aria-label['\"],\s*['\"]Organization graph['\"]\)")
        self.assertRegex(self.js_text, r"setAttribute\(['\"]tabindex['\"],\s*['\"]0['\"]\)")

    def test_reduced_motion_contract_present(self):
        self.assertIn("prefers-reduced-motion", self.js_text)
        self.assertRegex(self.js_text, r"matchMedia\(['\"]\(prefers-reduced-motion:\s*reduce\)['\"]\)")
        self.assertRegex(self.js_text, r"lineDashOffset\s*=\s*0")

    def test_css_a11y_and_design_token_contract_present(self):
        self.assertIn(":root", self.css_text)
        self.assertIn("--vis-focus-ring", self.css_text)
        self.assertIn("--vis-touch-target", self.css_text)
        self.assertIn(".vis-a11y-option:focus-visible", self.css_text)
        self.assertRegex(self.css_text, r"min-height:\s*var\(--vis-touch-target\)")
        self.assertIn("@media (prefers-reduced-motion: reduce)", self.css_text)

    def test_css_removed_fallback_styles(self):
        self.assertNotIn(".vis-fallback-list", self.css_text)
        self.assertNotIn(".vis-fallback-node", self.css_text)
        self.assertIn("canvas", self.css_text)

    def test_force_layout_and_cooling_primitives_present(self):
        self.assertIn("temperature", self.js_lower)
        self.assertRegex(self.js_text, r"\*\s*0\.95")
        self.assertRegex(self.js_text, r"1\s*/\s*\(.*\*.*\)")
        self.assertRegex(self.js_text, r"Math\.sqrt\(")

    def test_node_radius_importance_and_edge_rendering_foundation(self):
        self.assertRegex(self.js_text, r"max\(\s*8\s*,\s*degree\s*\*\s*2\s*\+\s*8\s*\)")
        self.assertIn("arc(", self.js_text)
        self.assertIn("setLineDash", self.js_text)
        self.assertIn("lineDashOffset", self.js_text)

    def test_wrapper_api_compatibility_methods_present(self):
        self.assertRegex(self.js_text, r"DataSet\.prototype\.add\s*=")
        self.assertRegex(self.js_text, r"DataSet\.prototype\.update\s*=")
        self.assertRegex(self.js_text, r"DataSet\.prototype\.get\s*=")
        self.assertRegex(self.js_text, r"DataSet\.prototype\._subscribe\s*=")
        self.assertRegex(self.js_text, r"Network\.prototype\.setOptions\s*=")
        self.assertRegex(self.js_text, r"Network\.prototype\.on\s*=")
        self.assertRegex(self.js_text, r"Network\.prototype\.focus\s*=")
        self.assertRegex(self.js_text, r"Network\.prototype\.fit\s*=")

    def test_template_vis_integration_points_unchanged(self):
        self.assertIn("new vis.DataSet(RENDER_CONTEXT.nodes", self.template_text)
        self.assertIn("new vis.DataSet(RENDER_CONTEXT.edges", self.template_text)
        self.assertIn("new vis.Network(container, { nodes, edges }", self.template_text)
        self.assertIn("network.focus(nodeId", self.template_text)
        self.assertIn("network.setOptions({", self.template_text)
        self.assertIn("network.fit({ animation: true })", self.template_text)
        self.assertIn("network.on(\"click\"", self.template_text)

    def test_hierarchy_expand_collapse_contract_present(self):
        self.assertIn("supertype", self.js_text)
        self.assertRegex(self.js_text, r"expandedNodeIds")
        self.assertRegex(self.js_text, r"_toggleExpandCollapse")
        self.assertRegex(self.js_text, r"hidden\s*=\s*!")

    def test_hover_drag_and_selected_state_contract_present(self):
        self.assertRegex(self.js_text, r"addEventListener\(['\"]mousemove['\"]")
        self.assertRegex(self.js_text, r"addEventListener\(['\"]mousedown['\"]")
        self.assertRegex(self.js_text, r"addEventListener\(['\"]mouseup['\"]")
        self.assertIn("hoveredNodeId", self.js_text)
        self.assertIn("isDragging", self.js_text)
        self.assertRegex(self.js_text, r"nodes:\s*\[node\.id\]")

    def test_root_and_importance_radius_contract_present(self):
        self.assertRegex(self.js_text, r"isRoot")
        self.assertRegex(self.js_text, r"importance")
        self.assertRegex(self.js_text, r"Math\.max\(12")

    def test_template_cleanup_has_no_fallback_tokens(self):
        self.assertNotIn("vis-fallback", self.template_text)


# ── Slice 1a contracts (REQ-1.1, REQ-1.2, REQ-1.9, REQ-1.11, REQ-1.12, REQ-1.13) ──

class TestSlice1aViewportContracts(unittest.TestCase):
    """Slice 1a: viewport matrix + pan + hit-test refactor.

    All 7 tests here must FAIL before implementation and PASS after.
    The 25 contracts in TestCanvasRendererContracts must remain GREEN throughout.
    """

    @classmethod
    def setUpClass(cls):
        assets_dir = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "assets"
        cls.js_path = assets_dir / "vis-offline-network.js"
        cls.js_text = cls.js_path.read_text(encoding="utf-8")

    # 1a.2 – REQ-1.1
    def test_viewport_matrix_state_present(self):
        """viewport = { scale: ..., tx: ..., ty: ... } must be initialised in constructor."""
        self.assertRegex(self.js_text, r"this\.viewport\s*=\s*\{")
        self.assertIn("scale", self.js_text)
        self.assertIn("tx", self.js_text)
        self.assertIn("ty", self.js_text)

    # 1a.3 – REQ-1.9
    def test_screen_to_world_helper_present(self):
        """_screenToWorld must be defined as a prototype method."""
        self.assertRegex(self.js_text, r"_screenToWorld\s*=\s*function")

    # 1a.4 – REQ-1.9
    def test_world_to_screen_helper_present(self):
        """_worldToScreen must be defined as a prototype method."""
        self.assertRegex(self.js_text, r"_worldToScreen\s*=\s*function")

    # 1a.5 – REQ-1.1
    def test_setTransform_called_in_render_path(self):
        """ctx.setTransform( must appear in the renderer (applies viewport matrix)."""
        self.assertRegex(self.js_text, r"ctx\.setTransform\(")

    # 1a.6 – REQ-1.2
    def test_pan_state_uses_distinct_flag(self):
        """isPanning flag must be present AND existing isDragging must still be present."""
        self.assertIn("isPanning", self.js_text)
        self.assertIn("isDragging", self.js_text)

    # 1a.7 – REQ-1.9 / OBS-1.8
    def test_hit_test_applies_inverse_transform(self):
        """_screenToWorld must appear before _nodeAt in each of _onClick,
        _onMouseMove, _onMouseDown (string-index ordering contract)."""
        for handler in ("_onClick", "_onMouseMove", "_onMouseDown"):
            # Find the body slice for this handler
            start = self.js_text.find("Network.prototype." + handler + " = function")
            self.assertNotEqual(start, -1, f"handler {handler} not found")
            # Find where the NEXT handler/method starts (the function ends before the next
            # Network.prototype. definition or the end of the script).
            next_method = self.js_text.find("Network.prototype.", start + 1)
            body = self.js_text[start: next_method if next_method != -1 else len(self.js_text)]
            sw_pos = body.find("_screenToWorld")
            na_pos = body.find("_nodeAt")
            self.assertNotEqual(sw_pos, -1,
                f"_screenToWorld not found in {handler}")
            self.assertNotEqual(na_pos, -1,
                f"_nodeAt not found in {handler}")
            self.assertLess(sw_pos, na_pos,
                f"_screenToWorld must precede _nodeAt in {handler}")

    # 1a.8 – REQ-X.4 (regression guard)
    def test_locked_literals_survive_1a(self):
        """All pre-existing locked literals must still be present after 1a."""
        for literal in (
            "isDragging",
            "dragNodeId",
            "selectedNodeId",
            "hoveredNodeId",
            "expandedNodeIds",
            "_toggleExpandCollapse",
            "temperature * 0.95",
        ):
            self.assertIn(literal, self.js_text,
                f"locked literal '{literal}' has been removed — regression!")


if __name__ == "__main__":
    unittest.main()
