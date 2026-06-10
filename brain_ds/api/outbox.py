from __future__ import annotations

import asyncio
import json
import logging

from brain_ds.api.events import EventBus
from brain_ds.api.receipt_store import ActionReceipt, ReceiptStore
from brain_ds.store.graph_store import GraphStore

logger = logging.getLogger(__name__)


async def publish_outbox_batch(
    store: GraphStore,
    event_bus: EventBus,
    receipt_store: ReceiptStore | None = None,
) -> int:
    store.outbox_repo.conn.commit()
    rows = store.outbox_repo.get_unpublished_events(limit=50)
    if not rows:
        return 0

    published_ids: list[int] = []
    for row in rows:
        payload = json.loads(row["payload"]) if row["payload"] else {}
        await event_bus.publish(
            row["event"],
            graph_id=row["graph_id"],
            payload=payload,
        )
        if row["event"] == "tool.invoked" and receipt_store is not None:
            receipt_store.add(ActionReceipt(**payload))
        published_ids.append(int(row["id"]))

    store.outbox_repo.mark_published(published_ids)
    return len(published_ids)


async def outbox_poller(
    store: GraphStore,
    event_bus: EventBus,
    interval: float = 0.5,
    receipt_store: ReceiptStore | None = None,
) -> None:
    while True:
        try:
            await publish_outbox_batch(store, event_bus, receipt_store=receipt_store)
        except Exception:  # pragma: no cover
            logger.exception("Failed to publish outbox batch")
        await asyncio.sleep(interval)
