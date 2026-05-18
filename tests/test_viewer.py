import json
import io
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


class TestViewerFoundation(unittest.TestCase):
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
        with tempfile.TemporaryDirectory() as tmp:
            with patch("pathlib.Path.cwd", return_value=Path(tmp)):
                out = render_graph_data(graph_dict)
            self.assertEqual(out, Path(tmp) / "graph-output.html")
            self.assertTrue(out.exists())

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
        assets_dir = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "assets"
        js_text = (assets_dir / "vis-offline-network.js").read_text(encoding="utf-8").lower()
        css_text = (assets_dir / "vis-network.min.css").read_text(encoding="utf-8").lower()
        for token in FORBIDDEN_REMOTE_TOKENS:
            self.assertNotIn(token, js_text)
            self.assertNotIn(token, css_text)

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
            self.assertIn('id="show-all"', html)
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


class TestSlice2TwoHopHighlight(unittest.TestCase):
    """RED contracts for Slice 2 — 2-hop highlighting (REQ-2.1 through REQ-2.9).

    These tests assert source-level presence of the 2-hop neighborhood logic in
    brain_ds/ui/templates/graph_viewer.html following the same pattern used by
    TestCanvasRendererContracts for vis-offline-network.js.
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

    def test_template_two_hop_neighborhood_helper(self):
        """REQ-2.1: The template MUST define a twoHopNeighborhood helper function.

        The helper computes the full 2-hop set (root + 1-hop + 2-hop) from an
        adjacency map.  Asserting the literal name ensures the function exists
        as a named, reusable unit rather than being inlined ad-hoc.
        """
        self.assertIn(
            "twoHopNeighborhood",
            self.template_text,
            "Expected 'twoHopNeighborhood' helper function to be defined in graph_viewer.html (REQ-2.1)",
        )

    def test_focus_node_uses_two_hop(self):
        """REQ-2.1: The focusNode function body MUST reference twoHopNeighborhood.

        This contract verifies that the existing 1-hop 'nearby' set construction
        has been replaced by the 2-hop helper call.  We do this by asserting that
        the substring 'twoHopNeighborhood' appears inside the focusNode function
        body (after its opening line).
        """
        # Locate focusNode and verify twoHopNeighborhood appears after it.
        focus_node_idx = self.template_text.find("const focusNode")
        self.assertGreater(
            focus_node_idx,
            -1,
            "focusNode function not found in graph_viewer.html",
        )
        two_hop_idx = self.template_text.find("twoHopNeighborhood", focus_node_idx)
        self.assertGreater(
            two_hop_idx,
            focus_node_idx,
            "Expected 'twoHopNeighborhood' to appear inside focusNode body in graph_viewer.html (REQ-2.1)",
        )

    def test_two_hop_opacity_constants(self):
        """REQ-2.3 through REQ-2.5: Both opacity literals 0.70 and 0.25 MUST appear
        in the focusNode logic after the twoHopNeighborhood call.

        REQ-2.3: 1-hop neighbors render at 1.0 (not separately asserted here —
                  1.0 already exists in the file for other uses).
        REQ-2.4: 2-hop neighbors render at 0.70 (asserted: literal '0.70').
        REQ-2.5: All other nodes render at 0.25 (asserted: literal '0.25').
        """
        focus_node_idx = self.template_text.find("const focusNode")
        self.assertGreater(
            focus_node_idx,
            -1,
            "focusNode function not found in graph_viewer.html",
        )

        # Both opacity constants must appear somewhere after focusNode opens.
        opacity_70_idx = self.template_text.find("0.70", focus_node_idx)
        self.assertGreater(
            opacity_70_idx,
            focus_node_idx,
            "Expected opacity constant '0.70' (2-hop dim) inside focusNode body (REQ-2.4)",
        )

        opacity_25_idx = self.template_text.find("0.25", focus_node_idx)
        self.assertGreater(
            opacity_25_idx,
            focus_node_idx,
            "Expected opacity constant '0.25' (out-of-neighborhood dim) inside focusNode body (REQ-2.5)",
        )


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
        assets_dir = (
            Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "assets"
        )
        js_text = (assets_dir / "vis-offline-network.js").read_text(encoding="utf-8")
        self.assertRegex(
            js_text,
            r"Network\.prototype\.clearSelection",
            "Expected 'Network.prototype.clearSelection' in vis-offline-network.js (REQ-3.10)",
        )

    def test_click_event_payload_unchanged(self):
        """REQ-X.4: Locked contract — 'nodes: [node.id]' payload in single-click path
        must remain unchanged after Slice 3b. Cite locked contract REQ-X.4.
        """
        assets_dir = (
            Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "assets"
        )
        js_text = (assets_dir / "vis-offline-network.js").read_text(encoding="utf-8")
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
            "Score threshold",
            self.template_text,
            "Expected 'Score threshold' label text in graph_viewer.html (REQ-5.1)",
        )

    def test_template_score_badge_present(self):
        """REQ-5.7: A score badge MUST be displayed adjacent to the slider showing
        the current threshold value in '0.00' format.

        Asserted by verifying a score-badge element or identifier that pairs with
        the slider and displays a formatted numeric value.
        """
        self.assertRegex(
            self.template_text,
            r"score.?badge|scoreBadge|score-badge",
            "Expected a score badge element/id (scoreBadge, score-badge, or score_badge) "
            "in graph_viewer.html (REQ-5.7)",
        )
        self.assertRegex(
            self.template_text,
            r"toFixed\s*\(\s*2\s*\)",
            "Expected toFixed(2) for '0.00' format on score badge (REQ-5.7)",
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

        Cite REQ-6.2 / OBS-6.2."""
        for item in [
            "Focus this node",
            "Show only this node + neighbors",
            "Copy entity JSON to clipboard",
            "Open detail panel",
        ]:
            self.assertIn(
                item,
                self.template_text,
                f"Node context menu item '{item}' must be present in graph_viewer.html (REQ-6.2).",
            )

    def test_template_canvas_menu_items_present(self):
        """REQ-6.3: Canvas context menu MUST contain 'Zoom to fit', 'Reset filters',
        and 'Switch layout' items.  'Toggle theme' MUST be absent until Slice 7 lands.

        Cite REQ-6.3 / OBS-6.3 / OBS-6.4."""
        for item in ["Zoom to fit", "Reset filters", "Switch layout"]:
            self.assertIn(
                item,
                self.template_text,
                f"Canvas context menu item '{item}' must be present (REQ-6.3).",
            )
        # REQ-6.3: Toggle theme absent until Slice 7 provides light theme tokens.
        self.assertNotIn(
            "Toggle theme",
            self.template_text,
            "Toggle theme MUST be absent from context menu until Slice 7 lands (REQ-6.3 / OBS-6.4).",
        )

    def test_template_grid_aria_disabled(self):
        """REQ-6.3 + REQ-6.9: Grid layout placeholder MUST be rendered as disabled
        (greyed out) with aria-disabled='true', not hidden.

        Cite REQ-6.3 (Grid always disabled) / REQ-6.9 (disabled items use aria-disabled)
        / OBS-6.3."""
        self.assertRegex(
            self.template_text,
            r'[Gg]rid.*aria-disabled\s*=\s*["\']true["\']'
            r'|aria-disabled\s*=\s*["\']true["\'].*[Gg]rid',
            "Grid layout menu item MUST have aria-disabled='true' (REQ-6.9 / REQ-6.3).",
        )


if __name__ == "__main__":
    unittest.main()
