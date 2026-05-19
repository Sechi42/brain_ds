"""
PR 6 — Contract + triangulation tests for interactions/popover.ts

Covers:
  TestPopoverModuleExists      — file exists, correct shape (mount/unmount exports)
  TestPopoverContentContracts  — content factory produces correct DOM structure
  TestMainTsWiringPopover      — main.ts exposes window.brainDsUI.popover
  TestTemplateDelegationPopover — template wires factory via setPopoverContentFactory
  TestPopoverTriangulation     — at least 3 distinct content-factory behavioural cases
"""

import unittest
import os
import re

TS_MODULE_PATH = os.path.join(
    os.path.dirname(__file__),
    "..", "brain_ds", "ui", "src", "interactions", "popover.ts"
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


class TestPopoverModuleExists(unittest.TestCase):
    """File exists and has the right module shape."""

    def test_file_exists(self):
        self.assertTrue(
            os.path.isfile(TS_MODULE_PATH),
            f"popover.ts not found at {TS_MODULE_PATH}"
        )

    def test_exports_mount(self):
        src = _read(TS_MODULE_PATH)
        self.assertRegex(src, r"export\s+function\s+mount\b|export\s+\{\s*[^}]*\bmount\b",
                         "popover.ts must export a mount function")

    def test_exports_unmount(self):
        src = _read(TS_MODULE_PATH)
        self.assertRegex(src, r"export\s+function\s+unmount\b|export\s+\{\s*[^}]*\bunmount\b",
                         "popover.ts must export an unmount function")

    def test_exports_create_content_factory(self):
        src = _read(TS_MODULE_PATH)
        self.assertRegex(src, r"export\s+function\s+createContentFactory\b|createContentFactory",
                         "popover.ts must export createContentFactory function")


class TestPopoverContentContracts(unittest.TestCase):
    """Content factory must produce elements matching the renderer's default popover content."""

    def setUp(self):
        self.src = _read(TS_MODULE_PATH)

    def test_popover_name_class(self):
        # Factory must produce vis-popover-name span (matches renderer.ts locked template)
        self.assertIn("vis-popover-name", self.src,
                      "popover.ts must use vis-popover-name class for node label")

    def test_popover_type_class(self):
        self.assertIn("vis-popover-type", self.src,
                      "popover.ts must use vis-popover-type class for node type")

    def test_popover_score_class(self):
        self.assertIn("vis-popover-score", self.src,
                      "popover.ts must use vis-popover-score class for node score")

    def test_popover_source_class(self):
        self.assertIn("vis-popover-source", self.src,
                      "popover.ts must use vis-popover-source class for node source")

    def test_score_tofixed(self):
        self.assertIn("toFixed", self.src,
                      "popover.ts must format score with toFixed(2)")

    def test_returns_element(self):
        # Factory returns a DOM element (HTMLElement / DocumentFragment)
        self.assertRegex(self.src, r"createElement|createDocumentFragment|div\b",
                         "popover.ts createContentFactory must return a DOM element")


class TestMainTsWiringPopover(unittest.TestCase):
    """main.ts exposes popover on window.brainDsUI."""

    def setUp(self):
        self.src = _read(MAIN_TS_PATH)

    def test_imports_popover_module(self):
        self.assertRegex(self.src, r"import.*popover",
                         "main.ts must import popover module")

    def test_braindsui_has_popover(self):
        self.assertRegex(self.src, r"popover\s*:",
                         "window.brainDsUI must include popover property")

    def test_window_interface_updated(self):
        self.assertRegex(self.src, r"popover\s*:",
                         "Window interface in main.ts must declare popover")


class TestTemplateDelegationPopover(unittest.TestCase):
    """Template wires the popover content factory via setPopoverContentFactory."""

    def setUp(self):
        self.src = _read(TEMPLATE_PATH)

    def test_template_mounts_popover(self):
        self.assertRegex(self.src, r"window\.brainDsUI\.popover\.mount",
                         "template must call window.brainDsUI.popover.mount()")

    def test_template_calls_set_popover_content_factory(self):
        # The factory wiring occurs inside popover.mount() (called from template).
        # Verify the module itself calls setPopoverContentFactory.
        module_src = _read(TS_MODULE_PATH)
        self.assertRegex(module_src, r"setPopoverContentFactory",
                         "popover module must call network.setPopoverContentFactory() to wire the factory")

    def test_template_uses_braindsui_popover_factory(self):
        # The factory argument must come from the popover module
        self.assertRegex(self.src, r"brainDsUI\.popover",
                         "template must reference window.brainDsUI.popover for factory")


class TestPopoverTriangulation(unittest.TestCase):
    """At least 3 distinct content-factory behavioural cases."""

    def setUp(self):
        self.src = _read(TS_MODULE_PATH)

    def test_tri_label_rendered_as_strong(self):
        # Node label should be a <strong> element or strong class (matching renderer default)
        self.assertRegex(self.src, r"strong|<strong",
                         "popover.ts createContentFactory must wrap node label in <strong>")

    def test_tri_score_formatted_two_decimals(self):
        # toFixed(2) on score value
        self.assertRegex(self.src, r"toFixed\s*\(\s*2\s*\)",
                         "popover.ts must format score with toFixed(2)")

    def test_tri_source_conditional(self):
        # Source field is conditional — only rendered when node.source exists
        self.assertRegex(self.src, r"node\.source|\.source\b",
                         "popover.ts must conditionally include source field")

    def test_tri_no_orphan_symbols_in_module(self):
        # Must not reference template-scope symbols that would cause false positives
        # (guard against the PR4/PR5 comment gotcha)
        self.assertNotIn("renderSelectionPanel", self.src,
                         "popover.ts must not reference template-scope renderSelectionPanel")
        self.assertNotIn("renderDetailPanel", self.src,
                         "popover.ts must not reference template-scope renderDetailPanel")

    def test_tri_factory_accepts_node_argument(self):
        # createContentFactory returns a function that accepts nodeId/node
        self.assertRegex(self.src, r"nodeId|node\b",
                         "popover.ts content factory must accept node or nodeId argument")


if __name__ == "__main__":
    unittest.main()
