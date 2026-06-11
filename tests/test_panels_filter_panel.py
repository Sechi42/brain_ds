"""
PR 5 — TDD contract tests for panels/filter-panel.ts extraction.

These tests assert source-file contracts (no DOM execution).
Pattern follows test_panels_search.py exactly.

TDD cycle: RED (this file) -> GREEN (module creation) -> TRIANGULATE -> REFACTOR.
"""

import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
FILTER_PANEL_MODULE = REPO / "brain_ds" / "ui" / "src" / "panels" / "filter-panel.ts"
MAIN_TS = REPO / "brain_ds" / "ui" / "src" / "main.ts"
TEMPLATE = REPO / "brain_ds" / "ui" / "templates" / "graph_viewer.html"
TREE_MODULE = REPO / "brain_ds" / "ui" / "src" / "panels" / "tree.ts"
RENDERER_D4 = REPO / "brain_ds" / "ui" / "src" / "renderer-d4.ts"


class TestFilterPanelModuleExists(unittest.TestCase):
    """Module-existence and export contracts."""

    def test_filter_panel_module_file_exists(self):
        """brain_ds/ui/src/panels/filter-panel.ts must exist after PR5."""
        self.assertTrue(
            FILTER_PANEL_MODULE.exists(),
            f"Expected {FILTER_PANEL_MODULE} to exist. Run the PR5 extraction.",
        )

    def test_filter_panel_exports_mount(self):
        """filter-panel.ts must export a mount function."""
        src = FILTER_PANEL_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            "export function mount",
            src,
            "filter-panel.ts must export 'mount' function",
        )

    def test_filter_panel_exports_unmount(self):
        """filter-panel.ts must export an unmount function."""
        src = FILTER_PANEL_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            "export function unmount",
            src,
            "filter-panel.ts must export 'unmount' function",
        )

    def test_filter_panel_has_ontoggle_callback(self):
        """mount must accept a deps object with onToggle callback."""
        src = FILTER_PANEL_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            "onToggle",
            src,
            "filter-panel.ts must reference 'onToggle' in deps",
        )

    def test_filter_panel_has_typegroups_in_deps(self):
        """mount must accept typeGroups (the data needed to build the filter list)."""
        src = FILTER_PANEL_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            "typeGroups",
            src,
            "filter-panel.ts must reference 'typeGroups' in deps",
        )


class TestFilterPanelContentContracts(unittest.TestCase):
    """Verify that the filter DOM construction logic is present in the module."""

    def test_filter_item_class_present(self):
        """filter-panel.ts must use .filter-item CSS class (ported from template)."""
        src = FILTER_PANEL_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            "filter-item",
            src,
            "filter-panel.ts must contain 'filter-item' class name (ported from template)",
        )

    def test_chip_class_present(self):
        """filter-panel.ts must create chip elements with .chip class."""
        src = FILTER_PANEL_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            '"chip"',
            src,
            "filter-panel.ts must use 'chip' class name for color swatches",
        )

    def test_legend_item_class_present(self):
        """filter-panel.ts must build legend items with .legend-item class."""
        src = FILTER_PANEL_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            "legend-item",
            src,
            "filter-panel.ts must contain 'legend-item' class name (ported from template)",
        )

    def test_checkbox_input_type(self):
        """filter-panel.ts must create checkbox inputs (cb.type = 'checkbox')."""
        src = FILTER_PANEL_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            '"checkbox"',
            src,
            "filter-panel.ts must create input elements with type='checkbox'",
        )

    def test_supertype_heading(self):
        """filter-panel.ts must render typeGroup.supertype as a heading (h3 or similar)."""
        src = FILTER_PANEL_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            "supertype",
            src,
            "filter-panel.ts must reference group.supertype for heading text",
        )


class TestMainTsWiringFilterPanel(unittest.TestCase):
    """main.ts must import and expose the filterPanel module on window.brainDsUI."""

    def test_main_imports_filter_panel_module(self):
        """main.ts must import * as filterPanel from './panels/filter-panel'."""
        src = MAIN_TS.read_text(encoding="utf-8")
        self.assertIn(
            "panels/filter-panel",
            src,
            "main.ts must import from './panels/filter-panel'",
        )

    def test_main_exposes_filterPanel_on_window(self):
        """main.ts window.brainDsUI must include 'filterPanel' property."""
        src = MAIN_TS.read_text(encoding="utf-8")
        self.assertIn(
            "filterPanel",
            src,
            "main.ts must expose filterPanel module on window.brainDsUI",
        )

    def test_window_interface_includes_filterPanel(self):
        """The Window interface in main.ts must declare the filterPanel property."""
        src = MAIN_TS.read_text(encoding="utf-8")
        self.assertIn(
            "filterPanel:",
            src,
            "Window interface in main.ts must include 'filterPanel:' property",
        )


class TestTemplateDelegationFilterPanel(unittest.TestCase):
    """Template must delegate filter panel behavior to window.brainDsUI.filterPanel."""

    def test_template_calls_filter_panel_mount(self):
        """graph_viewer.html must call window.brainDsUI.filterPanel.mount(...)."""
        src = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn(
            "window.brainDsUI.filterPanel.mount",
            src,
            "Template must call window.brainDsUI.filterPanel.mount()",
        )

    def test_template_no_longer_has_inline_typegroups_foreach(self):
        """After extraction, typeGroups.forEach DOM construction must not be inline.

        Discriminator: the unique 'filter-item' className assignment was moved
        to filter-panel.ts; it should no longer appear in the template script.
        """
        src = TEMPLATE.read_text(encoding="utf-8")
        self.assertNotIn(
            '"filter-item"',
            src,
            "Template must not contain inline 'filter-item' string after PR5 extraction",
        )

    def test_template_no_longer_has_inline_toggletype(self):
        """After extraction, toggleType function must not be defined inline in template."""
        src = TEMPLATE.read_text(encoding="utf-8")
        self.assertNotIn(
            "const toggleType",
            src,
            "Template must not contain inline 'const toggleType' after PR5 extraction",
        )

    def test_template_type_filters_div_still_present(self):
        """The #type-filters div anchor must remain in the template HTML."""
        src = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn(
            'id="type-filters"',
            src,
            "Template must still contain the #type-filters div anchor",
        )

    def test_template_legend_div_still_present(self):
        """The #legend div anchor must remain in the template HTML."""
        src = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn(
            'id="legend"',
            src,
            "Template must still contain the #legend div anchor",
        )


class TestFilterPanelTriangulation(unittest.TestCase):
    """At least 3 distinct triangulation cases for the filter-panel module."""

    def test_show_all_wired_in_module(self):
        """Case A: show-all and hide-all button wiring must be in filter-panel.ts."""
        src = FILTER_PANEL_MODULE.read_text(encoding="utf-8")
        self.assertTrue(
            "show-all" in src or "showAll" in src,
            "filter-panel.ts must handle show-all button wiring",
        )

    def test_type_count_rendered(self):
        """Case B: filter-panel must display type count per filter item (e.g., t.count)."""
        src = FILTER_PANEL_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            ".count",
            src,
            "filter-panel.ts must reference .count to show node count per type",
        )

    def test_checkbox_change_event(self):
        """Case C: checkbox must register a 'change' event listener."""
        src = FILTER_PANEL_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            '"change"',
            src,
            "filter-panel.ts must register 'change' event on checkboxes",
        )

    def test_listener_teardown_via_array(self):
        """Case D: module must collect event listeners for teardown in unmount."""
        src = FILTER_PANEL_MODULE.read_text(encoding="utf-8")
        self.assertTrue(
            "_listeners" in src or "listeners" in src,
            "filter-panel.ts must maintain a listeners array for unmount teardown",
        )

    def test_color_chip_style_background(self):
        """Case E: chip color must be set from t.color (ported from template)."""
        src = FILTER_PANEL_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            ".color",
            src,
            "filter-panel.ts must reference .color for chip background styling",
        )


class TestW2TreeHooksInTemplate(unittest.TestCase):
    """W2 RED contracts for tree panel and clear-filter UI wiring."""

    def test_template_has_tree_mount_anchor(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn('id="tree-panel"', src, "Template must include #tree-panel anchor for W2")

    def test_template_calls_tree_panel_mount(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("window.brainDsUI.tree.mount", src, "Template must delegate tree panel to module mount")

    def test_template_has_tree_filter_breadcrumb(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn('id="tree-filter-chip"', src, "Template must include clearable tree-filter breadcrumb chip")


class TestPR3InformationArchitectureContracts(unittest.TestCase):
    """PR3 RED contracts: hierarchy grouped by type + consolidated filters."""

    def test_hierarchy_shows_type_groups_not_per_node_buttons(self):
        """REQ-3.1: hierarchy module must render collapsible type groups."""
        template_src = TEMPLATE.read_text(encoding="utf-8")
        tree_src = TREE_MODULE.read_text(encoding="utf-8")

        self.assertIn(
            'id="tree-panel"',
            template_src,
            "Hierarchy mount anchor must stay in template",
        )
        self.assertIn(
            "data-hierarchy-group",
            tree_src,
            "tree.ts must render per-type hierarchy groups (data-hierarchy-group)",
        )


class TestPrBFilterPolishContracts(unittest.TestCase):
    """PR B contracts: compact tokenized toggles, no per-actor Mostrar buttons."""

    def test_filter_panel_does_not_render_mostrar_toggle_buttons(self):
        src = FILTER_PANEL_MODULE.read_text(encoding="utf-8")
        self.assertNotIn(
            "Mostrar",
            src,
            "PR B must remove per-type 'Mostrar' button labels from filter-panel.ts",
        )
        self.assertNotIn(
            "filter-toggle",
            src,
            "PR B must remove legacy .filter-toggle per-type button wiring",
        )

    def test_filter_panel_applies_custom_checkbox_class(self):
        src = FILTER_PANEL_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            "filter-checkbox",
            src,
            "PR B must mark type checkboxes with .filter-checkbox for tokenized styling",
        )

    def test_filters_consolidated_no_duplicate_toggles(self):
        """REQ-3.2: no duplicated global Mostrar/Ocultar controls in filter panel."""
        template_src = TEMPLATE.read_text(encoding="utf-8")
        filter_src = FILTER_PANEL_MODULE.read_text(encoding="utf-8")

        self.assertNotIn(
            'id="show-all"',
            template_src,
            "Template must remove global #show-all button after PR3 consolidation",
        )
        self.assertNotIn(
            'id="hide-all"',
            template_src,
            "Template must remove global #hide-all button after PR3 consolidation",
        )
        self.assertNotIn("filter-toggle", filter_src)


class TestPR3BugGuardrailsContracts(unittest.TestCase):
    """Guardrails for user-reported interaction bugs before/within PR3."""

    def test_renderer_click_does_not_call_selectnodes_directly(self):
        """Node click in D4 overlay must avoid selectNodes() re-stabilization jumps."""
        src = RENDERER_D4.read_text(encoding="utf-8")
        self.assertNotIn(
            "network.selectNodes([node.id])",
            src,
            "renderer-d4 click handler must not call network.selectNodes([node.id]) directly",
        )

    def test_renderer_cleans_stale_edge_elements(self):
        """D4 renderer must prune stale edge SVGs so highlight ghosts cannot persist.

        Since the lifecycle choreography change, stale edges are removed through
        beginExit (sever animation -> removeEl) instead of a direct removeChild.
        """
        src = RENDERER_D4.read_text(encoding="utf-8")
        self.assertIn("activeEdgeIds", src, "renderer-d4.ts must track activeEdgeIds each render")
        self.assertRegex(
            src,
            r"beginExit\(line, 'edge-sever'\)",
            "renderer-d4.ts must route stale edge lines through the exit lifecycle (which removes them)",
        )
        self.assertRegex(
            src,
            r"el\.parentNode\.removeChild\(el\)",
            "renderer-d4.ts exit lifecycle must ultimately remove the element from the DOM",
        )

    def test_filter_eye_icons_use_currentcolor_paint_rule(self):
        """Filter/controls eye icons must be painted as Lucide stroke icons (not black fill)."""
        src = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn(
            ".pill-group button svg",
            src,
            "Template icon paint selector must include filter/control pill-group SVGs",
        )
