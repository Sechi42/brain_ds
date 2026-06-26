"""
T1.1 — Label-policy unit tests (Slice 1: graph-label-culling)

These tests check the source-level contract of:
  brain_ds/ui/src/labels/label-policy.ts

Convention: source-level regex/string checks, matching the pattern used by
test_canvas_renderer.py and test_d4_overlay_runtime.py in this repo.

All tests in this file MUST be RED before T1.2 implementation and GREEN after.
"""
import unittest
from pathlib import Path


class TestLabelPolicyModule(unittest.TestCase):
    """T1.1: Failing tests for label-policy.ts source contract."""

    @classmethod
    def setUpClass(cls):
        cls.labels_dir = (
            Path(__file__).resolve().parent.parent
            / "brain_ds" / "ui" / "src" / "labels"
        )
        cls.policy_path = cls.labels_dir / "label-policy.ts"
        # Read once; individual tests skip gracefully if file missing.
        if cls.policy_path.exists():
            cls.src = cls.policy_path.read_text(encoding="utf-8")
        else:
            cls.src = ""

    # ── File existence ──────────────────────────────────────────────────────

    def test_label_policy_file_exists(self):
        """T1.2 creates brain_ds/ui/src/labels/label-policy.ts."""
        self.assertTrue(
            self.policy_path.exists(),
            "brain_ds/ui/src/labels/label-policy.ts does not exist — T1.2 not yet implemented.",
        )

    # ── LabelDecision type export ───────────────────────────────────────────

    def test_label_decision_type_exported(self):
        """LabelDecision type must be exported (design interface contract)."""
        self.assertRegex(
            self.src,
            r"export\s+type\s+LabelDecision",
            "LabelDecision type must be exported from label-policy.ts.",
        )

    def test_label_decision_has_visible_field(self):
        """LabelDecision must have a 'visible' boolean field."""
        self.assertRegex(
            self.src,
            r"visible\s*:\s*boolean",
            "LabelDecision must declare 'visible: boolean'.",
        )

    def test_label_decision_has_reason_field(self):
        """LabelDecision must have a 'reason' discriminated union field."""
        self.assertIn(
            "reason",
            self.src,
            "LabelDecision must declare a 'reason' field.",
        )
        # Reason must cover the always-visible cases and culled/budget cases
        for reason in ("selected", "hovered", "focused", "pinned", "budget", "culled"):
            self.assertIn(
                reason,
                self.src,
                f"LabelDecision reason union must include '{reason}'.",
            )

    # ── computeVisibleLabels function ───────────────────────────────────────

    def test_compute_visible_labels_exported(self):
        """computeVisibleLabels must be an exported function."""
        self.assertRegex(
            self.src,
            r"export\s+(function\s+computeVisibleLabels|const\s+computeVisibleLabels)",
            "computeVisibleLabels must be exported from label-policy.ts.",
        )

    def test_compute_visible_labels_accepts_nodes_viewport_config(self):
        """computeVisibleLabels signature must accept nodes, viewport, config."""
        self.assertRegex(
            self.src,
            r"computeVisibleLabels\s*\([^)]*nodes[^)]*viewport[^)]*config[^)]*\)",
            "computeVisibleLabels must accept (nodes, viewport, config) parameters.",
        )

    # ── Config fields ───────────────────────────────────────────────────────

    def test_config_has_zoom_threshold(self):
        """Config must expose zoomThreshold field."""
        self.assertIn(
            "zoomThreshold",
            self.src,
            "Config must declare zoomThreshold.",
        )

    def test_config_has_budget_per_frame(self):
        """Config must expose budgetPerFrame field."""
        self.assertIn(
            "budgetPerFrame",
            self.src,
            "Config must declare budgetPerFrame.",
        )

    def test_config_has_priority_weights(self):
        """Config must expose priorityWeights field."""
        self.assertIn(
            "priorityWeights",
            self.src,
            "Config must declare priorityWeights.",
        )

    # ── Below-threshold logic ───────────────────────────────────────────────

    def test_below_threshold_returns_all_culled(self):
        """Below zoomThreshold all nodes must be culled (visible=false, reason='culled')."""
        self.assertRegex(
            self.src,
            r"viewport\.scale\s*<\s*\w+\.zoomThreshold|zoomThreshold.*viewport\.scale",
            "Module must compare viewport.scale against zoomThreshold.",
        )
        self.assertRegex(
            self.src,
            r"visible\s*:\s*false",
            "Must set visible: false for culled labels.",
        )
        self.assertIn(
            "'culled'",
            self.src,
            "Must use reason: 'culled' when below zoom threshold.",
        )

    # ── Always-visible logic ────────────────────────────────────────────────

    def test_always_visible_selected_hovered_pinned(self):
        """Selected, hovered, focused, pinned nodes must always be visible."""
        for state in ("selected", "hovered", "focused", "pinned", "clusterAnchor"):
            self.assertIn(
                state,
                self.src,
                f"Module must reference '{state}' state for always-visible logic.",
            )

    def test_always_visible_returns_true(self):
        """Always-visible nodes must return visible: true."""
        self.assertRegex(
            self.src,
            r"visible\s*:\s*true",
            "Always-visible nodes must return visible: true.",
        )

    # ── Budget cap logic ────────────────────────────────────────────────────

    def test_budget_cap_limits_label_count(self):
        """Budget cap must be applied — at most budgetPerFrame labels drawn."""
        self.assertIn(
            "budgetPerFrame",
            self.src,
            "Budget cap must reference budgetPerFrame.",
        )
        # Must compare a counter or slice against budget
        self.assertRegex(
            self.src,
            r"budget|count\s*>=|\.length\s*>=|\.slice\s*\(",
            "Module must implement a budget cap on the number of visible labels.",
        )

    # ── Priority ordering ───────────────────────────────────────────────────

    def test_priority_ordering_by_degree(self):
        """Priority ordering must reference degree or centrality for sorting."""
        self.assertRegex(
            self.src,
            r"\bdegree\b|\bcentrality\b",
            "Priority ordering must reference node degree or centrality.",
        )

    # ── No side effects ─────────────────────────────────────────────────────

    def test_no_dom_side_effects(self):
        """Module must not reference document, window, or DOM APIs."""
        for forbidden in ("document.", "window.", "getElementById", "querySelector"):
            self.assertNotIn(
                forbidden,
                self.src,
                f"label-policy.ts must be pure — no DOM reference to '{forbidden}'.",
            )

    # ── Return type is array of LabelDecision ──────────────────────────────

    def test_returns_label_decision_array(self):
        """computeVisibleLabels must return an array (LabelDecision[])."""
        self.assertRegex(
            self.src,
            r"LabelDecision\[\]|Array<LabelDecision>",
            "computeVisibleLabels return type must be LabelDecision[] or Array<LabelDecision>.",
        )


class TestCanvasRendererLabelIntegration(unittest.TestCase):
    """T1.3 — Canvas renderer label integration tests.

    These tests verify that renderer.ts is wired to computeVisibleLabels
    before each fillText call, and that the label-policy contract is honoured.

    Tests MUST be RED before T1.4 implementation and GREEN after.
    """

    @classmethod
    def setUpClass(cls):
        src_dir = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "src"
        cls.js_path = src_dir / "renderer.ts"
        cls.js_text = cls.js_path.read_text(encoding="utf-8")

    def test_label_policy_import_present(self):
        """renderer.ts must import computeVisibleLabels from label-policy."""
        self.assertRegex(
            self.js_text,
            r"computeVisibleLabels",
            "renderer.ts must reference computeVisibleLabels (T1.4 wiring).",
        )

    def test_fill_text_guarded_by_label_decision(self):
        """fillText must be guarded by a label decision check (visible === false skips)."""
        self.assertRegex(
            self.js_text,
            r"decision\.visible|labelDecision\.visible|\.visible\s*===\s*false|\.visible\s*!==\s*false",
            "fillText in renderer.ts must be guarded by label decision .visible flag.",
        )

    def test_fill_text_count_respects_budget(self):
        """Renderer must call computeVisibleLabels before the fillText loop."""
        # computeVisibleLabels call must appear before fillText in _drawNodes
        draw_nodes_start = self.js_text.find("Network.prototype._drawNodes = function")
        self.assertNotEqual(draw_nodes_start, -1, "_drawNodes not found in renderer.ts")
        next_method = self.js_text.find("Network.prototype.", draw_nodes_start + 1)
        body = self.js_text[draw_nodes_start: next_method if next_method != -1 else len(self.js_text)]
        cvl_pos = body.find("computeVisibleLabels")
        fill_pos = body.find("fillText")
        self.assertNotEqual(cvl_pos, -1, "computeVisibleLabels not found in _drawNodes body")
        self.assertNotEqual(fill_pos, -1, "fillText not found in _drawNodes body")
        self.assertLess(
            cvl_pos, fill_pos,
            "computeVisibleLabels must be called before fillText in _drawNodes.",
        )

    def test_selected_node_always_has_fill_text(self):
        """Selected/focused nodes must still get fillText (always-visible contract)."""
        # The renderer must pass selection/hover/focus state to computeVisibleLabels
        self.assertRegex(
            self.js_text,
            r"selectedNodeId|selectedNodeIds",
            "renderer.ts must pass selection state to label policy.",
        )


class TestD4OverlayLabelIndependence(unittest.TestCase):
    """T1.5 — D4 overlay label independence tests.

    Verifies that renderer-d4.ts applies the same label policy to .node-label
    CSS visibility, independently of canvas labels, without removing ARIA labels.

    Tests MUST be RED before T1.6 implementation and GREEN after.
    """

    @classmethod
    def setUpClass(cls):
        src_dir = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "src"
        cls.d4_path = src_dir / "renderer-d4.ts"
        cls.d4_text = cls.d4_path.read_text(encoding="utf-8")

    def test_d4_references_compute_visible_labels(self):
        """renderer-d4.ts must reference computeVisibleLabels for overlay labels."""
        self.assertIn(
            "computeVisibleLabels",
            self.d4_text,
            "renderer-d4.ts must reference computeVisibleLabels (T1.6 wiring).",
        )

    def test_d4_label_visibility_controlled_by_policy(self):
        """D4 overlay must set label visibility based on label decision."""
        self.assertRegex(
            self.d4_text,
            r"label\.style\.visibility|label\.hidden|label\.style\.display|label\.setAttribute.*aria-hidden",
            "renderer-d4.ts must control .node-label visibility via label policy decision.",
        )

    def test_d4_accessible_button_label_never_removed(self):
        """aria-label on button elements must not be removed by label policy."""
        # aria-label is always set on the button element (accessibility contract)
        self.assertRegex(
            self.d4_text,
            r"setAttribute\s*\(\s*['\"]aria-label['\"]",
            "renderer-d4.ts must always set aria-label on node button (never removed).",
        )

    def test_d4_label_gate_independent_of_canvas(self):
        """D4 overlay label gate must be independently computed (separate viewport/config)."""
        # D4 overlay has its own gate — must reference viewport scale or zoom independently
        self.assertRegex(
            self.d4_text,
            r"zoomThreshold|viewport\.scale|computeVisibleLabels",
            "D4 overlay must have its own label visibility gate independent of canvas.",
        )


class TestLabelConfigWiring(unittest.TestCase):
    """T1.7/T1.8 — Config wiring and WCAG smoke tests.

    Verifies that graph_viewer.html has label config wired in the script block,
    and that the feature flag (labels.enabled) and safe degradation are present.

    Tests MUST be RED before T1.8 implementation and GREEN after.
    """

    @classmethod
    def setUpClass(cls):
        cls.template_path = (
            Path(__file__).resolve().parent.parent
            / "brain_ds" / "ui" / "templates" / "graph_viewer.html"
        )
        cls.template = cls.template_path.read_text(encoding="utf-8")

    def test_label_config_zoom_threshold_present(self):
        """graph_viewer.html must define labels.zoomThreshold in the config block."""
        self.assertRegex(
            self.template,
            r"labels\s*[=:]\s*\{|zoomThreshold",
            "graph_viewer.html must wire labels.zoomThreshold config.",
        )

    def test_label_config_budget_per_frame_present(self):
        """graph_viewer.html must define labels.budgetPerFrame in the config block."""
        self.assertIn(
            "budgetPerFrame",
            self.template,
            "graph_viewer.html must wire labels.budgetPerFrame config.",
        )

    def test_label_config_enabled_flag_present(self):
        """graph_viewer.html must define labels.enabled feature flag (default true)."""
        self.assertIn(
            "labels.enabled",
            self.template,
            "graph_viewer.html must include labels.enabled feature flag.",
        )

    def test_label_safe_degradation_fallback_present(self):
        """Safe degradation: if module fails, all labels render."""
        # Either a try/catch around the computeVisibleLabels call, or a fallback
        # that renders all labels when the policy module is unavailable
        self.assertRegex(
            self.template,
            r"try\s*\{[\s\S]*?computeVisibleLabels|labels\.enabled\s*(?:===\s*false|!==\s*false|\?\?|&&)",
            "graph_viewer.html must include safe degradation for label policy failure.",
        )

    def test_keyboard_focus_label_always_visible(self):
        """Keyboard focus label must always render (WCAG — keyboard navigation)."""
        # The renderer must treat keyboardFocusedNodeId as always-visible
        renderer_path = (
            Path(__file__).resolve().parent.parent
            / "brain_ds" / "ui" / "src" / "renderer.ts"
        )
        renderer_src = renderer_path.read_text(encoding="utf-8")
        self.assertIn(
            "keyboardFocusedNodeId",
            renderer_src,
            "Keyboard focused node must always have its label visible (WCAG).",
        )


class TestRendererLabelPolicyDriftGuard(unittest.TestCase):
    """
    W1 drift guard: renderer.ts inlines a hand-synced copy of label-policy.ts.
    This test fails if critical constants or behavioural literals present in
    label-policy.ts diverge from the renderer.ts inline copy.

    CONTRACT (documented here and in a renderer.ts comment):
      Every constant/literal checked below must appear in BOTH sources.
      When you change label-policy.ts, update the inline in renderer.ts to match.
    """

    @classmethod
    def setUpClass(cls):
        src_dir = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "src"
        renderer_path = src_dir / "renderer.ts"
        policy_path = src_dir / "labels" / "label-policy.ts"
        cls.renderer = renderer_path.read_text(encoding="utf-8") if renderer_path.exists() else ""
        cls.policy = policy_path.read_text(encoding="utf-8") if policy_path.exists() else ""

    # ── Default-value constants ───────────────────────────────────────────────

    def test_zoom_threshold_default_in_both(self):
        """W1: zoomThreshold default 0.4 must appear in both label-policy.ts and renderer.ts."""
        self.assertRegex(
            self.policy,
            r"zoomThreshold\s*:\s*0\.4",
            "label-policy.ts must declare zoomThreshold default 0.4 (canonical source).",
        )
        self.assertRegex(
            self.renderer,
            r"zoomThreshold\s*:\s*0\.4|zoomThreshold.*0\.4",
            "renderer.ts inline must match label-policy.ts zoomThreshold default 0.4 (W1 drift guard).",
        )

    def test_budget_per_frame_default_in_both(self):
        """W1: budgetPerFrame default 80 must appear in both sources."""
        self.assertRegex(
            self.policy,
            r"budgetPerFrame\s*:\s*80",
            "label-policy.ts must declare budgetPerFrame default 80.",
        )
        self.assertRegex(
            self.renderer,
            r"budgetPerFrame\s*:\s*80",
            "renderer.ts inline must match label-policy.ts budgetPerFrame default 80 (W1 drift guard).",
        )

    # ── Behavioural literals ──────────────────────────────────────────────────

    def test_culled_reason_in_both(self):
        """W1: 'culled' reason literal must appear in both sources."""
        self.assertIn(
            "'culled'",
            self.policy,
            "label-policy.ts must use 'culled' reason literal.",
        )
        self.assertIn(
            "'culled'",
            self.renderer,
            "renderer.ts inline must use same 'culled' reason literal (W1 drift guard).",
        )

    def test_always_visible_reasons_in_both(self):
        """W1: always-visible reasons (selected/hovered/focused/pinned) must be in both."""
        for reason in ("selected", "hovered", "focused", "pinned"):
            self.assertIn(
                f"'{reason}'",
                self.policy,
                f"label-policy.ts must declare '{reason}' as always-visible reason.",
            )
            self.assertIn(
                f"'{reason}'",
                self.renderer,
                f"renderer.ts inline must have same '{reason}' always-visible reason (W1 drift guard).",
            )

    def test_compute_visible_labels_function_in_both(self):
        """W1: computeVisibleLabels function must exist in both sources."""
        self.assertIn(
            "computeVisibleLabels",
            self.policy,
            "label-policy.ts must export computeVisibleLabels.",
        )
        self.assertIn(
            "computeVisibleLabels",
            self.renderer,
            "renderer.ts inline must contain computeVisibleLabels (W1 drift guard).",
        )

    def test_cluster_anchor_reason_in_both(self):
        self.assertIn(
            "'cluster-anchor'",
            self.policy,
            "Cluster anchors must keep readable labels independent of label budget.",
        )
        self.assertIn(
            "'cluster-anchor'",
            self.renderer,
            "renderer.ts inline label policy must keep cluster anchor labels readable.",
        )

    def test_renderer_documents_inline_source(self):
        """
        W1: renderer.ts must have a comment naming label-policy.ts as the canonical source.
        This documents the hand-sync contract so it cannot be silently forgotten.
        """
        self.assertRegex(
            self.renderer,
            r"label-policy\.ts",
            "renderer.ts must document that the inline is sourced from label-policy.ts (W1 contract comment).",
        )


if __name__ == "__main__":
    unittest.main()
