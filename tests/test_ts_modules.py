"""PR 2 — theme-bridge.ts and motion.ts module extraction.

Contract tests (Python source-scanning) for the two pure utility modules.
These run RED until the TS files are created.

Modules:
  - brain_ds/ui/src/tokens/theme-bridge.ts
      getComputedStyle wrapper; emits 'theme-changed' event.
      Single source of truth for reading CSS custom properties.

  - brain_ds/ui/src/motion/motion.ts
      motionEnabled() helper; prefers-reduced-motion subscription.
      Single place reduced-motion is consulted from JS-side code.

Design binding: §1.2 — both modules are pure additive infrastructure.
renderer.ts is NOT modified in PR2 (locked literal contracts remain).
"""

import unittest
from pathlib import Path

UI_DIR = Path(__file__).resolve().parent.parent / "brain_ds" / "ui"
SRC_DIR = UI_DIR / "src"
TOKENS_DIR = SRC_DIR / "tokens"
MOTION_DIR = SRC_DIR / "motion"
PANELS_DIR = SRC_DIR / "panels"


class TestThemeBridgeModuleExists(unittest.TestCase):
    """theme-bridge.ts must exist at src/tokens/theme-bridge.ts (RED until created)."""

    @classmethod
    def setUpClass(cls):
        cls.path = TOKENS_DIR / "theme-bridge.ts"
        cls.exists = cls.path.exists()
        cls.text = cls.path.read_text(encoding="utf-8") if cls.exists else ""

    def _require(self):
        if not self.exists:
            self.fail(f"src/tokens/theme-bridge.ts not found at {self.path}")

    def test_file_exists(self):
        self._require()

    def test_file_is_nonempty(self):
        self._require()
        self.assertGreater(len(self.text.splitlines()), 5,
                           "theme-bridge.ts must have more than 5 lines")

    def test_exports_readCssVar(self):
        """readCssVar: getComputedStyle wrapper returning CSS custom property value."""
        self._require()
        self.assertRegex(
            self.text,
            r"export\s+function\s+readCssVar",
            "theme-bridge.ts must export a function named readCssVar",
        )

    def test_exports_getThemeTokens(self):
        """getThemeTokens: returns a record of resolved token values for an element."""
        self._require()
        self.assertRegex(
            self.text,
            r"export\s+function\s+getThemeTokens",
            "theme-bridge.ts must export a function named getThemeTokens",
        )

    def test_exports_emitThemeChanged(self):
        """emitThemeChanged: dispatches a 'theme-changed' CustomEvent."""
        self._require()
        self.assertRegex(
            self.text,
            r"export\s+function\s+emitThemeChanged",
            "theme-bridge.ts must export a function named emitThemeChanged",
        )

    def test_exports_subscribeThemeChanged(self):
        """subscribeThemeChanged: registers a listener for 'theme-changed' events."""
        self._require()
        self.assertRegex(
            self.text,
            r"export\s+function\s+subscribeThemeChanged",
            "theme-bridge.ts must export a function named subscribeThemeChanged",
        )

    def test_uses_getComputedStyle(self):
        """Must use getComputedStyle — the raison d'etre of this module."""
        self._require()
        self.assertIn(
            "getComputedStyle",
            self.text,
            "theme-bridge.ts must contain getComputedStyle",
        )

    def test_getPropertyValue_pattern(self):
        """Must call .getPropertyValue() on the computed style result."""
        self._require()
        self.assertRegex(
            self.text,
            r"getPropertyValue",
            "theme-bridge.ts must call getPropertyValue on computed style",
        )

    def test_theme_changed_event_name(self):
        """Must reference the 'theme-changed' event string."""
        self._require()
        self.assertIn(
            "theme-changed",
            self.text,
            "theme-bridge.ts must reference the 'theme-changed' event name",
        )

    def test_no_matchMedia_in_theme_bridge(self):
        """theme-bridge.ts must NOT handle reduced-motion — that's motion.ts's job."""
        self._require()
        self.assertNotIn(
            "matchMedia",
            self.text,
            "theme-bridge.ts must not contain matchMedia (reduced-motion belongs in motion.ts)",
        )

    def test_readCssVar_accepts_fallback(self):
        """readCssVar signature must accept a fallback parameter."""
        self._require()
        self.assertRegex(
            self.text,
            r"function\s+readCssVar\s*\([^)]*fallback",
            "readCssVar must accept a fallback parameter",
        )

    def test_no_external_imports(self):
        """theme-bridge.ts must have no external package imports."""
        self._require()
        for line in self.text.splitlines():
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("*"):
                continue
            if stripped.startswith("import "):
                self.assertRegex(
                    stripped,
                    r"""^import\s+.*['"]\./""",
                    f"Only relative imports allowed in theme-bridge.ts, got: {stripped}",
                )


class TestMotionModuleExists(unittest.TestCase):
    """motion.ts must exist at src/motion/motion.ts (RED until created)."""

    @classmethod
    def setUpClass(cls):
        cls.path = MOTION_DIR / "motion.ts"
        cls.exists = cls.path.exists()
        cls.text = cls.path.read_text(encoding="utf-8") if cls.exists else ""

    def _require(self):
        if not self.exists:
            self.fail(f"src/motion/motion.ts not found at {self.path}")

    def test_file_exists(self):
        self._require()

    def test_file_is_nonempty(self):
        self._require()
        self.assertGreater(len(self.text.splitlines()), 5,
                           "motion.ts must have more than 5 lines")

    def test_exports_motionEnabled(self):
        """motionEnabled(): boolean — single source of truth for reduced-motion check."""
        self._require()
        self.assertRegex(
            self.text,
            r"export\s+function\s+motionEnabled",
            "motion.ts must export a function named motionEnabled",
        )

    def test_exports_subscribeReducedMotion(self):
        """subscribeReducedMotion(cb): registers a change listener."""
        self._require()
        self.assertRegex(
            self.text,
            r"export\s+function\s+subscribeReducedMotion",
            "motion.ts must export a function named subscribeReducedMotion",
        )

    def test_uses_matchMedia(self):
        """Must call matchMedia — core mechanism for reduced-motion detection."""
        self._require()
        self.assertIn(
            "matchMedia",
            self.text,
            "motion.ts must contain matchMedia",
        )

    def test_prefers_reduced_motion_query_string(self):
        """Must reference the exact media query string."""
        self._require()
        self.assertIn(
            "prefers-reduced-motion",
            self.text,
            "motion.ts must contain 'prefers-reduced-motion'",
        )

    def test_prefers_reduced_motion_reduce_value(self):
        """Must test for 'reduce' specifically, not just the media feature."""
        self._require()
        self.assertRegex(
            self.text,
            r"prefers-reduced-motion.*reduce",
            "motion.ts must reference 'prefers-reduced-motion: reduce'",
        )

    def test_motionEnabled_returns_negation_of_matches(self):
        """motionEnabled returns true when reduced-motion is NOT requested."""
        self._require()
        # Should contain a negation — either !matches or matches === false
        self.assertRegex(
            self.text,
            r"!\s*(?:\w+\.)?matches|matches\s*===?\s*false|!.*matches",
            "motionEnabled must return the negation of MediaQueryList.matches",
        )

    def test_addEventListener_or_addListener_for_change(self):
        """Must subscribe to media query changes (addEventListener or addListener)."""
        self._require()
        self.assertRegex(
            self.text,
            r"addEventListener\s*\(\s*['\"]change['\"]|addListener",
            "motion.ts must subscribe to media query change events",
        )

    def test_no_getComputedStyle_in_motion(self):
        """motion.ts must NOT handle CSS token reads — that's theme-bridge.ts's job."""
        self._require()
        self.assertNotIn(
            "getComputedStyle",
            self.text,
            "motion.ts must not contain getComputedStyle (CSS reads belong in theme-bridge.ts)",
        )

    def test_no_external_imports(self):
        """motion.ts must have no external package imports."""
        self._require()
        for line in self.text.splitlines():
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("*"):
                continue
            if stripped.startswith("import "):
                self.assertRegex(
                    stripped,
                    r"""^import\s+.*['"]\./""",
                    f"Only relative imports allowed in motion.ts, got: {stripped}",
                )


class TestThemeBridgeTriangulation(unittest.TestCase):
    """Triangulate: alternate paths not covered by the primary contract.

    These ensure the module is complete enough to be useful to later slices.
    RED until theme-bridge.ts is created.
    """

    @classmethod
    def setUpClass(cls):
        cls.path = TOKENS_DIR / "theme-bridge.ts"
        cls.exists = cls.path.exists()
        cls.text = cls.path.read_text(encoding="utf-8") if cls.exists else ""

    def _require(self):
        if not self.exists:
            self.fail(f"src/tokens/theme-bridge.ts not found at {self.path}")

    def test_readCssVar_handles_empty_value(self):
        """readCssVar must have a code path for empty / whitespace values.

        Design binding: the renderer's _readCssVar checks for empty+trim before
        returning the fallback. theme-bridge.ts must preserve this contract.
        """
        self._require()
        # Either 'trim' or a truthy check on the value
        self.assertRegex(
            self.text,
            r"\.trim\(\)|value\s*&&|if\s*\(\s*value",
            "readCssVar must handle empty/whitespace CSS property values",
        )

    def test_getThemeTokens_references_vis_panel_bg(self):
        """getThemeTokens must know about --vis-panel-bg (one of the locked token names).

        This ensures the token map in theme-bridge.ts is aligned with renderer.ts.
        """
        self._require()
        self.assertIn(
            "--vis-panel-bg",
            self.text,
            "getThemeTokens must reference --vis-panel-bg token",
        )

    def test_getThemeTokens_references_vis_focus_ring(self):
        """getThemeTokens must know about --vis-focus-ring."""
        self._require()
        self.assertIn(
            "--vis-focus-ring",
            self.text,
            "getThemeTokens must reference --vis-focus-ring token",
        )

    def test_CustomEvent_dispatched_on_emitThemeChanged(self):
        """emitThemeChanged must dispatch a real browser event using CustomEvent or dispatchEvent."""
        self._require()
        self.assertRegex(
            self.text,
            r"CustomEvent|dispatchEvent",
            "emitThemeChanged must use CustomEvent / dispatchEvent",
        )


class TestMotionTriangulation(unittest.TestCase):
    """Triangulate: alternate paths in motion.ts.

    RED until motion.ts is created.
    """

    @classmethod
    def setUpClass(cls):
        cls.path = MOTION_DIR / "motion.ts"
        cls.exists = cls.path.exists()
        cls.text = cls.path.read_text(encoding="utf-8") if cls.exists else ""

    def _require(self):
        if not self.exists:
            self.fail(f"src/motion/motion.ts not found at {self.path}")

    def test_motionEnabled_guards_matchMedia_availability(self):
        """If matchMedia is not a function (e.g., JSDOM), motionEnabled must return true (safe default).

        Design binding: renderer._bindReducedMotion has:
          if (typeof window.matchMedia !== 'function') return;
        motion.ts must preserve the same defensive guard.
        """
        self._require()
        self.assertRegex(
            self.text,
            r"typeof.*matchMedia|matchMedia\s*!==|window\.matchMedia",
            "motionEnabled must guard for matchMedia availability",
        )

    def test_subscribeReducedMotion_accepts_callback(self):
        """subscribeReducedMotion takes a callback parameter."""
        self._require()
        self.assertRegex(
            self.text,
            r"function\s+subscribeReducedMotion\s*\(\s*\w+",
            "subscribeReducedMotion must accept a callback parameter",
        )

    def test_handles_legacy_addListener_fallback(self):
        """For older browser compat, must try addListener if addEventListener is unavailable.

        Design binding: renderer._bindReducedMotion has the addListener fallback.
        motion.ts must carry this forward.
        """
        self._require()
        self.assertIn(
            "addListener",
            self.text,
            "motion.ts must have addListener fallback for older browsers",
        )


if __name__ == "__main__":
    unittest.main()


class TestMarkdownMiniModuleContracts(unittest.TestCase):
    """W3 RED contracts for panels/markdown-mini.ts."""

    @classmethod
    def setUpClass(cls):
        cls.path = PANELS_DIR / "markdown-mini.ts"
        cls.exists = cls.path.exists()
        cls.text = cls.path.read_text(encoding="utf-8") if cls.exists else ""

    def _require(self):
        if not self.exists:
            self.fail(f"src/panels/markdown-mini.ts not found at {self.path}")

    def test_file_exists(self):
        self._require()

    def test_exports_escapeHtml(self):
        self._require()
        self.assertRegex(self.text, r"export\s+function\s+escapeHtml")

    def test_exports_renderMarkdown(self):
        self._require()
        self.assertRegex(self.text, r"export\s+function\s+renderMarkdown")

    def test_escapes_angle_brackets_and_quotes(self):
        self._require()
        self.assertRegex(self.text, r"replace\([^\n]*<[^\n]*&lt;")
        self.assertRegex(self.text, r"replace\([^\n]*>[^\n]*&gt;")
        self.assertRegex(self.text, r"replace\([^\n]*\"[^\n]*&quot;")

    def test_supports_headers_lists_bold(self):
        self._require()
        self.assertRegex(self.text, r"#{1,3}|h1|h2|h3")
        self.assertRegex(self.text, r"<ul>|<li>|[-*]\\s+")
        self.assertRegex(self.text, r"<strong>|\*\*")

    def test_supports_wikilinks_without_network(self):
        self._require()
        self.assertRegex(self.text, r"\[\[([^\]]+)\]\]")
        self.assertIn("data-node-label", self.text)
        self.assertNotIn("fetch(", self.text)
        self.assertNotIn("XMLHttpRequest", self.text)


class TestSplitPaneModuleContracts(unittest.TestCase):
    """W3 RED contracts for panels/split-pane.ts integration hooks."""

    @classmethod
    def setUpClass(cls):
        cls.path = PANELS_DIR / "split-pane.ts"
        cls.exists = cls.path.exists()
        cls.text = cls.path.read_text(encoding="utf-8") if cls.exists else ""
        cls.main_text = (SRC_DIR / "main.ts").read_text(encoding="utf-8")
        cls.template_text = (UI_DIR / "templates" / "graph_viewer.html").read_text(encoding="utf-8")

    def _require(self):
        if not self.exists:
            self.fail(f"src/panels/split-pane.ts not found at {self.path}")

    def test_split_pane_file_exists(self):
        self._require()

    def test_split_pane_exports_mount(self):
        self._require()
        self.assertRegex(self.text, r"export\s+function\s+mount")

    def test_main_imports_and_exposes_split_pane(self):
        self.assertRegex(self.main_text, r"import\s+\*\s+as\s+splitPane\s+from\s+['\"]\./panels/split-pane['\"]")
        self.assertIn("splitPane", self.main_text)

    def test_template_has_show_more_and_reader_pane_hooks(self):
        self.assertIn('id="show-more"', self.template_text)
        self.assertIn('id="markdown-reader"', self.template_text)
        self.assertIn('id="center-split"', self.template_text)
        # D.4 visual port: button label aligned with reference (Spanish "Ver Más").
        # "Show More" / "Ver Más" / "Mostrar más" all acceptable.
        self.assertRegex(self.template_text, r"Show More|Ver M[áa]s|Mostrar m[áa]s")


class TestGraphVisualRichnessD4aContracts(unittest.TestCase):
    """D.4.a RED/GREEN contracts: dual-engine architecture skeleton only."""

    @classmethod
    def setUpClass(cls):
        cls.renderer_dom_path = SRC_DIR / "renderer-dom.ts"
        cls.renderer_dom_exists = cls.renderer_dom_path.exists()
        cls.renderer_dom_text = cls.renderer_dom_path.read_text(encoding="utf-8") if cls.renderer_dom_exists else ""
        cls.main_text = (SRC_DIR / "main.ts").read_text(encoding="utf-8")
        cls.template_text = (UI_DIR / "templates" / "graph_viewer.html").read_text(encoding="utf-8")

    def _require_renderer_dom(self):
        if not self.renderer_dom_exists:
            self.fail(f"src/renderer-dom.ts not found at {self.renderer_dom_path}")

    def test_renderer_dom_file_exists(self):
        self._require_renderer_dom()

    def test_renderer_dom_exports_mount_and_deps_interface(self):
        self._require_renderer_dom()
        self.assertRegex(self.renderer_dom_text, r"export\s+interface\s+DomRendererDeps")
        self.assertRegex(self.renderer_dom_text, r"export\s+function\s+mount\s*\(")

    def test_renderer_dom_subscribes_to_dataset(self):
        self._require_renderer_dom()
        self.assertIn("deps.dataset._subscribe", self.renderer_dom_text)

    def test_main_imports_and_wires_renderer_dom_mount(self):
        self.assertRegex(self.main_text, r"import\s+\*\s+as\s+rendererDom\s+from\s+['\"]\./renderer-dom['\"]")
        self.assertIn("rendererDom.mount", self.main_text)
        self.assertIn("dataset: nodes", self.main_text)

    def test_template_contains_d4_mount_points_and_isolated_style_block(self):
        self.assertIn('<style id="d4-visual-richness">', self.template_text)
        self.assertIn('id="d4-edges"', self.template_text)
        self.assertIn('id="d4-nodes"', self.template_text)


class TestGraphVisualRichnessD4bcContracts(unittest.TestCase):
    """D.4.b + D.4.c contracts for node-state engine and SVG edge layer."""

    @classmethod
    def setUpClass(cls):
        cls.renderer_dom_path = SRC_DIR / "renderer-dom.ts"
        cls.renderer_dom_exists = cls.renderer_dom_path.exists()
        cls.renderer_dom_text = cls.renderer_dom_path.read_text(encoding="utf-8") if cls.renderer_dom_exists else ""
        cls.template_text = (UI_DIR / "templates" / "graph_viewer.html").read_text(encoding="utf-8")

    def _require_renderer_dom(self):
        if not self.renderer_dom_exists:
            self.fail(f"src/renderer-dom.ts not found at {self.renderer_dom_path}")

    def test_renderer_dom_declares_node_state_and_ego_dimming_contract(self):
        self._require_renderer_dom()
        for token in [
            "default",
            "hover-target",
            "hover-related",
            "selected-target",
            "selected-related",
            "data-has-hover",
            "data-has-selection",
        ]:
            self.assertIn(token, self.renderer_dom_text)

    def test_renderer_dom_has_wcc_color_and_muted_color_mapping(self):
        self._require_renderer_dom()
        self.assertIn("--node-color", self.renderer_dom_text)
        self.assertIn("--node-color-muted", self.renderer_dom_text)
        self.assertIn("var(--wcc-c${", self.renderer_dom_text)

    def test_renderer_dom_creates_svg_line_edges_and_marks_related_state(self):
        self._require_renderer_dom()
        self.assertRegex(self.renderer_dom_text, r"createElementNS\([^\n]*line")
        self.assertIn("data-related", self.renderer_dom_text)
        self.assertIn("aria-hidden", self.renderer_dom_text)

    def test_renderer_dom_has_accessibility_and_roving_tabindex_contract(self):
        self._require_renderer_dom()
        self.assertIn(":focus-visible", self.template_text)
        self.assertIn("aria-label", self.renderer_dom_text)
        self.assertIn("tabIndex", self.renderer_dom_text)
        self.assertRegex(self.renderer_dom_text, r"ArrowLeft|ArrowRight|ArrowUp|ArrowDown")

    def test_template_style_block_contains_d4b_d4c_and_reduced_motion_rules(self):
        for token in [
            '.d4-node[data-state="selected-target"]',
            '.d4-node[data-state="hover-target"]',
            "@keyframes node-hover-breathe",
            "prefers-reduced-motion: reduce",
            "#d4-edges .d4-edge",
            ".canvas-container[data-has-hover='true']",
            ".canvas-container[data-has-selection='true']",
        ]:
            self.assertIn(token, self.template_text)

    def test_checkpoint_files_for_pr2_exist(self):
        checkpoints_dir = UI_DIR / "design" / "checkpoints"
        self.assertTrue((checkpoints_dir / "d4b-node-states.html").exists())
        self.assertTrue((checkpoints_dir / "d4c-edge-glow.html").exists())


class TestGraphVisualRichnessD4deContracts(unittest.TestCase):
    """D.4.d + D.4.e contracts for rich popover and canvas atmosphere."""

    @classmethod
    def setUpClass(cls):
        cls.popover_path = SRC_DIR / "interactions" / "popover.ts"
        cls.popover_exists = cls.popover_path.exists()
        cls.popover_text = cls.popover_path.read_text(encoding="utf-8") if cls.popover_exists else ""
        cls.template_text = (UI_DIR / "templates" / "graph_viewer.html").read_text(encoding="utf-8")

    def _require_popover(self):
        if not self.popover_exists:
            self.fail(f"src/interactions/popover.ts not found at {self.popover_path}")

    def test_popover_factory_contains_d4d_content_contract(self):
        self._require_popover()
        for token in [
            "hover-popover-title",
            "hover-popover-dot",
            "hover-popover-grid",
            "Score",
            "Neighbors",
            "Cluster",
            "Type",
            "hover-popover-hint",
            "adjacency",
        ]:
            self.assertIn(token, self.popover_text)

    def test_popover_mount_sets_hover_delay_150ms(self):
        self._require_popover()
        self.assertRegex(self.popover_text, r"hoverDelayMs\s*=\s*150")

    def test_template_contains_popover_chrome_css_contract(self):
        for token in [
            ".vis-popover",
            "width: 188px",
            "backdrop-filter: blur(8px)",
            "rgba(18,18,20,0.85)",
            ".vis-popover::before",
            "@keyframes d4-popover-reveal",
            "pointer-events: none",
            "aria-hidden",
        ]:
            self.assertIn(token, self.template_text)

    def test_template_contains_atmosphere_pattern_and_labels_contract(self):
        for token in [
            ".canvas-bg-gradient",
            "linear-gradient(#0a0a0c, #0f0f13)",
            ".canvas-bg-pattern",
            "radial-gradient(circle at 2px 2px, var(--text-bright) 1px, transparent 1px)",
            "opacity: 0.03",
            "pointer-events: none",
            ".off-side-label",
            "backdrop-filter: blur(4px)",
            "rgba(10,10,12,0.8)",
            "left: calc(100% + 10px)",
            "color: var(--text-bright)",
        ]:
            self.assertIn(token, self.template_text)

    def test_checkpoint_files_for_pr3_exist(self):
        checkpoints_dir = UI_DIR / "design" / "checkpoints"
        self.assertTrue((checkpoints_dir / "d4d-popover.html").exists())
        self.assertTrue((checkpoints_dir / "d4e-atmosphere.html").exists())
        self.assertTrue((checkpoints_dir / "d4-final-parity.html").exists())
