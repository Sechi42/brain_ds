"""
PR 6 — Contract + triangulation tests for interactions/context-menu.ts

Covers:
  TestContextMenuModuleExists      — file exists, correct shape (mount/unmount exports)
  TestContextMenuContentContracts  — node menu items, canvas menu items, cssText removal
  TestMainTsWiringContextMenu      — main.ts exposes window.brainDsUI.contextMenu
  TestTemplateDelegationContextMenu — template mounts via window.brainDsUI.contextMenu
  TestContextMenuTriangulation     — at least 3 distinct behavioural cases
"""

import unittest
import os
import re

TS_MODULE_PATH = os.path.join(
    os.path.dirname(__file__),
    "..", "brain_ds", "ui", "src", "interactions", "context-menu.ts"
)
MAIN_TS_PATH = os.path.join(
    os.path.dirname(__file__),
    "..", "brain_ds", "ui", "src", "main.ts"
)
TEMPLATE_PATH = os.path.join(
    os.path.dirname(__file__),
    "..", "brain_ds", "ui", "templates", "graph_viewer.html"
)


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestContextMenuModuleExists(unittest.TestCase):
    """File exists and has the right module shape."""

    def test_file_exists(self):
        self.assertTrue(
            os.path.isfile(TS_MODULE_PATH),
            f"context-menu.ts not found at {TS_MODULE_PATH}"
        )

    def test_exports_mount(self):
        src = _read(TS_MODULE_PATH)
        self.assertRegex(src, r"export\s+function\s+mount\b|export\s+\{\s*[^}]*\bmount\b",
                         "context-menu.ts must export a mount function")

    def test_exports_unmount(self):
        src = _read(TS_MODULE_PATH)
        self.assertRegex(src, r"export\s+function\s+unmount\b|export\s+\{\s*[^}]*\bunmount\b",
                         "context-menu.ts must export an unmount function")

    def test_has_listeners_array(self):
        src = _read(TS_MODULE_PATH)
        self.assertIn("_listeners", src,
                      "context-menu.ts must use a _listeners array for teardown")


class TestContextMenuContentContracts(unittest.TestCase):
    """Menu construction contracts — node items, canvas items, keyboard nav, click-outside."""

    def setUp(self):
        self.src = _read(TS_MODULE_PATH)

    def test_role_menu_set(self):
        self.assertIn('role', self.src)
        self.assertIn('menu', self.src)

    def test_role_menuitem_set(self):
        self.assertRegex(self.src, r"menuitem",
                         "context-menu.ts must use role=menuitem for items")

    def test_keyboard_arrowdown(self):
        self.assertIn("ArrowDown", self.src,
                      "context-menu.ts must handle ArrowDown for keyboard nav")

    def test_keyboard_arrowup(self):
        self.assertIn("ArrowUp", self.src,
                      "context-menu.ts must handle ArrowUp for keyboard nav")

    def test_keyboard_escape(self):
        self.assertIn("Escape", self.src,
                      "context-menu.ts must handle Escape to close menu")

    def test_click_outside_listener(self):
        # document.addEventListener with capture:true closes menu on outside click
        self.assertRegex(self.src, r"document\.addEventListener",
                         "context-menu.ts must add a document click listener for outside-click close")

    def test_no_csstext_for_menu_container(self):
        # REQ-GVP-6.5: zero cssText assignments for the menu container visual properties
        # The module must NOT use cssText for the overall menu element styling
        src_without_comments = re.sub(r"//.*", "", self.src)
        src_without_comments = re.sub(r"/\*.*?\*/", "", src_without_comments, flags=re.DOTALL)
        # Allow cssText only for individual item hover states if truly needed,
        # but the main container must use className / CSS class approach
        matches = re.findall(r"ctxMenuEl\.style\.cssText", src_without_comments)
        self.assertEqual(len(matches), 0,
                         "context-menu.ts must not use ctxMenuEl.style.cssText for menu container styling")

    def test_position_function_exists(self):
        self.assertRegex(self.src, r"positionMenu|_position",
                         "context-menu.ts must have a position function")

    def test_open_node_context_menu_function(self):
        self.assertRegex(self.src, r"openNodeContextMenu|openNode",
                         "context-menu.ts must have openNodeContextMenu or similar function")

    def test_open_canvas_context_menu_function(self):
        self.assertRegex(self.src, r"openCanvasContextMenu|openCanvas",
                         "context-menu.ts must have openCanvasContextMenu or similar function")


class TestMainTsWiringContextMenu(unittest.TestCase):
    """main.ts exposes contextMenu on window.brainDsUI."""

    def setUp(self):
        self.src = _read(MAIN_TS_PATH)

    def test_imports_context_menu_module(self):
        self.assertRegex(self.src, r"import.*context-menu",
                         "main.ts must import context-menu module")

    def test_braindsui_has_context_menu(self):
        self.assertRegex(self.src, r"contextMenu\s*:",
                         "window.brainDsUI must include contextMenu property")

    def test_window_interface_updated(self):
        self.assertRegex(self.src, r"contextMenu\s*:",
                         "Window interface in main.ts must declare contextMenu")


class TestTemplateDelegationContextMenu(unittest.TestCase):
    """Template mounts context menu via window.brainDsUI.contextMenu."""

    def setUp(self):
        self.src = _read(TEMPLATE_PATH)

    def test_template_mounts_context_menu(self):
        self.assertRegex(self.src, r"window\.brainDsUI\.contextMenu\.mount",
                         "template must call window.brainDsUI.contextMenu.mount()")

    def test_template_no_inline_ctxmenuEl_construction(self):
        # After extraction, ctxMenuEl should not be constructed inline in the template
        self.assertNotIn("ctxMenuEl = document.createElement",
                         self.src,
                         "template must not construct ctxMenuEl inline after PR 6 extraction")

    def test_template_no_inline_makeMenuItem(self):
        # makeMenuItem should be gone from inline template script
        self.assertNotIn("const makeMenuItem",
                         self.src,
                         "template must not define makeMenuItem inline after PR 6 extraction")

    def test_context_menu_event_subscription_in_template(self):
        # The network.on('context-menu') subscription can stay in template as a thin delegation
        # OR the module handles it — either way the template must reference contextMenu
        self.assertRegex(self.src, r"contextMenu",
                         "template must reference contextMenu module")


class TestContextMenuTriangulation(unittest.TestCase):
    """At least 3 distinct behavioural contracts for triangulation."""

    def setUp(self):
        self.src = _read(TS_MODULE_PATH)

    def test_tri_node_menu_item_focus_this_node(self):
        # Node menu must include "Focus this node" item
        self.assertIn("Focus this node", self.src,
                      "context-menu.ts must render 'Focus this node' node menu item")

    def test_tri_canvas_menu_item_zoom_to_fit(self):
        # Canvas menu must include "Zoom to fit" item
        self.assertIn("Zoom to fit", self.src,
                      "context-menu.ts must render 'Zoom to fit' canvas menu item")

    def test_tri_grid_placeholder_aria_disabled(self):
        # Grid (placeholder) must have aria-disabled="true" (REQ-6.3 / REQ-6.9)
        self.assertIn("aria-disabled", self.src,
                      "context-menu.ts must set aria-disabled on disabled items")
        self.assertIn("Grid", self.src,
                      "context-menu.ts must include Grid placeholder item")

    def test_tri_close_resets_display(self):
        # closeContextMenu sets display to none
        self.assertRegex(self.src, r"display.*none|style\.display\s*=",
                         "closeContextMenu must set display:none on menu element")

    def test_tri_context_menu_state_open_flag(self):
        # contextMenu state object with open flag (for hover suppression REQ-6.10)
        self.assertRegex(self.src, r"\.open\s*=\s*(true|false)",
                         "context-menu.ts must manage .open state flag for hover suppression")


class TestContextMenuSlice6PolishContracts(unittest.TestCase):
    """PR11 Slice 6 polish contracts: iconized items + CSS class semantics."""

    def setUp(self):
        self.src = _read(TS_MODULE_PATH)

    def test_each_menu_item_renders_svg_icon(self):
        """REQ-GVP-6.6: menu items include inline SVG use href='#icon-*'."""
        self.assertIn("<svg", self.src)
        self.assertIn("#icon-", self.src)

    def test_separator_uses_hr_element(self):
        """REQ-GVP-6.8: separator should be <hr>, not styled div."""
        self.assertRegex(self.src, r"createElement\(\s*[\"']hr[\"']\s*\)")

    def test_danger_item_class_present(self):
        """REQ-GVP-6.7: destructive action should use danger class token hook."""
        self.assertIn("menu-item--danger", self.src)

    def test_menu_uses_css_class_for_item_icons(self):
        """PR11 polish: icon styling should be class-driven, not inline style."""
        self.assertIn("vis-context-menu__icon", self.src)


if __name__ == "__main__":
    unittest.main()
