from __future__ import annotations

import asyncio
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from brain_ds.api.events import EventBus
from brain_ds.api.outbox import publish_outbox_batch
from brain_ds.mcp.tools import add_edge, delete_edge, delete_node, update_node
from brain_ds.store.graph_store import GraphStore


def _external_enqueue(db_path: Path, *, event: str, graph_id: str, payload: dict[str, object]) -> None:
    script = """
import json
import sqlite3
import sys
from datetime import datetime, timezone

db_path, event, graph_id, payload = sys.argv[1:5]
conn = sqlite3.connect(db_path)
conn.execute(
    \"\"\"
    INSERT INTO event_outbox(event, graph_id, payload, created_at, published)
    VALUES (?, ?, ?, ?, 0)
    \"\"\",
    (
        event,
        graph_id,
        payload,
        datetime.now(timezone.utc).isoformat(),
    ),
)
conn.commit()
conn.close()
"""
    subprocess.run(
        [sys.executable, "-c", script, str(db_path), event, graph_id, json.dumps(payload)],
        check=True,
        capture_output=True,
        text=True,
    )


class CrossProcessOutboxTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "store.db"
        self.store = GraphStore(str(self.db_path), allow_cross_thread=True)
        self.store.meta_repo.save_graph_meta(
            graph_id="g-1",
            workspace_root=self.temp_dir.name,
            workspace_path=self.temp_dir.name,
            project="brain_ds",
            org="brain_ds",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    async def asyncTearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def _last_outbox_row(self, event: str) -> tuple[str, str, str]:
        row = self.store.conn.execute(
            "SELECT event, graph_id, payload FROM event_outbox WHERE event = ? ORDER BY id DESC LIMIT 1",
            (event,),
        ).fetchone()
        self.assertIsNotNone(row)
        return row[0], row[1], row[2]

    def _seed_node(self, node_id: str, *, label: str = "Alpha", card_sections: list[dict[str, object]] | None = None) -> dict[str, object]:
        payload: dict[str, object] = {
            "graph_id": "g-1",
            "node_id": node_id,
            "label": label,
            "type": "Task",
            "supertype": "Work",
            "details": {"summary": label.lower()},
        }
        if card_sections is not None:
            payload["card_sections"] = card_sections
        return update_node(self.store, payload)

    def _seed_edge(self, *, source: str = "n-1", target: str = "n-2", label: str = "depends_on") -> dict[str, object]:
        self._seed_node(source, label="Source")
        self._seed_node(target, label="Target")
        return add_edge(
            self.store,
            {"graph_id": "g-1", "source": source, "target": target, "label": label},
        )

    async def test_external_process_enqueue_not_visible_without_snapshot_reset(self) -> None:
        bus = EventBus()
        subscriber = bus.subscribe()

        self.store.conn.execute("BEGIN")
        self.store.outbox_repo.get_unpublished_events()
        _external_enqueue(
            self.db_path,
            event="node.created",
            graph_id="g-1",
            payload={"id": "n-1", "label": "Alpha", "type": "Task"},
        )

        published = await publish_outbox_batch(self.store, bus)

        self.assertEqual(published, 1)
        received = await asyncio.wait_for(subscriber.get(), timeout=0.5)
        self.assertEqual(received["event"], "node.created")

    async def test_external_enqueue_visible_after_snapshot_reset(self) -> None:
        bus = EventBus()
        subscriber = bus.subscribe()

        self.store.conn.execute("BEGIN")
        self.store.outbox_repo.get_unpublished_events()
        _external_enqueue(
            self.db_path,
            event="edge.created",
            graph_id="g-1",
            payload={"id": "e-1", "source": "n-1", "target": "n-2"},
        )

        published = await publish_outbox_batch(self.store, bus)

        self.assertEqual(published, 1)
        received = await asyncio.wait_for(subscriber.get(), timeout=0.5)
        self.assertEqual(received["event"], "edge.created")
        self.assertEqual(received["payload"]["id"], "e-1")

    async def test_publish_outbox_batch_emits_ws_event_for_external_write(self) -> None:
        bus = EventBus()
        subscriber = bus.subscribe()

        _external_enqueue(
            self.db_path,
            event="node.updated",
            graph_id="g-1",
            payload={"id": "n-2", "label": "Beta", "card_sections": [{"title": "Summary", "content": "Ready"}]},
        )

        published = await publish_outbox_batch(self.store, bus)

        self.assertEqual(published, 1)
        received = await asyncio.wait_for(subscriber.get(), timeout=0.5)
        self.assertEqual(received["event"], "node.updated")
        self.assertEqual(received["graph_id"], "g-1")
        self.assertEqual(received["payload"]["card_sections"][0]["title"], "Summary")

    async def test_poller_does_not_hold_stale_wal_snapshot(self) -> None:
        bus = EventBus()
        subscriber = bus.subscribe()

        self.store.conn.execute("BEGIN")
        self.store.outbox_repo.get_unpublished_events()
        _external_enqueue(self.db_path, event="node.created", graph_id="g-1", payload={"id": "n-1"})
        first_published = await publish_outbox_batch(self.store, bus)
        first_event = await asyncio.wait_for(subscriber.get(), timeout=0.5)

        self.store.conn.execute("BEGIN")
        self.store.outbox_repo.get_unpublished_events()
        _external_enqueue(self.db_path, event="node.created", graph_id="g-1", payload={"id": "n-2"})
        second_published = await publish_outbox_batch(self.store, bus)
        second_event = await asyncio.wait_for(subscriber.get(), timeout=0.5)

        self.assertEqual(first_published, 1)
        self.assertEqual(second_published, 1)
        self.assertEqual(first_event["payload"]["id"], "n-1")
        self.assertEqual(second_event["payload"]["id"], "n-2")

    async def test_outbox_marks_published_idempotent_no_double_emit(self) -> None:
        bus = EventBus()
        subscriber = bus.subscribe()

        _external_enqueue(self.db_path, event="node.created", graph_id="g-1", payload={"id": "n-1"})

        first_published = await publish_outbox_batch(self.store, bus)
        first_event = await asyncio.wait_for(subscriber.get(), timeout=0.5)
        second_published = await publish_outbox_batch(self.store, bus)

        self.assertEqual(first_published, 1)
        self.assertEqual(first_event["payload"]["id"], "n-1")
        self.assertEqual(second_published, 0)

    async def test_event_payload_carries_card_sections_for_info_update(self) -> None:
        bus = EventBus()
        subscriber = bus.subscribe()
        self._seed_node(
            "n-card",
            card_sections=[{"title": "Owner", "content": "Ops", "icon": "", "order": 1}],
        )

        published = await publish_outbox_batch(self.store, bus)

        self.assertEqual(published, 2)
        first_event = await asyncio.wait_for(subscriber.get(), timeout=0.5)
        second_event = await asyncio.wait_for(subscriber.get(), timeout=0.5)
        node_event = first_event if first_event["event"] != "tool.invoked" else second_event
        self.assertEqual(node_event["event"], "node.created")
        self.assertEqual(node_event["payload"]["card_sections"][0]["title"], "Owner")

    async def test_delete_node_enqueues_deleted_event(self) -> None:
        bus = EventBus()
        subscriber = bus.subscribe()
        self._seed_node("n-delete")
        await publish_outbox_batch(self.store, bus)
        await asyncio.wait_for(subscriber.get(), timeout=0.5)
        await asyncio.wait_for(subscriber.get(), timeout=0.5)

        result = delete_node(self.store, {"graph_id": "g-1", "node_id": "n-delete"})

        self.assertEqual(result["deleted"], 1)
        event, graph_id, payload = self._last_outbox_row("node.deleted")
        self.assertEqual(event, "node.deleted")
        self.assertEqual(graph_id, "g-1")
        self.assertEqual(json.loads(payload), {"id": "n-delete", "graph_id": "g-1"})

    async def test_delete_edge_enqueues_deleted_event(self) -> None:
        bus = EventBus()
        subscriber = bus.subscribe()
        self._seed_edge()
        for _ in range(5):
            await publish_outbox_batch(self.store, bus)
            try:
                while True:
                    await asyncio.wait_for(subscriber.get(), timeout=0.05)
            except asyncio.TimeoutError:
                pass

        result = delete_edge(self.store, {"graph_id": "g-1", "source": "n-1", "target": "n-2"})

        self.assertEqual(result["deleted"], 1)
        event, graph_id, payload = self._last_outbox_row("edge.deleted")
        self.assertEqual(event, "edge.deleted")
        self.assertEqual(graph_id, "g-1")
        self.assertEqual(
            json.loads(payload),
            {"id": "n-1->n-2", "graph_id": "g-1", "source": "n-1", "target": "n-2"},
        )


if __name__ == "__main__":
    unittest.main()
