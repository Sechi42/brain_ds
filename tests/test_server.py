import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from brain_ds.ontology import Graph
from brain_ds.store.graph_store import GraphStore


def _sample_graph_payload(org: str) -> dict:
    return {
        "org": org,
        "generated_at": "2026-03-01T08:00:00Z",
        "nodes": [{"id": "n1", "label": f"{org} Node", "type": "Department"}],
        "edges": [],
        "evidence": [],
    }


class TestServerRuntime(unittest.TestCase):
    def test_run_server_creates_workspace_store_when_missing(self):
        from brain_ds.ui import server

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_path = root / ".brain_ds" / "store.db"
            self.assertFalse(store_path.exists())

            fake_server = Mock()
            fake_server.config.bind_socket.return_value = None
            with patch("brain_ds.ui.server.uvicorn.Server", return_value=fake_server), patch("brain_ds.ui.server.signal.signal"):
                server.run_server(project_root=root, port=8765)

            self.assertTrue(store_path.exists())
            fake_server.run.assert_called_once()

    def test_run_server_port_conflict_reports_clear_error_and_exits_1(self):
        from brain_ds.ui import server

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stderr = io.StringIO()
            with self.assertRaises(SystemExit) as ctx:
                with redirect_stderr(stderr):
                    fake_server = Mock()
                    fake_server.config.bind_socket.side_effect = OSError("Address in use")
                    with patch("brain_ds.ui.server.uvicorn.Server", return_value=fake_server):
                        server.run_server(project_root=root, port=8765)

        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("Error: port 8765 is already in use", stderr.getvalue())

    def test_get_root_returns_rendered_html_from_active_graph(self):
        from brain_ds.ui import server

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_store = Mock()
            fake_store.list_graphs.return_value = [
                SimpleNamespace(id="old-id", org="Older Org", imported_from=str(root / "old.json")),
                SimpleNamespace(id="new-id", org="Latest Org", imported_from=str(root / "new.json")),
            ]
            fake_store.load_graph.return_value = Graph.from_v1(_sample_graph_payload("Latest Org"))

            app = server.build_ui_app(project_root=root, store=fake_store)
            with TestClient(app) as client:
                response = client.get("/")
                self.assertEqual(response.status_code, 200)
                self.assertIn("Latest Org", response.text)

    def test_get_root_with_empty_store_returns_200(self):
        from brain_ds.ui import server

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_store = Mock()
            fake_store.list_graphs.return_value = []

            app = server.build_ui_app(project_root=root, store=fake_store)
            with TestClient(app) as client:
                response = client.get("/")
                self.assertEqual(response.status_code, 200)
                self.assertIn("RENDER_CONTEXT", response.text)

    def test_get_root_tolerates_poisoned_card_sections_row(self):
        from brain_ds.ui import server

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_path = root / ".brain_ds" / "store.db"
            store_path.parent.mkdir(parents=True, exist_ok=True)
            store = GraphStore(str(store_path), allow_cross_thread=True)
            try:
                graph_id = store.create_graph("runtime-org", workspace_root=str(root), workspace_path=str(root))
                store.upsert_node(
                    graph_id,
                    {"id": "valid", "label": "Valid Node", "type": "Department", "details": {"summary": "ok"}},
                )
                store.upsert_node(
                    graph_id,
                    {
                        "id": "poisoned",
                        "label": "Poisoned Node",
                        "type": "Department",
                        "details": {"summary": "bad"},
                        "card_sections": [{"title": "Overview", "content": "new", "icon": "", "order": 1}],
                    },
                )
                store.conn.execute(
                    "UPDATE nodes SET card_sections = ? WHERE graph_id = ? AND id = ?",
                    (json.dumps([{"title": "Overview", "body": "legacy only"}]), graph_id, "poisoned"),
                )
                store.conn.commit()

                app = server.build_ui_app(project_root=root, store=store)
                with TestClient(app) as client:
                    response = client.get("/")

                self.assertEqual(response.status_code, 200)
                self.assertIn("Valid Node", response.text)
                self.assertIn("Poisoned Node", response.text)
            finally:
                store.close()

    def test_get_api_graphs_returns_id_and_label_json(self):
        from brain_ds.ui import server

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_store = Mock()
            fake_store.list_graphs.return_value = [
                SimpleNamespace(id="graph-1", org="Label Org", imported_from=str(root / "graph.json"))
            ]
            app = server.build_ui_app(project_root=root, store=fake_store)
            with TestClient(app) as client:
                response = client.get("/api/graphs")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), [{"id": "graph-1", "label": "Label Org"}])

    def test_sigint_handler_closes_store_and_exits_0(self):
        from brain_ds.ui import server

        runtime = server.ServerRuntime(project_root=Path("."), store=Mock())
        fake_httpd = SimpleNamespace(shutdown=Mock())

        with self.assertRaises(SystemExit) as ctx:
            runtime._handle_signal(2, None, fake_httpd)

        self.assertEqual(ctx.exception.code, 0)
        runtime.store.close.assert_called_once()
        fake_httpd.shutdown.assert_called_once()

    def test_sigint_handler_closes_file_backed_store_and_releases_wal_shm_handles(self):
        from brain_ds.store.graph_store import GraphStore
        from brain_ds.ui import server

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_path = root / ".brain_ds" / "store.db"
            store_path.parent.mkdir(parents=True, exist_ok=True)
            store = GraphStore(str(store_path))
            store.import_json(_sample_graph_payload("Wal Org"), workspace_root=str(root))

            runtime = server.ServerRuntime(project_root=root, store=store)
            fake_httpd = SimpleNamespace(shutdown=Mock())

            with self.assertRaises(SystemExit) as ctx:
                runtime._handle_signal(2, None, fake_httpd)

            self.assertEqual(ctx.exception.code, 0)
            self.assertTrue(store._closed)
            fake_httpd.shutdown.assert_called_once()

            for suffix in ("-wal", "-shm"):
                sidecar = Path(f"{store_path}{suffix}")
                if sidecar.exists():
                    renamed = sidecar.with_name(sidecar.name + ".moved")
                    sidecar.rename(renamed)
                    renamed.unlink()
                self.assertFalse(sidecar.exists(), f"Expected {sidecar.name} to be absent after shutdown")


# ---------------------------------------------------------------------------
# T2.1 / T2.2 — POST /api/graphs  (R4, R5, R14)
# ---------------------------------------------------------------------------

class TestPostApiGraphs(unittest.TestCase):
    def _make_app_with_real_store(self, tmp: str):
        from brain_ds.ui import server

        root = Path(tmp)
        store_path = root / ".brain_ds" / "store.db"
        store_path.parent.mkdir(parents=True, exist_ok=True)
        store = GraphStore(str(store_path), allow_cross_thread=True)
        app = server.build_ui_app(project_root=root, store=store)
        return app, store, root

    def test_post_api_graphs_creates_org_returns_201_with_id_and_label(self):

        with tempfile.TemporaryDirectory() as tmp:
            app, store, root = self._make_app_with_real_store(tmp)
            try:
                with TestClient(app) as client:
                    response = client.post("/api/graphs", json={"label": "my-org"})
                self.assertEqual(response.status_code, 201)
                body = response.json()
                self.assertIn("id", body)
                self.assertEqual(body["label"], "my-org")
                # R14 parity: org is visible via list_graphs on same store
                graphs = store.list_graphs()
                ids = [g.id for g in graphs]
                self.assertIn(body["id"], ids)
            finally:
                store.close()

    def test_post_api_graphs_rejects_empty_label_with_4xx(self):

        with tempfile.TemporaryDirectory() as tmp:
            app, store, root = self._make_app_with_real_store(tmp)
            try:
                with TestClient(app) as client:
                    response = client.post("/api/graphs", json={"label": ""})
                self.assertGreaterEqual(response.status_code, 400)
                self.assertLess(response.status_code, 500)
            finally:
                store.close()

    def test_post_api_graphs_rejects_whitespace_label_with_4xx(self):

        with tempfile.TemporaryDirectory() as tmp:
            app, store, root = self._make_app_with_real_store(tmp)
            try:
                with TestClient(app) as client:
                    response = client.post("/api/graphs", json={"label": "   "})
                self.assertGreaterEqual(response.status_code, 400)
                self.assertLess(response.status_code, 500)
            finally:
                store.close()


# ---------------------------------------------------------------------------
# T2.3 / T2.4 — GET /?graph_id= routing  (R6, R7)
# ---------------------------------------------------------------------------

class TestGetRootGraphIdRouting(unittest.TestCase):
    def _make_app_with_two_orgs(self, tmp: str):
        """Returns (app, store, older_id, newer_id) using real GraphStore."""
        from brain_ds.ui import server
        from brain_ds.ontology import Graph

        root = Path(tmp)
        store_path = root / ".brain_ds" / "store.db"
        store_path.parent.mkdir(parents=True, exist_ok=True)
        store = GraphStore(str(store_path), allow_cross_thread=True)

        older = Graph.from_v1({"nodes": [], "edges": [], "org": "Older Org"})
        older_id = store.save_graph(older, workspace_root=str(root))

        newer = Graph.from_v1({"nodes": [], "edges": [], "org": "Newer Org"})
        newer_id = store.save_graph(newer, workspace_root=str(root))

        app = server.build_ui_app(project_root=root, store=store)
        return app, store, older_id, newer_id

    def test_get_root_with_graph_id_renders_specified_org(self):
        """R6: ?graph_id=older-id must render Older Org, not Newer Org (the auto-pick winner)."""
        with tempfile.TemporaryDirectory() as tmp:
            app, store, older_id, newer_id = self._make_app_with_two_orgs(tmp)
            try:
                with TestClient(app) as client:
                    response = client.get(f"/?graph_id={older_id}")
                self.assertEqual(response.status_code, 200)
                self.assertIn("Older Org", response.text)
            finally:
                store.close()

    def test_get_root_without_graph_id_autopicks_most_recent(self):
        """R6 backward compat: no graph_id → auto-pick still works."""
        with tempfile.TemporaryDirectory() as tmp:
            app, store, older_id, newer_id = self._make_app_with_two_orgs(tmp)
            try:
                with TestClient(app) as client:
                    response = client.get("/")
                self.assertEqual(response.status_code, 200)
                # Should render whatever the most-recent is (Newer Org in this fixture)
                self.assertIn("Newer Org", response.text)
            finally:
                store.close()

    def test_get_root_with_unknown_graph_id_falls_back_no_404(self):
        """R7: unknown graph_id must NOT 404; falls back to auto-pick."""
        with tempfile.TemporaryDirectory() as tmp:
            app, store, older_id, newer_id = self._make_app_with_two_orgs(tmp)
            try:
                with TestClient(app) as client:
                    response = client.get("/?graph_id=nonexistent-uuid")
                self.assertEqual(response.status_code, 200)
            finally:
                store.close()


# ---------------------------------------------------------------------------
# Slice 1 — Token assertion for index.html (R2, R13)
# (Animation quality is bundled-smoke-verified-by-user; token presence is assertable)
# ---------------------------------------------------------------------------

class TestSplashTokens(unittest.TestCase):
    BOOTSTRAP_HTML = Path(__file__).parent.parent / "src-tauri" / "bootstrap" / "index.html"

    def _html(self) -> str:
        return self.BOOTSTRAP_HTML.read_text(encoding="utf-8")

    def test_old_slate_blue_palette_removed(self):
        """R2: old palette must not appear."""
        html = self._html()
        for old_token in ("#0f172a", "#2563eb", "#111827", "#334155", "#e2e8f0", "#cbd5e1"):
            self.assertNotIn(old_token, html, f"Old color {old_token} still present in splash")

    def test_carbon_zinc_tokens_present(self):
        """R13: carbon/zinc token variables must be declared."""
        html = self._html()
        for token in ("--bg-main", "--accent-mora", "--text-normal", "--text-muted"):
            self.assertIn(token, html, f"Token {token} missing from splash")

    def test_prefers_reduced_motion_media_query_present(self):
        """R3: prefers-reduced-motion degradation must be present."""
        html = self._html()
        self.assertIn("prefers-reduced-motion", html)


# ---------------------------------------------------------------------------
# T3.1 / T3.2 / T3.3 / T3.4 — GET /vault-picker  (R8, R9, R13, R14)
# ---------------------------------------------------------------------------

class TestGetVaultPicker(unittest.TestCase):
    """Tests for the vault-picker route and template renderer (Slice 3)."""

    def _make_app_fake_store(self, graphs):
        """Build app with a mock store returning the given graph list."""
        from brain_ds.ui import server
        import tempfile

        tmp_dir = tempfile.mkdtemp()
        root = Path(tmp_dir)
        fake_store = Mock()
        fake_store.list_graphs.return_value = graphs
        app = server.build_ui_app(project_root=root, store=fake_store)
        return app

    def _make_app_real_store(self, tmp: str, org_names: list):
        """Build app with real GraphStore seeded with org_names."""
        from brain_ds.ui import server
        from brain_ds.ontology import Graph

        root = Path(tmp)
        store_path = root / ".brain_ds" / "store.db"
        store_path.parent.mkdir(parents=True, exist_ok=True)
        store = GraphStore(str(store_path), allow_cross_thread=True)
        ids = []
        for name in org_names:
            g = Graph.from_v1({"nodes": [], "edges": [], "org": name})
            ids.append(store.save_graph(g, workspace_root=str(root)))
        app = server.build_ui_app(project_root=root, store=store)
        return app, store, ids

    # --- R8: list orgs as selectable, focusable rows ---

    def test_vault_picker_lists_orgs_in_html(self):
        """R8: /vault-picker must include each org label in the page."""
        graphs = [
            SimpleNamespace(id="id-alpha", org="alpha", imported_from=None),
            SimpleNamespace(id="id-beta", org="beta", imported_from=None),
        ]
        app = self._make_app_fake_store(graphs)
        with TestClient(app) as client:
            response = client.get("/vault-picker")
        self.assertEqual(response.status_code, 200)
        self.assertIn("alpha", response.text)
        self.assertIn("beta", response.text)

    def test_vault_picker_org_rows_are_focusable(self):
        """R8: org rows must be keyboard-focusable (anchor href or tabindex)."""
        graphs = [
            SimpleNamespace(id="id-alpha", org="alpha", imported_from=None),
        ]
        app = self._make_app_fake_store(graphs)
        with TestClient(app) as client:
            response = client.get("/vault-picker")
        self.assertEqual(response.status_code, 200)
        html = response.text
        # Row must be either an <a href=...> link or carry tabindex
        is_focusable = (
            'href="/?graph_id=id-alpha"' in html
            or 'href=\'/?graph_id=id-alpha\'' in html
            or ('id-alpha' in html and 'tabindex' in html)
        )
        self.assertTrue(is_focusable, "Org row for id-alpha is not keyboard-focusable")

    def test_vault_picker_org_row_id_attribute_present(self):
        """R8: the org id must be embedded in the row so the picker can navigate."""
        graphs = [
            SimpleNamespace(id="id-beta", org="beta", imported_from=None),
        ]
        app = self._make_app_fake_store(graphs)
        with TestClient(app) as client:
            response = client.get("/vault-picker")
        self.assertIn("id-beta", response.text)

    # --- R9: create-org form present even on empty store ---

    def test_vault_picker_empty_store_returns_200_with_form(self):
        """R9: empty store must not crash the picker; form must be present."""
        app = self._make_app_fake_store([])
        with TestClient(app) as client:
            response = client.get("/vault-picker")
        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn("<form", html)
        # Form must POST to /api/graphs
        self.assertIn("/api/graphs", html)

    def test_vault_picker_create_org_form_has_label_input(self):
        """R9: form must contain an input for the org label."""
        app = self._make_app_fake_store([])
        with TestClient(app) as client:
            response = client.get("/vault-picker")
        html = response.text
        self.assertIn("<input", html)

    def test_vault_picker_form_present_with_orgs(self):
        """R9: create-org form must be present even when the store has orgs."""
        graphs = [
            SimpleNamespace(id="id-alpha", org="alpha", imported_from=None),
        ]
        app = self._make_app_fake_store(graphs)
        with TestClient(app) as client:
            response = client.get("/vault-picker")
        self.assertIn("<form", response.text)

    # --- R13: design tokens substituted ---

    def test_vault_picker_uses_carbon_zinc_tokens(self):
        """R13: picker HTML must include carbon/zinc token declarations."""
        app = self._make_app_fake_store([])
        with TestClient(app) as client:
            response = client.get("/vault-picker")
        html = response.text
        self.assertIn("--accent-mora", html)
        self.assertIn("--bg-main", html)

    # --- R14: real store parity ---

    def test_vault_picker_r14_orgs_from_real_store(self):
        """R14: orgs created via GraphStore are visible in the picker."""
        with tempfile.TemporaryDirectory() as tmp:
            app, store, ids = self._make_app_real_store(tmp, ["gamma", "delta"])
            try:
                with TestClient(app) as client:
                    response = client.get("/vault-picker")
                self.assertEqual(response.status_code, 200)
                self.assertIn("gamma", response.text)
                self.assertIn("delta", response.text)
            finally:
                store.close()

    # --- render_vault_picker_html direct unit tests ---

    def test_render_vault_picker_html_empty_graphs_no_crash(self):
        """R9: renderer must not crash with empty graph list."""
        from brain_ds.ui.template_renderer import render_vault_picker_html
        html = render_vault_picker_html([])
        self.assertIsInstance(html, str)
        self.assertIn("<form", html)

    def test_render_vault_picker_html_injects_org_labels(self):
        """R8: renderer must inject org labels into the HTML."""
        from brain_ds.ui.template_renderer import render_vault_picker_html
        graphs = [{"id": "x1", "label": "zeta"}]
        html = render_vault_picker_html(graphs)
        self.assertIn("zeta", html)
        self.assertIn("x1", html)

    def test_render_vault_picker_html_substitutes_tokens(self):
        """R13: renderer must substitute __BRAIN_DS_TOKENS_CSS__ placeholder."""
        from brain_ds.ui.template_renderer import render_vault_picker_html
        html = render_vault_picker_html([])
        # Placeholder must be replaced; canonical token value must appear
        self.assertNotIn("__BRAIN_DS_TOKENS_CSS__", html)
        self.assertIn("--accent-mora", html)


# ---------------------------------------------------------------------------
# T4.1 — bootstrap.js Ready → /vault-picker  (R10)
# T4.3 — picker JS create-org navigates to /?graph_id=  (R12)
# ---------------------------------------------------------------------------

class TestSlice4BootstrapWiring(unittest.TestCase):
    """R10: bootstrap.js must navigate to /vault-picker on Ready (T4.1).
    R12: vault_picker.html JS must navigate to /?graph_id=<id> on create success (T4.3).
    """

    BOOTSTRAP_JS = Path(__file__).parent.parent / "src-tauri" / "bootstrap" / "bootstrap.js"
    VAULT_PICKER_HTML = (
        Path(__file__).parent.parent / "brain_ds" / "ui" / "templates" / "vault_picker.html"
    )

    def _js(self) -> str:
        return self.BOOTSTRAP_JS.read_text(encoding="utf-8")

    def _picker_html(self) -> str:
        return self.VAULT_PICKER_HTML.read_text(encoding="utf-8")

    def test_bootstrap_js_navigates_to_vault_picker_on_ready(self):
        """R10: on server Ready the bootstrap MUST navigate to /vault-picker (not root)."""
        js = self._js()
        self.assertIn("/vault-picker", js, (
            "bootstrap.js must navigate to /vault-picker on Ready, but /vault-picker not found"
        ))

    def test_bootstrap_js_does_not_navigate_to_root_only(self):
        """R10: old bare-root navigation (result.url without /vault-picker) must not be present."""
        js = self._js()
        # The old pattern assigned result.url directly; must be gone
        self.assertNotIn("location.assign(result.url)", js, (
            "bootstrap.js must not navigate to bare result.url — must navigate to /vault-picker"
        ))

    def test_picker_js_navigates_to_graph_id_on_create_success(self):
        """R12: vault_picker.html JS must navigate to /?graph_id=<new_id> on create-org success."""
        html = self._picker_html()
        self.assertIn("/?graph_id=", html, (
            "vault_picker.html JS must navigate to /?graph_id=<id> after successful create-org"
        ))
