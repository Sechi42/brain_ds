"""T3.1 — TDD tests for GET /api/ai/suggestions and /api/ai/completeness routes.

These tests are RED until T3.2 is implemented (routes added to routes.py).

Design notes:
- suggest_connections(store, params) requires graph_id + node_id.
- assess_completeness(store, params) requires graph_id only (graph-level assessment;
  node_id is accepted as an optional hint in the HTTP route but not passed to handler).
- Both routes are GET (read-only); no write side-effects.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from brain_ds.api.events import EventBus
from brain_ds.api.server import create_app
from brain_ds.store.graph_store import GraphStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _store_with_graph(tmp_path: Path) -> GraphStore:
    brain_ds_dir = tmp_path / ".brain_ds"
    brain_ds_dir.mkdir(parents=True)
    store = GraphStore(str(brain_ds_dir / "store.db"), allow_cross_thread=True)
    store.meta_repo.save_graph_meta(
        graph_id="g1",
        workspace_root=str(tmp_path),
        workspace_path=str(tmp_path),
        project="proj",
        org="org",
        schema_version="2.0.0",
        contract_version="1.0.0",
        node_count=0,
        edge_count=0,
        imported_from=None,
        generated_at="",
    )
    return store


def _api_client(store: GraphStore, tmp_path: Path) -> TestClient:
    return TestClient(create_app(project_root=tmp_path, store=store, event_bus=EventBus()))


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    store = _store_with_graph(tmp_path)
    return _api_client(store, tmp_path)


@pytest.fixture()
def client_with_node(tmp_path: Path) -> tuple[TestClient, str]:
    """Client with a graph that has at least one node."""
    store = _store_with_graph(tmp_path)
    store.upsert_node("g1", {
        "id": "node-1",
        "label": "Test Node",
        "type": "DataSource",
        "details": {"description": "A test node"},
    })
    return _api_client(store, tmp_path), "node-1"


# ---------------------------------------------------------------------------
# T3.1 — Tests for GET /api/ai/suggestions
# ---------------------------------------------------------------------------


class TestSuggestionsRoute:
    def test_missing_graph_id_returns_422(self, client: TestClient) -> None:
        """Missing graph_id → 422."""
        resp = client.get("/api/ai/suggestions", params={"node_id": "node-1"})
        assert resp.status_code == 422

    def test_missing_node_id_returns_422(self, client: TestClient) -> None:
        """Missing node_id → 422."""
        resp = client.get("/api/ai/suggestions", params={"graph_id": "g1"})
        assert resp.status_code == 422

    def test_missing_both_params_returns_422(self, client: TestClient) -> None:
        """Missing both params → 422."""
        resp = client.get("/api/ai/suggestions")
        assert resp.status_code == 422

    def test_nonexistent_node_returns_4xx_not_500(self, client: TestClient) -> None:
        """Node not found → 4xx (not 5xx) with message."""
        resp = client.get("/api/ai/suggestions", params={"graph_id": "g1", "node_id": "nonexistent"})
        assert resp.status_code in (400, 404, 422)
        body = resp.json()
        assert "detail" in body or "message" in body or "error" in body

    def test_valid_request_returns_200_with_suggestion_fields(
        self, client_with_node: tuple[TestClient, str]
    ) -> None:
        """Valid graph_id + node_id → 200, JSON with suggestion fields."""
        client, node_id = client_with_node
        resp = client.get("/api/ai/suggestions", params={"graph_id": "g1", "node_id": node_id})
        assert resp.status_code == 200
        body = resp.json()
        # suggest_connections returns a dict; check top-level keys from the handler
        assert isinstance(body, dict)
        # The handler result includes at minimum 'suggestions' or 'candidates' or similar
        # (check brain_ds/scoring/similarity.py for exact shape)
        assert "suggestions" in body or "candidates" in body or "ranked" in body or len(body) > 0

    def test_route_is_readonly_get(self, client: TestClient) -> None:
        """Route must be GET only; POST must not match (405 or 404)."""
        resp = client.post("/api/ai/suggestions", json={})
        assert resp.status_code in (404, 405)


# ---------------------------------------------------------------------------
# T3.1 — Tests for GET /api/ai/completeness
# ---------------------------------------------------------------------------


class TestCompletenessRoute:
    def test_missing_graph_id_returns_422(self, client: TestClient) -> None:
        """Missing graph_id → 422."""
        resp = client.get("/api/ai/completeness")
        assert resp.status_code == 422

    def test_valid_graph_id_returns_200_with_completeness_fields(
        self, client: TestClient
    ) -> None:
        """Valid graph_id → 200, JSON with completeness assessment fields."""
        resp = client.get("/api/ai/completeness", params={"graph_id": "g1"})
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, dict)
        # assess_completeness returns graph_id + completeness_matrix + missing_for_brd etc.
        assert "graph_id" in body
        assert "completeness_matrix" in body
        assert "pre_mapping_recommendation" in body

    def test_node_id_optional_for_completeness(self, client: TestClient) -> None:
        """node_id may be provided (for UI context) but is not required; route accepts it."""
        resp = client.get(
            "/api/ai/completeness", params={"graph_id": "g1", "node_id": "some-node"}
        )
        assert resp.status_code == 200

    def test_handler_error_graph_not_found_returns_4xx_not_500(
        self, client: TestClient
    ) -> None:
        """Unknown graph_id → 4xx with message, NOT 500."""
        resp = client.get("/api/ai/completeness", params={"graph_id": "nonexistent-graph"})
        assert resp.status_code in (400, 404, 422)
        body = resp.json()
        assert "detail" in body or "message" in body or "error" in body

    def test_route_is_readonly_get(self, client: TestClient) -> None:
        """Route must be GET only; POST must not match."""
        resp = client.post("/api/ai/completeness", json={})
        assert resp.status_code in (404, 405)
