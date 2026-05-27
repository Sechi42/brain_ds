import json
import sqlite3
import unittest

from brain_ds.store.migrations import apply_pending
from brain_ds.store.repository import OutboxRepository


class TestOutboxRepository(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        apply_pending(self.conn)
        self.repo = OutboxRepository(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_enqueue_event_inserts_row(self) -> None:
        payload = {"id": "n-1", "label": "Node"}
        self.repo.enqueue_event("node.created", "g-1", payload)

        row = self.conn.execute(
            "SELECT event, graph_id, payload, published FROM event_outbox ORDER BY id ASC LIMIT 1"
        ).fetchone()
        self.assertEqual(row[0], "node.created")
        self.assertEqual(row[1], "g-1")
        self.assertEqual(json.loads(row[2]), payload)
        self.assertEqual(row[3], 0)

    def test_get_unpublished_returns_published_false(self) -> None:
        self.repo.enqueue_event("node.created", "g-1", {"id": "n-1"})
        self.repo.enqueue_event("node.updated", "g-1", {"id": "n-1", "label": "Renamed"})
        rows = self.repo.get_unpublished_events(limit=1)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event"], "node.created")
        self.assertEqual(rows[0]["published"], 0)

    def test_mark_published_sets_flag(self) -> None:
        self.repo.enqueue_event("node.created", "g-1", {"id": "n-1"})
        rows = self.repo.get_unpublished_events(limit=10)
        event_id = int(rows[0]["id"])

        self.repo.mark_published([event_id])

        published = self.conn.execute(
            "SELECT published FROM event_outbox WHERE id = ?",
            (event_id,),
        ).fetchone()[0]
        self.assertEqual(published, 1)

    def test_purge_removes_published_rows(self) -> None:
        self.repo.enqueue_event("node.created", "g-1", {"id": "n-1"})
        self.repo.enqueue_event("node.updated", "g-1", {"id": "n-1"})
        rows = self.repo.get_unpublished_events(limit=10)
        self.repo.mark_published([int(rows[0]["id"])])

        self.repo.purge_published_events()

        remaining = self.conn.execute("SELECT event, published FROM event_outbox ORDER BY id ASC").fetchall()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0][0], "node.updated")
        self.assertEqual(remaining[0][1], 0)


if __name__ == "__main__":
    unittest.main()
