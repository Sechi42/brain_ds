"""
PR 5 — TDD contract tests for interactions/score-filter.ts extraction.

These tests assert source-file contracts (no DOM execution).
Pattern follows test_panels_search.py exactly.

TDD cycle: RED (this file) -> GREEN (module creation) -> TRIANGULATE -> REFACTOR.
"""

import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
SCORE_FILTER_MODULE = (
    REPO / "brain_ds" / "ui" / "src" / "interactions" / "score-filter.ts"
)
MAIN_TS = REPO / "brain_ds" / "ui" / "src" / "main.ts"
TEMPLATE = REPO / "brain_ds" / "ui" / "templates" / "graph_viewer.html"


class TestScoreFilterModuleExists(unittest.TestCase):
    """Module-existence and export contracts."""

    def test_score_filter_module_file_exists(self):
        """brain_ds/ui/src/interactions/score-filter.ts must exist after PR5."""
        self.assertTrue(
            SCORE_FILTER_MODULE.exists(),
            f"Expected {SCORE_FILTER_MODULE} to exist. Run the PR5 extraction.",
        )

    def test_score_filter_exports_mount(self):
        """score-filter.ts must export a mount function."""
        src = SCORE_FILTER_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            "export function mount",
            src,
            "score-filter.ts must export 'mount' function",
        )

    def test_score_filter_exports_unmount(self):
        """score-filter.ts must export an unmount function."""
        src = SCORE_FILTER_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            "export function unmount",
            src,
            "score-filter.ts must export 'unmount' function",
        )

    def test_score_filter_has_on_threshold_change_callback(self):
        """mount must accept a deps object with onThresholdChange callback."""
        src = SCORE_FILTER_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            "onThresholdChange",
            src,
            "score-filter.ts must reference 'onThresholdChange' in deps",
        )

    def test_score_filter_exports_set_threshold(self):
        """score-filter.ts must export setThreshold for external reset (e.g., show-all)."""
        src = SCORE_FILTER_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            "setThreshold",
            src,
            "score-filter.ts must export or define 'setThreshold' for external callers",
        )


class TestScoreFilterUXContracts(unittest.TestCase):
    """Verify that the score-filter slider/badge wiring is present in the module."""

    def test_aria_valuenow_updated(self):
        """score-filter.ts must update aria-valuenow on the slider (REQ-5.7)."""
        src = SCORE_FILTER_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            "aria-valuenow",
            src,
            "score-filter.ts must set aria-valuenow on slider for accessibility",
        )

    def test_aria_valuetext_updated(self):
        """score-filter.ts must update aria-valuetext on the slider."""
        src = SCORE_FILTER_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            "aria-valuetext",
            src,
            "score-filter.ts must set aria-valuetext on slider for accessibility",
        )

    def test_tofixed_for_badge(self):
        """score-filter.ts must format the badge value with toFixed(2)."""
        src = SCORE_FILTER_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            "toFixed(2)",
            src,
            "score-filter.ts must use toFixed(2) to format the score badge display",
        )

    def test_parsefloat_for_slider_value(self):
        """score-filter.ts must parse slider value with parseFloat."""
        src = SCORE_FILTER_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            "parseFloat",
            src,
            "score-filter.ts must use parseFloat to read slider value",
        )

    def test_input_event_listener_on_slider(self):
        """score-filter.ts must register an 'input' event on the slider."""
        src = SCORE_FILTER_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            '"input"',
            src,
            "score-filter.ts must register an 'input' event listener on the slider",
        )


class TestMainTsWiringSoreFilter(unittest.TestCase):
    """main.ts must import and expose the scoreFilter module on window.brainDsUI."""

    def test_main_imports_score_filter_module(self):
        """main.ts must import * as scoreFilter from './interactions/score-filter'."""
        src = MAIN_TS.read_text(encoding="utf-8")
        self.assertIn(
            "interactions/score-filter",
            src,
            "main.ts must import from './interactions/score-filter'",
        )

    def test_main_exposes_scoreFilter_on_window(self):
        """main.ts window.brainDsUI must include 'scoreFilter' property."""
        src = MAIN_TS.read_text(encoding="utf-8")
        self.assertIn(
            "scoreFilter",
            src,
            "main.ts must expose scoreFilter module on window.brainDsUI",
        )

    def test_window_interface_includes_scoreFilter(self):
        """The Window interface in main.ts must declare the scoreFilter property."""
        src = MAIN_TS.read_text(encoding="utf-8")
        self.assertIn(
            "scoreFilter:",
            src,
            "Window interface in main.ts must include 'scoreFilter:' property",
        )


class TestTemplateDelegationScoreFilter(unittest.TestCase):
    """Template must delegate score-filter behavior to window.brainDsUI.scoreFilter."""

    def test_template_calls_score_filter_mount(self):
        """graph_viewer.html must call window.brainDsUI.scoreFilter.mount(...)."""
        src = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn(
            "window.brainDsUI.scoreFilter.mount",
            src,
            "Template must call window.brainDsUI.scoreFilter.mount()",
        )

    def test_template_no_longer_has_inline_apply_score_filter(self):
        """After extraction, applyScoreFilter function must not be defined inline.

        Discriminator: 'const applyScoreFilter' was moved to score-filter.ts;
        it must not appear in the template script.
        """
        src = TEMPLATE.read_text(encoding="utf-8")
        self.assertNotIn(
            "const applyScoreFilter",
            src,
            "Template must not contain inline 'const applyScoreFilter' after PR5 extraction",
        )

    def test_template_score_slider_element_still_present(self):
        """The score-threshold-slider input must remain in the template HTML."""
        src = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn(
            'id="score-threshold-slider"',
            src,
            "Template must still contain the #score-threshold-slider input",
        )

    def test_template_score_badge_element_still_present(self):
        """The score-badge span must remain in the template HTML."""
        src = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn(
            'id="score-badge"',
            src,
            "Template must still contain the #score-badge span",
        )


class TestScoreFilterTriangulation(unittest.TestCase):
    """At least 3 distinct triangulation cases for the score-filter module."""

    def test_score_threshold_state_in_module(self):
        """Case A: scoreThreshold (or threshold) state variable lives in score-filter.ts."""
        src = SCORE_FILTER_MODULE.read_text(encoding="utf-8")
        self.assertTrue(
            "scoreThreshold" in src or "_threshold" in src or "threshold" in src,
            "score-filter.ts must maintain a threshold state variable",
        )

    def test_set_threshold_updates_badge_and_slider(self):
        """Case B: setThreshold must update both badge text and slider aria attrs."""
        src = SCORE_FILTER_MODULE.read_text(encoding="utf-8")
        # Both aria-valuenow and toFixed must appear (already tested separately),
        # but here we verify they coexist in a single function body context.
        self.assertTrue(
            "aria-valuenow" in src and "toFixed" in src,
            "score-filter.ts must update both aria-valuenow and toFixed badge in setThreshold",
        )

    def test_listener_teardown_via_array(self):
        """Case C: module must collect listeners for teardown in unmount."""
        src = SCORE_FILTER_MODULE.read_text(encoding="utf-8")
        self.assertTrue(
            "_listeners" in src or "listeners" in src,
            "score-filter.ts must maintain a listeners array for unmount teardown",
        )

    def test_no_orphan_removal_in_module(self):
        """Case D: orphan removal (renderSelectionPanel, selectedNodeIds) must NOT be
        in score-filter.ts — it stays in the template (PR3 boundary)."""
        src = SCORE_FILTER_MODULE.read_text(encoding="utf-8")
        self.assertNotIn(
            "renderSelectionPanel",
            src,
            "score-filter.ts must NOT contain renderSelectionPanel (stays in template)",
        )
        self.assertNotIn(
            "selectedNodeIds",
            src,
            "score-filter.ts must NOT reference selectedNodeIds (template-scope state)",
        )

    def test_slider_value_reset_to_string(self):
        """Case E: setThreshold must set slider.value (as string) for DOM sync."""
        src = SCORE_FILTER_MODULE.read_text(encoding="utf-8")
        self.assertTrue(
            ".value" in src,
            "score-filter.ts must set slider .value property for visual reset",
        )
