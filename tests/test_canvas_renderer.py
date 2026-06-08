import re
import unittest
from pathlib import Path

try:
    from test_viewer import FORBIDDEN_REMOTE_TOKENS
except ModuleNotFoundError:  # Direct module execution: `python -m unittest tests.test_canvas_renderer`
    from tests.test_viewer import FORBIDDEN_REMOTE_TOKENS


class TestCanvasRendererContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assets_dir = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "assets"
        cls.src_dir = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "src"
        cls.templates_dir = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "templates"
        cls.js_path = cls.src_dir / "renderer.ts"
        cls.css_path = cls.assets_dir / "vis-network.min.css"
        cls.template_path = cls.templates_dir / "graph_viewer.html"
        cls.js_text = cls.js_path.read_text(encoding="utf-8")
        cls.js_lower = cls.js_text.lower()
        cls.css_text = cls.css_path.read_text(encoding="utf-8")
        cls.template_text = cls.template_path.read_text(encoding="utf-8")

    def test_vis_offline_js_exists_and_is_replaced(self):
        # PR 1: check renderer.ts exists (identity port of legacy renderer JS)
        self.assertTrue(self.js_path.exists(),
                        f"src/renderer.ts not found — identity rename not complete")
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
        self.assertNotIn("network.focus(nodeId", self.template_text)
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

    def test_slice8_selection_ring_scales_with_zoom_and_cap(self):
        self.assertRegex(self.js_text, r"2\s*/\s*(this|self)\.viewport\.scale")
        self.assertRegex(self.js_text, r"Math\.min\(\s*8\s*,\s*2\s*/\s*(this|self)\.viewport\.scale\s*\)")

    def test_slice8_keyboard_focus_outer_ring_contract(self):
        self.assertIn("keyboardFocusedNodeId", self.js_text)
        self.assertRegex(self.js_text, r"setLineDash\(\[\s*4\s*/\s*(this|self)\.viewport\.scale\s*,\s*4\s*/\s*(this|self)\.viewport\.scale\s*\]\)")
        self.assertRegex(self.js_text, r"1\.5\s*/\s*(this|self)\.viewport\.scale")
        self.assertRegex(self.js_text, r"Math\.min\(\s*6\s*,\s*1\.5\s*/\s*(this|self)\.viewport\.scale\s*\)")
        self.assertRegex(self.js_text, r"--state-focus-ring")

    def test_template_cleanup_has_no_fallback_tokens(self):
        self.assertNotIn("vis-fallback", self.template_text)

    def test_w5_hover_dimming_contract_present(self):
        self.assertRegex(self.js_text, r"_neighborIndex")
        self.assertRegex(self.js_text, r"globalAlpha\s*=\s*0\.15")
        self.assertRegex(self.js_text, r"hoveredNodeId\s*!==\s*null")

    def test_w5_ego_edge_theme_token_contract_present(self):
        # Phase D.1: tokens moved from inline :root{} in graph_viewer.html to
        # the canonical brain_ds/ui/static/tokens.css; the runtime inlines it
        # via __BRAIN_DS_TOKENS_CSS__ substitution. Assert the declaration
        # lives in the canonical file.
        tokens_path = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "static" / "tokens.css"
        tokens_text = tokens_path.read_text(encoding="utf-8")
        self.assertIn("--color-ego-edge", tokens_text)
        self.assertRegex(self.js_text, r"egoEdge")
        self.assertRegex(self.js_text, r"#7c3aed")

    def test_w5_canvas_mouseleave_clears_hover_contract_present(self):
        self.assertRegex(self.js_text, r"addEventListener\(['\"]mouseleave['\"]")
        self.assertRegex(self.js_text, r"hoveredNodeId\s*=\s*null")

    def test_d4OverlayActive_flag_exists(self):
        self.assertRegex(self.js_text, r"this\._d4OverlayActive\s*=\s*false")

    def test_draw_calls_gated_when_overlay_active(self):
        self.assertRegex(self.js_text, r"if\s*\(\s*!this\._d4OverlayActive\s*\)\s*\{")
        self.assertRegex(self.js_text, r"if\s*\(\s*!this\._d4OverlayActive\s*\)\s*\{[\s\S]*_drawEdges\(")
        self.assertRegex(self.js_text, r"if\s*\(\s*!this\._d4OverlayActive\s*\)\s*\{[\s\S]*_drawMarquee\(")
        self.assertRegex(self.js_text, r"if\s*\(\s*!this\._d4OverlayActive\s*\)\s*\{[\s\S]*_drawNodes\(")
        self.assertRegex(self.js_text, r"if\s*\(\s*!this\._d4OverlayActive\s*\)\s*\{[\s\S]*_syncA11yList\(")

    def test_physics_viewport_run_when_gated(self):
        self.assertIn("_applyForces(state, dt)", self.js_text)
        self.assertIn("ctx.setTransform(", self.js_text)
        self.assertIn("this._stepInertia(dt)", self.js_text)


# ── Slice 1a contracts (REQ-1.1, REQ-1.2, REQ-1.9, REQ-1.11, REQ-1.12, REQ-1.13) ──

class TestSlice1aViewportContracts(unittest.TestCase):
    """Slice 1a: viewport matrix + pan + hit-test refactor.

    All 7 tests here must FAIL before implementation and PASS after.
    The 25 contracts in TestCanvasRendererContracts must remain GREEN throughout.
    """

    @classmethod
    def setUpClass(cls):
        src_dir = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "src"
        cls.js_path = src_dir / "renderer.ts"
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


# ── Slice 1b contracts (REQ-1.3, 1.4, 1.5, 1.7, 1.8, 1.10, 1.12, 1.13) ──

class TestSlice1bInertiaContracts(unittest.TestCase):
    """Slice 1b: wheel-zoom + inertia + fit/focus re-implementation.

    All 7 tests here must FAIL before implementation and PASS after.
    The 32 contracts from TestCanvasRendererContracts + TestSlice1aViewportContracts
    must remain GREEN throughout.
    """

    @classmethod
    def setUpClass(cls):
        src_dir = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "src"
        cls.js_path = src_dir / "renderer.ts"
        cls.js_text = cls.js_path.read_text(encoding="utf-8")

    # 1b.1 – REQ-1.3
    def test_wheel_zoom_handler_present(self):
        """addEventListener('wheel', ...) must exist and call preventDefault(). Cite REQ-1.3."""
        self.assertRegex(self.js_text, r"addEventListener\(['\"]wheel['\"]")
        # The wheel handler body must contain preventDefault
        start = self.js_text.find("addEventListener(\"wheel\"")
        if start == -1:
            start = self.js_text.find("addEventListener('wheel'")
        self.assertNotEqual(start, -1, "wheel addEventListener not found")
        # Check that preventDefault appears after the wheel listener attachment
        after = self.js_text[start:]
        self.assertIn("preventDefault", after)

    # 1b.2 – REQ-1.4
    def test_zoom_clamped_to_min_max(self):
        """Zoom bounds literals 0.25 (min) and 4.0 (max) must be present. Cite REQ-1.4."""
        self.assertIn("0.25", self.js_text)
        self.assertIn("4.0", self.js_text)

    # 1b.3 – REQ-1.5
    def test_zoom_sensitivity_multiplicative_model(self):
        """Multiplicative zoom factor literal 1.1 must appear near the wheel handler. Cite REQ-1.5."""
        # 1.1 is the base for Math.pow(1.1, ...) multiplicative zoom
        self.assertIn("1.1", self.js_text)

    # 1b.4 – REQ-1.7
    def test_inertia_friction_constant_distinct_from_cooling(self):
        """inertiaFriction must be present AND temperature * 0.95 must remain unmodified. Cite REQ-1.7."""
        self.assertIn("inertiaFriction", self.js_text)
        # The cooling literal must be UNCHANGED (locked — forces are cooled via * 0.95)
        self.assertIn("temperature * 0.95", self.js_text)

    # 1b.5 – REQ-1.10
    def test_fit_reimplemented_against_viewport(self):
        """network.fit body must reference 'viewport' (not just set temperature=0.2). Cite REQ-1.10."""
        # Find the fit method body
        start = self.js_text.find("Network.prototype.fit = function")
        self.assertNotEqual(start, -1, "Network.prototype.fit not found")
        next_method = self.js_text.find("Network.prototype.", start + 1)
        body = self.js_text[start: next_method if next_method != -1 else len(self.js_text)]
        self.assertIn("viewport", body)

    # 1b.6 – REQ-1.10
    def test_focus_accepts_scale_and_animation_options(self):
        """network.focus signature must accept options with scale and animation. Cite REQ-1.10."""
        # Focus must accept (nodeId, options) — check the prototype method signature
        start = self.js_text.find("Network.prototype.focus = function")
        self.assertNotEqual(start, -1, "Network.prototype.focus not found")
        next_method = self.js_text.find("Network.prototype.", start + 1)
        body = self.js_text[start: next_method if next_method != -1 else len(self.js_text)]
        # Must accept options parameter
        self.assertRegex(body, r"function\s*\(\s*nodeId\s*,\s*options\s*\)")
        # Must reference scale and animation in options
        self.assertIn("scale", body)
        self.assertIn("animation", body)

    # 1b.7 – REQ-1.8
    def test_reduced_motion_skips_inertia(self):
        """_prefersReducedMotion must guard _stepInertia (inertia skipped on reduced-motion). Cite REQ-1.8."""
        # _stepInertia must exist as a method
        self.assertRegex(self.js_text, r"_stepInertia\s*=\s*function")
        # _prefersReducedMotion must appear inside _stepInertia body
        start = self.js_text.find("_stepInertia = function")
        self.assertNotEqual(start, -1, "_stepInertia not found")
        next_method = self.js_text.find("Network.prototype.", start + 1)
        body = self.js_text[start: next_method if next_method != -1 else len(self.js_text)]
        self.assertIn("_prefersReducedMotion", body)



# ── Slice 3a contracts (REQ-3.1–3.9, REQ-3.12, REQ-3.13) ──

class TestSlice3aMultiSelectContracts(unittest.TestCase):
    """Slice 3a: multi-select state + REPLACE-only marquee + keyboard shortcuts.

    All 7 tests here must FAIL before implementation and PASS after.
    The 42 contracts from prior slices must remain GREEN throughout.
    Decision 2 is binding: marquee commit REPLACES selection (not additive).
    """

    @classmethod
    def setUpClass(cls):
        src_dir = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "src"
        cls.js_path = src_dir / "renderer.ts"
        cls.js_text = cls.js_path.read_text(encoding="utf-8")

    # 3a.1 – REQ-3.4
    def test_selected_node_ids_set_present(self):
        """selectedNodeIds = new Set() must be initialised in constructor. Cite REQ-3.4."""
        self.assertRegex(
            self.js_text,
            r"selectedNodeIds\s*=\s*new\s+Set"
        )

    # 3a.2 – REQ-3.4 (additive — locked literal must NOT be removed)
    def test_selected_node_id_legacy_still_present(self):
        """this.selectedNodeId = ... must still be present (additive, not replacement). Cite REQ-3.4."""
        self.assertRegex(
            self.js_text,
            r"this\.selectedNodeId\s*="
        )

    # 3a.3 – REQ-3.5 / REQ-3.13
    def test_marquee_state_object_present(self):
        """marquee = { active: ... } must be initialised in constructor. Cite REQ-3.5."""
        self.assertRegex(
            self.js_text,
            r"marquee\s*=\s*\{[^}]*active"
        )

    # 3a.4 – REQ-3.5 (ordering: _drawEdges < _drawMarquee < _drawNodes inside _render)
    def test_marquee_draw_between_edges_and_nodes(self):
        """_drawMarquee must be called between _drawEdges and _drawNodes in _render. Cite REQ-3.5."""
        render_start = self.js_text.find("Network.prototype._render = function")
        self.assertNotEqual(render_start, -1, "_render method not found")
        next_method = self.js_text.find("Network.prototype.", render_start + 1)
        render_body = self.js_text[render_start: next_method if next_method != -1 else len(self.js_text)]
        edges_pos = render_body.find("_drawEdges")
        marquee_pos = render_body.find("_drawMarquee")
        nodes_pos = render_body.find("_drawNodes")
        self.assertNotEqual(edges_pos, -1, "_drawEdges not found in _render body")
        self.assertNotEqual(marquee_pos, -1, "_drawMarquee not found in _render body")
        self.assertNotEqual(nodes_pos, -1, "_drawNodes not found in _render body")
        self.assertLess(edges_pos, marquee_pos, "_drawEdges must precede _drawMarquee in _render")
        self.assertLess(marquee_pos, nodes_pos, "_drawMarquee must precede _drawNodes in _render")

    # 3a.5 – REQ-3.5 / REQ-3.6 (world-coord marquee)
    def test_marquee_uses_world_coordinates(self):
        """Marquee mousedown/mousemove handlers must invoke _screenToWorld. Cite REQ-3.5/3.6."""
        # Look for _screenToWorld usage near marquee-related code
        # The marquee mousedown path (shift+empty canvas) must call _screenToWorld
        self.assertIn("_screenToWorld", self.js_text)
        # Marquee state object must be referenced alongside _screenToWorld invocation
        # Check that the marquee.active assignment path includes _screenToWorld call nearby
        # Strategy: find _onMouseDown body and verify _screenToWorld appears before marquee.active = true
        start = self.js_text.find("Network.prototype._onMouseDown = function")
        self.assertNotEqual(start, -1, "_onMouseDown not found")
        next_method = self.js_text.find("Network.prototype.", start + 1)
        body = self.js_text[start: next_method if next_method != -1 else len(self.js_text)]
        sw_pos = body.find("_screenToWorld")
        marquee_pos = body.find("marquee")
        self.assertNotEqual(sw_pos, -1, "_screenToWorld not found in _onMouseDown")
        self.assertNotEqual(marquee_pos, -1, "marquee not referenced in _onMouseDown")
        self.assertLess(sw_pos, marquee_pos, "_screenToWorld must precede marquee assignment in _onMouseDown")

    # 3a.6 – REQ-3.12
    def test_select_change_event_emitted(self):
        """_emit('select-change', ...) must appear in the renderer. Cite REQ-3.12."""
        self.assertRegex(
            self.js_text,
            r"_emit\(['\"]select-change['\"]"
        )

    # 3a.7 – Decision 2 (REPLACE-only marquee — NOT additive)
    def test_marquee_replace_semantics(self):
        """Marquee mouseup path must REPLACE selection (new Set(...) or .clear() then add).
        Pure additive-only (.add() without replacement) is forbidden. Cite Decision 2."""
        # Find the _onMouseUp handler body
        start = self.js_text.find("Network.prototype._onMouseUp = function")
        self.assertNotEqual(start, -1, "_onMouseUp not found")
        next_method = self.js_text.find("Network.prototype.", start + 1)
        body = self.js_text[start: next_method if next_method != -1 else len(self.js_text)]
        # REPLACE pattern: selectedNodeIds = new Set(...)
        replace_pattern = re.search(r"selectedNodeIds\s*=\s*new\s+Set\s*\(", body)
        # OR: .clear() followed by add (alternative REPLACE idiom)
        clear_pattern = re.search(r"selectedNodeIds\.clear\s*\(\s*\)", body)
        self.assertTrue(
            replace_pattern is not None or clear_pattern is not None,
            "Marquee mouseup must REPLACE selection via 'selectedNodeIds = new Set(...)' "
            "or '.clear()' — pure additive (.add() only) is forbidden per Decision 2."
        )


class TestSlice4HoverPopoverContracts(unittest.TestCase):
    """RED contracts for Slice 4 — hover metadata popovers (REQ-4.1 through REQ-4.10).

    All assertions are source-level regex/string checks — no JS execution required.
    Spec is binding: delay = 350 ms (REQ-4.1). Design default 320 ms is NOT a supersede.
    """

    @classmethod
    def setUpClass(cls):
        cls.assets_dir = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "assets"
        cls.src_dir = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "src"
        cls.templates_dir = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "templates"
        cls.js_path = cls.src_dir / "renderer.ts"
        cls.template_path = cls.templates_dir / "graph_viewer.html"
        cls.js_text = cls.js_path.read_text(encoding="utf-8")
        cls.template_text = cls.template_path.read_text(encoding="utf-8")

    def test_hover_popover_helper_present(self):
        """A popover show/hide helper method MUST be defined on the Network prototype.
        Cite REQ-4.4 (DOM element positioned via world→screen), OBS-4.1 (popover delay).
        Acceptable names: _showHoverPopover, _showPopover, _hoverPopover."""
        self.assertRegex(
            self.js_text,
            r"Network\.prototype\._(?:show(?:Hover)?Popover|hoverPopover)\s*=\s*function",
            "A popover helper (_showHoverPopover, _showPopover, or _hoverPopover) "
            "must be defined on Network.prototype (REQ-4.4).",
        )

    def test_hover_delay_constant_present(self):
        """A named hover-delay constant of 350 ms MUST be present in the renderer.
        Cite REQ-4.1: popover MUST NOT appear before the 350 ms delay elapses."""
        self.assertRegex(
            self.js_text,
            r"hoverDelay(?:Ms)?\s*=\s*350",
            "hoverDelayMs (or hoverDelay) must be set to 350 (REQ-4.1 — spec overrides design's 320).",
        )

    def test_hover_popover_dismissed_on_pan_or_scroll(self):
        """Popover must be cleared when pan starts, wheel fires, or select-change occurs.
        Cite REQ-4.6 (suppress during pan/zoom), REQ-4.7 (dismiss on wheel zoom)."""
        # _onMouseDown (pan start) and _onWheel (wheel zoom) must both call a hide/dismiss helper
        dismiss_calls = re.findall(
            r"_(?:hide|dismiss|clear)(?:Hover)?Popover\s*\(",
            self.js_text,
        )
        self.assertGreaterEqual(
            len(dismiss_calls),
            2,
            "Popover dismiss helper must be called in at least 2 places "
            "(pan start in _onMouseDown + wheel in _onWheel). Cite REQ-4.6 / OBS-4.6.",
        )

    def test_hover_popover_uses_world_to_screen(self):
        """Popover positioning MUST use _worldToScreen (Slice 1a) to track node's screen coords.
        Cite REQ-4.4 (positioned via world→screen transform)."""
        # The _updatePopoverPosition helper (or equivalent) must reference _worldToScreen
        # Strategy: find block that contains popover position logic and assert _worldToScreen presence
        self.assertIn(
            "_worldToScreen",
            self.js_text,
            "_worldToScreen must be present (added in Slice 1a).",
        )
        # A dedicated position update function must exist that calls _worldToScreen
        self.assertRegex(
            self.js_text,
            r"_updatePopoverPosition\b",
            "_updatePopoverPosition must be defined (REQ-4.4 — world→screen tracking).",
        )

    def test_hover_popover_aria_live_or_role_tooltip(self):
        """Popover element MUST have role='tooltip' (REQ-4.10) AND the renderer must
        reference aria-describedby for the node's a11y companion element (REQ-4.10).

        JS source uses setAttribute("role", "tooltip") — match either setAttribute form
        or an inline attribute literal."""
        self.assertRegex(
            self.js_text,
            r"""setAttribute\s*\(\s*['"]role['"]\s*,\s*['"]tooltip['"]\s*\)"""
            r"""|role=['"]{1}tooltip['"]{1}""",
            "Popover element must have role='tooltip' set in renderer (REQ-4.10). "
            "Acceptable forms: setAttribute(\"role\", \"tooltip\") or role=\"tooltip\".",
        )
        self.assertIn(
            "aria-describedby",
            self.js_text,
            "Renderer must set aria-describedby on focusable node element referencing "
            "the popover (REQ-4.10).",
        )


class TestSlice6ContextMenuContracts(unittest.TestCase):
    """RED contracts for Slice 6 — context menu (right-click) (REQ-6.1 through REQ-6.10).

    All assertions are source-level string/regex checks — no JS execution required.
    Cite spec §7 Slice 6 and design §3 Slice 6.
    """

    @classmethod
    def setUpClass(cls):
        src_dir = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "src"
        cls.js_path = src_dir / "renderer.ts"
        cls.js_text = cls.js_path.read_text(encoding="utf-8")

    def test_contextmenu_listener_and_preventDefault(self):
        """REQ-6.1: Renderer MUST attach a 'contextmenu' listener that calls
        event.preventDefault() to suppress the browser native menu.

        Cite REQ-6.1 / OBS-6.1."""
        self.assertRegex(
            self.js_text,
            r"""addEventListener\s*\(\s*['"]contextmenu['"]\s*,""",
            "Renderer must attach a 'contextmenu' event listener (REQ-6.1).",
        )
        self.assertIn(
            "event.preventDefault",
            self.js_text,
            "Renderer contextmenu handler MUST call event.preventDefault() (REQ-6.1).",
        )

    def test_context_menu_event_emitted(self):
        """REQ-6.2 / REQ-6.3: Renderer MUST emit a 'context-menu' event with
        nodeId, screen coords, world coords, and selection payload.

        Cite REQ-6.2 / design §3 Slice 6 algorithm."""
        self.assertRegex(
            self.js_text,
            r"""_emit\s*\(\s*['"]context-menu['"]\s*,""",
            "Renderer must emit 'context-menu' event (REQ-6.2).",
        )

    def test_context_menu_state_object_present(self):
        """Renderer MUST maintain a contextMenu state object with at minimum an
        'open' boolean field.  Design §3 Slice 6 specifies shape:
          { open: false, x: 0, y: 0, target: null }

        This state object is the gate that Slice 4's hover-suppression logic
        depends on (REQ-6.10 / REQ-4.6 coordination)."""
        self.assertRegex(
            self.js_text,
            r"this\.contextMenu\s*=\s*\{",
            "Renderer MUST initialise this.contextMenu object (design §3 Slice 6).",
        )
        self.assertRegex(
            self.js_text,
            r"contextMenu.*\bopen\b",
            "contextMenu state object MUST contain an 'open' boolean field (REQ-6.10).",
        )

    def test_context_menu_suppresses_popover(self):
        """REQ-6.10 / REQ-4.6: Opening a context menu MUST suppress the hover popover.
        The _onMouseMove hover guard MUST check contextMenu.open so that popover
        timers are not armed while a context menu is active.

        Cite REQ-6.10 / OBS-6.11."""
        # The guard at the top of the popover-arming block must include contextMenu.open
        self.assertRegex(
            self.js_text,
            r"contextMenu(?:\.open|\[.open.\])",
            "_onMouseMove popover guard MUST reference contextMenu.open (REQ-6.10).",
        )


class TestSlice7bThemeRendererContracts(unittest.TestCase):
    """RED contracts for Slice 7b — renderer consumption of CSS design tokens."""

    @classmethod
    def setUpClass(cls):
        src_dir = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "src"
        cls.js_path = src_dir / "renderer.ts"
        cls.js_text = cls.js_path.read_text(encoding="utf-8")

    def test_renderer_reads_computed_style_for_theme_tokens(self):
        self.assertIn("getComputedStyle", self.js_text)
        self.assertIn("--vis-panel-text", self.js_text)
        self.assertIn("--vis-panel-bg", self.js_text)
        self.assertIn("--vis-focus-ring", self.js_text)

    def test_renderer_has_theme_token_refresh_helper(self):
        self.assertRegex(self.js_text, r"_refreshThemeTokens\s*=\s*function")

    def test_draw_paths_use_cached_theme_tokens(self):
        self.assertRegex(self.js_text, r"this\._themeTokens")


if __name__ == "__main__":
    unittest.main()
