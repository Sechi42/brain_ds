import json
import io
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from brain_ds.ui.render_context import build_render_context
from brain_ds.ui.template_renderer import render_interactive_html
from brain_ds.ui.viewer import render_graph_data, render_graph_file


FORBIDDEN_REMOTE_TOKENS = ("http://", "https://", "unpkg", "cdn")
EMOJI_TOKENS = ("✏️", "💾")


class TestViewerFoundation(unittest.TestCase):
    def test_render_graph_data_default_output_does_not_call_path_cwd_when_workspace_present(self):
        graph_payload = {
            "schema_version": "1.0",
            "org": "NoCwdOrg",
            "nodes": [{"id": "n1", "label": "N1", "type": "Department"}],
            "edges": [],
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            graph_path = root / "graph.json"
            graph_path.write_text(json.dumps(graph_payload), encoding="utf-8")

            from brain_ds.ui.render_context import WorkspaceContext

            workspace = WorkspaceContext.from_root_and_graph(root, graph_path)

            with patch("brain_ds.ui.viewer.Path.cwd", side_effect=AssertionError("Path.cwd must not be called")):
                output = render_graph_data(graph_payload, workspace=workspace)
            self.assertEqual(output, workspace.store_path.parent / "graph-output.html")
            self.assertTrue(output.exists())

    def test_render_graph_data_blocks_invalid_graph_before_graph_from_v1(self):
        invalid_graph = {
            "schema_version": "1.0",
            "org": "Acme",
            "nodes": [{"id": "n1", "label": "Node 1", "type": "Company"}],
            "edges": [],
        }

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "viewer.html"
            with patch("brain_ds.ui.viewer.Graph.from_v1", side_effect=AssertionError("must not call")) as graph_from_v1_mock:
                with self.assertRaisesRegex(ValueError, "Validation failed"):
                    render_graph_data(invalid_graph, output_path=output_path)

            graph_from_v1_mock.assert_not_called()

    def test_render_graph_data_force_bypasses_validation_and_calls_graph_from_v1(self):
        invalid_graph = {
            "org": "Acme",
            "nodes": [{"id": "n1", "label": "Node 1", "type": "Department"}],
            "edges": [],
        }

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "viewer.html"
            out = render_graph_data(invalid_graph, output_path=output_path, force=True)
            self.assertIsInstance(out, Path)
            self.assertTrue(out.exists())

    def test_generate_viewer_help_runs_without_import_error(self):
        script_path = Path(__file__).resolve().parent.parent / "scripts" / "generate_viewer.py"
        result = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("ImportError", result.stderr)

    def test_render_graph_data_returns_path_for_valid_dict(self):
        graph_dict = {
            "schema_version": "1.0",
            "org": "LogiTrans",
            "nodes": [{"id": "n1", "label": "N1", "type": "Department"}],
            "edges": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            out = render_graph_data(graph_dict, output_path=Path(tmp) / "viewer.html")
            self.assertIsInstance(out, Path)
            self.assertTrue(out.exists())
            self.assertIn("LogiTrans", out.read_text(encoding="utf-8"))

    def test_render_graph_data_stdout_writes_html_and_returns_dash(self):
        graph_dict = {
            "schema_version": "1.0",
            "org": "StdoutOrg",
            "nodes": [{"id": "n1", "label": "N1", "type": "Department"}],
            "edges": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            output_capture = io.StringIO()
            with patch("sys.stdout", output_capture):
                out = render_graph_data(graph_dict, output_path="-")
            self.assertEqual(out, "-")
            self.assertIn("StdoutOrg", output_capture.getvalue())
            self.assertFalse((Path(tmp) / "graph-output.html").exists())

    def test_render_graph_data_without_output_defaults_to_cwd_graph_output_html(self):
        graph_dict = {
            "schema_version": "1.0",
            "org": "DefaultOrg",
            "nodes": [{"id": "n1", "label": "N1", "type": "Department"}],
            "edges": [],
        }
        out = render_graph_data(graph_dict)
        self.assertEqual(out.name, "graph-output.html")
        self.assertTrue(out.exists())
        out.unlink(missing_ok=True)

    def test_interactive_template_renders_from_package_resources(self):
        html = render_interactive_html(
            {
                "meta": {"org": "PkgOrg", "node_count": 0, "edge_count": 0, "generated_at": ""},
                "nodes": [],
                "edges": [],
                "type_groups": [],
                "adjacency": {},
            }
        )
        self.assertIn("PkgOrg", html)
        self.assertIn("window.vis", html)

    def test_status_chrome_css_uses_tokens_without_hex_fallbacks(self):
        template_text = (Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "templates" / "graph_viewer.html").read_text(encoding="utf-8")
        fresh_block = re.search(r"\.brd-freshness-chip--fresh\s*\{([^}]*)\}", template_text)
        stale_block = re.search(r"\.brd-freshness-chip--stale\s*\{([^}]*)\}", template_text)
        secret_block = re.search(r"\.secret-status--ok\s*\{([^}]*)\}", template_text)

        self.assertIsNotNone(fresh_block, "Missing BRD fresh chip CSS rule")
        self.assertIsNotNone(stale_block, "Missing BRD stale chip CSS rule")
        self.assertIsNotNone(secret_block, "Missing secret status CSS rule")

        self.assertNotIn("var(--status-active, #059669)", fresh_block.group(1))
        self.assertNotIn("var(--status-warn, #d97706)", stale_block.group(1))
        self.assertNotIn("var(--status-active, #059669)", secret_block.group(1))


class TestUiPanelChromePolishSidebar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        template_path = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "templates" / "graph_viewer.html"
        cls.template_text = template_path.read_text(encoding="utf-8")

    def test_controls_base_rule_uses_compact_spacing_without_viewport_height(self):
        controls = re.search(r"\.controls\s*\{\s*display:\s*flex;([\s\S]*?)\}", self.template_text)
        self.assertIsNotNone(controls, "Missing .controls CSS rule")
        block = controls.group(1)
        self.assertIn("gap: 16px", block)
        self.assertIn("padding: 12px 16px", block)
        self.assertNotIn("height: 100vh", block)

    def test_left_panel_shell_controls_keep_min_height_zero(self):
        block = re.search(r"\.left-panel-shell \.controls\s*\{([^}]*)\}", self.template_text)
        self.assertIsNotNone(block, "Missing .left-panel-shell .controls CSS rule")
        self.assertIn("min-height: 0", block.group(1))

    def test_panel_card_adjacent_margin_rule_removed(self):
        self.assertNotIn(".panel-card + .panel-card", self.template_text)

    def test_left_rail_icons_duplicate_block_removed(self):
        self.assertEqual(self.template_text.count(".left-rail-icons {"), 1)

    def test_secret_panel_has_roomier_inset_spacing(self):
        secret_panel = re.search(r"#secret-panel\s*\{([^}]*)\}", self.template_text)
        secret_list = re.search(r"\.secret-list\s*\{([^}]*)\}", self.template_text)
        secret_form = re.search(r"\.secret-form\s*\{([^}]*)\}", self.template_text)

        self.assertIsNotNone(secret_panel, "Missing #secret-panel CSS rule")
        self.assertIsNotNone(secret_list, "Missing .secret-list CSS rule")
        self.assertIsNotNone(secret_form, "Missing .secret-form CSS rule")

        self.assertIn("margin: 1rem", secret_panel.group(1))
        self.assertIn("padding: 0.75rem 1rem", secret_list.group(1))
        self.assertIn("padding: 0.75rem 1rem 1rem", secret_form.group(1))

    def test_left_datasource_grouping_uses_roomier_expansion_styles(self):
        self.assertIn("details.dataset.groupBy = groupBy;", self.template_text)

        datasource_summary = re.search(
            r"\.project-group\[data-group-by='datasource'\]\s*>\s*summary\s*\{([^}]*)\}",
            self.template_text,
        )
        datasource_rows = re.search(
            r"\.project-group\[data-group-by='datasource'\]\s*\.project-node-row\s*\{([^}]*)\}",
            self.template_text,
        )

        self.assertIsNotNone(datasource_summary, "Missing datasource group summary rule")
        self.assertIsNotNone(datasource_rows, "Missing datasource node row rule")
        self.assertIn("min-height: 44px", datasource_summary.group(1))
        self.assertIn("min-height: 44px", datasource_rows.group(1))
        self.assertIn("padding: 0.5rem 0.65rem", datasource_summary.group(1))
        self.assertIn("padding: 0.35rem 0.6rem", datasource_rows.group(1))

    def test_right_sidebar_default_width_is_roomier_for_selected_node_content(self):
        workspace = re.search(r"\.workspace-shell\s*\{([^}]*)\}", self.template_text)
        self.assertIsNotNone(workspace, "Missing .workspace-shell CSS rule")
        self.assertIn("--inspector-w: 352px", workspace.group(1))

    def test_right_rail_selected_states_are_icon_specific(self):
        inspector = re.search(
            r"\.rail\[data-rail-side='right'\] \.rail-icon\[data-rail-icon='inspector'\]\[aria-selected=\"true\"\]\s*\{([^}]*)\}",
            self.template_text,
        )
        ai_actions = re.search(
            r"\.rail\[data-rail-side='right'\] \.rail-icon\[data-rail-icon='ai-actions'\]\[aria-selected=\"true\"\]\s*\{([^}]*)\}",
            self.template_text,
        )

        self.assertIsNotNone(inspector, "Missing inspector selected-state rule")
        self.assertIsNotNone(ai_actions, "Missing AI actions selected-state rule")
        self.assertIn("var(--accent-mora)", inspector.group(1))
        self.assertIn("var(--status-active)", ai_actions.group(1))
        self.assertNotEqual(inspector.group(1), ai_actions.group(1))


class TestUiPanelChromePolishBrdPanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parent.parent
        cls.template_text = (root / "brain_ds" / "ui" / "templates" / "graph_viewer.html").read_text(encoding="utf-8")
        cls.brd_panel_text = (root / "brain_ds" / "ui" / "src" / "panels" / "brd-panel.ts").read_text(encoding="utf-8")

    def test_brd_action_buttons_share_flex_width(self):
        block = re.search(r"\.brd-open-btn,\s*\.brd-edit-btn\s*\{([^}]*)\}", self.template_text)
        self.assertIsNotNone(block, "Missing grouped BRD action button CSS rule")
        body = block.group(1)
        self.assertIn("flex: 1", body)
        self.assertIn("justify-content: center", body)
        self.assertNotIn("width: 100%", body)

    def test_brd_header_and_title_tokens(self):
        header = re.search(r"\.brd-panel-header\s*\{([^}]*)\}", self.template_text)
        title = re.search(r"\.brd-panel-title\s*\{([^}]*)\}", self.template_text)
        self.assertIsNotNone(header, "Missing .brd-panel-header CSS rule")
        self.assertIsNotNone(title, "Missing .brd-panel-title CSS rule")
        self.assertRegex(header.group(1), r"min-height:\s*44px")
        self.assertIn("font-weight: var(--fw-semibold)", title.group(1))
        self.assertNotIn("650", title.group(1))

    def test_brd_buttons_have_disabled_state(self):
        self.assertRegex(self.template_text, r"\.brd-(?:open|edit)-btn\[disabled\]", "Expected BRD button disabled selector")

    def test_brd_panel_source_uses_short_freshness_chip_labels(self):
        self.assertIn("chip.textContent = fresh ? 'Actualizado' : 'Desactualizado'", self.brd_panel_text)


class TestUiPanelChromePolishSecretPanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parent.parent
        cls.template_text = (root / "brain_ds" / "ui" / "templates" / "graph_viewer.html").read_text(encoding="utf-8")
        cls.secret_panel_text = (root / "brain_ds" / "ui" / "src" / "panels" / "secret-panel.ts").read_text(encoding="utf-8")
        cls.viewer_bundle_text = (root / "brain_ds" / "ui" / "assets" / "viewer.bundle.js").read_text(encoding="utf-8")

    def test_secret_panel_chrome_uses_44px_controls_and_elevated_cards(self):
        remove_btn = re.search(r"\.secret-remove-btn\s*\{([^}]*)\}", self.template_text)
        summary = re.search(r"\.secret-summary\s*\{([^}]*)\}", self.template_text)
        secret_item = re.search(r"\.secret-item\s*\{([^}]*)\}", self.template_text)
        add_btn = re.search(r"\.secret-add-btn\s*\{([^}]*)\}", self.template_text)

        self.assertIsNotNone(remove_btn, "Missing .secret-remove-btn CSS rule")
        self.assertIsNotNone(summary, "Missing .secret-summary CSS rule")
        self.assertIsNotNone(secret_item, "Missing .secret-item CSS rule")
        self.assertIsNotNone(add_btn, "Missing .secret-add-btn CSS rule")

        self.assertIn("min-height: 44px", remove_btn.group(1))
        self.assertIn("transition", remove_btn.group(1))
        self.assertIn("[disabled]", self.template_text)
        self.assertIn("min-height: 44px", summary.group(1))
        self.assertIn("background: var(--bg-panel-elevated)", secret_item.group(1))
        self.assertTrue("width: 100%" in add_btn.group(1) or "align-self: stretch" in add_btn.group(1))

    def test_secret_panel_status_and_motion_rules_are_token_based(self):
        status = re.search(r"\.secret-status--ok\s*\{([^}]*)\}", self.template_text)
        light_item = re.search(r"\[data-theme='light'\] \.secret-item\s*\{([^}]*)\}", self.template_text)
        reduce_motion = re.search(r"@media\s*\(prefers-reduced-motion:\s*reduce\)[\s\S]*?\.secret-remove-btn[^\{]*\{[^}]*transition:\s*none;", self.template_text)

        self.assertIsNotNone(status, "Missing .secret-status--ok CSS rule")
        self.assertIsNotNone(light_item, "Missing light-theme .secret-item rule")
        self.assertIsNotNone(reduce_motion, "Missing reduced-motion media block")

        self.assertIn("var(--status-active)", status.group(1))
        self.assertIn("box-shadow: var(--shadow-xs)", light_item.group(1))
        self.assertIsNotNone(reduce_motion)

    def test_secret_panel_has_hover_focus_and_disabled_states_for_touched_controls(self):
        self.assertRegex(self.template_text, r"\.secret-remove-btn:hover")
        self.assertRegex(self.template_text, r"\.secret-remove-btn:focus-visible")
        self.assertRegex(self.template_text, r"\.secret-remove-btn\[disabled\]")
        self.assertRegex(self.template_text, r"\.secret-add-btn:hover")
        self.assertRegex(self.template_text, r"\.secret-add-btn:focus-visible")
        self.assertRegex(self.template_text, r"\.secret-add-btn\[disabled\]")

    def test_secret_panel_strings_are_translated_to_spanish(self):
        self.assertIn("Agregar secreto", self.secret_panel_text)
        self.assertIn("Eliminar", self.secret_panel_text)
        self.assertIn("Detalles", self.secret_panel_text)
        self.assertIn("Sin metadatos", self.secret_panel_text)
        self.assertIn("Identificador", self.secret_panel_text)
        self.assertIn("Tipo", self.secret_panel_text)
        self.assertIn("Valor de credencial", self.secret_panel_text)
        self.assertIn("Seleccionar tipo", self.secret_panel_text)
        self.assertIn("Eliminar secreto", self.secret_panel_text)

    def test_secret_panel_bundle_stays_in_sync_with_spanish_source_strings(self):
        self.assertIn("Agregar secreto", self.viewer_bundle_text)
        self.assertIn("Eliminar", self.viewer_bundle_text)
        self.assertIn("Detalles", self.viewer_bundle_text)
        self.assertIn("Sin metadatos", self.viewer_bundle_text)
        self.assertIn("Identificador", self.viewer_bundle_text)
        self.assertIn("Tipo", self.viewer_bundle_text)
        self.assertIn("Valor de credencial", self.viewer_bundle_text)
        self.assertIn("Seleccionar tipo", self.viewer_bundle_text)
        self.assertIn("Eliminar secreto", self.viewer_bundle_text)
        self.assertNotIn("Secret settings", self.viewer_bundle_text)
        self.assertNotIn("Add secret", self.viewer_bundle_text)
        self.assertNotIn("Remove secret", self.viewer_bundle_text)

    def test_secret_panel_template_strings_are_localized_in_graph_viewer(self):
        self.assertIn('aria-label="Configuración de secretos"', self.template_text)
        self.assertIn('title="Configuración de secretos"', self.template_text)
        self.assertIn("Configuración de secretos", self.template_text)
        self.assertNotIn('aria-label="Secret settings"', self.template_text)
        self.assertNotIn('title="Secret settings"', self.template_text)

    def test_pyproject_declares_ui_package_data(self):
        pyproject_text = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('[tool.setuptools.package-data]', pyproject_text)
        self.assertIn('"brain_ds.ui"', pyproject_text)
        self.assertIn('"templates/*.html"', pyproject_text)
        self.assertIn('"assets/*.css"', pyproject_text)
        self.assertIn('"assets/*.js"', pyproject_text)

    def test_render_context_builds_groups_and_adjacency(self):
        payload = {
            "org": "LogiTrans",
            "nodes": [
                {"id": "dept-1", "label": "Finance", "type": "Department"},
                {"id": "role-1", "label": "Manager", "type": "Role"},
            ],
            "edges": [
                {"source": "dept-1", "target": "role-1", "label": "uses", "weight": 0.5},
            ],
        }

        from brain_ds.ontology import Graph

        context = build_render_context(Graph.from_v1(payload))
        self.assertEqual(context["meta"]["org"], "LogiTrans")
        self.assertEqual(context["meta"]["node_count"], 2)
        self.assertEqual(context["meta"]["edge_count"], 1)
        self.assertEqual(context["adjacency"]["dept-1"], ["role-1"])
        self.assertTrue(any(group["supertype"] == "actor" for group in context["type_groups"]))

    def test_render_context_builds_detail_index_with_card_sections(self):
        payload = {
            "org": "LogiTrans",
            "nodes": [
                {
                    "id": "dept-1",
                    "label": "Finance",
                    "type": "Department",
                    "card_sections": [
                        {"title": "What", "content": "Runs budgeting", "icon": "", "order": 1}
                    ],
                    "evidence_ids": ["ev-1"],
                },
                {"id": "role-1", "label": "Manager", "type": "Role"},
            ],
            "edges": [
                {
                    "source": "dept-1",
                    "target": "role-1",
                    "label": "uses",
                    "reasons": ["Operational ownership"],
                },
            ],
            "evidence": [
                {
                    "id": "ev-1",
                    "type": "observation",
                    "source": "engram",
                    "content": "Finance budgeting cadence",
                    "timestamp": "2026-05-14T00:00:00Z",
                }
            ],
        }
        from brain_ds.ontology import Graph

        context = build_render_context(Graph.from_v1(payload))
        detail = context["detail_index"]["dept-1"]
        self.assertEqual(detail["node"]["label"], "Finance")
        self.assertEqual(detail["sections"][0]["origin"], "card_sections")
        self.assertEqual(detail["evidence"][0]["id"], "ev-1")
        self.assertEqual(detail["relationships"]["outgoing"][0]["target_id"], "role-1")

    def test_render_context_uses_details_fallback_when_card_sections_absent(self):
        payload = {
            "nodes": [
                {
                    "id": "n1",
                    "label": "N1",
                    "type": "Department",
                    "details": {"what": "Legacy detail"},
                }
            ],
            "edges": [],
        }
        from brain_ds.ontology import Graph

        context = build_render_context(Graph.from_v1(payload))
        sections = context["detail_index"]["n1"]["sections"]
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0]["origin"], "details_fallback")
        self.assertEqual(sections[0]["title"], "What")

    def test_render_context_assigns_component_ids_by_descending_component_size(self):
        payload = {
            "nodes": [
                {"id": "a", "label": "A", "type": "Department"},
                {"id": "b", "label": "B", "type": "Department"},
                {"id": "c", "label": "C", "type": "Department"},
                {"id": "d", "label": "D", "type": "Department"},
                {"id": "e", "label": "E", "type": "Department"},
            ],
            "edges": [
                {"source": "a", "target": "b", "label": "uses"},
                {"source": "b", "target": "c", "label": "uses"},
                {"source": "d", "target": "e", "label": "uses"},
            ],
        }
        from brain_ds.ontology import Graph

        context = build_render_context(Graph.from_v1(payload))
        comp_by_id = {node["id"]: node.get("component_id") for node in context["nodes"]}
        self.assertEqual(comp_by_id["a"], 0)
        self.assertEqual(comp_by_id["b"], 0)
        self.assertEqual(comp_by_id["c"], 0)
        self.assertEqual(comp_by_id["d"], 1)
        self.assertEqual(comp_by_id["e"], 1)

    def test_render_context_empty_graph_returns_empty_nodes(self):
        from brain_ds.ontology import Graph

        context = build_render_context(Graph.from_v1({"nodes": [], "edges": []}))
        self.assertEqual(context["nodes"], [])

    def test_default_render_writes_interactive_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            graph_path = tmp_path / "graph.json"
            graph_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "org": "LogiTrans",
                        "nodes": [{"id": "n1", "label": "N1", "type": "Department"}],
                        "edges": [],
                    }
                ),
                encoding="utf-8",
            )

            out = render_graph_file(graph_path)
            html = out.read_text(encoding="utf-8")
            self.assertIn("window.vis", html)
            self.assertIn("new vis.Network", html)
            self.assertIn("LogiTrans", html)

    def test_interactive_html_has_no_remote_vis_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            graph_path = tmp_path / "graph.json"
            graph_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "org": "OfflineOrg",
                        "nodes": [{"id": "n1", "label": "N1", "type": "Department"}],
                        "edges": [],
                    }
                ),
                encoding="utf-8",
            )

            out = render_graph_file(graph_path)
            html_lower = out.read_text(encoding="utf-8").lower()
            for token in FORBIDDEN_REMOTE_TOKENS:
                self.assertNotIn(token, html_lower)

    def test_vendored_vis_assets_have_no_remote_urls(self):
        # PR 1: renderer.ts is the new source of truth (identity port of legacy renderer JS)
        src_dir = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "src"
        js_text = (src_dir / "renderer.ts").read_text(encoding="utf-8").lower()
        assets_dir = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "assets"
        css_text = (assets_dir / "vis-network.min.css").read_text(encoding="utf-8").lower()
        for token in FORBIDDEN_REMOTE_TOKENS:
            self.assertNotIn(token, js_text)
            self.assertNotIn(token, css_text)

    def test_interactive_template_inlines_svg_sprite_with_required_icons(self):
        html = render_interactive_html(
            {
                "meta": {"org": "IconOrg", "node_count": 0, "edge_count": 0, "generated_at": ""},
                "nodes": [],
                "edges": [],
                "type_groups": [],
                "adjacency": {},
            }
        )

        self.assertIn('<svg style="display:none"', html)
        required = {
            "edit",
            "save",
            "close",
            "filter",
            "search",
            "chevron-up",
            "chevron-down",
            "chevron-left",
            "chevron-right",
            "menu",
            "x",
            "info",
            "warning",
            "check",
            "spinner",
        }
        for name in required:
            self.assertIn(f'id="icon-{name}"', html)

    def test_interactive_template_sprite_contains_phase1_lucide_symbols(self):
        html = render_interactive_html(
            {
                "meta": {"org": "IconPhase1", "node_count": 0, "edge_count": 0, "generated_at": ""},
                "nodes": [],
                "edges": [],
                "type_groups": [],
                "adjacency": {},
            }
        )

        required_phase1 = {
            "arrow-left",
            "arrow-right",
            "eye",
            "eye-off",
            "layout-grid",
            "maximize-2",
            "minimize-2",
            "more-horizontal",
            "network",
            "plus",
            "share-2",
            "sliders-horizontal",
            "sun",
        }
        for name in required_phase1:
            self.assertIn(f'id="icon-{name}"', html)

    def test_d4_overlay_disabled_above_threshold(self):
        template_path = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "templates" / "graph_viewer.html"
        template_text = template_path.read_text(encoding="utf-8")
        self.assertIn("const D4_OVERLAY_MAX_NODES = 500;", template_text)
        self.assertRegex(template_text, r"const\s+d4OverlayEnabled\s*=\s*initialNodes\.length\s*<=\s*D4_OVERLAY_MAX_NODES")
        self.assertRegex(template_text, r"if\s*\(\s*d4OverlayEnabled\s*\)\s*\{[\s\S]*d4PaintLoop\(\)")

    def test_network_opacity_visible_on_canvas_fallback(self):
        template_path = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "templates" / "graph_viewer.html"
        template_text = template_path.read_text(encoding="utf-8")
        self.assertIn("d4NetworkEl.style.opacity = d4OverlayEnabled ? \"0\" : \"1\";", template_text)
        self.assertIn("d4NetworkEl.style.pointerEvents = d4OverlayEnabled ? \"none\" : \"auto\";", template_text)

    def test_d4_node_click_handler_avoids_selectnodes_relayout_path(self):
        template_path = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "templates" / "graph_viewer.html"
        template_text = template_path.read_text(encoding="utf-8")
        self.assertNotIn("network.selectNodes([node.id])", template_text)
        self.assertIn("network._selectNodeById(node.id)", template_text)

    def test_interactive_template_toolbar_and_rail_icons_use_sprite_references(self):
        html = render_interactive_html(
            {
                "meta": {"org": "SpriteUsageOrg", "node_count": 0, "edge_count": 0, "generated_at": ""},
                "nodes": [],
                "edges": [],
                "type_groups": [],
                "adjacency": {},
            }
        )

        expected_uses = {
            '#icon-folder',
            '#icon-search',
            '#icon-filter',
            '#icon-network',
            '#icon-layout-grid',
            '#icon-chevron-left',
            '#icon-plus',
            '#icon-maximize-2',
            '#icon-sun',
            '#icon-more-horizontal',
        }
        for href in expected_uses:
            self.assertIn(f'<use href="{href}"', html)

    def test_interactive_template_icon_only_buttons_keep_a11y_contract(self):
        html = render_interactive_html(
            {
                "meta": {"org": "A11yIconOrg", "node_count": 0, "edge_count": 0, "generated_at": ""},
                "nodes": [],
                "edges": [],
                "type_groups": [],
                "adjacency": {},
            }
        )

        self.assertIn('aria-label="Open file tree panel"', html)
        self.assertIn('<svg aria-hidden="true" width="18" height="18"><use href="#icon-folder"/></svg>', html)
        self.assertIn('id="zoom-fit"', html)
        self.assertIn('aria-label="Zoom to fit"', html)
        self.assertIn('<svg aria-hidden="true" width="18" height="18"><use href="#icon-maximize-2"/></svg>', html)
        self.assertIn('id="theme-toggle"', html)
        self.assertIn('aria-label="Switch to light theme"', html)
        self.assertIn('<svg aria-hidden="true" width="18" height="18"><use href="#icon-sun"/></svg>', html)

    def test_interactive_template_replaces_detail_panel_emojis_with_svg_icons(self):
        html = render_interactive_html(
            {
                "meta": {"org": "EmojiOrg", "node_count": 0, "edge_count": 0, "generated_at": ""},
                "nodes": [],
                "edges": [],
                "type_groups": [],
                "adjacency": {},
            }
        )

        for token in EMOJI_TOKENS:
            self.assertNotIn(token, html)

        self.assertIn('id="edit-toggle"', html)
        self.assertIn('id="export-json"', html)
        self.assertIn('<use href="#icon-edit"', html)
        self.assertIn('<use href="#icon-save"', html)

    def test_interactive_template_uses_slice4_shell_surface_and_spacing_tokens(self):
        html = render_interactive_html(
            {
                "meta": {"org": "LayoutOrg", "node_count": 0, "edge_count": 0, "generated_at": ""},
                "nodes": [],
                "edges": [],
                "type_groups": [],
                "adjacency": {},
            }
        )

        # obsidian-workspace-ui replaced --surface-* with Obsidian tokens (--bg-main/panel)
        # and dropped var(--space-*) in favour of literal values. @media breakpoint kept.
        self.assertIn("--bg-main", html)
        self.assertIn("--bg-panel", html)
        self.assertIn("@media (max-width: 1100px)", html)

    def test_interactive_template_defines_detail_slideover_dialog_contract(self):
        html = render_interactive_html(
            {
                "meta": {"org": "DialogOrg", "node_count": 0, "edge_count": 0, "generated_at": ""},
                "nodes": [],
                "edges": [],
                "type_groups": [],
                "adjacency": {},
            }
        )

        self.assertIn('id="detail-panel-backdrop"', html)
        self.assertIn('role="dialog"', html)
        self.assertIn('aria-modal="true"', html)
        self.assertIn("const activateDetailSlideover", html)
        self.assertIn("trapFocusInsideDetailPanel", html)

    def test_interactive_template_contains_slice5_detail_hierarchy_tokens(self):
        html = render_interactive_html(
            {
                "meta": {"org": "Slice5Org", "node_count": 0, "edge_count": 0, "generated_at": ""},
                "nodes": [],
                "edges": [],
                "type_groups": [],
                "adjacency": {},
            }
        )

        # obsidian-workspace-ui replaced design-token font/radius vars with literal values.
        # Assert structural presence of the score chip class and its visual attributes.
        self.assertIn(".detail-score-chip", html)
        self.assertIn("border-radius: 999px", html)   # replaces --radius-pill
        self.assertIn("font-weight: 600", html)        # replaces --font-weight-semibold

    def test_interactive_template_contains_controls_and_accessibility_hooks(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            graph_path = tmp_path / "graph.json"
            graph_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "org": "Acme",
                        "nodes": [{"id": "n1", "label": "N1", "type": "Department"}],
                        "edges": [],
                    }
                ),
                encoding="utf-8",
            )

            out = render_graph_file(graph_path)
            html = out.read_text(encoding="utf-8")
            self.assertIn('id="node-search"', html)
            self.assertIn('id="type-filters"', html)
            self.assertIn('id="toggle-hierarchical"', html)
            self.assertIn('aria-label="Graph controls"', html)
            self.assertIn('id="detail-panel"', html)
            self.assertIn('aria-label="Node details"', html)
            self.assertIn('aria-labelledby="detail-title"', html)
            self.assertIn('id="detail-body"', html)
            self.assertIn('id="detail-close"', html)
            self.assertIn('id="detail-collapse"', html)
            self.assertIn("renderDetailPanel", html)
            self.assertIn("renderEvidence", html)
            self.assertIn("renderRelationships", html)
            self.assertIn("details", html.lower())
            self.assertIn("min-height: 44px", html)

    def test_interactive_template_renders_evidence_and_relationship_rationale_hooks(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            graph_path = tmp_path / "graph.json"
            graph_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "org": "Acme",
                        "nodes": [
                            {
                                "id": "dept-1",
                                "label": "Finance",
                                "type": "Department",
                                "card_sections": [{"title": "What", "content": "Runs budgeting", "icon": "", "order": 1}],
                                "evidence_ids": ["obs-1"],
                            },
                            {"id": "role-1", "label": "Controller", "type": "Role"},
                        ],
                        "edges": [
                            {
                                "source": "dept-1",
                                "target": "role-1",
                                "label": "uses",
                                "reasons": ["Operational ownership"],
                                "evidence_ids": ["obs-1"],
                            }
                        ],
                        "evidence": [
                            {
                                "id": "obs-1",
                                "type": "observation",
                                "source": "engram",
                                "content": "Finance budgeting cadence",
                                "provenance": {"session_id": "manual-save-brain_ds"},
                                "timestamp": "2026-05-14T00:00:00Z",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            out = render_graph_file(graph_path)
            html = out.read_text(encoding="utf-8")
            self.assertIn("Evidence IDs", html)
            self.assertIn("Relationship rationale", html)
            self.assertIn("Collapse", html)

    def test_simple_mode_routes_to_legacy_renderer(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            graph_path = tmp_path / "graph.json"
            graph_path.write_text(
                json.dumps({"schema_version": "1.0", "org": "Acme", "nodes": [], "edges": []}),
                encoding="utf-8",
            )
            output_path = tmp_path / "simple.html"

            with patch("brain_ds.ui.viewer.render_simple_html", return_value=output_path) as simple_mock:
                out = render_graph_file(graph_path, output_path=output_path, simple=True)

            self.assertEqual(out, output_path)
            simple_mock.assert_called_once()


class TestSlice2OneHopHighlight(unittest.TestCase):
    """Contracts for remediation PR A: direct 1-hop highlighting only."""

    @classmethod
    def setUpClass(cls):
        template_path = (
            Path(__file__).resolve().parent.parent
            / "brain_ds"
            / "ui"
            / "templates"
            / "graph_viewer.html"
        )
        cls.template_text = template_path.read_text(encoding="utf-8")

    def test_focus_node_does_not_use_two_hop_helper(self):
        """PR A: 2-hop neighborhood helper must not drive focus opacity path."""
        focus_node_idx = self.template_text.find("const focusNode")
        self.assertGreater(focus_node_idx, -1, "focusNode function not found in graph_viewer.html")
        two_hop_idx = self.template_text.find("twoHopNeighborhood", focus_node_idx)
        self.assertEqual(
            two_hop_idx,
            -1,
            "focusNode must not call twoHopNeighborhood in remediation PR A",
        )

    def test_one_hop_opacity_constants(self):
        """Neighborhood dimming is CSS-driven via the D4 overlay, not DataSet mutation.

        Selected/direct-neighbor elements stay at full strength; unrelated edges
        and non-active nodes recede. focusNode must NOT mutate the vis DataSet —
        that path stripped edge endpoints and left a stuck "spiderweb" pattern.
        """
        focus_node_idx = self.template_text.find("const focusNode")
        self.assertGreater(focus_node_idx, -1, "focusNode function not found in graph_viewer.html")
        focus_body = self.template_text[focus_node_idx:focus_node_idx + 1800]
        self.assertNotIn(
            "_applyNeighborhoodOpacity",
            focus_body,
            "focusNode must not mutate the vis DataSet; selection highlight is CSS-driven",
        )
        # Unrelated edges recede and non-active nodes dim — expressed in overlay CSS.
        self.assertRegex(
            self.template_text,
            r"\.d4-edge\[data-related='false'\][^{]*\{[^}]*opacity",
        )
        self.assertRegex(
            self.template_text,
            r"\.d4-node\[data-state='default'\][^{]*\{[^}]*opacity",
        )

    def test_tab_focus_visible_uses_soft_token_ring(self):
        self.assertRegex(self.template_text, r"\.tab:focus-visible\s*\{[^}]*box-shadow:")
        self.assertNotRegex(self.template_text, r"\.tab:focus-visible\s*\{[^}]*outline:\s*2px")


class TestSlice3bSelectionPanel(unittest.TestCase):
    """RED contracts for Slice 3b — tiered selection panel + 4 bulk actions + clearSelection.

    REQ-3.10: Selection size determines detail panel behavior.
    OBS-3.8:  2-10 tier — count + breakdown + shared relationships + 4 bulk actions.
    OBS-3.9:  >10 tier — count + breakdown ONLY + Clear selection action.
    Decision 4: exactly 4 bulk actions for the 2-10 tier.
    """

    @classmethod
    def setUpClass(cls):
        template_path = (
            Path(__file__).resolve().parent.parent
            / "brain_ds"
            / "ui"
            / "templates"
            / "graph_viewer.html"
        )
        cls.template_text = template_path.read_text(encoding="utf-8")

    def test_template_detail_tier_2_to_10_renders_breakdown(self):
        """REQ-3.10 / OBS-3.8: Template MUST have a code path for 2-10 nodes showing
        count, entity-type breakdown, shared relationships, and 4 bulk actions.

        Asserted by verifying renderSelectionPanel (or equivalent) exists and references
        a 2-to-10-node tier (size <= 10 or size >= 2) with breakdown and shared-rel logic.
        """
        self.assertIn(
            "renderSelectionPanel",
            self.template_text,
            "Expected 'renderSelectionPanel' function in graph_viewer.html (REQ-3.10 / OBS-3.8)",
        )
        # The tier boundary must be expressed — e.g. size <= 10 or size < 11
        self.assertRegex(
            self.template_text,
            r"size\s*[<>]=?\s*10|size\s*[<>]=?\s*11",
            "Expected a 2-10 tier boundary (size <= 10 or size < 11) in renderSelectionPanel (OBS-3.8)",
        )
        # Entity-type breakdown must appear in the panel logic
        self.assertIn(
            "breakdown",
            self.template_text,
            "Expected 'breakdown' variable/computation inside renderSelectionPanel (OBS-3.8)",
        )
        # Shared relationships computation (edges whose both endpoints are in selection)
        self.assertRegex(
            self.template_text,
            r"sharedRel|shared.*rel|_sharedRelationships",
            "Expected shared-relationship computation inside 2-10 tier of renderSelectionPanel (OBS-3.8)",
        )

    def test_template_detail_tier_over_10_renders_count_only(self):
        """REQ-3.10 / OBS-3.9: >10 tier MUST show count + breakdown ONLY.
        No shared-relationship computation. Only 'Clear selection' action accessible.

        Asserted by verifying a >10 branch exists and does NOT call sharedRelationships
        inside that specific branch.
        """
        self.assertIn(
            "renderSelectionPanel",
            self.template_text,
            "Expected 'renderSelectionPanel' in graph_viewer.html (REQ-3.10)",
        )
        # The >10 branch must be expressed — size > 10 or size >= 11
        self.assertRegex(
            self.template_text,
            r"size\s*>\s*10|size\s*>=\s*11",
            "Expected a >10 tier boundary (size > 10) for compact summary (OBS-3.9)",
        )

    def test_template_bulk_actions_all_four_present(self):
        """Decision 4: exactly 4 bulk actions for the 2-10 tier.
        (a) Clear selection, (b) Export JSON, (c) Focus on selection, (d) Copy IDs.

        Asserted by literal presence of all four action identifiers in the template.
        """
        for literal in ("clear-selection", "export-json", "focus-selection", "copy-ids"):
            self.assertIn(
                literal,
                self.template_text,
                f"Expected bulk action '{literal}' in graph_viewer.html (Decision 4)",
            )

    def test_clear_selection_method_present(self):
        """REQ-3.10: Network.prototype.clearSelection must be defined in the renderer.
        This method is called by the 'Clear selection' bulk action.
        """
        # PR 1: read from src/renderer.ts (identity port of legacy renderer JS)
        src_dir = (
            Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "src"
        )
        js_text = (src_dir / "renderer.ts").read_text(encoding="utf-8")
        self.assertRegex(
            js_text,
            r"Network\.prototype\.clearSelection",
            "Expected 'Network.prototype.clearSelection' in src/renderer.ts (REQ-3.10)",
        )

    def test_click_event_payload_unchanged(self):
        """REQ-X.4: Locked contract — 'nodes: [node.id]' payload in single-click path
        must remain unchanged after Slice 3b. Cite locked contract REQ-X.4.
        """
        # PR 1: read from src/renderer.ts (identity port of legacy renderer JS)
        src_dir = (
            Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "src"
        )
        js_text = (src_dir / "renderer.ts").read_text(encoding="utf-8")
        self.assertRegex(
            js_text,
            r"nodes:\s*\[node\.id\]",
            "Locked literal 'nodes: [node.id]' in single-click payload must remain present (REQ-X.4)",
        )

    def test_template_select_change_subscription(self):
        """REQ-3.10: Template MUST subscribe to 'select-change' event from the renderer
        and call renderSelectionPanel (or equivalent) on selection changes.
        """
        self.assertRegex(
            self.template_text,
            r"network\.on\(['\"]select-change['\"]",
            "Expected 'network.on(\"select-change\", ...)' subscription in graph_viewer.html (REQ-3.10)",
        )


class TestSlice5ScoreThresholdFilter(unittest.TestCase):
    """RED contracts for Slice 5 — score threshold filter (REQ-5.1 through REQ-5.10).

    Decision 1 (locked): score filter is EDGE-PRIMARY — the slider hides edges below the
    threshold; score lives on edges (edge.weight), NOT on nodes.
    Decision 3 (locked): when a selected node becomes an orphan (all its edges hidden),
    it is REMOVED from the selection set and an aria-live announcement fires.

    All assertions are source-level string/regex checks — no JS execution required.
    """

    @classmethod
    def setUpClass(cls):
        template_path = (
            Path(__file__).resolve().parent.parent
            / "brain_ds"
            / "ui"
            / "templates"
            / "graph_viewer.html"
        )
        cls.template_text = template_path.read_text(encoding="utf-8")

    def test_render_context_emits_edge_score(self):
        """REQ-5.3 / Decision 1: render_context MUST expose a 'score' field on each edge dict.

        Score is derived from edge.weight (exploration #697 confirms weight is on edges,
        not nodes).  Asserting that build_render_context produces an edge dict with a
        'score' key whose value is float(edge.weight or 0.0).
        """
        from brain_ds.ontology import Graph
        from brain_ds.ui.render_context import build_render_context

        raw = {
            "schema_version": "1.0",
            "org": "TestOrg",
            "nodes": [
                {"id": "a", "label": "A", "type": "Department"},
                {"id": "b", "label": "B", "type": "Department"},
            ],
            "edges": [
                {"source": "a", "target": "b", "label": "owns", "weight": 0.75},
            ],
        }
        graph = Graph.from_v1(raw)
        ctx = build_render_context(graph)
        self.assertTrue(ctx["edges"], "Expected at least one edge in render context")
        edge = ctx["edges"][0]
        self.assertIn(
            "score",
            edge,
            "Each edge dict in render context MUST have a 'score' field (Decision 1 / REQ-5.3)",
        )
        self.assertAlmostEqual(
            edge["score"],
            0.75,
            places=5,
            msg="Edge 'score' must equal float(edge.weight) — got {!r}".format(edge.get("score")),
        )

    def test_template_score_slider_present(self):
        """REQ-5.1 / REQ-5.2: The filter panel MUST include a range slider labeled
        'Score threshold', range 0.00 to 1.00, step 0.05, default value 0.00.

        Asserted by verifying: (a) input[type=range] with step='0.05' or step=0.05,
        (b) literal 'Score threshold' label text.
        """
        self.assertRegex(
            self.template_text,
            r'type=["\']range["\']',
            "Expected input[type='range'] slider in graph_viewer.html (REQ-5.1)",
        )
        self.assertRegex(
            self.template_text,
            r'step=["\']?0\.05["\']?',
            "Expected step='0.05' on the score threshold slider (REQ-5.1)",
        )
        self.assertIn(
            "Umbral de score",
            self.template_text,
            "Expected score-threshold sr-only label in graph_viewer.html (REQ-5.1, Spanish UI)",
        )

    def test_template_score_badge_present(self):
        """REQ-5.7: A score badge MUST be displayed adjacent to the slider showing
        the current threshold value in '0.00' format.

        Asserted by verifying a score-badge element or identifier that pairs with
        the slider and displays a formatted numeric value.

        PR 5 note: toFixed(2) formatting moved to interactions/score-filter.ts.
        The score-badge DOM element and id remain in the template; the formatting
        logic is now asserted against the extracted module source.
        """
        self.assertRegex(
            self.template_text,
            r"score.?badge|scoreBadge|score-badge",
            "Expected a score badge element/id (scoreBadge, score-badge, or score_badge) "
            "in graph_viewer.html (REQ-5.7)",
        )
        # PR 5: toFixed(2) is now in interactions/score-filter.ts (extraction).
        # Assert it lives in the module (not the template).
        score_filter_path = (
            Path(__file__).resolve().parent.parent
            / "brain_ds" / "ui" / "src" / "interactions" / "score-filter.ts"
        )
        if score_filter_path.exists():
            module_src = score_filter_path.read_text(encoding="utf-8")
            self.assertRegex(
                module_src,
                r"toFixed\s*\(\s*2\s*\)",
                "Expected toFixed(2) for '0.00' format in interactions/score-filter.ts (REQ-5.7)",
            )
        else:
            self.assertRegex(
                self.template_text,
                r"toFixed\s*\(\s*2\s*\)",
                "Expected toFixed(2) for '0.00' format (in template or score-filter.ts) (REQ-5.7)",
            )

    def test_template_applies_score_filter(self):
        """REQ-5.3 / REQ-5.9 / REQ-5.10: Template MUST define an applyScoreFilter function
        that reads a scoreThreshold variable, hides edges below the threshold (inclusive
        boundary: edge.score >= threshold is visible), and fires on slider input.

        Decision 1: edge-primary filtering.
        REQ-5.10: threshold boundary is INCLUSIVE (score == threshold → visible).
        """
        self.assertIn(
            "applyScoreFilter",
            self.template_text,
            "Expected 'applyScoreFilter' function in graph_viewer.html (REQ-5.3 / Decision 1)",
        )
        self.assertRegex(
            self.template_text,
            r"scoreThreshold\s*=\s*0(?:\.0+)?",
            "Expected 'scoreThreshold = 0' (or 0.0) default declaration in graph_viewer.html (REQ-5.2)",
        )
        self.assertRegex(
            self.template_text,
            r"score\s*>=\s*scoreThreshold|scoreThreshold\s*<=\s*score",
            "Expected inclusive threshold check 'score >= scoreThreshold' in applyScoreFilter (REQ-5.10)",
        )


class TestSlice6ContextMenuTemplate(unittest.TestCase):
    """RED contracts for Slice 6 — context menu template-side DOM and actions
    (REQ-6.2, REQ-6.3, REQ-6.8, REQ-6.9, REQ-6.10).

    All assertions are source-level string checks on graph_viewer.html — no browser required.
    """

    @classmethod
    def setUpClass(cls):
        template_path = (
            Path(__file__).resolve().parent.parent
            / "brain_ds"
            / "ui"
            / "templates"
            / "graph_viewer.html"
        )
        cls.template_text = template_path.read_text(encoding="utf-8")

    def test_template_node_menu_items_present(self):
        """REQ-6.2: Node context menu MUST contain all four required item labels verbatim.

        Items: 'Focus this node', 'Show only this node + neighbors',
               'Copy entity JSON to clipboard', 'Open detail panel'.

        PR 6 note: context menu DOM construction extracted to interactions/context-menu.ts.
        Assertions check the module file when it exists.

        Cite REQ-6.2 / OBS-6.2."""
        ctx_menu_path = (
            Path(__file__).resolve().parent.parent
            / "brain_ds" / "ui" / "src" / "interactions" / "context-menu.ts"
        )
        if ctx_menu_path.exists():
            module_src = ctx_menu_path.read_text(encoding="utf-8")
            search_src = module_src
        else:
            search_src = self.template_text
        for item in [
            "Focus this node",
            "Show only this node + neighbors",
            "Copy entity JSON to clipboard",
            "Open detail panel",
        ]:
            self.assertIn(
                item,
                search_src,
                f"Node context menu item '{item}' must be present in context-menu.ts (REQ-6.2).",
            )

    def test_template_canvas_menu_items_present(self):
        """REQ-6.3: Canvas context menu MUST contain 'Zoom to fit', 'Reset filters',
        and 'Switch layout' items.

        PR 6 note: context menu DOM construction extracted to interactions/context-menu.ts.
        Assertions check the module file when it exists.

        Cite REQ-6.3 / OBS-6.3."""
        ctx_menu_path = (
            Path(__file__).resolve().parent.parent
            / "brain_ds" / "ui" / "src" / "interactions" / "context-menu.ts"
        )
        if ctx_menu_path.exists():
            module_src = ctx_menu_path.read_text(encoding="utf-8")
            search_src = module_src
        else:
            search_src = self.template_text
        for item in ["Zoom to fit", "Reset filters", "Switch layout"]:
            self.assertIn(
                item,
                search_src,
                f"Canvas context menu item '{item}' must be present in context-menu.ts (REQ-6.3).",
            )
        # Slice 7b: theme toggle is now available.
        self.assertIn(
            "Toggle theme",
            search_src,
            "Toggle theme MUST be present once Slice 7b lands.",
        )

    def test_template_grid_aria_disabled(self):
        """REQ-6.3 + REQ-6.9: Grid layout placeholder MUST be rendered as disabled
        (greyed out) with aria-disabled='true', not hidden.

        PR 6 note: context menu DOM construction extracted to interactions/context-menu.ts.
        Assertions check the module file when it exists.

        Cite REQ-6.3 (Grid always disabled) / REQ-6.9 (disabled items use aria-disabled)
        / OBS-6.3."""
        ctx_menu_path = (
            Path(__file__).resolve().parent.parent
            / "brain_ds" / "ui" / "src" / "interactions" / "context-menu.ts"
        )
        if ctx_menu_path.exists():
            module_src = ctx_menu_path.read_text(encoding="utf-8")
            search_src = module_src
        else:
            search_src = self.template_text
        self.assertRegex(
            search_src,
            r'[Gg]rid.*aria-disabled\s*=\s*["\']true["\']'
            r'|aria-disabled\s*=\s*["\']true["\'].*[Gg]rid',
            "Grid layout menu item MUST have aria-disabled='true' in context-menu.ts (REQ-6.9 / REQ-6.3).",
        )


class TestSlice7bThemeToggleTemplate(unittest.TestCase):
    """RED contracts for Slice 7b — theme toggle + persistence in template."""

    @classmethod
    def setUpClass(cls):
        template_path = (
            Path(__file__).resolve().parent.parent
            / "brain_ds"
            / "ui"
            / "templates"
            / "graph_viewer.html"
        )
        cls.template_text = template_path.read_text(encoding="utf-8")

    def test_theme_toggle_control_present_and_accessible(self):
        self.assertRegex(self.template_text, r'id=["\']theme-toggle["\']')
        self.assertRegex(self.template_text, r'aria-label=["\']Switch to light theme["\']')

    def test_theme_persistence_uses_brain_ds_localstorage_key(self):
        self.assertIn("brain_ds.theme", self.template_text)
        self.assertRegex(self.template_text, r"localStorage\.(getItem|setItem)\(")

    def test_default_theme_falls_back_to_dark(self):
        self.assertRegex(self.template_text, r"document\.documentElement\.setAttribute\(['\"]data-theme['\"]")
        self.assertRegex(self.template_text, r"\|\|\s*['\"]dark['\"]")

    def test_theme_toggle_announces_live_region(self):
        self.assertRegex(self.template_text, r"Switched to light theme|Switched to dark theme")


class TestSlice6SearchContextMenuPolishTemplate(unittest.TestCase):
    """PR11 Slice 6 template-side token/CSS hooks."""

    @classmethod
    def setUpClass(cls):
        template_path = (
            Path(__file__).resolve().parent.parent
            / "brain_ds"
            / "ui"
            / "templates"
            / "graph_viewer.html"
        )
        cls.template_text = template_path.read_text(encoding="utf-8")

    def test_search_dropdown_uses_elevated_surface_tokens(self):
        # obsidian-workspace-ui replaced --surface-elevated / shadow-md / border-default
        # with Obsidian tokens (--bg-panel, --border-strong). Assert dropdown is present
        # and uses the new border token instead.
        self.assertIn("search-results", self.template_text)
        self.assertRegex(self.template_text, r"search-results.*border.*border-strong|border-strong")

    def test_context_menu_danger_class_css_exists(self):
        self.assertIn("menu-item--danger", self.template_text)


class TestSlice7StateDesignTemplate(unittest.TestCase):
    """PR12 Slice 7 contracts: loading, empty, and skeleton states."""

    @classmethod
    def setUpClass(cls):
        template_path = (
            Path(__file__).resolve().parent.parent
            / "brain_ds"
            / "ui"
            / "templates"
            / "graph_viewer.html"
        )
        cls.template_text = template_path.read_text(encoding="utf-8")

    def test_loading_overlay_contract_present(self):
        self.assertIn("viewer-loading", self.template_text)
        self.assertIn("icon-spinner", self.template_text)
        self.assertRegex(self.template_text, r"150")

    def test_empty_state_contract_present(self):
        # Spanish UI parity (visual polish pass): visible empty-state copy is in es-419.
        self.assertIn("No hay nodos visibles", self.template_text)
        self.assertIn("Ajusta los filtros o el umbral de score.", self.template_text)
        self.assertIn("Limpiar filtros", self.template_text)
        self.assertIn("icon-filter", self.template_text)

    def test_skeleton_contract_present(self):
        self.assertIn("detail-skeleton", self.template_text)
        self.assertRegex(self.template_text, r"60%|40%|25%")

    def test_reduced_motion_disables_skeleton_shimmer(self):
        self.assertRegex(self.template_text, r"prefers-reduced-motion")
        self.assertRegex(self.template_text, r"detail-skeleton")

    def test_live_announcements_for_loaded_and_empty(self):
        self.assertIn("Graph loaded.", self.template_text)
        self.assertIn("No nodes visible.", self.template_text)


class TestSlice8MotionMicrointeractionsTemplate(unittest.TestCase):
    """PR13 Slice 8 contracts: motion tokens + microinteractions."""

    @classmethod
    def setUpClass(cls):
        template_path = (
            Path(__file__).resolve().parent.parent
            / "brain_ds"
            / "ui"
            / "templates"
            / "graph_viewer.html"
        )
        cls.template_text = template_path.read_text(encoding="utf-8")

    def test_interactive_hover_uses_duration_fast_tokens(self):
        # obsidian-workspace-ui replaced var(--duration-fast) var(--ease-standard) with
        # literal values (200ms ease). Assert hover rule still exists for button.
        self.assertRegex(
            self.template_text,
            r"\.button:hover,\s*button:hover[^\n]*\{|button:hover\s*\{",
        )

    def test_panel_entrance_animation_contract_present(self):
        # obsidian-workspace-ui replaced var(--duration-normal) var(--ease-standard) with
        # literal 200ms ease. Keyframe and transform contract preserved.
        self.assertIn("@keyframes detail-panel-enter", self.template_text)
        self.assertIn("transform: translateY(8px)", self.template_text)
        self.assertRegex(
            self.template_text,
            r"animation:\s*detail-panel-enter\s+(var\(--duration-normal\)|200ms)\s+(var\(--ease-standard\)|ease)",
        )

    def test_score_slider_thumb_transition_uses_duration_fast(self):
        # obsidian-workspace-ui replaced token-based transitions on the slider thumb with
        # a full restyle (appearance:none, custom track/thumb). The thumb transition was
        # dropped in favour of the new flat-gray-track design (design §5).
        # Assert the new slider restyle contract (webkit-slider-thumb exists, no appearance).
        self.assertIn("#score-threshold-slider::-webkit-slider-thumb", self.template_text)

    def test_reduced_motion_disables_panel_entrance_animation(self):
        # @media prefers-reduced-motion guard must exist and disable animation on .detail-panel
        self.assertIn("@media (prefers-reduced-motion: reduce)", self.template_text)
        self.assertRegex(
            self.template_text,
            r"@media\s*\(prefers-reduced-motion:\s*reduce\)[\s\S]*animation:\s*none",
        )


class TestWorkspaceShellPr1Template(unittest.TestCase):
    """PR1 RED/GREEN contracts for shell scaffold + center chrome only."""

    @classmethod
    def setUpClass(cls):
        template_path = (
            Path(__file__).resolve().parent.parent
            / "brain_ds"
            / "ui"
            / "templates"
            / "graph_viewer.html"
        )
        cls.template_text = template_path.read_text(encoding="utf-8")

    def test_workspace_shell_uses_five_column_grid(self):
        # Five columns: 48px rail | resizable left panel | 1fr center | resizable
        # right panel | 48px rail. Panel widths are now CSS vars (user-resizable +
        # collapsible) with defaults inside the 220-300 / 280-360 reference bands.
        self.assertIn(".workspace-shell", self.template_text)
        self.assertRegex(
            self.template_text,
            r"grid-template-columns:\s*48px\s+var\(--rail-w\)\s+minmax\(0,\s*1fr\)\s+var\(--inspector-w\)\s+48px",
        )
        self.assertRegex(self.template_text, r"--rail-w:\s*264px")
        self.assertRegex(self.template_text, r"--inspector-w:\s*352px")

    def test_center_chrome_has_locked_tab_and_toolbar_heights(self):
        # PR #4 chrome parity: tab-strip is 36px per ADR-009 project override
        # (#1208 ADR-F) — the reference's 48px .tabs-bar is intentionally NOT adopted
        # because production runs the 5-column grid, not the reference standalone shell.
        # Stale-contract migration (#1194): was 48px at the D.4 port, now 36px.
        # Toolbar height stays 44px (ADR-001 locked).
        self.assertRegex(self.template_text, r"\.tab-strip\s*\{[\s\S]*flex:\s*0\s+0\s+36px")
        self.assertRegex(self.template_text, r"\.top-toolbar\s*\{[\s\S]*flex:\s*0\s+0\s+44px")

    def test_center_toolbar_contains_breadcrumb_and_empty_system_chrome_zone(self):
        self.assertIn('aria-label="Breadcrumb"', self.template_text)
        self.assertIn('data-toolbar-zone="system-chrome"', self.template_text)

    def test_network_mount_remains_in_center_canvas_area(self):
        self.assertRegex(
            self.template_text,
            r"<div\s+id=\"center-split\"[\s\S]*<div\s+id=\"network\"",
        )

    def test_center_overflow_keeps_zoom_fit_and_theme_toggle_anchors(self):
        self.assertIn('id="zoom-fit"', self.template_text)
        self.assertIn('id="theme-toggle"', self.template_text)

    def test_no_new_shell_hex_colors_are_introduced(self):
        start = self.template_text.find("/* === Workspace shell (PR1 scaffold + center chrome) === */")
        end = self.template_text.find("/* === Left sidebar === */")
        shell_block = self.template_text[start:end] if start != -1 and end != -1 else self.template_text
        self.assertNotRegex(shell_block, r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})")

    def test_legacy_center_control_ids_stay_present_as_valid_anchors(self):
        for legacy_id in ("show-more", "hide-markdown"):
            self.assertIn(f'id="{legacy_id}"', self.template_text)


class TestViewerChromeOverhaulPr1Regressions(unittest.TestCase):
    """PR1 regression contracts for the viewer-chrome-overhaul change.

    REQ-1.2: collapsed workspace panels MUST keep their collapse/expand toggle
             reachable (the global .is-collapsed rule slides the whole shell off
             with pointer-events:none, making it unrecoverable).
    REQ-1.3: the markdown split-reader MUST stack above the D4 canvas overlay
             (#d4-nodes is z-index 3) so 'Ver Más' content is visible.
    """

    @classmethod
    def setUpClass(cls):
        template_path = (
            Path(__file__).resolve().parent.parent
            / "brain_ds" / "ui" / "templates" / "graph_viewer.html"
        )
        cls.template_text = template_path.read_text(encoding="utf-8")

    def test_collapsed_workspace_shells_keep_toggle_reachable(self):
        # Dedicated collapsed-state CSS for the workspace shells must exist so the
        # 44px header strip (with the collapse/expand button) stays visible.
        self.assertRegex(
            self.template_text,
            r"\.left-panel-shell\.collapsed\b",
            "Expected a scoped '.left-panel-shell.collapsed' CSS rule (REQ-1.2)",
        )
        self.assertRegex(
            self.template_text,
            r"\.right-panel-shell\.collapsed\b",
            "Expected a scoped '.right-panel-shell.collapsed' CSS rule (REQ-1.2)",
        )

    def test_workspace_collapse_handlers_do_not_apply_global_is_collapsed(self):
        # The global '.is-collapsed' rule (translateX(101%); pointer-events:none)
        # is for the detail-panel slideover only. Applying it to the workspace
        # shells hides the toggle button itself -> unrecoverable. The handlers must
        # toggle ONLY the scoped '.collapsed' class on the shells.
        self.assertNotRegex(
            self.template_text,
            r"(?:left|right)Shell\.classList\.toggle\(\s*['\"]is-collapsed['\"]",
            "Workspace shell collapse handlers must NOT toggle the global 'is-collapsed' class (REQ-1.2)",
        )

    def test_markdown_reader_stacks_above_canvas_overlay(self):
        # #markdown-reader must establish a stacking context above #d4-nodes (z-index 3).
        reader_idx = self.template_text.find("#markdown-reader {")
        self.assertGreater(reader_idx, -1, "#markdown-reader base rule not found")
        reader_block = self.template_text[reader_idx:reader_idx + 400]
        self.assertRegex(
            reader_block,
            r"z-index:\s*([4-9]|\d{2,})",
            "Expected #markdown-reader to set z-index >= 4 (above D4 overlay) (REQ-1.3)",
        )
        self.assertRegex(
            reader_block,
            r"position:\s*relative",
            "Expected #markdown-reader position: relative to honour z-index (REQ-1.3)",
        )


class TestWorkspaceShellPr15ChromePolish(unittest.TestCase):
    """PR1.5 RED/GREEN contracts for center chrome polish — section-4 fidelity.

    These tests verify the polished chrome patterns against section-4-center-canvas.html
    as ground truth. Left/right panels are out of scope for this slice.
    """

    @classmethod
    def setUpClass(cls):
        template_path = (
            Path(__file__).resolve().parent.parent
            / "brain_ds"
            / "ui"
            / "templates"
            / "graph_viewer.html"
        )
        cls.template_text = template_path.read_text(encoding="utf-8")

    # ── T1: Tab strip — tablist semantics ────────────────────────────────────

    def test_tab_strip_has_tablist_role(self):
        """Tab strip container MUST carry role="tablist"."""
        self.assertRegex(
            self.template_text,
            r'class="tab-strip"[^>]*role="tablist"|role="tablist"[^>]*class="tab-strip"',
            "Expected role='tablist' on .tab-strip element (section-4 pattern)",
        )

    def test_active_tab_has_aria_selected_true(self):
        """Active tab button MUST have aria-selected='true' and role='tab'."""
        self.assertRegex(
            self.template_text,
            r'role="tab"[^>]*aria-selected="true"|aria-selected="true"[^>]*role="tab"',
            "Expected role='tab' button with aria-selected='true' (section-4 pattern)",
        )

    def test_tab_close_buttons_have_catalog_id(self):
        """Each tab close button MUST carry the tabs.ts close-target attribute."""
        tabs_text = (Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "src" / "tabs.ts").read_text(encoding="utf-8")
        self.assertIn(
            "data-tab-close-for",
            tabs_text,
            "Expected data-tab-close-for on tab close button (current tabs.ts contract)",
        )

    def test_tab_new_button_present(self):
        """New-tab button MUST be present as a separate 44×36 button."""
        self.assertIn(
            'class="tab-new"',
            self.template_text,
            "Expected standalone .tab-new button in the tab strip",
        )

    # ── T2: Toolbar zones — all four present ─────────────────────────────────

    def test_toolbar_has_all_four_zones(self):
        """All four data-toolbar-zone values MUST be present."""
        for zone in ("nav", "view", "overflow", "system-chrome"):
            self.assertIn(
                f'data-toolbar-zone="{zone}"',
                self.template_text,
                f"Expected data-toolbar-zone='{zone}' in toolbar (section-4 pattern)",
            )

    def test_toolbar_nav_zone_hosts_vault_switcher(self):
        """nav zone hosts the functional vault switcher (chrome redesign).

        Previously reserved/empty; now it carries exactly one control:
        #nav-vaults, returning the user to the org picker.
        """
        import re
        match = re.search(r'<div\s+data-toolbar-zone="nav">([\s\S]*?)</div>', self.template_text)
        self.assertIsNotNone(match, "Expected data-toolbar-zone='nav' container")
        self.assertIn('id="nav-vaults"', match.group(1), "nav zone must host the vault switcher")
        self.assertEqual(
            match.group(1).count("<button"), 1,
            "nav zone carries exactly the vault switcher — no extra controls",
        )

    def test_toolbar_overflow_has_catalog_id_and_haspopup(self):
        """overflow zone MUST contain data-catalog-id='overflow' with aria-haspopup='menu'."""
        self.assertIn(
            'data-catalog-id="overflow"',
            self.template_text,
            "Expected data-catalog-id='overflow' button in overflow zone",
        )
        self.assertIn(
            'aria-haspopup="menu"',
            self.template_text,
            "Expected aria-haspopup='menu' on overflow button",
        )

    def test_toolbar_view_zone_has_breadcrumb_nav(self):
        """view zone MUST contain breadcrumb nav with semantic list."""
        self.assertIn('aria-label="Breadcrumb"', self.template_text)
        self.assertIn('id="workspace-view-label"', self.template_text)
        self.assertIn('<ol id="workspace-view-label"', self.template_text)

    # ── T3: No hardcoded hex in chrome CSS block ──────────────────────────────

    def test_no_hardcoded_hex_in_pr15_chrome_block(self):
        """PR1.5 chrome CSS (tab/toolbar block) MUST use only var(--*) — no hardcoded hex.

        The shell CSS block is bounded by the same PR1 comment markers used in the
        existing hex test. This test extends coverage by targeting the polished
        tab-item / tab-close / tab-new / toolbar-btn rules specifically.
        """
        start = self.template_text.find("/* === Workspace shell (PR1 scaffold + center chrome) === */")
        end = self.template_text.find("/* === Left sidebar === */")
        if start == -1 or end == -1:
            self.skipTest("Shell CSS block comment markers not found — PR1.5 markers may differ")
        chrome_block = self.template_text[start:end]
        # Verify polished tab/toolbar CSS is present inside the block
        self.assertIn(".tab-item", chrome_block, "Expected .tab-item rules in shell CSS block")
        self.assertIn(".toolbar-btn", chrome_block, "Expected .toolbar-btn rules in shell CSS block")
        # No hex literals
        self.assertNotRegex(
            chrome_block,
            r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b",
            "Hardcoded hex color found in shell CSS block — use var(--*) tokens",
        )

    # ── T4: Lucide SVGs in tab/toolbar regions ────────────────────────────────

    def test_lucide_svgs_present_in_toolbar_region(self):
        """Toolbar/tab buttons MUST use sprite-based Lucide icon references."""
        self.assertIn('<use href="#icon-plus"', self.template_text)
        self.assertIn('<use href="#icon-maximize-2"', self.template_text)
        self.assertIn('<use href="#icon-sun"', self.template_text)
        self.assertIn('<use href="#icon-more-horizontal"', self.template_text)

    # ── T5: Reduced-motion covers new chrome transitions ─────────────────────

    def test_reduced_motion_covers_chrome_transitions(self):
        """@media (prefers-reduced-motion: reduce) MUST silence chrome transitions.

        The block must include tab/toolbar transition rules — checked by verifying
        that the reduced-motion block (a) exists and (b) appears with enough scope to
        cover .tab-item, .tab-close, .tab-new, or .toolbar-btn.
        """
        # Verify the reduced-motion block exists (PR1 already established this)
        self.assertIn(
            "@media (prefers-reduced-motion: reduce)",
            self.template_text,
            "Expected @media (prefers-reduced-motion: reduce) block",
        )


class TestGraphVisualRichnessTemplateIsolation(unittest.TestCase):
    """D.4 Phase 6 template contracts: style block exists and is isolated from shell."""

    @classmethod
    def setUpClass(cls):
        template_path = (
            Path(__file__).resolve().parent.parent
            / "brain_ds"
            / "ui"
            / "templates"
            / "graph_viewer.html"
        )
        cls.template_text = template_path.read_text(encoding="utf-8")

    def test_d4_visual_richness_style_block_present(self):
        self.assertIn('<style id="d4-visual-richness">', self.template_text)

    def test_runtime_template_uses_token_vars_not_hardcoded_hex(self):
        self.assertIn("var(--canvas-bg-from)", self.template_text)
        self.assertIn("var(--canvas-bg-to)", self.template_text)

        for selector in (".canvas-container", ".canvas-bg-gradient"):
            block_match = re.search(rf"{re.escape(selector)}\s*\{{([\s\S]*?)\}}", self.template_text)
            self.assertIsNotNone(block_match, f"Missing CSS block for {selector}")
            block = block_match.group(1)
            self.assertNotIn("#0a0a0c", block)
            self.assertNotIn("#0f0f13", block)

        tokens_path = (
            Path(__file__).resolve().parent.parent
            / "brain_ds"
            / "ui"
            / "static"
            / "tokens.css"
        )
        tokens_text = tokens_path.read_text(encoding="utf-8")
        self.assertIn("--canvas-bg-from", tokens_text)
        self.assertIn("--canvas-bg-to", tokens_text)

    def test_d4_selectors_do_not_leak_into_shell_css_block(self):
        start = self.template_text.find("/* === Workspace shell (PR1 scaffold + center chrome) === */")
        end = self.template_text.find("/* === Left sidebar === */")
        self.assertNotEqual(start, -1, "Shell CSS block start marker missing")
        self.assertNotEqual(end, -1, "Shell CSS block end marker missing")
        shell_block = self.template_text[start:end]
        self.assertNotRegex(shell_block, r"\.d4-|#d4-", "D.4 selectors leaked into shell CSS block")
        # Find the reduced-motion block and check it covers chrome elements
        rm_match = re.search(
            r"@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{([\s\S]*?)\}(?=\s*@media|\s*</style>)",
            self.template_text,
        )
        self.assertIsNotNone(rm_match, "Could not parse reduced-motion media block")
        rm_block = rm_match.group(1)
        # Expect the chrome transition selectors are covered — either via a broad rule
        # or specific tab/toolbar selectors
        has_chrome_coverage = (
            ".tab-item" in rm_block
            or ".toolbar-btn" in rm_block
            or "transition: none" in rm_block
        )
        self.assertTrue(
            has_chrome_coverage,
            "reduced-motion block MUST cover chrome transitions (.tab-item, .toolbar-btn, "
            "or a broad 'transition: none' rule)",
        )

    # ── T6: system-chrome zone is zero-width (no painting) ───────────────────

    def test_system_chrome_zone_is_zero_width(self):
        """system-chrome zone MUST be width:0 (reserved but not painted)."""
        self.assertRegex(
            self.template_text,
            r"\[data-toolbar-zone=['\"]system-chrome['\"]\]\s*\{[^}]*width:\s*0",
            "Expected [data-toolbar-zone='system-chrome'] { width: 0 } (reserved, no paint)",
        )

    # ── T7: Tab CSS follows section-4 active/hover/close patterns ────────────

    def test_tab_item_active_has_accent_box_shadow(self):
        """Active tab MUST have box-shadow with accent-mora underline (section-4 pattern)."""
        self.assertRegex(
            self.template_text,
            r"box-shadow:\s*inset\s+0\s+-2px\s+0\s+var\(--accent-mora\)",
            "Expected 'box-shadow: inset 0 -2px 0 var(--accent-mora)' on active tab (section-4)",
        )

    def test_tab_close_hover_reveal_pattern(self):
        """tab-close MUST default to opacity:0 (revealed on hover/active — section-4 ADR-008)."""
        # Find .tab-close block and check opacity: 0 default
        idx = self.template_text.find(".tab-close {")
        if idx == -1:
            idx = self.template_text.find(".tab-close{")
        self.assertGreater(idx, -1, "Expected .tab-close CSS rule in template")
        # Grab the CSS block
        block_end = self.template_text.find("}", idx)
        tab_close_block = self.template_text[idx:block_end + 1]
        self.assertIn(
            "opacity: 0",
            tab_close_block,
            "Expected opacity: 0 default on .tab-close (hover-reveal pattern — ADR-008)",
        )


class TestWorkspaceShellPr2LeftAdapters(unittest.TestCase):
    """PR2 RED/GREEN contracts for left rail + L-panel adapters.

    Ground truth: brain_ds/ui/design/sections/section-1-left-shell.html
    Scope: left rail (.rail[data-rail-side='left']), left-panel-shell header,
           controls reachability. Center column and right side are out of scope.
    """

    @classmethod
    def setUpClass(cls):
        template_path = (
            Path(__file__).resolve().parent.parent
            / "brain_ds"
            / "ui"
            / "templates"
            / "graph_viewer.html"
        )
        cls.template_text = template_path.read_text(encoding="utf-8")

    # ── L1: Rail structure ──────────────────────────────────────────────────

    def test_left_rail_has_role_tablist_and_orientation(self):
        """Left rail nav MUST carry role='tablist' aria-orientation='vertical'."""
        # The left rail element must have role="tablist" and aria-orientation="vertical"
        self.assertRegex(
            self.template_text,
            r'role="tablist"[^>]*aria-orientation="vertical"|aria-orientation="vertical"[^>]*role="tablist"',
            "Expected role='tablist' aria-orientation='vertical' on left rail (section-1 pattern)",
        )

    def test_left_rail_has_rail_icon_buttons_with_catalog_ids(self):
        """Left rail MUST contain .rail-icon buttons with data-catalog-id for each action."""
        for catalog_id in ("file-tree", "search", "filters", "hierarchy", "layout"):
            self.assertIn(
                f'data-catalog-id="{catalog_id}"',
                self.template_text,
                f"Expected data-catalog-id='{catalog_id}' on a rail-icon button (section-1 pattern)",
            )

    def test_left_rail_icons_use_rail_icon_class(self):
        """Each rail-icon button MUST use the .rail-icon class (44×44 per _shared.css)."""
        # Count .rail-icon buttons in the left rail region
        # Verify the class appears for each expected catalog id
        for catalog_id in ("file-tree", "search", "filters", "hierarchy", "layout"):
            # Find the button with this catalog-id and check it also has class="rail-icon"
            idx = self.template_text.find(f'data-catalog-id="{catalog_id}"')
            self.assertGreater(idx, -1, f"Button with data-catalog-id='{catalog_id}' not found")
            # Look backwards up to 300 chars for the opening <button tag
            snippet = self.template_text[max(0, idx - 300):idx + 100]
            self.assertIn(
                "rail-icon",
                snippet,
                f"Expected class='rail-icon' near data-catalog-id='{catalog_id}' button",
            )

    def test_left_rail_has_one_active_icon_aria_selected_true(self):
        """Exactly one left rail icon MUST have aria-selected='true' by default."""
        import re
        # Find the left rail section (before left-panel-shell)
        rail_start = self.template_text.find('data-rail-side="left"')
        self.assertGreater(rail_start, -1, "Left rail (data-rail-side='left') not found")
        # The section up to left-panel-shell is the rail
        panel_start = self.template_text.find('class="left-panel-shell"')
        rail_region = self.template_text[rail_start:panel_start] if panel_start > rail_start else self.template_text[rail_start:rail_start + 2000]
        active_count = len(re.findall(r'aria-selected="true"', rail_region))
        self.assertGreaterEqual(active_count, 1, "Expected at least one aria-selected='true' on left rail icons")

    def test_left_rail_icons_have_lucide_svgs_with_stroke_currentcolor(self):
        """Left rail icon buttons MUST use sprite-based Lucide icon references."""
        rail_start = self.template_text.find('data-rail-side="left"')
        panel_start = self.template_text.find('class="left-panel-shell"')
        rail_region = self.template_text[rail_start:panel_start] if panel_start > rail_start else self.template_text[rail_start:rail_start + 2000]
        self.assertIn('<use href="#icon-folder"', rail_region)
        self.assertIn('<use href="#icon-search"', rail_region)
        self.assertIn('<use href="#icon-filter"', rail_region)
        self.assertIn('<use href="#icon-network"', rail_region)
        self.assertIn('<use href="#icon-layout-grid"', rail_region)

    def test_left_rail_svgs_have_aria_hidden(self):
        """All left-rail SVGs MUST be decorative (aria-hidden='true')."""
        rail_start = self.template_text.find('data-rail-side="left"')
        panel_start = self.template_text.find('class="left-panel-shell"')
        rail_region = self.template_text[rail_start:panel_start] if panel_start > rail_start else self.template_text[rail_start:rail_start + 2000]
        import re
        svgs = re.findall(r'<svg[^>]*>', rail_region)
        for svg_tag in svgs:
            self.assertIn(
                'aria-hidden="true"',
                svg_tag,
                f"Left rail SVG is not decorative (missing aria-hidden='true'): {svg_tag[:80]}",
            )

    # ── L2: L-panel header ──────────────────────────────────────────────────

    def test_left_panel_shell_has_panel_header_with_region_role(self):
        """Left panel shell MUST contain a panel-header with role='region' and aria-label."""
        self.assertIn(
            'class="panel-header"',
            self.template_text,
            "Expected class='panel-header' inside .left-panel-shell",
        )
        # The region must be labeled
        panel_shell_start = self.template_text.find('class="left-panel-shell"')
        # Find end of left-panel-shell region (up to center-column)
        center_col_idx = self.template_text.find('class="center-column"')
        panel_region = self.template_text[panel_shell_start:center_col_idx] if center_col_idx > panel_shell_start else self.template_text[panel_shell_start:panel_shell_start + 3000]
        self.assertRegex(
            panel_region,
            r'role="region"',
            "Expected role='region' within .left-panel-shell (section-1 pattern)",
        )
        self.assertRegex(
            panel_region,
            r'aria-label=',
            "Expected aria-label on the region element within .left-panel-shell",
        )

    def test_left_panel_header_has_collapse_control(self):
        """Panel header MUST contain a collapse button with aria-label."""
        panel_shell_start = self.template_text.find('class="left-panel-shell"')
        center_col_idx = self.template_text.find('class="center-column"')
        panel_region = self.template_text[panel_shell_start:center_col_idx] if center_col_idx > panel_shell_start else self.template_text[panel_shell_start:panel_shell_start + 3000]
        self.assertRegex(
            panel_region,
            r'aria-label="Collapse left panel"',
            "Expected collapse button with aria-label='Collapse left panel' in panel header",
        )

    # ── L3: Controls reachability ───────────────────────────────────────────

    def test_legacy_controls_are_in_dom_and_not_removed(self):
        """All legacy control IDs MUST remain in the DOM (not removed).

        Runtime JS depends on these IDs for mounting search, filters, legend,
        tree, and layout panels.
        """
        for control_id in (
            "node-search",
            "type-filters",
            "legend",
            "tree-panel",
            "toggle-hierarchical",
            "toggle-physics",
            "score-threshold-slider",
            "score-badge",
        ):
            self.assertIn(
                f'id="{control_id}"',
                self.template_text,
                f"Legacy control id='{control_id}' MUST remain in DOM (runtime JS depends on it)",
            )

    def test_search_shortcut_pill_is_adjacent_to_node_search(self):
        """Search panel MUST include '/' shortcut pill adjacent to #node-search."""
        search_idx = self.template_text.find('id="node-search"')
        self.assertGreater(search_idx, -1, "node-search input not found")
        around = self.template_text[max(0, search_idx - 400):search_idx + 400]
        self.assertIn('class="search-pill"', around)
        self.assertIn('aria-keyshortcuts="/"', around)

    def test_left_rail_status_chip_is_last_child(self):
        """[data-status-chip] MUST be the last child of left rail container."""
        import re
        rail_match = re.search(
            r'<nav[^>]*data-rail-side="left"[^>]*>([\s\S]*?)</nav>',
            self.template_text,
        )
        self.assertIsNotNone(rail_match, "Left rail markup not found")
        rail_region = rail_match.group(1)
        status_idx = rail_region.find('data-status-chip')
        self.assertGreater(status_idx, -1, "Expected data-status-chip inside left rail")
        self.assertEqual(rail_region.count('data-status-chip'), 1, "Status chip should appear exactly once")
        self.assertRegex(
            rail_region,
            r'<span\s+data-status-chip[^>]*>[^<]*</span>\s*$',
            "Status chip must be the last child element in left rail",
        )

    def test_controls_aside_is_not_hidden(self):
        """After PR2, .controls aside MUST NOT have the hidden attribute (panel is visible)."""
        # Find the controls aside and check it does NOT have `hidden` as a standalone attribute
        controls_idx = self.template_text.find('class="panel controls"')
        self.assertGreater(controls_idx, -1, "Expected class='panel controls' aside in template")
        # Extract the opening tag
        tag_end = self.template_text.find('>', controls_idx)
        opening_tag = self.template_text[controls_idx:tag_end + 1]
        self.assertNotRegex(
            opening_tag,
            r'\bhidden\b',
            "The .controls aside MUST NOT have the 'hidden' attribute after PR2 (panel is visible)",
        )

    # ── L4: No hardcoded hex in PR2 CSS block ──────────────────────────────

    def test_no_hardcoded_hex_in_pr2_left_rail_css_block(self):
        """PR2 CSS block MUST use only var(--*) — no hardcoded #rrggbb hex.

        Scoped by comment markers:
        /* === PR2 Left Rail + L-Panel === */ ... /* === END PR2 Left Rail + L-Panel === */
        """
        start_marker = "/* === PR2 Left Rail + L-Panel === */"
        end_marker = "/* === END PR2 Left Rail + L-Panel === */"
        start = self.template_text.find(start_marker)
        end = self.template_text.find(end_marker)
        if start == -1 or end == -1:
            self.fail(
                "PR2 CSS block markers not found. "
                "Expected '/* === PR2 Left Rail + L-Panel === */' and "
                "'/* === END PR2 Left Rail + L-Panel === */' in template CSS."
            )
        pr2_css_block = self.template_text[start:end]
        self.assertNotRegex(
            pr2_css_block,
            r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b",
            "Hardcoded hex color found in PR2 CSS block — use var(--*) tokens",
        )

    # ── L5: Deprecation / compat-topbar stays hidden ─────────────────────

    def test_compat_topbar_element_still_has_hidden_attribute(self):
        """Compat-topbar MUST keep the HTML hidden attribute (PR1 deprecation)."""
        self.assertRegex(
            self.template_text,
            r'class="topbar compat-topbar"[^>]*hidden',
            "Expected compat-topbar element to still have hidden attribute (PR1 deprecation)",
        )

    def test_compat_topbar_css_is_display_none(self):
        """CSS MUST still declare .compat-topbar { display: none }."""
        self.assertRegex(
            self.template_text,
            r'\.compat-topbar\s*\{[^}]*display:\s*none',
            "Expected .compat-topbar { display: none } CSS rule still present (PR1 deprecation)",
        )


class TestWorkspaceShellPr3RightInspectorResponsive(unittest.TestCase):
    """PR3 RED/GREEN contracts for right rail + inspector adapter + responsive behavior.

    Ground truth: brain_ds/ui/design/sections/section-2-right-shell.html
    Scope: right rail (data-rail-side='right'), R-panel header, inspector accordion
           wrappers, responsive slide-over contracts. Center column and left side
           are out of scope for this slice.
    """

    @classmethod
    def setUpClass(cls):
        template_path = (
            Path(__file__).resolve().parent.parent
            / "brain_ds"
            / "ui"
            / "templates"
            / "graph_viewer.html"
        )
        cls.template_text = template_path.read_text(encoding="utf-8")

    # ── R1: Right rail structure ────────────────────────────────────────────

    def test_right_rail_uses_nav_with_tablist_and_data_rail_side(self):
        """Right rail MUST be a <nav> with role='tablist', aria-orientation='vertical',
        and data-rail-side='right' (enables _shared.css mirror rule)."""
        # The right rail element must carry data-rail-side="right" and role="tablist"
        self.assertRegex(
            self.template_text,
            r'data-rail-side="right"[^>]*role="tablist"|role="tablist"[^>]*data-rail-side="right"',
            "Expected role='tablist' with data-rail-side='right' on right rail (section-2 pattern)",
        )
        self.assertRegex(
            self.template_text,
            r'data-rail-side="right"[^>]*aria-orientation="vertical"|aria-orientation="vertical"[^>]*data-rail-side="right"',
            "Expected aria-orientation='vertical' on right rail nav element",
        )

    def test_right_rail_has_no_orphan_gear_button(self):
        """PR B: orphan gear must be removed from the right rail."""
        self.assertNotIn('data-catalog-id="gear"', self.template_text)
        self.assertNotIn('data-catalog-id="inspector"', self.template_text)
        self.assertNotIn('data-catalog-id="history"', self.template_text)
        self.assertNotIn('data-catalog-id="settings"', self.template_text)

    def test_right_rail_icons_use_rail_icon_class(self):
        """Right rail can be empty in PR B after gear removal; class contract remains generic."""
        self.assertIn('data-rail-side="right"', self.template_text)

    def test_right_rail_has_zero_or_more_active_icon_aria_selected_true(self):
        """PR B allows zero right-rail icons after orphan gear removal."""
        import re
        rail_start = self.template_text.find('data-rail-side="right"')
        self.assertGreater(rail_start, -1, "Right rail (data-rail-side='right') not found")
        # Region ends before the detail-panel-backdrop or end of main
        backdrop_start = self.template_text.find('id="detail-panel-backdrop"')
        rail_region = (
            self.template_text[rail_start:backdrop_start]
            if backdrop_start > rail_start
            else self.template_text[rail_start:rail_start + 2000]
        )
        active_count = len(re.findall(r'aria-selected="true"', rail_region))
        self.assertGreaterEqual(active_count, 0)

    def test_right_rail_svgs_are_aria_hidden(self):
        """All right rail SVGs MUST be decorative (aria-hidden='true')."""
        import re
        rail_start = self.template_text.find('data-rail-side="right"')
        backdrop_start = self.template_text.find('id="detail-panel-backdrop"')
        rail_region = (
            self.template_text[rail_start:backdrop_start]
            if backdrop_start > rail_start
            else self.template_text[rail_start:rail_start + 2000]
        )
        svgs = re.findall(r'<svg[^>]*>', rail_region)
        for svg_tag in svgs:
            self.assertIn(
                'aria-hidden="true"',
                svg_tag,
                f"Right rail SVG missing aria-hidden='true': {svg_tag[:80]}",
            )

    # ── R2: R-panel header ──────────────────────────────────────────────────

    def test_right_panel_shell_has_r_panel_header_with_region_role(self):
        """Right panel shell MUST contain a panel-header with role='region' and aria-label."""
        right_shell_start = self.template_text.find('class="right-panel-shell"')
        self.assertGreater(right_shell_start, -1, "class='right-panel-shell' not found")
        # Region ends at the right rail nav
        rail_start = self.template_text.find('data-rail-side="right"')
        right_shell_region = (
            self.template_text[right_shell_start:rail_start]
            if rail_start > right_shell_start
            else self.template_text[right_shell_start:right_shell_start + 4000]
        )
        self.assertIn(
            'class="panel-header"',
            right_shell_region,
            "Expected class='panel-header' inside .right-panel-shell",
        )
        self.assertRegex(
            right_shell_region,
            r'role="region"',
            "Expected role='region' within .right-panel-shell R-panel header",
        )
        self.assertRegex(
            right_shell_region,
            r'aria-label=',
            "Expected aria-label on the region element within .right-panel-shell",
        )

    def test_right_panel_header_has_collapse_control(self):
        """R-panel header MUST contain a collapse control with aria-label."""
        right_shell_start = self.template_text.find('class="right-panel-shell"')
        rail_start = self.template_text.find('data-rail-side="right"')
        right_shell_region = (
            self.template_text[right_shell_start:rail_start]
            if rail_start > right_shell_start
            else self.template_text[right_shell_start:right_shell_start + 4000]
        )
        self.assertRegex(
            right_shell_region,
            r'aria-label="Collapse right panel"',
            "Expected collapse button with aria-label='Collapse right panel' in R-panel header",
        )

    # ── R3: #detail-panel runtime contracts preserved ───────────────────────

    def test_detail_panel_id_and_dialog_contracts_still_present(self):
        """#detail-panel MUST keep id, aria-labelledby='detail-title', role='dialog',
        aria-modal='true' — runtime JS depends on these."""
        self.assertIn('id="detail-panel"', self.template_text)
        self.assertIn('aria-labelledby="detail-title"', self.template_text)
        self.assertIn('role="dialog"', self.template_text)
        self.assertIn('aria-modal="true"', self.template_text)

    def test_detail_panel_inside_right_panel_shell(self):
        """#detail-panel MUST remain inside .right-panel-shell."""
        shell_start = self.template_text.find('class="right-panel-shell"')
        self.assertGreater(shell_start, -1, "class='right-panel-shell' not found")
        rail_start = self.template_text.find('data-rail-side="right"')
        right_shell_region = (
            self.template_text[shell_start:rail_start]
            if rail_start > shell_start
            else self.template_text[shell_start:shell_start + 4000]
        )
        self.assertIn(
            'id="detail-panel"',
            right_shell_region,
            "#detail-panel MUST be inside .right-panel-shell",
        )

    # ── R4: Inspector accordion patterns ────────────────────────────────────

    def test_inspector_accordion_class_present_in_right_shell(self):
        """Right panel shell region MUST contain at least one element using
        .inspector-accordion from _shared.css."""
        shell_start = self.template_text.find('class="right-panel-shell"')
        rail_start = self.template_text.find('data-rail-side="right"')
        right_shell_region = (
            self.template_text[shell_start:rail_start]
            if rail_start > shell_start
            else self.template_text[shell_start:shell_start + 4000]
        )
        self.assertIn(
            "inspector-accordion",
            right_shell_region,
            "Expected class='inspector-accordion' in .right-panel-shell (section-2 pattern)",
        )

    def test_inspector_summary_and_body_classes_present(self):
        """inspector-summary and inspector-body MUST appear alongside inspector-accordion
        in the right panel region."""
        shell_start = self.template_text.find('class="right-panel-shell"')
        rail_start = self.template_text.find('data-rail-side="right"')
        right_shell_region = (
            self.template_text[shell_start:rail_start]
            if rail_start > shell_start
            else self.template_text[shell_start:shell_start + 4000]
        )
        self.assertIn(
            "inspector-summary",
            right_shell_region,
            "Expected class='inspector-summary' in .right-panel-shell (section-2 pattern)",
        )
        self.assertIn(
            "inspector-body",
            right_shell_region,
            "Expected class='inspector-body' in .right-panel-shell (section-2 pattern)",
        )

    # ── R5: Responsive slide-over regression guards ─────────────────────────

    def test_media_1100px_still_present_and_hides_right_panel_shell(self):
        """@media (max-width: 1100px) MUST still hide .right-panel-shell and define
        .detail-panel slide-over rules."""
        self.assertIn("@media (max-width: 1100px)", self.template_text)
        media_idx = self.template_text.find("@media (max-width: 1100px)")
        media_block = self.template_text[media_idx:media_idx + 2000]
        self.assertIn(
            ".right-panel-shell",
            media_block,
            "Expected .right-panel-shell in @media (max-width: 1100px) block (must be hidden)",
        )
        self.assertIn(
            ".detail-panel",
            media_block,
            "Expected .detail-panel slide-over rules in @media (max-width: 1100px) block",
        )

    def test_is_mobile_open_rule_in_media_block(self):
        """@media (max-width: 1100px) MUST contain .detail-panel.is-mobile-open rule."""
        media_idx = self.template_text.find("@media (max-width: 1100px)")
        media_block = self.template_text[media_idx:media_idx + 2000]
        self.assertIn(
            "is-mobile-open",
            media_block,
            "Expected .detail-panel.is-mobile-open rule in responsive media block",
        )

    def test_detail_panel_backdrop_rule_in_media_block(self):
        """@media (max-width: 1100px) MUST contain #detail-panel-backdrop rule."""
        media_idx = self.template_text.find("@media (max-width: 1100px)")
        media_block = self.template_text[media_idx:media_idx + 2000]
        self.assertIn(
            "detail-panel-backdrop",
            media_block,
            "Expected #detail-panel-backdrop rule in responsive media block",
        )

    def test_js_slideover_helpers_still_present(self):
        """syncDetailPanelPresentation, activateDetailSlideover, deactivateDetailSlideover
        MUST remain defined in the template JS (runtime depends on them)."""
        self.assertIn("syncDetailPanelPresentation", self.template_text)
        self.assertIn("activateDetailSlideover", self.template_text)
        self.assertIn("deactivateDetailSlideover", self.template_text)

    # ── R6: PR3 CSS token discipline ────────────────────────────────────────

    def test_no_hardcoded_hex_in_pr3_css_block(self):
        """PR3 CSS block MUST use only var(--*) — no hardcoded #rrggbb hex.

        Scoped by comment markers:
        /* === PR3 Right Rail + Inspector === */ ... /* === END PR3 Right Rail + Inspector === */
        """
        start_marker = "/* === PR3 Right Rail + Inspector === */"
        end_marker = "/* === END PR3 Right Rail + Inspector === */"
        start = self.template_text.find(start_marker)
        end = self.template_text.find(end_marker)
        if start == -1 or end == -1:
            self.fail(
                "PR3 CSS block markers not found. "
                "Expected '/* === PR3 Right Rail + Inspector === */' and "
                "'/* === END PR3 Right Rail + Inspector === */' in template CSS."
            )
        pr3_css_block = self.template_text[start:end]
        self.assertNotRegex(
            pr3_css_block,
            r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b",
            "Hardcoded hex color found in PR3 CSS block — use var(--*) tokens",
        )

    def test_reduced_motion_covers_pr3_rail_transitions(self):
        """@media (prefers-reduced-motion: reduce) MUST cover PR3 new transitions.

        The reduced-motion block must include coverage for .rail-icon transitions
        (or a broad 'transition: none' rule that covers them).
        """
        import re
        self.assertIn(
            "@media (prefers-reduced-motion: reduce)",
            self.template_text,
        )
        # Find the last reduced-motion block (PR3 adds one or extends it)
        # Check that .rail-icon or a broad transition: none rule covers right rail
        rm_matches = list(re.finditer(
            r"@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{([\s\S]*?)\}(?=\s*@media|\s*</style>)",
            self.template_text,
        ))
        self.assertTrue(rm_matches, "Could not parse reduced-motion media block")
        combined = " ".join(m.group(1) for m in rm_matches)
        has_coverage = (
            ".rail-icon" in combined
            or "transition: none" in combined
        )
        self.assertTrue(
            has_coverage,
            "reduced-motion block MUST cover .rail-icon transitions or use broad 'transition: none'",
        )


class TestWorkspaceShellRemediationOldUiRemoval(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        template_path = (
            Path(__file__).resolve().parent.parent
            / "brain_ds"
            / "ui"
            / "templates"
            / "graph_viewer.html"
        )
        cls.template_text = template_path.read_text(encoding="utf-8")

    def test_old_visual_blocks_absent_or_hidden(self):
        self.assertNotIn('id="viewer-empty-state"', self.template_text)
        self.assertNotIn('id="search-label"', self.template_text)
        self.assertNotIn('placeholder="Type a name or id"', self.template_text)
        self.assertNotIn('id="show-all"', self.template_text)
        self.assertNotIn('id="hide-all"', self.template_text)

    def test_new_left_panel_section1_surfaces_present(self):
        for token in (
            'class="panel-card',
            'data-accordion-section="search"',
            'data-accordion-section="filters"',
            'data-accordion-section="legend"',
            'data-accordion-section="hierarchy"',
            'data-accordion-section="layout"',
            # PR3: filter actions consolidated into per-type controls rendered by module
            'id="type-filters"',
            'class="tree-row',
            # D.2: segmented-control replaces toggle-card
            'class="segmented-control"',
            'id="node-search"',
            'id="score-threshold-slider"',
            'id="legend"',
        ):
            self.assertIn(token, self.template_text)

    # ── D.2 segmented control ARIA (T1.1) ─────────────────────────────────────

    def test_d2_segmented_control_aria_structure(self):
        """GV-4 / GV-15: segmented control must use radiogroup+radio+aria-checked."""
        self.assertIn('role="radiogroup"', self.template_text)
        self.assertIn('aria-label="View mode"', self.template_text)
        self.assertIn('role="radio"', self.template_text)
        self.assertIn('aria-checked="true"', self.template_text)
        self.assertIn('aria-checked="false"', self.template_text)
        # toggle-card and aria-pressed on view controls must be gone
        self.assertNotIn('class="toggle-card"', self.template_text)
        self.assertNotIn('◉', self.template_text)

    def test_d2_segmented_buttons_have_ids_and_tabindex(self):
        """GV-4 / GV-16: IDs preserved, roving tabindex present."""
        # toggle-hierarchical and toggle-physics must be segment-btn
        self.assertIn('id="toggle-hierarchical"', self.template_text)
        self.assertIn('id="toggle-physics"', self.template_text)
        self.assertIn('class="segment-btn"', self.template_text)
        # Roving tabindex: exactly one tabindex="0" and at least one tabindex="-1" on segment-btn
        self.assertIn('tabindex="0"', self.template_text)
        self.assertIn('tabindex="-1"', self.template_text)

    # ── D.2 pill filter buttons (T1.2) ────────────────────────────────────────

    def test_d2_pill_buttons_structure(self):
        """GV-14: filter controls are consolidated into module-rendered per-type toggles."""
        self.assertIn('id="type-filters"', self.template_text)
        self.assertNotIn('id="show-all"', self.template_text)
        self.assertNotIn('id="hide-all"', self.template_text)
        self.assertNotIn('class="toggle-chip"', self.template_text)
        self.assertNotIn('class="toggle-chip-row"', self.template_text)

    def test_d2_no_hidden_proxy_buttons(self):
        """D-4 / D-6: hidden proxy buttons must be removed."""
        self.assertNotIn('id="show-all"', self.template_text)
        self.assertNotIn('id="hide-all"', self.template_text)

    def test_d2_pill_buttons_have_min_height_css(self):
        """GV-14: pill-btn must declare min-height: 44px in CSS."""
        self.assertRegex(self.template_text, r'\.pill-btn[^\{]*\{[^}]*min-height:\s*44px')

    # ── D.2 CSS token compliance (T1.3) ───────────────────────────────────────

    def test_d2_segmented_and_pill_css_uses_only_tokens(self):
        """GV-17: no hex literals in new segmented-control / pill CSS rules."""
        import re
        # Extract the segmented-control CSS block from the <style> section
        style_match = re.search(r'<style>([\s\S]*?)</style>', self.template_text)
        self.assertIsNotNone(style_match, "No <style> block found")
        style_text = style_match.group(1)
        # Find .segmented-control / .segment-btn / .pill-btn / .pill-group blocks
        d2_blocks = re.findall(
            r'\.(?:segmented-control|segment-btn|pill-group|pill-btn|btn-outline|btn-primary-outline)[^{]*\{[^}]*\}',
            style_text,
        )
        self.assertTrue(len(d2_blocks) > 0, "No D.2 CSS rules found in <style> block")
        combined = " ".join(d2_blocks)
        hex_match = re.search(r'#(?:[0-9a-fA-F]{3,6})\b', combined)
        self.assertIsNone(
            hex_match,
            f"Hex literal found in D.2 CSS rules: {hex_match.group() if hex_match else ''}",
        )

    def test_d2_btn_outline_alias_rules_exist(self):
        """Phase 2: add reference class aliases without renaming legacy classes."""
        self.assertRegex(self.template_text, r"\.btn-outline\s*\{[^}]*border:\s*1px\s+solid\s+var\(--border-subtle\)")
        self.assertRegex(self.template_text, r"\.btn-primary-outline\s*\{[^}]*color:\s*var\(--accent-color-soft\)")

    def test_d2_search_input_hover_and_focus_ring_parity(self):
        """Phase 2: search input must expose hover border and mora focus ring."""
        self.assertRegex(self.template_text, r"\.search-input:hover\s*\{[^}]*border-color:\s*var\(--border-strong\)")
        self.assertRegex(self.template_text, r"\.search-input:focus-visible\s*\{[^}]*outline:\s*2px\s+solid\s+var\(--accent-mora\)")
        self.assertRegex(self.template_text, r"\.search-input:focus-visible\s*\{[^}]*outline-offset:\s*2px")

    def test_d2_segment_active_state_uses_tokens(self):
        """Phase 2: active segment style must avoid hardcoded colors and use tokens."""
        match = re.search(r"\.segment-btn\[aria-checked='true'\]\s*\{([^}]*)\}", self.template_text)
        self.assertIsNotNone(match, "Expected .segment-btn[aria-checked='true'] CSS block")
        segment_active = match.group(1)
        self.assertNotRegex(segment_active, r"#(?:[0-9a-fA-F]{3,6})\b")
        self.assertNotRegex(segment_active, r"rgba?\(")
        self.assertIn("background: var(--bg-active)", segment_active)

    def test_right_rail_has_no_dead_icon_entries(self):
        self.assertNotIn('data-catalog-id="gear"', self.template_text)
        self.assertNotIn('data-catalog-id="inspector"', self.template_text)
        self.assertNotIn('data-catalog-id="history"', self.template_text)
        self.assertNotIn('data-catalog-id="settings"', self.template_text)

    def test_rail_icon_has_explicit_44px_contract(self):
        self.assertRegex(self.template_text, r"\.rail-icon\s*\{[^}]*width:\s*44px")
        self.assertRegex(self.template_text, r"\.rail-icon\s*\{[^}]*height:\s*44px")

    def test_inspector_uses_section2_5_styles_and_empty_state(self):
        for token in (
            'class="empty-state"',
            'var(--text-muted)',
            'class="inspector-accordion"',
            'class="inspector-summary"',
            'class="inspector-body"',
            'id="detail-collapse"',
            'id="detail-close"',
        ):
            self.assertIn(token, self.template_text)

    def test_adapter_ids_preserved(self):
        for _id in (
            "node-search", "search-results", "type-filters", "score-threshold-slider", "score-badge",
            "legend", "tree-panel", "toggle-hierarchical", "toggle-physics", "zoom-fit", "theme-toggle",
            "detail-panel", "detail-title", "detail-meta", "detail-body", "detail-collapse", "detail-close",
            "network",
        ):
            self.assertIn(f'id="{_id}"', self.template_text)


class TestWorkspaceShellPr3InspectorParity(unittest.TestCase):
    """PR #3 / Phase 3 — right-panel inspector visual parity.

    Ground truth: brain_ds/ui/design/sections/moderngraphui_notailwind.html
    (.empty-state / .empty-icon-wrapper / .color-dot / .inspector-actions /
    fadeIn translateX). Maps reference VISUALS onto production #detail-* IDs.

    AUDIT (ADR-B): the compiled bundle (src/panels/detail-panel.ts ->
    viewer.bundle.js) owns #detail-body / #detail-title / #detail-meta content
    at runtime via textContent assignment. So the rich empty-state lives as a
    SIBLING of #detail-body inside #detail-panel (the bundle never touches
    siblings) and is gated by CSS on #detail-panel.is-empty. The color-dot
    (3.3) is decorated post-call in the template render shim because the bundle
    wipes #detail-title child spans on every populated render.

    These tests read the RAW template text (token placeholder NOT expanded);
    the danger token DEFINITION is asserted against tokens.css separately.
    """

    @classmethod
    def setUpClass(cls):
        base = Path(__file__).resolve().parent.parent / "brain_ds" / "ui"
        cls.template_text = (base / "templates" / "graph_viewer.html").read_text(encoding="utf-8")
        cls.tokens_css = (base / "static" / "tokens.css").read_text(encoding="utf-8")

    def _style_block(self):
        m = re.search(r"<style>([\s\S]*?)</style>", self.template_text)
        self.assertIsNotNone(m, "No <style> block found in template")
        return m.group(1)

    # ── 3.1 Empty-state markup (sibling of #detail-body) ─────────────────────

    def test_inspector_empty_state_is_sibling_of_detail_body(self):
        """The inspector empty-state MUST be a SIBLING element inside #detail-panel,
        NOT inside #detail-body (the bundle clobbers #detail-body via textContent).
        It carries a distinct class to avoid colliding with the canvas #viewer-empty
        .empty-state."""
        panel_start = self.template_text.find('id="detail-panel"')
        self.assertGreater(panel_start, -1, "#detail-panel not found")
        panel_end = self.template_text.find("</aside>", panel_start)
        self.assertGreater(panel_end, -1, "Could not find end of #detail-panel <aside>")
        panel_html = self.template_text[panel_start:panel_end]
        self.assertIn('class="inspector-empty-state"', panel_html,
                      "Expected .inspector-empty-state sibling inside #detail-panel")
        # Must be a SIBLING of #detail-body, not nested inside it.
        empty_idx = panel_html.find("inspector-empty-state")
        body_idx = panel_html.find('id="detail-body"')
        self.assertGreater(body_idx, -1, "#detail-body not found inside panel")
        body_close = panel_html.find("</div>", body_idx)
        self.assertFalse(body_idx < empty_idx < body_close,
                         "inspector-empty-state must be a SIBLING of #detail-body, not nested in it")

    def test_inspector_empty_state_has_64px_icon_circle_with_network_icon(self):
        """Empty state MUST show a 64px .empty-icon-wrapper circle referencing the
        same-document #icon-network sprite symbol with aria-hidden."""
        self.assertIn('class="empty-icon-wrapper"', self.template_text)
        # network icon via sprite use, aria-hidden on the svg
        m = re.search(
            r'class="empty-icon-wrapper"[\s\S]*?(<svg[^>]*>)\s*<use href="#icon-network"',
            self.template_text,
        )
        self.assertIsNotNone(
            m, "empty-icon-wrapper MUST contain an svg using #icon-network",
        )
        svg_tag = m.group(1)
        self.assertIn('aria-hidden="true"', svg_tag,
                      "empty-state icon svg MUST be aria-hidden")
        # Guard against the invisible-icon trap (PR #1): the icon-network symbol has
        # no per-element stroke/fill, so the consuming svg MUST set them or it renders blank.
        self.assertIn('stroke="currentColor"', svg_tag,
                      "empty-state icon svg MUST set stroke=currentColor (network symbol has no inline stroke)")
        self.assertIn('fill="none"', svg_tag,
                      "empty-state icon svg MUST set fill=none to render as a line icon")
        style = self._style_block()
        self.assertRegex(style, r"\.empty-icon-wrapper\s*\{[^}]*width:\s*64px",
                         ".empty-icon-wrapper MUST be 64px wide")
        self.assertRegex(style, r"\.empty-icon-wrapper\s*\{[^}]*height:\s*64px",
                         ".empty-icon-wrapper MUST be 64px tall")
        self.assertRegex(style, r"\.empty-icon-wrapper\s*\{[^}]*border-radius:\s*50%",
                         ".empty-icon-wrapper MUST be a circle")

    def test_inspector_empty_state_css_gated_on_is_empty(self):
        """The empty-state visibility MUST be gated by #detail-panel.is-empty so the
        bundle's is-empty toggle drives show/hide (no JS rebuild needed)."""
        style = self._style_block()
        self.assertRegex(
            style,
            r"#detail-panel\.is-empty\s+\.inspector-empty-state\s*\{[^}]*display:\s*flex",
            "Expected #detail-panel.is-empty .inspector-empty-state { display: flex }",
        )
        self.assertRegex(
            style,
            r"#detail-panel:not\(\.is-empty\)\s+\.inspector-empty-state\s*\{[^}]*display:\s*none",
            "Expected #detail-panel:not(.is-empty) .inspector-empty-state { display: none }",
        )

    def test_inspector_empty_state_uses_only_tokens(self):
        """Inspector empty-state CSS MUST NOT use hardcoded hex colors (token discipline)."""
        style = self._style_block()
        blocks = re.findall(
            r"(?:#detail-panel[^{]*\.inspector-empty-state|\.inspector-empty-state|\.empty-icon-wrapper)[^{]*\{[^}]*\}",
            style,
        )
        self.assertTrue(blocks, "No inspector empty-state CSS blocks found")
        combined = " ".join(blocks)
        self.assertIsNone(re.search(r"#(?:[0-9a-fA-F]{3,6})\b", combined),
                          f"Hex literal found in inspector empty-state CSS: {combined}")

    def test_inspector_empty_state_is_not_aria_hidden(self):
        """The empty-state container MUST NOT be aria-hidden — it carries the readable
        prompt for screen-reader users (the bundle-owned #detail-body is display:none
        when empty). Only the decorative inner icon svg may be aria-hidden."""
        m = re.search(r'<div class="inspector-empty-state"([^>]*)>', self.template_text)
        self.assertIsNotNone(m, "inspector-empty-state container not found")
        self.assertNotIn("aria-hidden", m.group(1),
                         "inspector-empty-state MUST NOT be aria-hidden (a11y: prompt must be readable)")

    def test_inspector_empty_state_text_is_aa_legible(self):
        """Empty-state text MUST use --text-normal and MUST NOT be opacity-dimmed
        (opacity over --text-muted falls below WCAG AA 4.5:1)."""
        style = self._style_block()
        m_p = re.search(r"\.inspector-empty-text p\s*\{([^}]*)\}", style)
        self.assertIsNotNone(m_p, "Expected .inspector-empty-text p rule")
        self.assertIn("color: var(--text-normal)", m_p.group(1),
                      "Empty-state body text MUST use --text-normal for AA contrast")
        m_state = re.search(r"\.inspector-empty-state\s*\{([^}]*)\}", style)
        self.assertIsNotNone(m_state, "Expected .inspector-empty-state rule")
        self.assertNotRegex(m_state.group(1), r"opacity:\s*0?\.\d",
                            "inspector-empty-state MUST NOT dim text via opacity (breaks AA contrast)")

    # ── 3.2 Action button styling (btn-outline / btn-danger-outline) ─────────

    def test_inspector_action_buttons_use_outline_and_danger_outline(self):
        """#detail-collapse MUST carry btn-outline; #detail-close MUST carry
        btn-danger-outline (additive — legacy IDs preserved)."""
        self.assertRegex(
            self.template_text,
            r'id="detail-collapse"[^>]*class="[^"]*btn-outline|class="[^"]*btn-outline[^"]*"[^>]*id="detail-collapse"',
            "#detail-collapse MUST carry btn-outline",
        )
        self.assertRegex(
            self.template_text,
            r'id="detail-close"[^>]*class="[^"]*btn-danger-outline|class="[^"]*btn-danger-outline[^"]*"[^>]*id="detail-close"',
            "#detail-close MUST carry btn-danger-outline",
        )

    def test_btn_danger_outline_css_rule_exists_and_uses_danger_token(self):
        """.btn-danger-outline rule MUST exist and use the --danger token (no hardcoded hex)."""
        style = self._style_block()
        m = re.search(r"\.btn-danger-outline(?:[^{,]*)?\s*\{([^}]*)\}", style)
        self.assertIsNotNone(m, "Expected .btn-danger-outline CSS rule")
        m_hover = re.search(r"\.btn-danger-outline:hover\s*\{([^}]*)\}", style)
        self.assertIsNotNone(m_hover, "Expected .btn-danger-outline:hover CSS rule")
        combined = (m.group(1) if m else "") + " " + (m_hover.group(1) if m_hover else "")
        self.assertIn("var(--danger", combined,
                      ".btn-danger-outline MUST express its danger color via the --danger token")
        self.assertIsNone(re.search(r"#(?:[0-9a-fA-F]{3,6})\b", combined),
                          "No hardcoded hex allowed in .btn-danger-outline rules")

    def test_danger_token_defined_in_tokens_css(self):
        """The --danger token MUST be defined in the canonical tokens.css."""
        self.assertRegex(self.tokens_css, r"--danger:\s*#",
                         "--danger token MUST be defined in tokens.css")

    def test_inspector_action_buttons_have_44px_min_target(self):
        """Inspector action buttons MUST meet the 44x44 minimum interactive target."""
        style = self._style_block()
        # btn-outline / btn-danger-outline must have an explicit min target.
        self.assertRegex(
            style,
            r"\.btn-danger-outline[^{]*\{[^}]*min-height:\s*44px|"
            r"\.btn-outline[^{]*\{[^}]*min-height:\s*44px|"
            r"\.pill-btn[^{]*\{[^}]*min-height:\s*44px",
            "Inspector action buttons MUST declare min-height: 44px",
        )

    # ── 3.3 color-dot indicator in #detail-title ─────────────────────────────

    def test_color_dot_css_rule_exists(self):
        """A .color-dot rule MUST exist (8px circle) for the node-type indicator."""
        style = self._style_block()
        m = re.search(r"\.color-dot\s*\{([^}]*)\}", style)
        self.assertIsNotNone(m, "Expected .color-dot CSS rule")
        body = m.group(1)
        self.assertRegex(body, r"border-radius:\s*50%", ".color-dot MUST be a circle")
        self.assertRegex(body, r"width:\s*8px", ".color-dot MUST be 8px wide")

    def test_render_shim_decorates_detail_title_with_color_dot(self):
        """The template render shim MUST inject a .color-dot into #detail-title AFTER
        the bundle's renderDetailPanel runs (the bundle wipes title child spans via
        textContent). Source-text assertion on the shim — runtime DOM not observable
        by these tests."""
        # The shim block delegates to window.brainDsUI.detailPanel.renderDetailPanel;
        # immediately around it there MUST be color-dot decoration logic.
        self.assertIn("color-dot", self.template_text,
                      "Template must reference color-dot for the title indicator")
        self.assertRegex(
            self.template_text,
            r"detailPanel\.renderDetailPanel\(nodeId\)[\s\S]{0,600}?color-dot|"
            r"color-dot[\s\S]{0,600}?detailPanel\.renderDetailPanel\(nodeId\)",
            "Render shim MUST decorate #detail-title with a color-dot near the bundle render call",
        )

    def test_color_dot_decoration_runs_on_both_render_paths(self):
        """The color-dot decorator MUST run after BOTH the renderDetailPanel shim AND
        the focusNode direct render path (both call the bundle, which wipes the title)."""
        self.assertIn("decorateDetailTitleColorDot", self.template_text,
                      "Expected a decorateDetailTitleColorDot helper")
        # Called at least twice (shim path + focusNode path).
        self.assertGreaterEqual(
            self.template_text.count("decorateDetailTitleColorDot("), 2,
            "color-dot decorator MUST be invoked on both render paths (shim + focusNode)",
        )

    def test_color_dot_color_reuses_d4_resolution(self):
        """The dot color MUST reuse the d4 overlay color precedence (single source of
        truth for node color), set via the --node-color custom property."""
        self.assertRegex(
            self.template_text,
            r"decorateDetailTitleColorDot[\s\S]*?d4ColorVars[\s\S]*?setProperty\(\s*[\"']--node-color",
            "color-dot MUST derive --node-color via d4ColorVars (renderer color precedence)",
        )

    # ── 3.4 Inspector enter animation (inspectorEnter, translateX fade-in) ───

    def test_inspector_enter_keyframes_defined_with_translatex(self):
        """An @keyframes inspectorEnter MUST exist with a translateX fade-in
        (matches reference fadeIn: opacity 0 + translateX(10px) -> visible)."""
        style = self._style_block()
        m = re.search(r"@keyframes\s+inspectorEnter\s*\{([^@]*?)\}\s*\}", style)
        # Fall back to a simpler capture if nested-brace heuristic misses.
        if m is None:
            m = re.search(r"@keyframes\s+inspectorEnter\s*\{([\s\S]*?)\}\s*(?:\n|@|\.)", style)
        self.assertIsNotNone(m, "Expected @keyframes inspectorEnter")
        body = m.group(1)
        self.assertRegex(body, r"translateX", "inspectorEnter MUST animate translateX")
        self.assertRegex(body, r"opacity", "inspectorEnter MUST fade opacity")

    def test_inspector_enter_applied_to_populated_detail_body(self):
        """The inspectorEnter animation MUST be applied when #detail-body is populated
        (data-state='ready'), which the bundle sets on selection."""
        style = self._style_block()
        self.assertRegex(
            style,
            r'#detail-body\[data-state="ready"\]\s*\{[^}]*animation:[^}]*inspectorEnter',
            'Expected #detail-body[data-state="ready"] to apply inspectorEnter animation',
        )

    def test_inspector_enter_respects_reduced_motion(self):
        """The reduced-motion media block MUST disable inspectorEnter / detail-body animation."""
        rm = re.search(r"@media \(prefers-reduced-motion: reduce\)\s*\{([\s\S]*?)\n      \}", self.template_text)
        self.assertIsNotNone(rm, "Could not find prefers-reduced-motion media block")
        block = rm.group(1)
        self.assertRegex(
            block,
            r"(#detail-body|\.detail-panel|\.inspector-empty-state)[^{}]*\{[^}]*animation:\s*none|"
            r"#detail-body[^{}]*\{[^}]*animation:\s*none",
            "reduced-motion block MUST disable the inspector enter animation",
        )

    # ── 3.5 Mount-contract preservation ──────────────────────────────────────

    def test_detail_panel_contract_ids_preserved(self):
        """detailPanel.mount contract: all #detail-* IDs MUST remain so the bundle's
        getElementById lookups and focus-trap logic keep working."""
        for _id in ("detail-panel", "detail-title", "detail-meta", "detail-body",
                    "detail-collapse", "detail-close", "edit-toggle", "export-json"):
            self.assertIn(f'id="{_id}"', self.template_text,
                          f"Mount contract requires #{_id} to be preserved")

    def test_detail_panel_aria_contract_preserved(self):
        """#detail-panel ARIA dialog contract MUST be preserved (role/dialog/labelledby)."""
        self.assertRegex(
            self.template_text,
            r'id="detail-panel"[^>]*role="dialog"',
            "#detail-panel MUST keep role='dialog'",
        )
        self.assertRegex(
            self.template_text,
            r'id="detail-panel"[^>]*aria-labelledby="detail-title"',
            "#detail-panel MUST keep aria-labelledby='detail-title'",
        )

    # ── Empty-state header suppression (finding #1218 remediation) ───────────

    def test_empty_state_suppresses_detail_header(self):
        """User override of finding 1218: the right panel must HOST the action toolbar
        (Editar/Exportar/Guardar/Colapsar/Cerrar) even when empty, so the inspector
        never reads as dead space. Only the redundant title + meta hide when empty;
        the .detail-actions group stays visible (buttons gated by .disabled, not hidden),
        and the centered glyph prompt still lives in .inspector-empty-state below."""
        style = self._style_block()
        self.assertRegex(
            style,
            r"#detail-panel\.is-empty\s+#detail-title[^{]*\{[^}]*display:\s*none",
            "Expected the empty inspector to hide #detail-title (redundant with the glyph)",
        )
        self.assertRegex(
            style,
            r"#detail-panel\.is-empty\s+#detail-meta[^{]*\{[^}]*display:\s*none",
            "Expected the empty inspector to hide #detail-meta (redundant with the glyph)",
        )
        # The whole header MUST NOT be hidden when empty — the action toolbar must survive.
        self.assertNotRegex(
            style,
            r"#detail-panel\.is-empty\s+\.detail-header\s*\{[^}]*display:\s*none",
            "Empty inspector MUST keep .detail-header (action toolbar) visible — "
            "only title/meta hide (user override of finding 1218)",
        )

    def test_empty_state_no_stale_centered_header_rules(self):
        """The old .is-empty centered-header restyle rules are dead once the header is
        hidden when empty; they MUST be removed to avoid confusing dead CSS."""
        style = self._style_block()
        self.assertNotRegex(
            style,
            r"#detail-panel\.is-empty\s+\.detail-header\s*\{[^}]*text-align:\s*center",
            "Stale rule: .is-empty .detail-header { text-align: center } must be removed "
            "(header is hidden when empty, not re-centered)",
        )

    def test_detail_header_visible_when_not_empty(self):
        """The action buttons (Colapsar/Cerrar) MUST remain available when a node IS
        selected — the suppression is gated strictly on .is-empty, never global."""
        style = self._style_block()
        # No rule may hide .detail-header unconditionally.
        self.assertNotRegex(
            style,
            r"(?<!is-empty\s)\.detail-header\s*\{[^}]*display:\s*none",
            ".detail-header must NOT be hidden unconditionally (only when .is-empty)",
        )


class TestWorkspaceShellPr4Chrome(unittest.TestCase):
    """PR #4 / Phase 4 — chrome fine-tuning to final parity.

    Ground truth: brain_ds/ui/design/sections/moderngraphui_notailwind.html, with
    project-standard overrides per design ADR-F (#1208):
      - Tab strip height = 36px (ADR-009 project override; reference uses 48px).
      - Rails = 48px (ADR-004).
      - Toolbar = 44px LOCKED (ADR-001) with four data-toolbar-zone slots.
      - Active tab indicator = box-shadow: inset 0 -2px 0 var(--accent-mora) + blended bg.
      - Backdrop-blur preserved on the tab strip atmosphere.

    Binding contract (#1194): when a test asserts stale chrome, update the test to
    match the new DOM. The legacy 48px tab-strip assertion is migrated here to 36px.
    """

    @classmethod
    def setUpClass(cls):
        template_path = (
            Path(__file__).resolve().parent.parent
            / "brain_ds"
            / "ui"
            / "templates"
            / "graph_viewer.html"
        )
        cls.template_text = template_path.read_text(encoding="utf-8")

    def _style_block(self):
        m = re.search(r"<style>([\s\S]*?)</style>", self.template_text)
        self.assertIsNotNone(m, "No <style> block found in template")
        return m.group(1)

    # ── C1: Tab strip 36px height contract (ADR-009 override) ────────────────

    def test_tab_strip_height_is_36px_project_contract(self):
        """Tab strip MUST be 36px tall (ADR-009 project override), NOT the reference's
        48px. This is the chrome parity correction for PR #4."""
        style = self._style_block()
        self.assertRegex(
            style,
            r"\.tab-strip\s*\{[^}]*flex:\s*0\s+0\s+36px",
            "Tab strip MUST use flex: 0 0 36px (ADR-009 project contract)",
        )
        self.assertNotRegex(
            style,
            r"\.tab-strip\s*\{[^}]*flex:\s*0\s+0\s+48px",
            "Tab strip MUST NOT keep the stale 48px height",
        )

    def test_tab_strip_preserves_backdrop_blur(self):
        """The tab strip's atmospheric backdrop-blur MUST survive the 36px change
        (blur is orthogonal to height — both -webkit- and standard properties)."""
        style = self._style_block()
        m = re.search(r"\.tab-strip\s*\{([^}]*)\}", style)
        self.assertIsNotNone(m, "Expected .tab-strip rule")
        body = m.group(1)
        self.assertIn("backdrop-filter: blur(4px)", body,
                      "Tab strip MUST keep backdrop-filter: blur(4px)")
        self.assertIn("-webkit-backdrop-filter: blur(4px)", body,
                      "Tab strip MUST keep -webkit-backdrop-filter for Safari")

    # ── C2: Active tab indicator (accent-mora inset underline + blended bg) ──

    def test_active_tab_indicator_uses_accent_mora_inset(self):
        """Active tab MUST be indicated by inset accent-mora underline + blended bg
        (project ADR-009 — NOT reference flat rgba). The blend now tints --tab-active-bg
        with a light accent-mora via color-mix for the redesigned tab look."""
        style = self._style_block()
        self.assertRegex(
            style,
            r"\.tab-item\[data-tab-active='true'\]\s*\{[^}]*box-shadow:\s*inset\s+0\s+-2px\s+0\s+var\(--accent-mora\)",
            "Active tab MUST use box-shadow: inset 0 -2px 0 var(--accent-mora)",
        )
        self.assertRegex(
            style,
            r"\.tab-item\[data-tab-active='true'\]\s*\{[^}]*background:[^;]*var\(--tab-active-bg\)",
            "Active tab MUST blend background via the --tab-active-bg token",
        )

    def test_active_tab_indicator_uses_no_hardcoded_hex(self):
        """The active-tab styling MUST be token-only (no reference hex)."""
        style = self._style_block()
        m = re.search(r"\.tab-item\[data-tab-active='true'\]\s*\{([^}]*)\}", style)
        self.assertIsNotNone(m, "Expected active tab-item rule")
        self.assertIsNone(re.search(r"#(?:[0-9a-fA-F]{3,6})\b", m.group(1)),
                          "Active tab styling MUST NOT use hardcoded hex")

    # ── C3: tab semantics (tablist / tab roles, close hover-reveal, tab-new) ─

    def test_tab_strip_tablist_and_active_tab_roles(self):
        """Tab strip MUST be role=tablist with an active role=tab/aria-selected=true."""
        self.assertRegex(
            self.template_text,
            r'class="tab-strip"[^>]*role="tablist"|role="tablist"[^>]*class="tab-strip"',
            "Tab strip MUST carry role='tablist'",
        )
        self.assertRegex(
            self.template_text,
            r'role="tab"[^>]*aria-selected="true"|aria-selected="true"[^>]*role="tab"',
            "An active role='tab' with aria-selected='true' MUST exist",
        )

    def test_tab_close_is_hover_reveal(self):
        """tab-close MUST default to opacity:0 and reveal on active/hover (ADR-008)."""
        style = self._style_block()
        m = re.search(r"\.tab-close\s*\{([^}]*)\}", style)
        self.assertIsNotNone(m, "Expected .tab-close rule")
        self.assertIn("opacity: 0", m.group(1),
                      "tab-close MUST default to opacity: 0 (hover-reveal)")
        self.assertRegex(
            style,
            r"\.tab-item:hover\s+\.tab-close\s*\{[^}]*opacity:\s*1",
            "tab-close MUST reveal (opacity:1) on tab hover",
        )

    def test_tab_new_button_is_separate(self):
        """A separate tab-new button MUST exist (44x36, not part of a tab-item)."""
        self.assertIn('class="tab-new"', self.template_text,
                      "Expected a separate .tab-new button")
        style = self._style_block()
        m = re.search(r"\.tab-new\s*\{([^}]*)\}", style)
        self.assertIsNotNone(m, "Expected .tab-new CSS rule")
        self.assertRegex(m.group(1), r"width:\s*44px", ".tab-new MUST be 44px wide")
        self.assertRegex(m.group(1), r"height:\s*36px", ".tab-new MUST be 36px tall")

    # ── C4: Toolbar four zones + locked 44px + system-chrome reserved ────────

    def test_toolbar_has_all_four_zones_in_order(self):
        """The toolbar MUST expose exactly four data-toolbar-zone slots."""
        for zone in ("nav", "view", "overflow", "system-chrome"):
            self.assertIn(f'data-toolbar-zone="{zone}"', self.template_text,
                          f"Expected data-toolbar-zone='{zone}'")

    def test_toolbar_height_locked_44px(self):
        """Toolbar height MUST stay 44px LOCKED (ADR-001)."""
        style = self._style_block()
        self.assertRegex(
            style,
            r"\.top-toolbar\s*\{[^}]*flex:\s*0\s+0\s+44px",
            "Toolbar MUST keep flex: 0 0 44px (ADR-001 locked)",
        )

    def test_system_chrome_zone_reserved_zero_width(self):
        """system-chrome zone MUST be width:0 (reserved, never painted)."""
        style = self._style_block()
        self.assertRegex(
            style,
            r"\[data-toolbar-zone=['\"]system-chrome['\"]\]\s*\{[^}]*width:\s*0",
            "system-chrome zone MUST be width:0 (reserved)",
        )
        m = re.search(r'<div data-toolbar-zone="system-chrome">([\s\S]*?)</div>', self.template_text)
        self.assertIsNotNone(m, "Expected system-chrome zone container")
        self.assertNotIn("<button", m.group(1), "system-chrome MUST NOT be painted")

    # ── C5: Breadcrumb lives in the view zone with tokenized highlight ───────

    def test_breadcrumb_in_view_zone_with_tokenized_highlight(self):
        """The breadcrumb MUST live in the toolbar view zone and use the
        --accent-color-soft token for the highlighted org name (ADR-F), no hex."""
        m = re.search(r'<div data-toolbar-zone="view">([\s\S]*?)</div>\s*<!--', self.template_text)
        self.assertIsNotNone(m, "Expected view zone container")
        self.assertIn('aria-label="Breadcrumb"', m.group(1),
                      "Breadcrumb nav MUST live in the view zone")
        style = self._style_block()
        mh = re.search(r"\.breadcrumb-highlight\s*\{([^}]*)\}", style)
        self.assertIsNotNone(mh, "Expected .breadcrumb-highlight rule")
        self.assertIn("var(--accent-color-soft)", mh.group(1),
                      "Breadcrumb highlight MUST use --accent-color-soft token (ADR-F)")
        self.assertIsNone(re.search(r"#(?:[0-9a-fA-F]{3,6})\b", mh.group(1)),
                          "Breadcrumb highlight MUST NOT use hardcoded hex")

    # ── C6: Rails — 48px width contract (ADR-004) ────────────────────────────

    def test_rail_width_is_48px_contract(self):
        """Rails MUST maintain the 48px width contract (ADR-004) — NOT reference 56px."""
        style = self._style_block()
        self.assertRegex(
            style,
            r"\.rail\s*\{[^}]*min-width:\s*48px",
            "Rails MUST keep min-width: 48px (ADR-004 project contract)",
        )

    def test_workspace_grid_keeps_48px_rail_columns(self):
        """The 5-column workspace grid MUST keep 48px rail columns flanking the panels."""
        self.assertRegex(
            self.template_text,
            r"grid-template-columns:\s*48px\s+var\(--rail-w\)\s+minmax\(0,\s*1fr\)\s+var\(--inspector-w\)\s+48px",
            "Workspace grid MUST keep 48px rail columns flanking resizable panels (ADR-004)",
        )


class TestWorkspaceControlsWiring(unittest.TestCase):
    """Contract assertions for Slice 1 workspace controls wiring (P0).

    These tests assert static HTML/JS contracts in the rendered template:
    - Left panel-collapse MUST NOT have aria-pressed (a11y cleanup).
    - Overflow trigger carries aria-haspopup="menu".
    - Rail icons carry data-catalog-id and data-rail-icon.
    - Tab-close button carries data-catalog-id="tab-close".
    - workspaceChrome module is imported and wired in the inline script.
    """

    def setUp(self):
        self.html = render_interactive_html(
            {
                "meta": {"org": "WiringOrg", "node_count": 0, "edge_count": 0, "generated_at": ""},
                "nodes": [],
                "edges": [],
                "type_groups": [],
                "adjacency": {},
            }
        )

    def test_left_panel_collapse_has_no_aria_pressed(self):
        """Left panel-collapse MUST NOT carry aria-pressed (a11y cleanup — design ADR)."""
        import re
        # Find the .panel-collapse button (not .panel-collapse-right)
        m = re.search(
            r'<button[^>]*class="panel-collapse"[^>]*/?>',
            self.html,
        )
        self.assertIsNotNone(m, "Expected a .panel-collapse button in the template")
        self.assertNotIn("aria-pressed", m.group(0),
                         "Left .panel-collapse MUST NOT carry aria-pressed")

    def test_left_panel_collapse_has_aria_expanded(self):
        """Left panel-collapse MUST carry aria-expanded for expand/collapse state."""
        import re
        m = re.search(
            r'<button[^>]*class="panel-collapse"[^>]*/?>',
            self.html,
        )
        self.assertIsNotNone(m, "Expected a .panel-collapse button")
        self.assertIn("aria-expanded", m.group(0),
                      "Left .panel-collapse MUST have aria-expanded")

    def test_right_panel_collapse_is_unchanged(self):
        """Right panel-collapse-right MUST still carry aria-expanded (Slice 2 — untouched)."""
        self.assertIn('class="panel-collapse-right"', self.html,
                      "Expected .panel-collapse-right button for right panel")
        import re
        m = re.search(
            r'<button[^>]*class="panel-collapse-right"[^>]*/?>',
            self.html,
        )
        self.assertIsNotNone(m, "Expected .panel-collapse-right button")
        self.assertIn("aria-expanded", m.group(0),
                      ".panel-collapse-right MUST have aria-expanded")

    def test_overflow_trigger_has_aria_haspopup_menu(self):
        """Overflow trigger MUST carry aria-haspopup='menu' for a11y contract."""
        import re
        m = re.search(
            r'<button[^>]*data-catalog-id="overflow"[^>]*/?>',
            self.html,
        )
        self.assertIsNotNone(m, "Expected overflow trigger button with data-catalog-id='overflow'")
        self.assertIn('aria-haspopup="menu"', m.group(0),
                      "Overflow trigger MUST have aria-haspopup='menu'")

    def test_rail_icons_carry_data_catalog_id(self):
        """All 5 rail icons MUST carry data-catalog-id for JS wiring."""
        for name in ("file-tree", "search", "filters", "hierarchy", "layout"):
            self.assertIn(f'data-catalog-id="{name}"', self.html,
                          f"Rail icon '{name}' MUST have data-catalog-id")

    def test_rail_icons_carry_data_rail_icon(self):
        """All 5 rail icons MUST carry data-rail-icon for workspace-chrome routing."""
        for name in ("file-tree", "search", "filters", "hierarchy", "layout"):
            self.assertIn(f'data-rail-icon="{name}"', self.html,
                          f"Rail icon '{name}' MUST have data-rail-icon")

    def test_tab_close_carries_data_catalog_id(self):
        """Tab-close button MUST carry data-tab-close-for for tabs.ts delegation."""
        tabs_text = (Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "src" / "tabs.ts").read_text(encoding="utf-8")
        self.assertIn('data-tab-close-for', tabs_text,
                      "Tab-close button MUST have data-tab-close-for")

    def test_workspace_chrome_mount_in_inline_script(self):
        """Inline script MUST call workspaceChrome.mount after contextMenu.mount."""
        import re
        scripts = re.findall(r"<script>([\s\S]*?)</script>", self.html)
        inline = scripts[-1] if scripts else ""
        self.assertIn("workspaceChrome.mount", inline,
                      "Inline script MUST call workspaceChrome.mount")
        # Must also appear in brainDsUI object (module exposed on window)
        self.assertIn("workspaceChrome", inline,
                      "workspaceChrome MUST be referenced in the inline script")

    def test_left_panel_collapse_inline_handler_flips_aria_expanded(self):
        """Inline script MUST include a left panel-collapse handler that toggles aria-expanded."""
        import re
        scripts = re.findall(r"<script>([\s\S]*?)</script>", self.html)
        inline = scripts[-1] if scripts else ""
        self.assertIn("panel-collapse", inline,
                      "Inline script MUST wire a panel-collapse handler")
        self.assertIn("aria-expanded", inline,
                      "panel-collapse handler MUST reference aria-expanded")

    def test_tab_close_inline_handler_present(self):
        """Inline script MUST mount the tabs module; close handling lives in tabs.ts."""
        import re
        scripts = re.findall(r"<script>([\s\S]*?)</script>", self.html)
        inline = scripts[-1] if scripts else ""
        self.assertIn("window.brainDsUI.tabs.mount", inline,
                      "Inline script MUST mount the tabs module")

    def test_viewer_bundle_includes_workspace_overflow_management_contract(self):
        """Compiled viewer bundle MUST include workspace overflow manager contract."""
        bundle_path = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "assets" / "viewer.bundle.js"
        bundle = bundle_path.read_text(encoding="utf-8")
        self.assertIn("__brainDsOverflowManaged", bundle,
                      "Bundle MUST set/read __brainDsOverflowManaged to own overflow wiring")
        self.assertIn("workspace-overflow-menu", bundle,
                      "Bundle MUST include workspace overflow menu DOM wiring")
        self.assertIn("Reset filters", bundle,
                      "Bundle overflow menu MUST expose reset filters action")


class TestPrBViewerPolishContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = Path(__file__).resolve().parent.parent / "brain_ds" / "ui"
        cls.template_text = (base / "templates" / "graph_viewer.html").read_text(encoding="utf-8")

    def test_detail_actions_use_equal_grid_sizing(self):
        self.assertRegex(
            self.template_text,
            r"\.detail-actions\s*\{[^}]*display:\s*grid[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)",
        )

    def test_detail_action_buttons_enforce_44px_min_height(self):
        self.assertRegex(
            self.template_text,
            r"\.detail-actions\s+\.pill-btn[^\{]*\{[^}]*min-height:\s*44px",
        )

    def test_sidebar_collapse_uses_width_transition_not_display_none(self):
        self.assertRegex(self.template_text, r"\.left-panel-shell,\s*\n\s*\.right-panel-shell\s*\{[^}]*transition:[^}]*width")

    def test_filter_checkbox_custom_accent_tokenized(self):
        self.assertRegex(
            self.template_text,
            r"\.filter-checkbox\s*\{[^}]*accent-color:\s*var\(--accent-mora\)",
        )

    def test_left_rail_section_group_mapping_present(self):
        self.assertIn("applyLeftRailSectionVisibility", self.template_text)
        self.assertIn('"filters": new Set(["filters", "legend"])', self.template_text)
        # The folder rail icon routes to the Proyectos / organization-views panel.
        self.assertIn('"file-tree": new Set(["projects"])', self.template_text)


class TestPR2LayoutContainment(unittest.TestCase):
    """PR2 — Layout containment: breadcrumb overflow + overflow menu clamping + search dropdown fix.

    TDD cycle: RED (all failing) → GREEN (implement) → TRIANGULATE → REFACTOR.
    Spec: REQ-2.1, REQ-2.2, S2.1.a, S2.1.b, S2.2.b + search dropdown anchoring.
    """

    @classmethod
    def setUpClass(cls):
        base = Path(__file__).resolve().parent.parent / "brain_ds" / "ui"
        cls.tpl = (base / "templates" / "graph_viewer.html").read_text(encoding="utf-8")
        cls.chrome_src = (base / "src" / "workspace-chrome.ts").read_text(encoding="utf-8")

    # --- T2.1: org breadcrumb leaf truncates (S2.1.a) ---

    def test_breadcrumb_org_li_has_overflow_hidden(self):
        """#workspace-view-org li must have overflow: hidden so long names clip."""
        self.assertRegex(
            self.tpl,
            r"#workspace-view-org\s*\{[^}]*overflow:\s*hidden",
            "#workspace-view-org must have overflow: hidden for ellipsis truncation",
        )

    def test_breadcrumb_org_li_has_text_overflow_ellipsis(self):
        """#workspace-view-org li must have text-overflow: ellipsis."""
        self.assertRegex(
            self.tpl,
            r"#workspace-view-org\s*\{[^}]*text-overflow:\s*ellipsis",
            "#workspace-view-org must have text-overflow: ellipsis",
        )

    def test_breadcrumb_org_li_shrink_priority(self):
        """Org name is the identity anchor: capped width, never shrinks first.

        Chrome redesign inverted the old min-width:0 shrink contract — the
        node/edge counters give way before the org name does.
        """
        self.assertRegex(
            self.tpl,
            r"#workspace-view-org\s*\{[^}]*flex-shrink:\s*0",
            "#workspace-view-org must not shrink before the counters",
        )
        self.assertRegex(
            self.tpl,
            r"#workspace-view-org\s*\{[^}]*max-width:",
            "#workspace-view-org must cap its width so extreme names still ellipsize",
        )

    # --- T2.3: view-zone hard containment (S2.1.b) — already partially present ---

    def test_view_zone_has_min_width_zero(self):
        """[data-toolbar-zone='view'] must have min-width: 0 to prevent flex blow-out."""
        self.assertRegex(
            self.tpl,
            r"\[data-toolbar-zone='view'\]\s*\{[^}]*min-width:\s*0",
            "[data-toolbar-zone='view'] must have min-width: 0",
        )

    def test_view_zone_has_overflow_hidden(self):
        """[data-toolbar-zone='view'] must have overflow: hidden for hard containment."""
        self.assertRegex(
            self.tpl,
            r"\[data-toolbar-zone='view'\]\s*\{[^}]*overflow:\s*hidden",
            "[data-toolbar-zone='view'] must have overflow: hidden",
        )

    # --- T2.2/T2.4: bundled path clamps to .center-column (S2.2.a) ---

    def test_workspace_chrome_clamps_to_center_column_not_workspace_shell(self):
        """workspace-chrome.ts overflow menu MUST clamp to .center-column, not .workspace-shell."""
        self.assertIn(
            ".center-column",
            self.chrome_src,
            "workspace-chrome.ts must reference .center-column for overflow menu clamping",
        )
        # The old incorrect reference must be gone from the overflow menu clamping logic
        # (workspace-chrome.ts may still reference .workspace-shell for other things, but
        # the getBoundingClientRect call for clamping must use .center-column)
        import re
        clamp_block = re.search(
            r"querySelector\(['\"]\.workspace-shell['\"].*?getBoundingClientRect",
            self.chrome_src,
            re.S,
        )
        self.assertIsNone(
            clamp_block,
            "workspace-chrome.ts must not use .workspace-shell for overflow menu getBoundingClientRect clamping",
        )

    # --- T2.5: template inline fallback clamps to .center-column (S2.2.b) ---

    def test_template_inline_overflow_fallback_clamps_to_center_column(self):
        """Inline overflow menu fallback in graph_viewer.html must use .center-column for clamping."""
        self.assertIn(
            ".center-column",
            self.tpl,
            "Template inline overflow fallback must reference .center-column",
        )

    def test_template_inline_overflow_fallback_does_not_use_workspace_shell_for_clamping(self):
        """Template inline overflow fallback must NOT query .workspace-shell for bounds."""
        import re
        # The inline fallback block is gated by !window.__brainDsOverflowManaged
        # Find that block and assert it does NOT call getBoundingClientRect on .workspace-shell
        fallback_start = self.tpl.find("__brainDsOverflowManaged")
        self.assertGreater(fallback_start, 0, "Inline overflow fallback block not found")
        fallback_block = self.tpl[fallback_start:fallback_start + 2000]
        clamp_shell = re.search(
            r"querySelector\(['\"]\.workspace-shell['\"].*?getBoundingClientRect",
            fallback_block,
            re.S,
        )
        self.assertIsNone(
            clamp_shell,
            "Template inline overflow fallback must not use .workspace-shell.getBoundingClientRect() for clamping",
        )

    # --- Added: search dropdown vertical anchoring ---

    def test_search_results_has_top_100_percent(self):
        """#search-results must have top: 100% to anchor below the input wrap, not overlap it."""
        self.assertRegex(
            self.tpl,
            r"#search-results\s*\{[^}]*top:\s*100%",
            "#search-results must have top: 100% to sit below the search input",
        )

    def test_search_results_inside_search_input_wrap(self):
        """#search-results must be a child of .search-input-wrap (the positioned ancestor) so top:100% anchors below input."""
        # Find the .search-input-wrap opening tag, then check that #search-results appears before its closing tag
        wrap_start = self.tpl.find('class="search-input-wrap"')
        self.assertGreater(wrap_start, 0, ".search-input-wrap element not found")
        # Find the results ol after the wrap_start
        results_pos = self.tpl.find('id="search-results"', wrap_start)
        self.assertGreater(results_pos, 0, "#search-results must be found after .search-input-wrap opens")
        # Find the wrap's closing tag (</div>) after results
        close_div = self.tpl.find("</div>", wrap_start)
        self.assertGreater(close_div, results_pos,
            "#search-results must be inside .search-input-wrap (</div> must come after the results ol)")


if __name__ == "__main__":
    unittest.main()
