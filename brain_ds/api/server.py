from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from brain_ds.api.events import EventBus
from brain_ds.api.outbox import outbox_poller
from brain_ds.api.routes import create_router
from brain_ds.store.graph_store import GraphStore


def create_app(*, project_root: Path, store: GraphStore, event_bus: EventBus | None = None) -> FastAPI:
    bus = event_bus or EventBus()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store.outbox_repo.purge_published_events()
        poller_task = asyncio.create_task(outbox_poller(store, bus, 0.5))
        app.state.outbox_poller_task = poller_task
        try:
            yield
        finally:
            poller_task.cancel()
            try:
                await poller_task
            except asyncio.CancelledError:
                pass

    app = FastAPI(title="brain_ds live workspace", lifespan=lifespan)
    app.state.project_root = project_root.resolve()
    app.state.store = store
    app.state.event_bus = bus
    app.include_router(create_router(store=store, event_bus=bus))
    return app
