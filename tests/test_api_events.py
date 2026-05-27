from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from brain_ds.api.events import EventBus
from brain_ds.api.outbox import publish_outbox_batch
from brain_ds.api.receipt_store import ActionReceipt, ReceiptStore
from brain_ds.store.graph_store import GraphStore


class EventBusTests(unittest.IsolatedAsyncioTestCase):
    async def test_publish_broadcasts_to_multiple_subscribers(self) -> None:
        bus = EventBus()
        subscriber_a = bus.subscribe()
        subscriber_b = bus.subscribe()

        payload = {"id": "n-1", "type": "Concept", "label": "Live node"}
        envelope = await bus.publish("node.created", graph_id="g-1", payload=payload)

        received_a = await asyncio.wait_for(subscriber_a.get(), timeout=0.5)
        received_b = await asyncio.wait_for(subscriber_b.get(), timeout=0.5)

        self.assertEqual(envelope, received_a)
        self.assertEqual(envelope, received_b)
        self.assertEqual(received_a["event"], "node.created")
        self.assertEqual(received_a["graph_id"], "g-1")

    async def test_publish_event_envelope_is_stable_and_typed(self) -> None:
        bus = EventBus()

        node_payload = {"id": "n-2", "type": "Concept", "label": "Typed"}
        edge_payload = {"edge_id": "e-1", "source": "n-1", "target": "n-2", "weight": 0.8}

        node_envelope = await bus.publish("node.updated", graph_id="g-2", payload=node_payload)
        edge_envelope = await bus.publish("edge.created", graph_id="g-2", payload=edge_payload)

        self.assertEqual(
            set(node_envelope.keys()),
            {"event", "graph_id", "payload", "timestamp", "sequence_id", "highlight_type"},
        )
        self.assertEqual(
            set(edge_envelope.keys()),
            {"event", "graph_id", "payload", "timestamp", "sequence_id", "highlight_type"},
        )
        self.assertEqual(node_envelope["payload"], node_payload)
        self.assertEqual(edge_envelope["payload"], edge_payload)
        self.assertIn("T", node_envelope["timestamp"])
        self.assertTrue(node_envelope["timestamp"].endswith("Z"))

    async def test_publish_stamps_monotonic_sequence_and_highlight_type(self) -> None:
        bus = EventBus()

        created = await bus.publish("node.created", graph_id="g-1", payload={"id": "n-1"})
        updated = await bus.publish("node.updated", graph_id="g-1", payload={"id": "n-1"})
        deleted = await bus.publish("edge.deleted", graph_id="g-1", payload={"id": "e-1"})

        self.assertEqual(created["sequence_id"], 1)
        self.assertEqual(updated["sequence_id"], 2)
        self.assertEqual(deleted["sequence_id"], 3)
        self.assertEqual(created["highlight_type"], "create")
        self.assertEqual(updated["highlight_type"], "update")
        self.assertEqual(deleted["highlight_type"], "delete")

    async def test_unsubscribe_cleans_up_subscriber(self) -> None:
        bus = EventBus()
        removed = bus.subscribe()
        active = bus.subscribe()

        bus.unsubscribe(removed)
        await bus.publish("node.created", graph_id="g-3", payload={"id": "n-1"})

        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(removed.get(), timeout=0.05)

        active_event = await asyncio.wait_for(active.get(), timeout=0.5)
        self.assertEqual(active_event["event"], "node.created")

    async def test_publish_with_no_subscribers_returns_envelope_without_error(self) -> None:
        bus = EventBus()

        envelope = await bus.publish(
            "node.updated",
            graph_id="g-4",
            payload={"id": "n-9", "label": "No listeners"},
        )

        self.assertEqual(envelope["event"], "node.updated")
        self.assertEqual(envelope["graph_id"], "g-4")
        self.assertEqual(envelope["payload"]["id"], "n-9")
class TestOutboxPoller(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "store.db"
        self.store = GraphStore(str(self.db_path), allow_cross_thread=True)
        self.store.meta_repo.save_graph_meta(
            graph_id="g-1",
            workspace_root=self.temp_dir.name,
            workspace_path=self.temp_dir.name,
            project="p",
            org="o",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at="",
        )

    async def asyncTearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    async def test_poller_publishes_and_marks_published(self) -> None:
        bus = EventBus()
        sub = bus.subscribe()
        self.store.enqueue_event("node.created", "g-1", {"id": "n-1"})

        published = await publish_outbox_batch(self.store, bus)
        self.assertEqual(published, 1)

        received = await asyncio.wait_for(sub.get(), timeout=0.5)
        self.assertEqual(received["event"], "node.created")
        self.assertEqual(received["graph_id"], "g-1")

        row = self.store.conn.execute("SELECT published FROM event_outbox ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(row[0], 1)

    async def test_poller_handles_empty_outbox(self) -> None:
        bus = EventBus()
        published = await publish_outbox_batch(self.store, bus)
        self.assertEqual(published, 0)

    async def test_poller_tool_invoked_populates_receipt_store(self) -> None:
        bus = EventBus()
        receipt_store = ReceiptStore(max_receipts=50)
        payload = {
            "timestamp": "2026-01-01T00:00:00Z",
            "tool": "update_node",
            "params_summary": "node=n-1 fields=label",
            "status": "ok",
            "graph_id": "g-1",
            "target_id": "n-1",
        }
        self.store.enqueue_event("tool.invoked", "g-1", payload)

        published = await publish_outbox_batch(self.store, bus, receipt_store=receipt_store)
        self.assertEqual(published, 1)

        receipts = receipt_store.list()
        self.assertEqual(len(receipts), 1)
        self.assertEqual(
            receipts[0],
            ActionReceipt(
                timestamp="2026-01-01T00:00:00Z",
                tool="update_node",
                params_summary="node=n-1 fields=label",
                status="ok",
                graph_id="g-1",
                target_id="n-1",
            ),
        )


if __name__ == "__main__":
    unittest.main()
