"""PR 3 — panels/detail-panel.ts extraction.

Contract tests (Python source-scanning) for the detail-panel module and its
wiring back into graph_viewer.html via window.brainDsUI.

Design binding: §1.2 — panels/ modules have mount(root, deps) / unmount() shape.
PR 3 is extraction-only: zero new visual behaviour; behaviour preserved byte-for-byte.

RED until:
  1. brain_ds/ui/src/panels/detail-panel.ts is created with mount / unmount exports
  2. main.ts exposes window.brainDsUI.detailPanel
  3. graph_viewer.html delegates detail-card construction to the mounted module

Strict TDD — these tests define the contract; the module must satisfy them.
"""

import unittest
from pathlib import Path

UI_DIR = Path(__file__).resolve().parent.parent / "brain_ds" / "ui"
SRC_DIR = UI_DIR / "src"
PANELS_DIR = SRC_DIR / "panels"
TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent
    / "brain_ds" / "ui" / "templates" / "graph_viewer.html"
)


# ---------------------------------------------------------------------------
# 1. Module existence and API shape
# ---------------------------------------------------------------------------

class TestDetailPanelModuleExists(unittest.TestCase):
    """brain_ds/ui/src/panels/detail-panel.ts must exist with the right API."""

    @classmethod
    def setUpClass(cls):
        cls.path = PANELS_DIR / "detail-panel.ts"
        cls.exists = cls.path.exists()
        cls.text = cls.path.read_text(encoding="utf-8") if cls.exists else ""

    def _require(self):
        if not self.exists:
            self.fail(f"panels/detail-panel.ts not found at {self.path}")

    def test_file_exists(self):
        """panels/detail-panel.ts must be created for PR 3."""
        self._require()

    def test_file_is_nonempty(self):
        """Module must have at least 20 lines of substance."""
        self._require()
        self.assertGreater(
            len(self.text.splitlines()), 20,
            "detail-panel.ts must have more than 20 lines",
        )

    def test_exports_mount_function(self):
        """mount(root, deps) is the design-mandated lifecycle entry point (§1.2)."""
        self._require()
        self.assertRegex(
            self.text,
            r"export\s+function\s+mount",
            "detail-panel.ts must export a function named mount",
        )

    def test_exports_unmount_function(self):
        """unmount() is the design-mandated teardown entry point (§1.2)."""
        self._require()
        self.assertRegex(
            self.text,
            r"export\s+function\s+unmount",
            "detail-panel.ts must export a function named unmount",
        )

    def test_mount_accepts_root_param(self):
        """mount must accept a root element parameter."""
        self._require()
        self.assertRegex(
            self.text,
            r"function\s+mount\s*\(\s*\w+",
            "mount must accept at least one parameter (root)",
        )

    def test_mount_accepts_deps_param(self):
        """mount must accept a deps parameter (design §1.2)."""
        self._require()
        self.assertRegex(
            self.text,
            r"function\s+mount\s*\([^)]*,\s*\w+",
            "mount must accept at least two parameters (root, deps)",
        )

    def test_no_external_imports(self):
        """detail-panel.ts must have no third-party package imports (REQ-GVP-X.2 / NFR-3)."""
        self._require()
        for line in self.text.splitlines():
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("*"):
                continue
            if stripped.startswith("import "):
                self.assertRegex(
                    stripped,
                    r"""^import\s+.*['"]\./""",
                    f"Only relative imports allowed in detail-panel.ts, got: {stripped}",
                )

    def test_no_react_usage(self):
        """No React, no lifecycle library (design §1.2, NFR-3)."""
        self._require()
        # Check for actual React imports or hook calls, not comments that mention React.
        self.assertNotIn("useState", self.text,
                          "detail-panel.ts must not use React hooks")
        self.assertNotIn("useEffect", self.text,
                          "detail-panel.ts must not use React hooks")
        self.assertNotRegex(
            self.text,
            r"""^import\s+.*from\s+['"]react['"]""",
            "detail-panel.ts must not import from 'react'",
        )


# ---------------------------------------------------------------------------
# 2. Content extraction — core rendering logic is in the module
# ---------------------------------------------------------------------------

class TestDetailPanelContentExtraction(unittest.TestCase):
    """The extracted functions must appear in detail-panel.ts, not just exist."""

    @classmethod
    def setUpClass(cls):
        cls.path = PANELS_DIR / "detail-panel.ts"
        cls.exists = cls.path.exists()
        cls.text = cls.path.read_text(encoding="utf-8") if cls.exists else ""

    def _require(self):
        if not self.exists:
            self.fail(f"panels/detail-panel.ts not found at {self.path}")

    def test_contains_renderEvidence_logic(self):
        """Evidence rendering logic (renderEvidence) must live in this module."""
        self._require()
        # The function name or its key DOM construction pattern must be present
        self.assertRegex(
            self.text,
            r"renderEvidence|evidence-item|evidence-list",
            "detail-panel.ts must contain evidence rendering logic",
        )

    def test_contains_renderRelationships_logic(self):
        """Relationship rendering logic must live in this module."""
        self._require()
        self.assertRegex(
            self.text,
            r"renderRelationships|relationship-group|relationship-list",
            "detail-panel.ts must contain relationship rendering logic",
        )

    def test_contains_detail_panel_render_logic(self):
        """renderDetailPanel (or equivalent) must live in this module."""
        self._require()
        self.assertRegex(
            self.text,
            r"renderDetailPanel|detail-body|data-state|is-empty",
            "detail-panel.ts must contain detail panel render logic",
        )

    def test_contains_detail_panel_editable_logic(self):
        """renderDetailPanelEditable (or equivalent) must live in this module."""
        self._require()
        self.assertRegex(
            self.text,
            r"renderDetailPanelEditable|Editable|textarea|labelInput",
            "detail-panel.ts must contain editable mode render logic",
        )

    def test_contains_collapse_logic(self):
        """collapseDetailPanel must be in the module."""
        self._require()
        self.assertRegex(
            self.text,
            r"collapseDetailPanel|is-collapsed|aria-expanded",
            "detail-panel.ts must contain collapse/expand logic",
        )

    def test_data_source_connection_renders_now_explorable_badge(self):
        """A Data Source with details.connection must show an explicit explorable state."""
        self._require()
        for token in (
            "detail-explorable-badge",
            "now explorable",
            "connection",
            "role", "status",
        ):
            self.assertIn(token, self.text)


# ---------------------------------------------------------------------------
# 3. Wiring — main.ts exposes the module on window.brainDsUI
# ---------------------------------------------------------------------------

class TestMainTsWiring(unittest.TestCase):
    """main.ts must expose detail-panel functions via window.brainDsUI."""

    @classmethod
    def setUpClass(cls):
        cls.path = SRC_DIR / "main.ts"
        cls.exists = cls.path.exists()
        cls.text = cls.path.read_text(encoding="utf-8") if cls.exists else ""

    def _require(self):
        if not self.exists:
            self.fail(f"src/main.ts not found at {self.path}")

    def test_imports_detail_panel(self):
        """main.ts must import from panels/detail-panel."""
        self._require()
        self.assertRegex(
            self.text,
            r"""import\s+.*['"]\./panels/detail-panel""",
            "main.ts must import from ./panels/detail-panel",
        )

    def test_exposes_brainDsUI_namespace(self):
        """main.ts must attach the panel API to window.brainDsUI (wiring contract)."""
        self._require()
        self.assertIn(
            "brainDsUI",
            self.text,
            "main.ts must define/expose window.brainDsUI namespace",
        )

    def test_exposes_detailPanel_on_window(self):
        """window.brainDsUI.detailPanel must be the delegation target."""
        self._require()
        self.assertIn(
            "detailPanel",
            self.text,
            "main.ts must expose detailPanel on the brainDsUI namespace",
        )

    def test_exposes_network_slot_on_window_namespace(self):
        """W7: main.ts must expose a brainDsUI.network slot for click-to-focus wiring."""
        self._require()
        self.assertIn("brainDsUI", self.text)
        self.assertIn("network", self.text)


# ---------------------------------------------------------------------------
# 4. Template delegation — graph_viewer.html calls the mounted module
# ---------------------------------------------------------------------------

class TestTemplateDeligation(unittest.TestCase):
    """graph_viewer.html must delegate to window.brainDsUI.detailPanel, not inline."""

    @classmethod
    def setUpClass(cls):
        cls.exists = TEMPLATE_PATH.exists()
        cls.text = TEMPLATE_PATH.read_text(encoding="utf-8") if cls.exists else ""

    def _require(self):
        if not self.exists:
            self.fail(f"template not found at {TEMPLATE_PATH}")

    def test_template_delegates_renderDetailPanel(self):
        """Template must call brainDsUI.detailPanel.render (or equivalent)
        rather than defining renderDetailPanel inline."""
        self._require()
        self.assertIn(
            "brainDsUI",
            self.text,
            "graph_viewer.html must reference window.brainDsUI for delegation",
        )

    def test_template_no_longer_defines_renderEvidence_inline(self):
        """renderEvidence must be removed from the inline script — it now lives in the module."""
        self._require()
        self.assertNotIn(
            "const renderEvidence",
            self.text,
            "renderEvidence must be extracted from template inline script into detail-panel.ts",
        )

    def test_template_no_longer_defines_renderRelationships_inline(self):
        """renderRelationships must be removed from the inline script."""
        self._require()
        self.assertNotIn(
            "const renderRelationships",
            self.text,
            "renderRelationships must be extracted from template inline script into detail-panel.ts",
        )

    def test_template_no_longer_defines_renderDetailPanel_inline(self):
        """renderDetailPanel body must no longer be inline — only a delegation shim is allowed.

        The original inline body contained the pattern:
          editToggleBtn.setAttribute("aria-pressed", "false");
        which set internal editMode state directly in the template.
        In the extracted version, this is handled inside the module.
        A delegation shim that calls window.brainDsUI.detailPanel won't contain this.
        """
        self._require()
        # The old inline renderDetailPanel body directly manipulated editToggleBtn state.
        # The extracted version keeps this inside the module.
        self.assertNotIn(
            'editToggleBtn.setAttribute("aria-pressed", "false")',
            self.text,
            "renderDetailPanel inline body must be extracted; editToggleBtn.setAttribute "
            "inside the template indicates the implementation was not moved to detail-panel.ts",
        )

    def test_template_no_longer_defines_renderDetailPanelEditable_inline(self):
        """renderDetailPanelEditable must be removed from the inline script."""
        self._require()
        self.assertNotIn(
            "const renderDetailPanelEditable",
            self.text,
            "renderDetailPanelEditable must be extracted from template inline script into detail-panel.ts",
        )


# ---------------------------------------------------------------------------
# 5. Triangulation — mount / unmount lifecycle paths
# ---------------------------------------------------------------------------

class TestDetailPanelTriangulation(unittest.TestCase):
    """Triangulate: alternate paths to confirm completeness."""

    @classmethod
    def setUpClass(cls):
        cls.path = PANELS_DIR / "detail-panel.ts"
        cls.exists = cls.path.exists()
        cls.text = cls.path.read_text(encoding="utf-8") if cls.exists else ""

    def _require(self):
        if not self.exists:
            self.fail(f"panels/detail-panel.ts not found at {self.path}")

    def test_edit_mode_focuses_first_editable_input(self):
        """REQ-GVP-5.5: entering edit mode moves focus to first editable input."""
        self._require()
        self.assertRegex(
            self.text,
            r"(labelInput|textarea)\.focus\(",
            "detail-panel.ts must focus the first editable field when entering edit mode",
        )

    def test_relationships_render_before_evidence(self):
        """REQ-GVP-5.6: section order keeps relationships before evidence blocks."""
        self._require()
        rel_idx = self.text.find("const relationships = renderRelationships")
        ev_idx = self.text.find("const evidence = detail.evidence")
        self.assertNotEqual(rel_idx, -1, "Missing relationships render block")
        self.assertNotEqual(ev_idx, -1, "Missing evidence render block")
        self.assertLess(
            rel_idx,
            ev_idx,
            "detail-panel.ts must render relationships before evidence",
        )

    def test_score_chip_markup_is_defined(self):
        """REQ-GVP-5.4: score badge/chip contract must exist in module markup."""
        self._require()
        self.assertIn(
            "detail-score-chip",
            self.text,
            "detail-panel.ts must define a detail score chip element",
        )

    def test_unmount_removes_event_listeners(self):
        """unmount must clean up event listeners (removeEventListener or closure cleanup)."""
        self._require()
        self.assertRegex(
            self.text,
            r"removeEventListener|_listeners\s*=|listeners\.length\s*=|teardown|cleanup",
            "unmount must clean up event listeners or state",
        )

    def test_render_with_null_clears_panel(self):
        """Rendering with null/undefined nodeId must set the panel to empty state."""
        self._require()
        self.assertRegex(
            self.text,
            r"is-empty|data-state.*empty|null.*nodeId|!nodeId|!detail",
            "detail-panel.ts must handle null/undefined nodeId (empty state)",
        )

    def test_evidence_badge_construction(self):
        """Evidence badge (span.badge) must be constructed in this module."""
        self._require()
        self.assertIn(
            "badge",
            self.text,
            "detail-panel.ts must contain badge construction for evidence items",
        )

    def test_select_change_event_subscription(self):
        """Module must subscribe to or handle the select-change event (design §1.2)."""
        self._require()
        self.assertIn(
            "select-change",
            self.text,
            "detail-panel.ts must reference 'select-change' event",
        )

    def test_collapseDetailPanel_uses_aria_expanded(self):
        """Collapse logic must update aria-expanded (REQ-GVP-4.7)."""
        self._require()
        self.assertIn(
            "aria-expanded",
            self.text,
            "detail-panel.ts must set aria-expanded on collapse/expand",
        )

    def test_w6_gap_slots_render_dashed_placeholder_contract(self):
        self._require()
        self.assertIn("section--gap", self.text)
        self.assertIn("[Information Missing / Pending Capture]", self.text)

    def test_w7_relationships_group_by_type_contract(self):
        self._require()
        self.assertRegex(self.text, r"edge_label")
        self.assertRegex(self.text, r"relationship-group")
        self.assertRegex(self.text, r"No relationships")
        self.assertNotIn('gHeading.textContent = direction[0].toUpperCase() + direction.slice(1)', self.text)

    def test_w7_relationship_row_click_focuses_target_contract(self):
        self._require()
        self.assertRegex(self.text, r"data-target-id")
        self.assertRegex(self.text, r"brainDsUI\.network")
        self.assertRegex(self.text, r"focus\(")


# ---------------------------------------------------------------------------
# 6. R11 — TS prerequisite: --card-accent via setProperty (obsidian-workspace-ui)
# ---------------------------------------------------------------------------

class TestCardAccentProperty(unittest.TestCase):
    """R11: detail-panel.ts must set --card-accent via setProperty, not borderLeftColor."""

    @classmethod
    def setUpClass(cls):
        cls.path = PANELS_DIR / "detail-panel.ts"
        cls.exists = cls.path.exists()
        cls.text = cls.path.read_text(encoding="utf-8") if cls.exists else ""

    def _require(self):
        if not self.exists:
            self.fail(f"panels/detail-panel.ts not found at {self.path}")

    def test_no_border_left_color_assignment(self):
        """R11-scenario-1: borderLeftColor must not appear anywhere in detail-panel.ts."""
        self._require()
        self.assertNotIn(
            "borderLeftColor",
            self.text,
            "detail-panel.ts must not use borderLeftColor; use setProperty('--card-accent', ...) instead",
        )

    def test_set_property_card_accent_called(self):
        """R11-scenario-2: setProperty('--card-accent', ...) must appear at least twice."""
        self._require()
        # Accept both single-quoted and double-quoted string forms
        count = self.text.count("'--card-accent'") + self.text.count('"--card-accent"')
        self.assertGreaterEqual(
            count,
            2,
            f"setProperty('--card-accent', ...) must appear at least 2 times; found {count}",
        )


class TestMarkdownMiniModule(unittest.TestCase):
    """DDS-3: markdown-mini.ts must export renderMarkdown used in detail-panel."""

    @classmethod
    def setUpClass(cls):
        cls.mm_path = PANELS_DIR / "markdown-mini.ts"
        cls.mm_exists = cls.mm_path.exists()
        cls.mm_text = cls.mm_path.read_text(encoding="utf-8") if cls.mm_exists else ""
        cls.dp_path = PANELS_DIR / "detail-panel.ts"
        cls.dp_exists = cls.dp_path.exists()
        cls.dp_text = cls.dp_path.read_text(encoding="utf-8") if cls.dp_exists else ""

    def test_markdown_mini_exports_renderMarkdown(self):
        """markdown-mini.ts must export renderMarkdown function."""
        self.assertTrue(self.mm_exists, "markdown-mini.ts must exist")
        self.assertIn("export function renderMarkdown", self.mm_text)

    def test_markdown_mini_renders_pipe_tables(self):
        """DDS-S2: pipe tables must produce <table> output, not raw | characters."""
        self.assertTrue(self.mm_exists, "markdown-mini.ts must exist")
        self.assertIn("md-table", self.mm_text, "renderMarkdown must produce md-table class tables")
        self.assertIn("<table", self.mm_text)

    def test_detail_panel_imports_renderMarkdown(self):
        """detail-panel.ts must import renderMarkdown from markdown-mini."""
        self.assertTrue(self.dp_exists, "detail-panel.ts must exist")
        self.assertRegex(
            self.dp_text,
            r"import\s+.*renderMarkdown.*from.*markdown-mini",
            "detail-panel.ts must import renderMarkdown from markdown-mini",
        )

    def test_detail_panel_uses_renderMarkdown_for_read_only_content(self):
        """DDS-3: read-only section content must go through renderMarkdown (innerHTML), not textContent."""
        self.assertTrue(self.dp_exists, "detail-panel.ts must exist")
        self.assertIn(
            "renderMarkdown",
            self.dp_text,
            "detail-panel.ts must call renderMarkdown for section content",
        )
        # The read-only div must use innerHTML to render markdown
        self.assertIn(
            "innerHTML",
            self.dp_text,
            "detail-panel.ts must set innerHTML (not textContent) for rendered markdown sections",
        )

    def test_detail_panel_edit_mode_still_uses_textarea(self):
        """DDS-3: edit source must remain a textarea (plain markdown), not rendered HTML."""
        self.assertTrue(self.dp_exists, "detail-panel.ts must exist")
        self.assertIn("textarea", self.dp_text)
        self.assertIn("textarea.value", self.dp_text)


if __name__ == "__main__":
    unittest.main()
