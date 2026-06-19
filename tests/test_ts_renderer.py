"""PR 1 — Toolchain stand-up + identity rename.

RED tests:
  - test_toolchain_files_exist: package.json, tsconfig.json, build/esbuild.config.mjs,
    build/check-bundle-size.mjs must all be present.
  - test_renderer_ts_exists: brain_ds/ui/src/renderer.ts must exist.
  - test_main_ts_exists: brain_ds/ui/src/main.ts must exist.
  - test_viewer_bundle_js_exists: assets/viewer.bundle.js must exist and be non-empty.
  - test_viewer_bundle_css_exists: assets/viewer.bundle.css must exist and be non-empty.
  - test_legacy_renderer_asset_deleted: legacy renderer asset must NOT exist.
  - test_inliner_reads_viewer_bundle: template_renderer.py must reference viewer.bundle.js and
    viewer.bundle.css (not legacy renderer asset).
  - Literal-survival suite: all locked literals must survive verbatim in renderer.ts.

All tests targeting renderer.ts will FAIL until renderer.ts is created (RED).
"""
import re
import unittest
from pathlib import Path


UI_DIR = Path(__file__).resolve().parent.parent / "brain_ds" / "ui"
ASSETS_DIR = UI_DIR / "assets"
SRC_DIR = UI_DIR / "src"
BUILD_DIR = UI_DIR / "build"
TESTS_DIR = Path(__file__).resolve().parent


class TestToolchainFilesExist(unittest.TestCase):
    """Commit 1 — toolchain configs present."""

    def test_package_json_exists(self):
        path = UI_DIR / "package.json"
        self.assertTrue(path.exists(), f"package.json not found at {path}")

    def test_package_json_has_correct_name(self):
        import json
        path = UI_DIR / "package.json"
        self.assertTrue(path.exists(), "package.json not found")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data.get("name"), "@brain_ds/ui")

    def test_package_json_has_esbuild_dep(self):
        import json
        path = UI_DIR / "package.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        dev = data.get("devDependencies", {})
        self.assertIn("esbuild", dev, "esbuild must be a devDependency")

    def test_package_json_has_typescript_dep(self):
        import json
        path = UI_DIR / "package.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        dev = data.get("devDependencies", {})
        self.assertIn("typescript", dev, "typescript must be a devDependency")

    def test_package_json_has_no_runtime_deps(self):
        import json
        path = UI_DIR / "package.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        deps = data.get("dependencies", {})
        self.assertEqual(len(deps), 0, "No runtime deps allowed in package.json")

    def test_tsconfig_json_exists(self):
        path = UI_DIR / "tsconfig.json"
        self.assertTrue(path.exists(), f"tsconfig.json not found at {path}")

    def test_tsconfig_json_has_es2020_target(self):
        import json
        path = UI_DIR / "tsconfig.json"
        self.assertTrue(path.exists(), "tsconfig.json not found")
        data = json.loads(path.read_text(encoding="utf-8"))
        target = data.get("compilerOptions", {}).get("target", "")
        self.assertEqual(target, "ES2020", "tsconfig must target ES2020")

    def test_tsconfig_json_has_bundler_module_resolution(self):
        import json
        path = UI_DIR / "tsconfig.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        mr = data.get("compilerOptions", {}).get("moduleResolution", "")
        self.assertEqual(mr, "Bundler", "moduleResolution must be Bundler")

    def test_tsconfig_json_has_strict(self):
        import json
        path = UI_DIR / "tsconfig.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        strict = data.get("compilerOptions", {}).get("strict", False)
        self.assertTrue(strict, "strict must be true in tsconfig")

    def test_esbuild_config_exists(self):
        path = BUILD_DIR / "esbuild.config.mjs"
        self.assertTrue(path.exists(), f"build/esbuild.config.mjs not found at {path}")

    def test_esbuild_config_has_iife_format(self):
        path = BUILD_DIR / "esbuild.config.mjs"
        self.assertTrue(path.exists(), "build/esbuild.config.mjs not found")
        text = path.read_text(encoding="utf-8")
        self.assertIn("format: 'iife'", text, "esbuild config must use IIFE format")

    def test_esbuild_config_outputs_viewer_bundle_js(self):
        path = BUILD_DIR / "esbuild.config.mjs"
        text = path.read_text(encoding="utf-8")
        self.assertIn("viewer.bundle.js", text, "esbuild config must output viewer.bundle.js")

    def test_esbuild_config_outputs_viewer_bundle_css(self):
        path = BUILD_DIR / "esbuild.config.mjs"
        text = path.read_text(encoding="utf-8")
        self.assertIn("viewer.bundle.css", text, "esbuild config must output viewer.bundle.css")

    def test_check_bundle_size_exists(self):
        path = BUILD_DIR / "check-bundle-size.mjs"
        self.assertTrue(path.exists(), f"build/check-bundle-size.mjs not found at {path}")

    def test_check_bundle_size_has_js_limit(self):
        path = BUILD_DIR / "check-bundle-size.mjs"
        self.assertTrue(path.exists(), "build/check-bundle-size.mjs not found")
        text = path.read_text(encoding="utf-8")
        self.assertIn("136 * 1024", text, "JS raw limit must be 136KB")
        self.assertIn("40 * 1024", text, "JS gzip limit must be 40KB")

    def test_check_bundle_size_has_css_limit(self):
        path = BUILD_DIR / "check-bundle-size.mjs"
        text = path.read_text(encoding="utf-8")
        self.assertIn("15 * 1024", text, "CSS raw limit must be 15KB")
        self.assertIn("4 * 1024", text, "CSS gzip limit must be 4KB")

    def test_check_bundle_size_exits_nonzero_on_failure(self):
        path = BUILD_DIR / "check-bundle-size.mjs"
        text = path.read_text(encoding="utf-8")
        self.assertRegex(text, r"process\.exit\(\s*(?:failed\s*\?\s*1\s*:\s*0|1)\s*\)")


class TestRendererTsExists(unittest.TestCase):
    """Commit 3 — renderer.ts created (RED until file exists)."""

    @classmethod
    def setUpClass(cls):
        cls.ts_path = SRC_DIR / "renderer.ts"
        cls.ts_exists = cls.ts_path.exists()
        cls.ts_text = cls.ts_path.read_text(encoding="utf-8") if cls.ts_exists else ""

    def test_renderer_ts_exists(self):
        self.assertTrue(self.ts_exists, f"src/renderer.ts not found at {self.ts_path}")

    def test_renderer_ts_is_nonempty(self):
        self.assertTrue(self.ts_exists, "src/renderer.ts not found")
        self.assertGreater(len(self.ts_text.splitlines()), 100,
                           "renderer.ts must have >100 lines")

    def test_renderer_ts_has_ts_nocheck_directive(self):
        """PR 1 uses @ts-nocheck since npm install is blocked and tsc cannot run.
        Maintainer removes this in a later PR after npm install enables proper tsc."""
        self.assertTrue(self.ts_exists, "src/renderer.ts not found")
        self.assertTrue(
            self.ts_text.startswith("// @ts-nocheck"),
            "renderer.ts must start with // @ts-nocheck (PR 1 — tsc cannot run without npm install)",
        )


class TestMainTsExists(unittest.TestCase):
    """Commit 3 — main.ts created (RED until file exists)."""

    def test_main_ts_exists(self):
        path = SRC_DIR / "main.ts"
        self.assertTrue(path.exists(), f"src/main.ts not found at {path}")

    def test_main_ts_imports_renderer(self):
        path = SRC_DIR / "main.ts"
        if not path.exists():
            self.skipTest("src/main.ts not found")
        text = path.read_text(encoding="utf-8")
        self.assertRegex(text, r"import\s+.*renderer",
                         "main.ts must import renderer")

    def test_main_ts_imports_css_bundle_entry(self):
        path = SRC_DIR / "main.ts"
        if not path.exists():
            self.skipTest("src/main.ts not found")
        text = path.read_text(encoding="utf-8")
        self.assertRegex(text, r"import\s+['\"].*\.css['\"]",
                         "main.ts must import a CSS entry so esbuild emits viewer.bundle.css")

    def test_main_ts_exposes_network_slot_without_bootstrapping_network(self):
        path = SRC_DIR / "main.ts"
        if not path.exists():
            self.skipTest("src/main.ts not found")
        text = path.read_text(encoding="utf-8")
        self.assertIn("network: null", text)
        self.assertNotIn("new vis.Network(container, { nodes, edges }", text)


class TestBundleArtifactsExist(unittest.TestCase):
    """Commit 4 — hand-staged bundle artifacts (RED until committed)."""

    def test_viewer_bundle_js_exists(self):
        path = ASSETS_DIR / "viewer.bundle.js"
        self.assertTrue(path.exists(), f"assets/viewer.bundle.js not found at {path}")

    def test_viewer_bundle_js_is_nonempty(self):
        path = ASSETS_DIR / "viewer.bundle.js"
        if not path.exists():
            self.skipTest("assets/viewer.bundle.js not found")
        self.assertGreater(path.stat().st_size, 100,
                           "viewer.bundle.js must be non-empty")

    def test_viewer_bundle_css_exists(self):
        path = ASSETS_DIR / "viewer.bundle.css"
        self.assertTrue(path.exists(), f"assets/viewer.bundle.css not found at {path}")

    def test_viewer_bundle_css_is_nonempty(self):
        path = ASSETS_DIR / "viewer.bundle.css"
        if not path.exists():
            self.skipTest("assets/viewer.bundle.css not found")
        self.assertGreater(path.stat().st_size, 10,
                           "viewer.bundle.css must be non-empty")


class TestBundleRevisionGuard(unittest.TestCase):
    """Guard against stale bundle/source drift for viewer.bundle.js."""

    @classmethod
    def setUpClass(cls):
        cls.main_path = SRC_DIR / "main.ts"
        cls.bundle_path = ASSETS_DIR / "viewer.bundle.js"
        cls.main_text = cls.main_path.read_text(encoding="utf-8") if cls.main_path.exists() else ""
        cls.bundle_text = cls.bundle_path.read_text(encoding="utf-8") if cls.bundle_path.exists() else ""

    def _require_artifacts(self):
        if not self.main_path.exists() or not self.bundle_path.exists():
            self.skipTest("main.ts or viewer.bundle.js not found")

    def test_bundle_revision_matches_built_asset(self):
        self._require_artifacts()

        source_match = re.search(r'bundleRevision:\s*["\']([^"\']+)["\']', self.main_text)
        bundle_match = re.search(r'bundleRevision:\s*["\']([^"\']+)["\']', self.bundle_text)

        self.assertIsNotNone(source_match, "main.ts must declare window.brainDsUI.bundleRevision")
        self.assertIsNotNone(bundle_match, "viewer.bundle.js must embed the same bundleRevision marker")
        self.assertEqual(
            source_match.group(1),
            bundle_match.group(1),
            "bundleRevision in source and built bundle must stay in sync to catch stale rebuilds",
        )


class TestLegacyRendererAssetDeleted(unittest.TestCase):
    """Commit 5 — original JS file deleted (RED until deletion)."""

    def test_legacy_renderer_asset_deleted(self):
        path = ASSETS_DIR / ("vis-offline" + "-network.js")
        self.assertFalse(path.exists(),
                         "legacy renderer asset must be deleted after identity rename")


class TestInlinerUpdated(unittest.TestCase):
    """Commit 4 — template_renderer.py reads viewer.bundle.js/css (RED until updated)."""

    @classmethod
    def setUpClass(cls):
        cls.inliner_path = UI_DIR / "template_renderer.py"
        cls.inliner_text = cls.inliner_path.read_text(encoding="utf-8") if cls.inliner_path.exists() else ""

    def test_inliner_reads_viewer_bundle_js(self):
        self.assertIn("viewer.bundle.js", self.inliner_text,
                      "template_renderer.py must reference viewer.bundle.js")

    def test_inliner_reads_viewer_bundle_css(self):
        self.assertIn("viewer.bundle.css", self.inliner_text,
                      "template_renderer.py must reference viewer.bundle.css")

    def test_inliner_does_not_reference_vis_offline_network(self):
        self.assertNotIn("vis-offline" + "-network.js", self.inliner_text,
                         "template_renderer.py must NOT reference legacy renderer asset after PR 1")

    def test_inliner_smoke_renders_html(self):
        """Smoke test: render_interactive_html produces HTML with bundle content inlined."""
        import sys
        repo_root = Path(__file__).resolve().parent.parent
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))

        viewer_bundle = ASSETS_DIR / "viewer.bundle.js"
        viewer_css = ASSETS_DIR / "viewer.bundle.css"
        if not viewer_bundle.exists() or not viewer_css.exists():
            self.skipTest("Bundle artifacts not yet hand-staged")

        from brain_ds.ui.template_renderer import render_interactive_html
        html = render_interactive_html({"nodes": [], "edges": [], "metadata": {}})
        self.assertIsInstance(html, str)
        self.assertGreater(len(html), 500, "Rendered HTML must be substantial")
        # Must contain bundle content (not external URL references)
        for token in ("http://", "https://", "unpkg", "cdn"):
            self.assertNotIn(token, html.lower(), f"Rendered HTML must not contain: {token}")


class TestLockedLiteralsInRendererTs(unittest.TestCase):
    """Literal-survival tests: all locked literals must survive verbatim in renderer.ts.

    These are RED until renderer.ts is created from the legacy renderer JS.
    REQ-GVP-1.3, REQ-GVP-X.7.
    """

    @classmethod
    def setUpClass(cls):
        cls.ts_path = SRC_DIR / "renderer.ts"
        cls.ts_exists = cls.ts_path.exists()
        cls.ts_text = cls.ts_path.read_text(encoding="utf-8") if cls.ts_exists else ""
        cls.ts_lower = cls.ts_text.lower()

    def _require_ts(self):
        if not self.ts_exists:
            self.skipTest("src/renderer.ts not yet created")

    # ── Locked state properties ──────────────────────────────────────────────

    def test_locked_isDragging(self):
        self._require_ts()
        self.assertIn("isDragging", self.ts_text)

    def test_locked_dragNodeId(self):
        self._require_ts()
        self.assertIn("dragNodeId", self.ts_text)

    def test_locked_selectedNodeId(self):
        self._require_ts()
        self.assertIn("selectedNodeId", self.ts_text)

    def test_locked_hoveredNodeId(self):
        self._require_ts()
        self.assertIn("hoveredNodeId", self.ts_text)

    def test_locked_expandedNodeIds(self):
        self._require_ts()
        self.assertIn("expandedNodeIds", self.ts_text)

    # ── Locked method names ──────────────────────────────────────────────────

    def test_locked_toggleExpandCollapse(self):
        self._require_ts()
        self.assertIn("_toggleExpandCollapse", self.ts_text)

    def test_locked_refreshThemeTokens(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"_refreshThemeTokens")

    # ── Locked numeric expressions ───────────────────────────────────────────

    def test_locked_temperature_cooling(self):
        self._require_ts()
        self.assertIn("temperature * 0.95", self.ts_text)

    def test_locked_max_radius_formula(self):
        self._require_ts()
        self.assertIn("Math.min(30, 8 + Math.sqrt(degree) * 3.5)", self.ts_text)
        self.assertIn("Math.max(12, radiusBase + Math.min(10, Math.max(0, importance)))", self.ts_text)

    def test_locked_hover_delay_350(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"hoverDelay(?:Ms)?\s*=\s*350")

    # ── Locked event payload shape ───────────────────────────────────────────

    def test_locked_nodes_array_payload(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"nodes:\s*\[node\.id\]")

    # ── Locked IIFE / API surface ────────────────────────────────────────────

    def test_locked_window_vis_export(self):
        self._require_ts()
        self.assertRegex(
            self.ts_text,
            r"window\.vis\s*=\s*\{[^}]*Network\s*:\s*Network[^}]*DataSet\s*:\s*DataSet[^}]*\}",
        )

    def test_locked_requestAnimationFrame(self):
        self._require_ts()
        self.assertIn("requestAnimationFrame", self.ts_text)

    def test_locked_canvas_element_created(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"createElement\(['\"]canvas['\"]\)")

    def test_locked_getContext_2d(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"getContext\(['\"]2d['\"]\)")

    # ── Locked a11y listbox mirror ───────────────────────────────────────────

    def test_locked_listbox_ul_element(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"createElement\(['\"]ul['\"]\)")

    def test_locked_listbox_role(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"role[\"']?\s*,\s*[\"']listbox[\"']")

    def test_locked_option_role(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"role[\"']?\s*,\s*[\"']option[\"']")

    def test_locked_graph_nodes_aria_label(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"aria-label[\"']?\s*,\s*[\"']Graph nodes[\"']")

    def test_locked_aria_live_polite(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"aria-live[\"']?\s*,\s*[\"']polite[\"']")

    # ── Locked canvas a11y ──────────────────────────────────────────────────

    def test_locked_canvas_role_img(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"setAttribute\(['\"]role['\"],\s*['\"]img['\"]\)")

    def test_locked_organization_graph_label(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"setAttribute\(['\"]aria-label['\"],\s*['\"]Organization graph['\"]\)")

    def test_locked_tabindex_0(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"setAttribute\(['\"]tabindex['\"],\s*['\"]0['\"]\)")

    # ── Locked prototype method names (DataSet + Network API) ────────────────

    def test_locked_DataSet_prototype_add(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"DataSet\.prototype\.add\s*=")

    def test_locked_DataSet_prototype_update(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"DataSet\.prototype\.update\s*=")

    def test_locked_DataSet_prototype_get(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"DataSet\.prototype\.get\s*=")

    def test_locked_DataSet_prototype__subscribe(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"DataSet\.prototype\._subscribe\s*=")

    def test_locked_Network_prototype_setOptions(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"Network\.prototype\.setOptions\s*=")

    def test_locked_Network_prototype_on(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"Network\.prototype\.on\s*=")

    def test_locked_Network_prototype_focus(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"Network\.prototype\.focus\s*=")

    def test_locked_Network_prototype_fit(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"Network\.prototype\.fit\s*=")

    # ── Locked obsidian-node-ui slice contracts ──────────────────────────────

    def test_locked_contextMenu_state(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"this\.contextMenu\s*=\s*\{")
        self.assertRegex(self.ts_text, r"contextMenu.*\bopen\b")

    def test_locked_context_menu_event(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"_emit\s*\(\s*['\"]context-menu['\"]")

    def test_locked_select_change_event(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"_emit\s*\(\s*['\"]select-change['\"]")

    def test_locked_hover_popover_method(self):
        self._require_ts()
        self.assertRegex(
            self.ts_text,
            r"Network\.prototype\._(?:show(?:Hover)?Popover|hoverPopover)\s*=\s*function",
        )

    def test_locked_updatePopoverPosition(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"_updatePopoverPosition\b")

    def test_locked_popover_role_tooltip(self):
        self._require_ts()
        self.assertRegex(
            self.ts_text,
            r"""setAttribute\s*\(\s*['"]role['"]\s*,\s*['"]tooltip['"]\s*\)"""
            r"""|role=['"]{1}tooltip['"]{1}""",
        )

    def test_locked_aria_describedby(self):
        self._require_ts()
        self.assertIn("aria-describedby", self.ts_text)

    def test_locked_viewport_matrix(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"this\.viewport\s*=\s*\{")
        self.assertIn("scale", self.ts_text)
        self.assertIn("tx", self.ts_text)
        self.assertIn("ty", self.ts_text)

    def test_locked_screenToWorld(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"_screenToWorld\s*=\s*function")

    def test_locked_worldToScreen(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"_worldToScreen\s*=\s*function")

    def test_locked_isPanning(self):
        self._require_ts()
        self.assertIn("isPanning", self.ts_text)

    def test_locked_inertiaFriction(self):
        self._require_ts()
        self.assertIn("inertiaFriction", self.ts_text)

    def test_locked_stepInertia(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"_stepInertia\s*=\s*function")

    def test_locked_selectedNodeIds_set(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"selectedNodeIds\s*=\s*new\s+Set")

    def test_locked_marquee_state(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"marquee\s*=\s*\{[^}]*active")

    def test_locked_theme_tokens_css_props(self):
        self._require_ts()
        self.assertIn("getComputedStyle", self.ts_text)
        self.assertIn("--vis-panel-text", self.ts_text)
        self.assertIn("--vis-panel-bg", self.ts_text)
        self.assertIn("--vis-focus-ring", self.ts_text)

    def test_locked_themeTokens_field(self):
        self._require_ts()
        self.assertRegex(self.ts_text, r"this\._themeTokens")

    def test_locked_prefers_reduced_motion(self):
        self._require_ts()
        self.assertIn("prefers-reduced-motion", self.ts_text)
        self.assertRegex(self.ts_text, r"matchMedia\(['\"].*prefers-reduced-motion.*['\"]")

    def test_no_external_imports(self):
        """renderer.ts must not import from external packages — standalone file."""
        self._require_ts()
        # ts-nocheck and internal references allowed; no external package imports
        for line in self.ts_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("*"):
                continue
            if re.match(r"^import\s+", stripped):
                # Only self-relative imports or no-import header allowed
                self.assertRegex(
                    stripped,
                    r"""^import\s+['\"]\./ """.strip(),
                    f"renderer.ts must only have relative imports, got: {stripped}",
                )


class TestNoLegacyRendererAssetReferences(unittest.TestCase):
    """After PR 1 the repo must have zero references to the legacy renderer asset
    (except in this test and history).

    RED until deletion + sweeps are complete.
    """

    def test_template_renderer_no_vis_offline_reference(self):
        path = UI_DIR / "template_renderer.py"
        text = path.read_text(encoding="utf-8")
        self.assertNotIn(
            "vis-offline" + "-network.js", text,
            "template_renderer.py must not reference the legacy renderer asset after PR 1",
        )

    def test_test_canvas_renderer_no_vis_offline_path(self):
        path = TESTS_DIR / "test_canvas_renderer.py"
        text = path.read_text(encoding="utf-8")
        self.assertNotIn(
            '"vis-offline" + "-network.js"', text,
            "test_canvas_renderer.py must not construct path to the legacy renderer asset",
        )
        self.assertNotIn(
            "'vis-offline' + '-network.js'", text,
            "test_canvas_renderer.py must not construct path to the legacy renderer asset",
        )

    def test_test_viewer_no_direct_vis_offline_reads(self):
        """test_viewer.py tests that directly read the legacy renderer asset
        must be swept to read src/renderer.ts instead."""
        path = TESTS_DIR / "test_viewer.py"
        text = path.read_text(encoding="utf-8")
        # Count lines that read the old file directly (not counting comments)
        bad_lines = [
            ln for ln in text.splitlines()
            if ('vis-offline' + '-network.js') in ln and not ln.strip().startswith('#')
        ]
        self.assertEqual(
            len(bad_lines), 0,
            f"test_viewer.py still has {len(bad_lines)} direct legacy-asset reads: "
            f"{bad_lines[:3]}",
        )


class TestSlice10CanvasVisualPolishContracts(unittest.TestCase):
    """PR 15 — Slice 10 canvas visual polish source contracts."""

    @classmethod
    def setUpClass(cls):
        cls.ts_path = SRC_DIR / "renderer.ts"
        cls.ts_text = cls.ts_path.read_text(encoding="utf-8")

    def test_renderer_reads_edge_dash_and_arrowhead_tokens(self):
        self.assertIn("--edge-dash", self.ts_text)
        self.assertIn("--edge-arrowhead-size", self.ts_text)

    def test_renderer_has_outline_fallback_map(self):
        self.assertIn("outlineFallbackByTheme", self.ts_text)
        self.assertIn("Organization", self.ts_text)
        self.assertIn("Project", self.ts_text)
        self.assertIn("Risk", self.ts_text)

    def test_renderer_reads_entity_fill_tokens(self):
        self.assertIn("entityFillByType", self.ts_text)
        self.assertIn("--entity-organization-fill", self.ts_text)
        self.assertIn("--entity-project-fill", self.ts_text)
        self.assertIn("--entity-risk-fill", self.ts_text)


class TestW2TreeFilterContracts(unittest.TestCase):
    """W2 RED contracts: tree-filter methods + heuristic removal in renderer.ts."""

    @classmethod
    def setUpClass(cls):
        cls.ts_path = SRC_DIR / "renderer.ts"
        cls.ts_text = cls.ts_path.read_text(encoding="utf-8")

    def test_renderer_exposes_setTreeFilter(self):
        self.assertRegex(self.ts_text, r"Network\.prototype\.setTreeFilter\s*=\s*function")

    def test_renderer_exposes_clearTreeFilter(self):
        self.assertRegex(self.ts_text, r"Network\.prototype\.clearTreeFilter\s*=\s*function")

    def test_renderer_state_applies_tree_filter_fields(self):
        self.assertIn("_treeFilterRootId", self.ts_text)
        self.assertIn("_treeFilterDescendants", self.ts_text)

    def test_renderer_drops_findRootNode_heuristic(self):
        self.assertNotIn("Network.prototype._findRootNode", self.ts_text)

    def test_renderer_drops_inferParentId_heuristic(self):
        self.assertNotIn("Network.prototype._inferParentId", self.ts_text)


class TestLayoutHintProjection(unittest.TestCase):
    """T1.1 — RED guard: build_render_context must project layout_hint x/y into node dict.

    This test is the failing-test half of the TDD pair for T1.2.
    It asserts that a node carrying layout_hint {x, y} produces 'x' and 'y'
    keys in the render-context node dict so the renderer's cold-start gate has
    a real signal.
    """

    def _build_ctx_with_layout_hint(self):
        import sys
        repo_root = Path(__file__).resolve().parent.parent
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))

        from brain_ds.ontology import Graph
        from brain_ds.ui.render_context import build_render_context

        payload = {
            "org": "Test",
            "nodes": [
                {
                    "id": "n1",
                    "label": "Node One",
                    "type": "Role",
                    "layout_hint": {"x": 123.0, "y": 456.0},
                },
                {
                    "id": "n2",
                    "label": "Node Two",
                    "type": "Role",
                    # no layout_hint — must NOT get x/y keys
                },
            ],
            "edges": [],
            "evidence": [],
        }
        graph = Graph.from_v1(payload)
        return build_render_context(graph)

    def test_node_with_layout_hint_has_x_key(self):
        ctx = self._build_ctx_with_layout_hint()
        node_n1 = next(n for n in ctx["nodes"] if n["id"] == "n1")
        self.assertIn("x", node_n1, "Node with layout_hint must have 'x' in render context")

    def test_node_with_layout_hint_has_y_key(self):
        ctx = self._build_ctx_with_layout_hint()
        node_n1 = next(n for n in ctx["nodes"] if n["id"] == "n1")
        self.assertIn("y", node_n1, "Node with layout_hint must have 'y' in render context")

    def test_node_with_layout_hint_x_value_correct(self):
        ctx = self._build_ctx_with_layout_hint()
        node_n1 = next(n for n in ctx["nodes"] if n["id"] == "n1")
        self.assertEqual(node_n1.get("x"), 123.0, "x must match layout_hint['x']")

    def test_node_with_layout_hint_y_value_correct(self):
        ctx = self._build_ctx_with_layout_hint()
        node_n1 = next(n for n in ctx["nodes"] if n["id"] == "n1")
        self.assertEqual(node_n1.get("y"), 456.0, "y must match layout_hint['y']")

    def test_node_without_layout_hint_has_no_x_key(self):
        ctx = self._build_ctx_with_layout_hint()
        node_n2 = next(n for n in ctx["nodes"] if n["id"] == "n2")
        self.assertNotIn("x", node_n2, "Node without layout_hint must NOT have 'x' in render context")

    def test_node_without_layout_hint_has_no_y_key(self):
        ctx = self._build_ctx_with_layout_hint()
        node_n2 = next(n for n in ctx["nodes"] if n["id"] == "n2")
        self.assertNotIn("y", node_n2, "Node without layout_hint must NOT have 'y' in render context")

    def test_layout_hint_with_partial_coords_has_no_xy(self):
        """A layout_hint with only x (no y) must NOT project either key."""
        import sys
        repo_root = Path(__file__).resolve().parent.parent
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))

        from brain_ds.ontology import Graph
        from brain_ds.ui.render_context import build_render_context

        payload = {
            "org": "Test",
            "nodes": [{"id": "n3", "label": "N3", "type": "Role", "layout_hint": {"x": 10.0}}],
            "edges": [],
            "evidence": [],
        }
        graph = Graph.from_v1(payload)
        ctx = build_render_context(graph)
        node_n3 = ctx["nodes"][0]
        self.assertNotIn("x", node_n3, "Partial layout_hint (no y) must not project x")
        self.assertNotIn("y", node_n3, "Partial layout_hint (no y) must not project y")


if __name__ == "__main__":
    unittest.main()
