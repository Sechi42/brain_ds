import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
TREE_MODULE = REPO / "brain_ds" / "ui" / "src" / "panels" / "tree.ts"
MAIN_TS = REPO / "brain_ds" / "ui" / "src" / "main.ts"


class TestTreePanelModuleContracts(unittest.TestCase):
    def test_tree_module_exists(self):
        self.assertTrue(TREE_MODULE.exists(), f"Expected {TREE_MODULE} to exist for W2")

    def test_tree_module_exports_mount(self):
        src = TREE_MODULE.read_text(encoding="utf-8")
        self.assertIn("export function mount", src)

    def test_tree_module_uses_parent_id_contract(self):
        src = TREE_MODULE.read_text(encoding="utf-8")
        self.assertIn("parent_id", src)

    def test_tree_module_uses_depth_contract(self):
        src = TREE_MODULE.read_text(encoding="utf-8")
        self.assertIn("depth", src)

    def test_tree_module_has_expand_collapse_toggle(self):
        src = TREE_MODULE.read_text(encoding="utf-8")
        self.assertTrue("aria-expanded" in src or "expand" in src.lower())


class TestMainTreeWiringContracts(unittest.TestCase):
    def test_main_imports_tree_module(self):
        src = MAIN_TS.read_text(encoding="utf-8")
        self.assertIn("panels/tree", src)

    def test_main_exposes_tree_module_on_window(self):
        src = MAIN_TS.read_text(encoding="utf-8")
        self.assertIn("tree:", src)
