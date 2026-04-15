from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from threading import RLock
from uuid import uuid4

from src.shared.schemas import TaskEventRecord


@dataclass(slots=True)
class EventSubscription:
    subscription_id: str
    task_run_id: str
    queue: asyncio.Queue[TaskEventRecord]


class InMemoryEventBus:
    """Process-local event bus for real-time run event fanout."""

    def __init__(self, *, queue_size: int = 256):
        self._queue_size = queue_size
        self._lock = RLock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._run_subscribers: dict[str, dict[str, asyncio.Queue[TaskEventRecord]]] = defaultdict(dict)
        self._closed = False

    def attach_loop(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        resolved_loop = loop or asyncio.get_running_loop()
        with self._lock:
            if self._closed:
                raise RuntimeError("event_bus_closed")
            if self._loop is None:
                self._loop = resolved_loop

    async def subscribe_run(self, task_run_id: str) -> EventSubscription:
        self.attach_loop()
        queue: asyncio.Queue[TaskEventRecord] = asyncio.Queue(maxsize=self._queue_size)
        subscription = EventSubscription(
            subscription_id=uuid4().hex,
            task_run_id=task_run_id,
            queue=queue,
        )
        with self._lock:
            self._run_subscribers[task_run_id][subscription.subscription_id] = queue
        return subscription

    def unsubscribe(self, subscription: EventSubscription) -> None:
        with self._lock:
            subscribers = self._run_subscribers.get(subscription.task_run_id)
            if not subscribers:
                return
            subscribers.pop(subscription.subscription_id, None)
            if not subscribers:
                self._run_subscribers.pop(subscription.task_run_id, None)

    def publish(self, event: TaskEventRecord) -> None:
        if event.task_run_id is None:
            return
        with self._lock:
            if self._closed or self._loop is None:
                return
            subscribers = list(self._run_subscribers.get(event.task_run_id, {}).values())
            loop = self._loop
        if loop is None or not subscribers:
            return
        for queue in subscribers:
            loop.call_soon_threadsafe(self._enqueue_event, queue, event)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._run_subscribers.clear()
            self._loop = None

    @staticmethod
    def _enqueue_event(queue: asyncio.Queue[TaskEventRecord], event: TaskEventRecord) -> None:
        try:
            queue.put_nowait(event)
            return
        except asyncio.QueueFull:
            pass

        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            return

        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            return
