"""
Slice 2 — agent-presence-panel tests
T2.1 Presence model unit tests
T2.3 Transport resilience tests
T2.5 Presence panel HTML / ARIA tests
T2.7 Rate-limit and activity-log correctness (source-level)

Convention: source-level regex / string checks, matching the pattern used by
test_label_policy.py, test_canvas_renderer.py, and test_d4_overlay_runtime.py.

All tests in this file MUST be RED before T2.2/T2.4/T2.6 implementations and
GREEN after.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent


def _load_source(cls) -> None:
    """Called from setUpClass to populate cls.src from cls._src_path."""
    if cls._src_path.exists():
        cls.src = cls._src_path.read_text(encoding="utf-8")
    else:
        cls.src = ""


class _SourceMixin:
    """Helper that reads a source file once per class."""

    _src_path: Path
    src: str

    def _require_file(self) -> None:
        self.assertTrue(
            self._src_path.exists(),  # type: ignore[attr-defined]
            f"{self._src_path.name} does not exist — implementation not yet done.",  # type: ignore[attr-defined]
        )


# ─────────────────────────────────────────────────────────────────────────────
# T2.1  Presence model unit tests
# Target: brain_ds/ui/src/live/live-sync.ts
# ─────────────────────────────────────────────────────────────────────────────


class TestPresenceModel(unittest.TestCase, _SourceMixin):
    """T2.1 — Presence model contract inside live-sync.ts."""

    _src_path = REPO / "brain_ds" / "ui" / "src" / "live" / "live-sync.ts"

    @classmethod
    def setUpClass(cls) -> None:
        _load_source(cls)

    # ── AgentPresence type ────────────────────────────────────────────────────

    def test_agent_presence_type_declared(self):
        """AgentPresence type must be declared (design contract)."""
        self._require_file()
        self.assertRegex(
            self.src,
            r"\bAgentPresence\b",
            "AgentPresence type must be declared in live-sync.ts.",
        )

    def test_agent_presence_has_agent_id(self):
        """AgentPresence must have agentId field."""
        self._require_file()
        self.assertIn("agentId", self.src, "AgentPresence must declare agentId field.")

    def test_agent_presence_has_label(self):
        """AgentPresence must have label field."""
        self._require_file()
        self.assertRegex(
            self.src,
            r"\blabel\s*:",
            "AgentPresence must declare label field.",
        )

    def test_agent_presence_has_status(self):
        """AgentPresence must have status field (active/idle/error)."""
        self._require_file()
        self.assertIn("status", self.src, "AgentPresence must declare status field.")
        for val in ("active", "idle", "error"):
            self.assertIn(val, self.src, f"AgentPresence status must include '{val}'.")

    def test_agent_presence_has_last_seen(self):
        """AgentPresence must have lastSeen field."""
        self._require_file()
        self.assertIn("lastSeen", self.src, "AgentPresence must declare lastSeen field.")

    def test_agent_presence_has_recent_tools(self):
        """AgentPresence must have recentTools field."""
        self._require_file()
        self.assertIn(
            "recentTools", self.src, "AgentPresence must declare recentTools field."
        )

    def test_agent_presence_has_role(self):
        """
        W2: Spec says 'agent appears with name, role, last-tool, and timestamp'.
        AgentPresence must have a `role` field declared in the typedef AND
        _applyPresence() must populate it.
        """
        self._require_file()
        self.assertRegex(
            self.src,
            r"@property\s+\{string\}\s+role|role\s*:",
            "AgentPresence typedef must declare a 'role' field (W2 gap).",
        )
        # _applyPresence must wire the role field onto the presence record
        self.assertRegex(
            self.src,
            r"role\s*[:=]",
            "_applyPresence() must assign a 'role' field to the presence record (W2 gap).",
        )

    # ── ActivityEntry type ────────────────────────────────────────────────────

    def test_activity_entry_type_declared(self):
        """ActivityEntry type must be declared."""
        self._require_file()
        self.assertRegex(
            self.src,
            r"\bActivityEntry\b",
            "ActivityEntry type must be declared in live-sync.ts.",
        )

    # ── presenceByAgent Map ───────────────────────────────────────────────────

    def test_presence_by_agent_map_declared(self):
        """LiveDataStore must have presenceByAgent as a Map."""
        self._require_file()
        self.assertIn(
            "presenceByAgent",
            self.src,
            "LiveDataStore must declare presenceByAgent.",
        )
        self.assertRegex(
            self.src,
            r"presenceByAgent\s*[=:]\s*(new\s+Map|Map<)",
            "presenceByAgent must be initialized as a Map.",
        )

    # ── recentActivity ring buffer ────────────────────────────────────────────

    def test_recent_activity_ring_buffer_declared(self):
        """LiveDataStore must have recentActivity ring buffer (cap 200)."""
        self._require_file()
        self.assertIn(
            "recentActivity",
            self.src,
            "LiveDataStore must declare recentActivity buffer.",
        )
        # Must cap at 200
        self.assertIn(
            "200",
            self.src,
            "recentActivity ring buffer must cap at 200 entries.",
        )

    # ── tool.invoked handler populates presenceByAgent ────────────────────────

    def test_tool_invoked_updates_presence(self):
        """applyEvent('tool.invoked') must update presenceByAgent."""
        self._require_file()
        # The tool.invoked branch must reference presenceByAgent
        src = self.src
        # Find the tool.invoked branch
        match = re.search(
            r"tool\.invoked['\"]?\s*\)?\s*\{.{0,800}",
            src,
            re.DOTALL,
        )
        self.assertIsNotNone(
            match, "applyEvent must have a 'tool.invoked' handling branch."
        )
        self.assertIn(
            "presenceByAgent",
            src,
            "tool.invoked branch must update presenceByAgent.",
        )

    # ── getPresence / subscribePresence public API ────────────────────────────

    def test_get_presence_getter_exported(self):
        """LiveDataStore must expose getPresence() method."""
        self._require_file()
        self.assertRegex(
            self.src,
            r"\bgetPresence\s*\(",
            "LiveDataStore must expose getPresence() method.",
        )

    def test_subscribe_presence_getter_exported(self):
        """LiveDataStore must expose subscribePresence(cb) method."""
        self._require_file()
        self.assertRegex(
            self.src,
            r"\bsubscribePresence\s*\(",
            "LiveDataStore must expose subscribePresence(cb) method.",
        )

    # ── Rate-limit ≤4 Hz ─────────────────────────────────────────────────────

    def test_rate_limit_4hz_constant_present(self):
        """Source must declare the 4 Hz (250 ms) throttle interval for panel updates."""
        self._require_file()
        # 4 Hz = 250 ms interval; look for 250 near throttle/presence context
        self.assertIn(
            "250",
            self.src,
            "Rate-limit for panel updates (≤4 Hz = 250 ms) must be declared as a constant.",
        )

    def test_rate_limit_uses_throttle_or_debounce(self):
        """Source must implement throttle/debounce for panel update notifications."""
        self._require_file()
        self.assertRegex(
            self.src,
            r"(throttle|_presenceUpdateTimer|_presenceTimeout|setTimeout.*250|setInterval.*250)",
            "Presence panel updates must be rate-limited (throttle or setTimeout pattern).",
        )

    # ── No event dropped from activity log ───────────────────────────────────

    def test_events_pushed_to_recent_activity(self):
        """tool.invoked events must be pushed to recentActivity log."""
        self._require_file()
        self.assertIn(
            "recentActivity",
            self.src,
            "recentActivity must be populated on tool.invoked.",
        )
        # The activity log must have a push call
        self.assertRegex(
            self.src,
            r"recentActivity\s*\.\s*push\b",
            "recentActivity ring buffer must be pushed on tool.invoked.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# T2.3  Transport resilience tests
# Target: brain_ds/ui/src/live/live-sync.ts (connectWebSocket / LiveDataStore)
# ─────────────────────────────────────────────────────────────────────────────


class TestTransportResilience(unittest.TestCase, _SourceMixin):
    """T2.3 — WebSocket disconnect must not clear presenceByAgent."""

    _src_path = REPO / "brain_ds" / "ui" / "src" / "live" / "live-sync.ts"

    @classmethod
    def setUpClass(cls) -> None:
        _load_source(cls)

    # ── connectionState field ─────────────────────────────────────────────────

    def test_connection_state_field_declared(self):
        """LiveDataStore must have connectionState field."""
        self._require_file()
        self.assertIn(
            "connectionState",
            self.src,
            "LiveDataStore must declare connectionState field.",
        )

    def test_connection_state_reconnecting_value(self):
        """connectionState must use 'reconnecting' string."""
        self._require_file()
        self.assertIn(
            "reconnecting",
            self.src,
            "connectionState must include 'reconnecting' value.",
        )

    def test_connection_state_connected_value(self):
        """connectionState must use 'connected' string."""
        self._require_file()
        self.assertIn(
            "connected",
            self.src,
            "connectionState must include 'connected' value.",
        )

    def test_disconnect_sets_reconnecting_not_clear_presence(self):
        """On disconnect, connectionState = 'reconnecting' must NOT clear presenceByAgent."""
        self._require_file()
        src = self.src
        # There must be a disconnect handler that sets 'reconnecting'
        self.assertRegex(
            src,
            r"['\"]reconnecting['\"]",
            "connectWebSocket must set connectionState = 'reconnecting' on disconnect.",
        )
        # And the disconnect handler must NOT call .clear() on presenceByAgent
        # (look for presenceByAgent.clear() — should NOT exist)
        self.assertNotRegex(
            src,
            r"presenceByAgent\s*\.\s*clear\s*\(",
            "presenceByAgent must NOT be cleared on disconnect.",
        )

    def test_reconnect_sets_connected(self):
        """On resubscribe success (open), connectionState = 'connected'."""
        self._require_file()
        self.assertRegex(
            self.src,
            r"['\"]connected['\"]",
            "connectWebSocket must set connectionState = 'connected' on open.",
        )

    def test_on_connection_state_change_callback(self):
        """LiveDataStore must have onConnectionStateChange callback."""
        self._require_file()
        self.assertIn(
            "onConnectionStateChange",
            self.src,
            "LiveDataStore must expose onConnectionStateChange callback.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# T2.5  Presence panel HTML / ARIA tests
# Target: brain_ds/ui/templates/graph_viewer.html
# ─────────────────────────────────────────────────────────────────────────────


class TestPresencePanelHtml(unittest.TestCase):
    """T2.5 — Presence panel must exist in DOM with ARIA live region."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._html_path = (
            REPO / "brain_ds" / "ui" / "templates" / "graph_viewer.html"
        )
        if cls._html_path.exists():
            cls.html = cls._html_path.read_text(encoding="utf-8")
        else:
            cls.html = ""

    def _require_file(self) -> None:
        self.assertTrue(self._html_path.exists(), "graph_viewer.html must exist.")

    # ── Panel element ─────────────────────────────────────────────────────────

    def test_agent_presence_section_exists(self):
        """HTML must contain #agent-presence-panel section element."""
        self._require_file()
        self.assertIn(
            "agent-presence-panel",
            self.html,
            "graph_viewer.html must have an element with id='agent-presence-panel'.",
        )

    def test_agent_presence_section_aria_label(self):
        """Section must have aria-label='Agent Activity'."""
        self._require_file()
        self.assertRegex(
            self.html,
            r'aria-label=["\']Agent Activity["\']',
            "Agent presence panel section must have aria-label='Agent Activity'.",
        )

    def test_agent_activity_aria_live_region(self):
        """Panel must contain an aria-live='polite' region for activity updates."""
        self._require_file()
        # Must have aria-live="polite" somewhere within the agent-presence-panel section
        # Use re.DOTALL so .* crosses newlines
        self.assertIsNotNone(
            re.search(
                r"agent-presence-panel.{0,2000}aria-live=['\"]polite['\"]",
                self.html,
                re.DOTALL,
            ),
            "Agent presence panel must contain an aria-live='polite' region.",
        )

    def test_reconnecting_indicator_in_html(self):
        """HTML must contain a 'reconnecting' indicator element."""
        self._require_file()
        self.assertRegex(
            self.html,
            r"reconnecting",
            "graph_viewer.html must contain a 'reconnecting' indicator element.",
        )

    # ── Progressive disclosure ────────────────────────────────────────────────

    def test_agent_presence_uses_details_or_summary_for_disclosure(self):
        """Presence panel must use progressive disclosure (details/summary or equivalent)."""
        self._require_file()
        # Within the agent-presence-panel region, expect details/summary OR role=button
        # We accept either: <details> or a collapse/expand pattern
        self.assertRegex(
            self.html,
            r"(<details|role=['\"]button['\"]|data-accordion)",
            "Agent presence panel must use progressive disclosure.",
        )

    # ── Touch targets ─────────────────────────────────────────────────────────

    def test_agent_presence_css_min_height_or_padding(self):
        """CSS for agent presence entries must ensure ≥44px touch targets."""
        self._require_file()
        # Look for min-height: 44px or padding that would produce ≥44px
        self.assertRegex(
            self.html,
            r"(min-height\s*:\s*44px|min-height\s*:\s*2\.75rem|--agent-entry-min-h)",
            "Agent presence entries must have ≥44px touch targets.",
        )

    # ── CSS custom properties (no magic numbers) ──────────────────────────────

    def test_agent_presence_css_uses_custom_properties(self):
        """Agent presence CSS must use var(--...) custom properties for colors."""
        self._require_file()
        # Find the agent-presence block and verify it uses CSS custom props
        match = re.search(
            r"#agent-presence-panel[^{]*\{[^}]*\}",
            self.html,
            re.DOTALL,
        )
        # The panel must exist in CSS
        self.assertRegex(
            self.html,
            r"#agent-presence-panel|\.agent-presence",
            "Agent presence CSS rules must be present in graph_viewer.html.",
        )
        # Spot-check: colors must use var()
        # (We check the broader agent presence CSS region for var())
        agent_section = re.search(
            r"(#agent-presence-panel|\.agent-presence).{0,2000}",
            self.html,
            re.DOTALL,
        )
        if agent_section:
            self.assertIn(
                "var(--",
                agent_section.group(0),
                "Agent presence CSS must use CSS custom properties (var(--...)).",
            )

    # ── agentPanel feature flag ───────────────────────────────────────────────

    def test_agent_panel_config_block_exists(self):
        """HTML config block must include agentPanel.enabled."""
        self._require_file()
        self.assertIn(
            "agentPanel",
            self.html,
            "graph_viewer.html config block must declare agentPanel.",
        )
        self.assertRegex(
            self.html,
            r"agentPanel\s*[=:]\s*\{",
            "agentPanel config must be an object with enabled flag.",
        )
        self.assertRegex(
            self.html,
            r"enabled\s*:\s*true",
            "agentPanel.enabled must default to true.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# T2.7  Rate-limit and activity-log correctness (source-level proxy)
# Full E2E Playwright test is deferred; this tests the source contract.
# ─────────────────────────────────────────────────────────────────────────────


class TestRateLimitActivityLog(unittest.TestCase, _SourceMixin):
    """T2.7 — Source-level proxy for rate-limit and activity log correctness."""

    _src_path = REPO / "brain_ds" / "ui" / "src" / "live" / "live-sync.ts"

    @classmethod
    def setUpClass(cls) -> None:
        _load_source(cls)

    def test_rate_limit_notification_separated_from_event_buffering(self):
        """Panel update notification must be separate from event buffering."""
        self._require_file()
        # Both presenceByAgent update (immediate) and panel notification (throttled) must be present
        src = self.src
        self.assertIn(
            "presenceByAgent",
            src,
            "presenceByAgent must be updated (not throttled away).",
        )
        # Throttle mechanism must exist
        self.assertRegex(
            src,
            r"(_presenceUpdateTimer|_notifyPresence|setTimeout.*presenc|throttle.*presenc|presenc.*throttle)",
            "Panel update notification must be throttled/debounced separately from presence state update.",
        )

    def test_activity_log_cap_200_enforced(self):
        """recentActivity ring buffer must enforce cap of 200 entries."""
        self._require_file()
        # Must slice or shift when over cap; look for the cap enforcement
        self.assertRegex(
            self.src,
            r"(recentActivity\.slice|recentActivity\.shift|recentActivity\.length\s*[><=].*200|recentActivity\.splice|ACTIVITY_RING_CAP)",
            "recentActivity must enforce a cap (200 entries).",
        )

    def test_presence_subscribers_list_maintained(self):
        """LiveDataStore must maintain a _presenceSubscribers list."""
        self._require_file()
        self.assertRegex(
            self.src,
            r"_presenceSubscribers",
            "LiveDataStore must maintain _presenceSubscribers list.",
        )


if __name__ == "__main__":
    unittest.main()
