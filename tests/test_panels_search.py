"""
PR 4 — TDD contract tests for panels/search.ts extraction.

These tests assert source-file contracts (no DOM execution).
Pattern follows test_panels_detail_panel.py exactly.

TDD cycle: RED (this file) → GREEN (module creation) → TRIANGULATE → REFACTOR.
"""

import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
SEARCH_MODULE = REPO / "brain_ds" / "ui" / "src" / "panels" / "search.ts"
MAIN_TS = REPO / "brain_ds" / "ui" / "src" / "main.ts"
TEMPLATE = REPO / "brain_ds" / "ui" / "templates" / "graph_viewer.html"


class TestSearchModuleExists(unittest.TestCase):
    """Module-existence and export contracts."""

    def test_search_module_file_exists(self):
        """brain_ds/ui/src/panels/search.ts must exist after PR4."""
        self.assertTrue(
            SEARCH_MODULE.exists(),
            f"Expected {SEARCH_MODULE} to exist. Run the PR4 extraction.",
        )

    def test_search_module_exports_mount(self):
        """search.ts must export a mount function."""
        src = SEARCH_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            "export function mount",
            src,
            "search.ts must export 'mount' function",
        )

    def test_search_module_exports_unmount(self):
        """search.ts must export an unmount function."""
        src = SEARCH_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            "export function unmount",
            src,
            "search.ts must export 'unmount' function",
        )

    def test_search_module_has_deps_bag(self):
        """mount must accept a deps object with onSelect and onClear callbacks."""
        src = SEARCH_MODULE.read_text(encoding="utf-8")
        # Both callbacks must be referenced in the source
        self.assertIn(
            "onSelect",
            src,
            "search.ts must reference 'onSelect' in deps",
        )
        self.assertIn(
            "onClear",
            src,
            "search.ts must reference 'onClear' in deps",
        )

    def test_search_mount_guards_null_root(self):
        """mount must safely no-op when called with null root."""
        src = SEARCH_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            "if (!root) return;",
            src,
            "search.ts mount must guard null root to prevent runtime crashes",
        )


class TestSearchUXContracts(unittest.TestCase):
    """REQ-GVP-6.1, REQ-GVP-6.4, REQ-GVP-6.8 contracts in search.ts source."""

    def test_clear_button_aria_label(self):
        """REQ-GVP-6.1: clear button must have aria-label='Clear search'."""
        src = SEARCH_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            'aria-label="Clear search"',
            src,
            "search.ts must include aria-label=\"Clear search\" for the clear button",
        )

    def test_zero_results_message_literal(self):
        """REQ-GVP-6.4: zero-results state must contain 'No nodes match' literal."""
        src = SEARCH_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            "No nodes match",
            src,
            "search.ts must contain 'No nodes match' literal for zero-results state",
        )

    def test_esc_closes_dropdown(self):
        """REQ-GVP-6.8: Esc key handler must exist in search module."""
        src = SEARCH_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            '"Escape"',
            src,
            "search.ts must handle Escape key to close dropdown",
        )

    def test_esc_returns_focus_to_input(self):
        """REQ-GVP-6.8: after Esc, focus returns to input (.focus() call present)."""
        src = SEARCH_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            ".focus()",
            src,
            "search.ts must call .focus() on Escape to return focus to input",
        )

    def test_esc_invokes_onClear(self):
        """REQ-GVP-6.8: Esc must invoke onClear so resetHighlight+applyVisibility run."""
        src = SEARCH_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            "onClear",
            src,
            "search.ts must invoke deps.onClear on Escape",
        )

    def test_algorithmic_search_uses_api_not_chat_affordances(self):
        """Search module must call the algorithmic HTTP adapter and expose no chat UI copy."""
        src = SEARCH_MODULE.read_text(encoding="utf-8")
        self.assertIn("/api/search", src)
        for forbidden in ("chat", "prompt", "send button", "streaming", "tokens"):
            self.assertNotIn(forbidden, src.lower())

    def test_search_results_render_score_and_highlight_callback(self):
        """Ranked API results must show scores and call highlight callback with ids."""
        src = SEARCH_MODULE.read_text(encoding="utf-8")
        self.assertIn("score", src)
        self.assertIn("onHighlight", src)
        self.assertRegex(src, r"onHighlight\([^)]*map\([^)]*id")

    def test_clear_removes_search_highlights(self):
        """Clear action must notify both clear and highlight reset paths."""
        src = SEARCH_MODULE.read_text(encoding="utf-8")
        self.assertIn("onClear", src)
        self.assertRegex(src, r"onHighlight\(\s*\[\s*\]\s*\)")

    def test_run_search_renders_local_results_before_api_await(self):
        """Keyboard navigation needs local matches synchronously before API enhancement."""
        src = SEARCH_MODULE.read_text(encoding="utf-8")
        render_i = src.find("renderResults(topMatches(q, _deps!.nodes), q)")
        await_i = src.find("await _apiMatches(q)")
        self.assertGreaterEqual(render_i, 0)
        self.assertGreaterEqual(await_i, 0)
        self.assertLess(render_i, await_i)

    def test_search_module_has_no_duplicate_classname_assignments(self):
        """Cleanup guard for accidental duplicated className writes."""
        src = SEARCH_MODULE.read_text(encoding="utf-8")
        self.assertEqual(src.count('emptyLi.className = "search-empty";'), 1)
        self.assertEqual(src.count('wrap.className = "search-input-wrap";'), 1)


class TestMainTsWiring(unittest.TestCase):
    """main.ts must import and expose the search module on window.brainDsUI."""

    def test_main_imports_search_module(self):
        """main.ts must import * as search from './panels/search'."""
        src = MAIN_TS.read_text(encoding="utf-8")
        self.assertIn(
            "panels/search",
            src,
            "main.ts must import from './panels/search'",
        )

    def test_main_exposes_search_on_window(self):
        """main.ts window.brainDsUI must include 'search' property."""
        src = MAIN_TS.read_text(encoding="utf-8")
        self.assertIn(
            "search",
            src,
            "main.ts must expose search module on window.brainDsUI",
        )

    def test_window_interface_includes_search(self):
        """The Window interface in main.ts must declare the search property."""
        src = MAIN_TS.read_text(encoding="utf-8")
        self.assertIn(
            "search:",
            src,
            "Window interface in main.ts must include 'search:' property",
        )


class TestTemplateDelegation(unittest.TestCase):
    """Template must delegate search behavior to window.brainDsUI.search."""

    def test_template_calls_search_mount(self):
        """graph_viewer.html must call window.brainDsUI.search.mount(...)."""
        src = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn(
            "window.brainDsUI.search.mount",
            src,
            "Template must call window.brainDsUI.search.mount()",
        )

    def test_template_no_longer_has_inline_topMatches(self):
        """After extraction, topMatches function body must not be inline in template.

        Discriminator: the unique '.slice(0, 10)' expression from the inline topMatches
        function was moved to search.ts; it should no longer appear in the template.
        """
        src = TEMPLATE.read_text(encoding="utf-8")
        self.assertNotIn(
            "topMatches",
            src,
            "Template must not contain inline 'topMatches' after PR4 extraction",
        )

    def test_template_no_longer_has_inline_renderResults(self):
        """After extraction, renderResults function body must not be inline in template."""
        src = TEMPLATE.read_text(encoding="utf-8")
        self.assertNotIn(
            "renderResults",
            src,
            "Template must not contain inline 'renderResults' after PR4 extraction",
        )

    def test_template_search_input_still_present(self):
        """The search input element must remain in the template HTML."""
        src = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn(
            'id="node-search"',
            src,
            "Template must still contain the search input #node-search",
        )


class TestSearchTriangulation(unittest.TestCase):
    """At least 3 distinct triangulation cases for the search module."""

    def test_clear_button_hidden_on_empty_input(self):
        """Case A: clear button must be toggled based on input emptiness.

        Source must show the clear button is shown/hidden based on value.
        """
        src = SEARCH_MODULE.read_text(encoding="utf-8")
        # The clear button hidden state: either 'hidden' attribute manipulation or display toggle
        self.assertTrue(
            "hidden" in src or "display" in src,
            "search.ts must toggle clear button visibility based on input state",
        )

    def test_top_matches_slice_in_module(self):
        """Case B: topMatches logic (including .slice(0, 10)) lives in search.ts."""
        src = SEARCH_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            ".slice(0, 10)",
            src,
            "search.ts must contain .slice(0, 10) from the topMatches logic",
        )

    def test_zero_results_no_empty_ul(self):
        """Case C: REQ-GVP-6.4 — zero results must not render an empty list.

        Source must have a conditional that prevents rendering when items is empty.
        """
        src = SEARCH_MODULE.read_text(encoding="utf-8")
        # There must be a length check: either items.length or q check before rendering
        self.assertTrue(
            "length" in src,
            "search.ts must check array/query length to prevent empty list render",
        )

    def test_enter_key_selects_first_result(self):
        """Case D: Enter key fires onSelect with first match."""
        src = SEARCH_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            '"Enter"',
            src,
            "search.ts must handle Enter key to select first result",
        )

    def test_module_uses_localeCompare_for_sort(self):
        """Case E: sort logic (localeCompare) is present in the module."""
        src = SEARCH_MODULE.read_text(encoding="utf-8")
        self.assertIn(
            "localeCompare",
            src,
            "search.ts must use localeCompare for result sorting (ported from template)",
        )


class TestSearchSlice6PolishContracts(unittest.TestCase):
    """PR11 Slice 6 polish contracts for ARIA + floating dropdown styling."""

    def test_input_combobox_role_present(self):
        """REQ-GVP-9.3/6.3: input should expose combobox role semantics."""
        src = SEARCH_MODULE.read_text(encoding="utf-8")
        self.assertIn("role", src)
        self.assertIn("combobox", src)

    def test_input_updates_aria_activedescendant(self):
        """REQ-GVP-6.3: arrow nav updates aria-activedescendant."""
        src = SEARCH_MODULE.read_text(encoding="utf-8")
        self.assertIn("aria-activedescendant", src)

    def test_result_items_use_option_role(self):
        """REQ-GVP-9.3: result items should carry role=option."""
        src = SEARCH_MODULE.read_text(encoding="utf-8")
        self.assertIn("role\", \"option\"", src)

    def test_search_icon_uses_sprite_symbol(self):
        """REQ-GVP-6.1: search input leading icon should use sprite icon-search."""
        src = SEARCH_MODULE.read_text(encoding="utf-8")
        self.assertIn("#icon-search", src)

    def test_clear_button_uses_sprite_x_icon(self):
        """REQ-GVP-6.1: clear button should use icon-x instead of text glyph."""
        src = SEARCH_MODULE.read_text(encoding="utf-8")
        self.assertIn("#icon-x", src)


class TestPR1SearchContainmentAndSelectionContracts(unittest.TestCase):
    """PR1 contracts for containment + selectAndReveal wiring."""

    def test_search_results_remain_absolute(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("#search-results", src)
        self.assertIn("position: absolute", src)

    def test_search_panel_card_is_positioned_ancestor(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn(
            '.panel-card[data-accordion-section="search"] { position: relative; }',
            src,
            "Search card must be positioned ancestor for #search-results",
        )

    def test_search_results_z_index_is_at_least_1200(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        match = __import__("re").search(r"#search-results\s*\{[^}]*z-index:\s*(\d+)", src, __import__("re").S)
        self.assertIsNotNone(match, "#search-results z-index declaration missing")
        self.assertGreaterEqual(int(match.group(1)), 1200)

    def test_template_declares_select_and_reveal_helper(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("const selectAndReveal = (nodeId) =>", src)

    def test_search_mount_onselect_calls_select_and_reveal(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("onSelect: (nodeId) => { selectAndReveal(nodeId); }", src)

    def test_select_and_reveal_call_order_contract(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        helper_start = src.find("const selectAndReveal = (nodeId) =>")
        self.assertGreaterEqual(helper_start, 0, "selectAndReveal helper missing")
        helper_end = src.find("};", helper_start)
        block = src[helper_start:helper_end]
        reset_i = block.find("resetHighlight()")
        emit_i = block.find("network._emit(\"selectNode\", { nodes: [nodeId] })")
        select_i = block.find("network.selectNodes([nodeId])")
        focus_i = block.find("focusNode(nodeId)")
        self.assertTrue(reset_i != -1 and focus_i != -1)
        self.assertTrue(reset_i < focus_i)
        self.assertTrue(emit_i == -1 or reset_i < emit_i)
        self.assertTrue(select_i == -1 or reset_i < select_i)

    def test_select_and_reveal_fails_loudly_without_selection_mechanisms(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn(
            "throw new Error(\"selectAndReveal: network selection APIs unavailable\")",
            src,
            "Helper must throw loudly when neither selection mechanism is available",
        )
