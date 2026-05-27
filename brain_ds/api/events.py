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
]


class EventEnvelope(TypedDict):
    event: EventName
    graph_id: str
    payload: dict[str, Any]
    timestamp: str


class EventBus:
    """In-memory pub/sub bus used by API routes and WebSocket streams."""

    def __init__(self) -> None:
        self._subscribers: set[Queue[EventEnvelope]] = set()

    def subscribe(self) -> Queue[EventEnvelope]:
        queue: Queue[EventEnvelope] = Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: Queue[EventEnvelope]) -> None:
        self._subscribers.discard(queue)

    async def publish(self, event: EventName, graph_id: str, payload: dict[str, Any]) -> EventEnvelope:
        envelope: EventEnvelope = {
            "event": event,
            "graph_id": graph_id,
            "payload": payload,
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
        for subscriber in self._subscribers:
            await subscriber.put(envelope)
        return envelope
