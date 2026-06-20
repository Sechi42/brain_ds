from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from brain_ds.api.events import EventBus
from brain_ds.api.server import create_app
from brain_ds.store.graph_store import GraphStore


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


class TestGraphSearchRoute:
    def test_search_returns_score_ordered_algorithmic_results(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            store.upsert_node("g1", {"id": "low", "label": "Alpha low", "type": "Concept", "details": {}})
            store.upsert_node("g1", {"id": "high", "label": "Alpha", "type": "System", "details": {}})
            client = _api_client(store, tmp_path)

            resp = client.get("/api/search", params={"graph_id": "g1", "q": "alpha"})

            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["graph_id"] == "g1"
            assert body["query"] == "alpha"
            assert [row["id"] for row in body["results"]] == ["high", "low"]
            assert body["results"][0]["score"] >= body["results"][1]["score"]
        finally:
            store.close()

    def test_search_contract_has_no_chat_or_prompt_fields(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            store.upsert_node("g1", {"id": "n1", "label": "Ventas", "type": "Dataset", "details": {}})
            client = _api_client(store, tmp_path)

            resp = client.get("/api/search", params={"graph_id": "g1", "q": "ventas"})

            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert set(body) == {"graph_id", "query", "results"}
            forbidden = {"prompt", "messages", "completion", "tokens", "stream", "chat"}
            assert forbidden.isdisjoint(body)
            for row in body["results"]:
                assert forbidden.isdisjoint(row)
                assert set(row).issuperset({"id", "label", "type", "score"})
        finally:
            store.close()

    def test_search_empty_query_returns_422(self, tmp_path: Path) -> None:
        store = _store_with_graph(tmp_path)
        try:
            client = _api_client(store, tmp_path)
            resp = client.get("/api/search", params={"graph_id": "g1", "q": "   "})
            assert resp.status_code == 422
        finally:
            store.close()
