"""Live updates over Server-Sent Events (I5).

An in-process publish/subscribe bus: every `GET /api/events` connection subscribes, and the server
publishes events such as `case.ended` (README "SSE events"). The events are internal to the App
track, not a contract. Each subscriber has its own queue, so a slow browser tab never holds up
another; if a queue fills up, that subscriber is dropped and its browser reconnects (`retry`).
"""

import asyncio
import itertools
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

RETRY_MS = 3000
"""How long a browser waits before reconnecting (the SSE `retry` field)."""
HEARTBEAT_S = 15.0
"""A comment line this often keeps proxies from closing an idle stream."""
QUEUE_SIZE = 100


@dataclass(frozen=True)
class Event:
    id: int
    name: str
    data: dict[str, Any]

    def encode(self) -> str:
        """The SSE wire form: `id`, `event` and one `data` line of JSON, then a blank line."""
        payload = json.dumps(self.data, ensure_ascii=False, separators=(",", ":"))
        return f"id: {self.id}\nevent: {self.name}\ndata: {payload}\n\n"


class EventBus:
    """Fan-out of events to every subscriber. Use from the server's event loop only."""

    def __init__(self, queue_size: int = QUEUE_SIZE) -> None:
        self._ids = itertools.count(1)
        self._queue_size = queue_size
        self._subscribers: set[asyncio.Queue[Event | None]] = set()

    @property
    def subscribers(self) -> int:
        return len(self._subscribers)

    def publish(self, name: str, data: dict[str, Any]) -> Event:
        event = Event(next(self._ids), name, data)
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Too slow: drop it; `None` ends its stream and the browser reconnects.
                self._subscribers.discard(queue)
                queue.get_nowait()
                queue.put_nowait(None)
        return event

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[Event | None]]:
        queue: asyncio.Queue[Event | None] = asyncio.Queue(self._queue_size)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)


async def stream(
    bus: EventBus,
    is_disconnected: Any,
    heartbeat_s: float = HEARTBEAT_S,
) -> AsyncIterator[str]:
    """The body of one `GET /api/events` response.

    `is_disconnected` is the request's async `is_disconnected()`; the stream ends when the client
    goes away or the bus drops it.
    """
    async with bus.subscribe() as queue:
        yield f"retry: {RETRY_MS}\n: connected\n\n"
        while not await is_disconnected():
            try:
                event = await asyncio.wait_for(queue.get(), heartbeat_s)
            except TimeoutError:
                yield ": ping\n\n"
                continue
            if event is None:
                return
            yield event.encode()
