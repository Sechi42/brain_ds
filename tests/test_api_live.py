from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from brain_ds.api.events import EventBus
from brain_ds.api.server import create_app
from brain_ds.ontology import Graph
from brain_ds.store.graph_store import GraphStore


def _seed_graph(store: GraphStore, *, graph_id: str) -> None:
    store.save_graph(
        Graph.from_v1(
            {
            "imported_from": f"/tmp/{graph_id}.json",
            "org": "Live Org",
            "generated_at": "2026-05-25T00:00:00Z",
            "nodes": [{"id": "n-root", "label": "Root", "type": "Department"}],
            "edges": [],
            "evidence": [],
            }
        ),
        graph_id=graph_id,
        workspace_root="/tmp",
    )


class TestApiLive(unittest.TestCase):
    def test_nodes_crud_and_query_by_graph_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_path = root / "store.db"
            store = GraphStore(str(store_path), allow_cross_thread=True)
            try:
                _seed_graph(store, graph_id="g-live")
                app = create_app(project_root=root, store=store)

                with TestClient(app) as client:
                    create_response = client.post(
                        "/api/nodes",
                        json={
                            "graph_id": "g-live",
                            "node": {
                                "id": "n-1",
                                "label": "Live Node",
                                "type": "Concept",
                                "details": {"source": "api"},
                            },
                        },
                    )
                    self.assertEqual(create_response.status_code, 201)
                    self.assertEqual(create_response.json()["node"]["id"], "n-1")

                    list_response = client.get("/api/nodes", params={"graph_id": "g-live"})
                    self.assertEqual(list_response.status_code, 200)
                    payload = list_response.json()
                    self.assertEqual(payload["graph_id"], "g-live")
                    node_ids = [item["id"] for item in payload["nodes"]]
                    self.assertIn("n-1", node_ids)

                    patch_response = client.patch(
                        "/api/nodes/n-1",
                        json={"graph_id": "g-live", "changes": {"label": "Live Node Updated"}},
                    )
                    self.assertEqual(patch_response.status_code, 200)
                    self.assertEqual(patch_response.json()["node"]["label"], "Live Node Updated")
            finally:
                store.close()

    def test_rest_write_publishes_matching_websocket_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = GraphStore(str(root / "store.db"), allow_cross_thread=True)
            try:
                _seed_graph(store, graph_id="g-events")
                app = create_app(project_root=root, store=store)

                with TestClient(app) as client:
                    with client.websocket_connect("/api/events?graph_id=g-events") as websocket:
                        response = client.post(
                            "/api/nodes",
                            json={
                                "graph_id": "g-events",
                                "node": {"id": "n-live", "label": "Node", "type": "Concept"},
                            },
                        )
                        self.assertEqual(response.status_code, 201)

                        event = websocket.receive_json()
                        self.assertEqual(event["event"], "node.created")
                        self.assertEqual(event["graph_id"], "g-events")
                        self.assertEqual(event["payload"]["id"], "n-live")
                        self.assertIn("timestamp", event)
            finally:
                store.close()

    def test_edges_create_and_query_by_graph_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = GraphStore(str(root / "store.db"), allow_cross_thread=True)
            try:
                _seed_graph(store, graph_id="g-edges")
                app = create_app(project_root=root, store=store)

                with TestClient(app) as client:
                    create_response = client.post(
                        "/api/edges",
                        json={
                            "graph_id": "g-edges",
                            "edge": {
                                "source": "n-root",
                                "target": "n-root",
                                "label": "relates_to",
                                "weight": 0.9,
                            },
                        },
                    )
                    self.assertEqual(create_response.status_code, 201)

                    list_response = client.get("/api/edges", params={"graph_id": "g-edges"})
                    self.assertEqual(list_response.status_code, 200)
                    payload = list_response.json()
                    self.assertEqual(payload["graph_id"], "g-edges")
                    self.assertEqual(len(payload["edges"]), 1)
                    self.assertEqual(payload["edges"][0]["source"], "n-root")
            finally:
                store.close()

    def test_patch_node_re_queries_full_node_publishes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = GraphStore(str(root / "store.db"), allow_cross_thread=True)
            try:
                _seed_graph(store, graph_id="g-patch")
                store.upsert_node(
                    "g-patch",
                    {
                        "id": "n-1",
                        "label": "Before",
                        "type": "Concept",
                        "card_sections": [{"title": "Summary", "content": "old", "icon": "", "order": 1}],
                    },
                )
                app = create_app(project_root=root, store=store)

                with TestClient(app) as client:
                    with client.websocket_connect("/api/events?graph_id=g-patch") as websocket:
                        response = client.patch(
                            "/api/nodes/n-1",
                            json={
                                "graph_id": "g-patch",
                                "changes": {
                                    "card_sections": [{"title": "Summary", "content": "updated", "icon": "", "order": 1}]
                                },
                            },
                        )
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.json()["node"]["id"], "n-1")
                        self.assertEqual(response.json()["node"]["label"], "Before")
                        self.assertEqual(response.json()["node"]["card_sections"][0]["content"], "updated")

                        event = websocket.receive_json()
                        self.assertEqual(event["event"], "node.updated")
                        self.assertEqual(event["payload"]["id"], "n-1")
                        self.assertEqual(event["payload"]["label"], "Before")
                        self.assertEqual(event["payload"]["card_sections"][0]["content"], "updated")
            finally:
                store.close()

    def test_patch_missing_4xx_no_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = GraphStore(str(root / "store.db"), allow_cross_thread=True)
            try:
                _seed_graph(store, graph_id="g-missing")
                bus = EventBus()
                app = create_app(project_root=root, store=store, event_bus=bus)

                with TestClient(app) as client:
                    response = client.patch(
                        "/api/nodes/n-404",
                        json={"graph_id": "g-missing", "changes": {"label": "nope"}},
                    )
                    self.assertEqual(response.status_code, 404)
                    self.assertEqual(bus._seq, 0)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
