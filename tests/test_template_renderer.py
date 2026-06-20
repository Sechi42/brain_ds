"""Tests for render_vault_picker_html — PR2 picker UX redesign.

TDD: These tests are written FIRST (RED phase). They assert the NEW structure:
- Single primary "Open workspace" CTA per card with data-workspace-open
- <details class="workspace-manage"> collapsed at rest (no open attribute)
- data-workspace-remove is INSIDE the details (not outside)
- No workspace-action-btn--primary on the Remove button
- workspace-name heading element present
"""
from __future__ import annotations

from brain_ds.ui.template_renderer import render_vault_picker_html


SAMPLE_GRAPHS = [
    {"id": "abc-123", "label": "My Workspace"},
    {"id": "def-456", "label": "Second WS"},
]


class TestVaultPickerManageBlockCollapsed:
    """T2.1: Assert manage block is collapsed at rest."""

    def test_data_workspace_open_present_per_card(self) -> None:
        """Each card must have exactly one element with data-workspace-open."""
        html = render_vault_picker_html(graphs=SAMPLE_GRAPHS)
        # Count occurrences — one per graph
        count = html.count("data-workspace-open")
        assert count == len(SAMPLE_GRAPHS), (
            f"Expected {len(SAMPLE_GRAPHS)} data-workspace-open attributes, got {count}"
        )

    def test_manage_details_present_per_card(self) -> None:
        """Each card must have a <details class="workspace-manage"> element."""
        html = render_vault_picker_html(graphs=SAMPLE_GRAPHS)
        count = html.count('class="workspace-manage"')
        assert count == len(SAMPLE_GRAPHS), (
            f"Expected {len(SAMPLE_GRAPHS)} workspace-manage details, got {count}"
        )

    def test_manage_details_not_open_at_rest(self) -> None:
        """The workspace-manage <details> must NOT carry an 'open' attribute."""
        html = render_vault_picker_html(graphs=SAMPLE_GRAPHS)
        # A collapsed <details> must not have open attribute
        # Check that no workspace-manage block has open on it
        import re
        # Find all workspace-manage details opening tags
        pattern = r'<details[^>]*class="workspace-manage"[^>]*>'
        matches = re.findall(pattern, html)
        assert len(matches) == len(SAMPLE_GRAPHS), (
            f"Expected {len(SAMPLE_GRAPHS)} workspace-manage details tags, got {len(matches)}"
        )
        for tag in matches:
            assert " open" not in tag and tag != "<details open", (
                f"workspace-manage details must not carry 'open' attribute, got: {tag!r}"
            )

    def test_workspace_remove_inside_manage_block(self) -> None:
        """data-workspace-remove must be INSIDE the workspace-manage details block."""
        html = render_vault_picker_html(graphs=[SAMPLE_GRAPHS[0]])
        manage_start = html.index('class="workspace-manage"')
        # Find the closing </details> for the manage block
        # The remove button must come AFTER workspace-manage opening
        remove_pos = html.find("data-workspace-remove")
        assert remove_pos > manage_start, (
            "data-workspace-remove must appear after workspace-manage details opening"
        )
        # And before </details> that closes the manage block
        # Find the first </details> after workspace-manage
        manage_close = html.find("</details>", manage_start)
        assert remove_pos < manage_close, (
            "data-workspace-remove must be INSIDE the workspace-manage details block"
        )

    def test_no_primary_styling_on_remove_button(self) -> None:
        """Remove button must NOT have workspace-action-btn--primary class."""
        html = render_vault_picker_html(graphs=SAMPLE_GRAPHS)
        # Find the data-workspace-remove elements and check they don't carry --primary
        import re
        # Get the context around data-workspace-remove
        pattern = r'<[^>]+data-workspace-remove[^>]*>'
        tags = re.findall(pattern, html)
        assert len(tags) == len(SAMPLE_GRAPHS), (
            f"Expected {len(SAMPLE_GRAPHS)} data-workspace-remove elements, got {len(tags)}"
        )
        for tag in tags:
            assert "workspace-action-btn--primary" not in tag, (
                f"Remove button must not have primary styling, got: {tag!r}"
            )

    def test_workspace_name_heading_present(self) -> None:
        """Each card must have a workspace-name heading element (h2 or similar)."""
        html = render_vault_picker_html(graphs=SAMPLE_GRAPHS)
        # Check workspace-name class exists as heading
        count = html.count("workspace-name")
        assert count >= len(SAMPLE_GRAPHS), (
            f"Expected at least {len(SAMPLE_GRAPHS)} workspace-name elements"
        )

    def test_open_cta_href_points_to_graph_id(self) -> None:
        """The Open workspace CTA must link to /?graph_id={id}."""
        html = render_vault_picker_html(graphs=[SAMPLE_GRAPHS[0]])
        assert 'href="/?graph_id=abc-123"' in html, (
            "Open workspace CTA must have href pointing to /?graph_id=abc-123"
        )

    def test_data_graph_id_on_card(self) -> None:
        """Each card must carry data-graph-id with the graph UUID."""
        html = render_vault_picker_html(graphs=SAMPLE_GRAPHS)
        assert 'data-graph-id="abc-123"' in html
        assert 'data-graph-id="def-456"' in html

    def test_empty_graphs_renders_no_cards(self) -> None:
        """Empty graph list renders no workspace cards — no data attributes from cards."""
        html = render_vault_picker_html(graphs=[])
        assert "data-workspace-open" not in html
        # Check for the element, not the CSS class name in the <style> block
        assert '<details class="workspace-manage">' not in html

    def test_html_escaping_in_label(self) -> None:
        """Labels with HTML special chars must be escaped in generated card markup."""
        graphs = [{"id": "x1", "label": '<script>alert("xss")</script>'}]
        html = render_vault_picker_html(graphs=graphs)
        # The injected label must NOT appear as a raw <script> tag in the cards section
        # We check the card markup region (before the template <script> block)
        # The workspace-name h2 must contain the escaped version
        assert "&lt;script&gt;" in html, "label must be HTML-escaped in the output"
        # The raw unescaped label text must not appear inside an h2 or data attribute
        assert '<h2 class="workspace-name"' in html  # heading element exists
        # Verify the literal unescaped label is NOT in an attribute position
        assert 'data-workspace-name="<script>' not in html
        assert '<h2 class="workspace-name" data-workspace-name="<script>' not in html

    def test_admin_only_delete_controls_and_active_context_are_rendered(self) -> None:
        """PR3: delete affordance is permission-gated and carries active workspace context."""
        html = render_vault_picker_html(
            graphs=SAMPLE_GRAPHS,
            permissions={"abc-123": {"workspace_admin": True}, "def-456": {"workspace_admin": False}},
            active_graph_id="abc-123",
        )

        first_card = html[html.index('data-graph-id="abc-123"'):html.index('data-graph-id="def-456"')]
        second_start = html.index('data-graph-id="def-456"')
        second_card = html[second_start:html.index("</li>", second_start)]
        assert "Eliminar" in first_card
        assert "data-active-graph-id=\"abc-123\"" in first_card
        assert "data-active-workspace=\"true\"" in first_card
        assert "data-workspace-remove" not in second_card
        assert "Delete all data" not in second_card


class TestTauriConfBranding:
    """T2.5: Assert tauri.conf.json branding fields."""

    def test_product_name_is_brainds(self) -> None:
        """tauri.conf.json productName must be 'BrainDS'."""
        import json
        from pathlib import Path

        conf_path = Path(__file__).parent.parent / "src-tauri" / "tauri.conf.json"
        assert conf_path.exists(), f"tauri.conf.json not found at {conf_path}"
        data = json.loads(conf_path.read_text(encoding="utf-8"))
        assert data["productName"] == "BrainDS", (
            f"productName must be 'BrainDS', got {data['productName']!r}"
        )

    def test_window_title_is_brainds(self) -> None:
        """tauri.conf.json windows[0].title must be 'BrainDS'."""
        import json
        from pathlib import Path

        conf_path = Path(__file__).parent.parent / "src-tauri" / "tauri.conf.json"
        data = json.loads(conf_path.read_text(encoding="utf-8"))
        windows = data.get("app", {}).get("windows", [])
        assert len(windows) > 0, "No windows defined in tauri.conf.json"
        assert windows[0]["title"] == "BrainDS", (
            f"windows[0].title must be 'BrainDS', got {windows[0]['title']!r}"
        )

    def test_identifier_unchanged(self) -> None:
        """identifier must remain com.brain-ds.desktop (not renamed)."""
        import json
        from pathlib import Path

        conf_path = Path(__file__).parent.parent / "src-tauri" / "tauri.conf.json"
        data = json.loads(conf_path.read_text(encoding="utf-8"))
        assert data["identifier"] == "com.brain-ds.desktop"

    def test_external_bin_unchanged(self) -> None:
        """externalBin must remain binaries/brain_ds (not renamed)."""
        import json
        from pathlib import Path

        conf_path = Path(__file__).parent.parent / "src-tauri" / "tauri.conf.json"
        data = json.loads(conf_path.read_text(encoding="utf-8"))
        ext_bin = data.get("bundle", {}).get("externalBin", [])
        assert "binaries/brain_ds" in ext_bin
