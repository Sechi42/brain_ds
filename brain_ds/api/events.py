from __future__ import annotations

from asyncio import Queue
from datetime import UTC, datetime
from typing import Any, Literal, TypedDict


EventName = Literal[
    "node.created",
    "node.updated",
    "node.deleted",
    "edge.created",
    "edge.updated",
    "edge.deleted",
    "tool.invoked",
]


class EventEnvelope(TypedDict):
    event: EventName
    graph_id: str
    payload: dict[str, Any]
    timestamp: str
    sequence_id: int
    highlight_type: str | None


class EventBus:
    """In-memory pub/sub bus used by API routes and WebSocket streams."""

    def __init__(self) -> None:
        self._subscribers: set[Queue[EventEnvelope]] = set()
        self._seq = 0

    def subscribe(self) -> Queue[EventEnvelope]:
        queue: Queue[EventEnvelope] = Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: Queue[EventEnvelope]) -> None:
        self._subscribers.discard(queue)

    async def publish(self, event: EventName, graph_id: str, payload: dict[str, Any]) -> EventEnvelope:
        self._seq += 1
        highlight_type = None
        if event.endswith(".created"):
            highlight_type = "create"
        elif event.endswith(".updated"):
            highlight_type = "update"
        elif event.endswith(".deleted"):
            highlight_type = "delete"

        envelope: EventEnvelope = {
            "event": event,
            "graph_id": graph_id,
            "payload": payload,
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "sequence_id": self._seq,
            "highlight_type": highlight_type,
        }
        for subscriber in self._subscribers:
            await subscriber.put(envelope)
        return envelope
