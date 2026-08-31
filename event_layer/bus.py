from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, replace
from typing import Protocol, runtime_checkable

from event_layer.contracts import EventEnvelope, EventType
from event_layer.topics import Topic


@dataclass(frozen=True, slots=True)
class PublishedEvent:
    topic: str
    key: str
    partition: int
    offset: int
    event: EventEnvelope


@dataclass(frozen=True, slots=True)
class ConsumedEvent(PublishedEvent):
    consumer_group: str
    consumer_id: str
    delivery_count: int = 1


@runtime_checkable
class EventBus(Protocol):
    async def publish(self, topic: str, event: EventEnvelope, *, key: str) -> PublishedEvent: ...

    def consume(
        self, topic: str, *, consumer_group: str, consumer_id: str
    ) -> AsyncIterator[ConsumedEvent]: ...

    async def acknowledge(self, message: ConsumedEvent) -> None: ...

    async def retry(self, message: ConsumedEvent, *, reason: str) -> None: ...

    async def dead_letter(self, message: ConsumedEvent, *, reason: str) -> PublishedEvent: ...

    async def close(self) -> None: ...


class InMemoryEventBus:
    """At-least-once event bus for tests and judge mode.

    Each consumer group owns one queue, so consumers in the same group divide
    work while separate groups receive independent copies. Events published
    before a group subscribes are replayed from the topic log.
    """

    def __init__(
        self,
        *,
        partitions: int = 3,
        event_callback: Callable[[str, PublishedEvent], None] | None = None,
    ) -> None:
        if partitions < 1:
            raise ValueError("partitions must be positive")
        self.partitions = partitions
        self._logs: dict[str, list[PublishedEvent]] = defaultdict(list)
        self._queues: dict[tuple[str, str], asyncio.Queue[ConsumedEvent]] = {}
        self._acknowledged: set[tuple[str, str, int, int]] = set()
        self._lock = asyncio.Lock()
        self._closed = False
        self.event_callback = event_callback

    async def publish(self, topic: str, event: EventEnvelope, *, key: str) -> PublishedEvent:
        if not key:
            raise ValueError("event key must not be empty")
        async with self._lock:
            self._ensure_open()
            partition = self._partition_for(key)
            offset = sum(item.partition == partition for item in self._logs[topic])
            published = PublishedEvent(topic, key, partition, offset, event)
            self._logs[topic].append(published)
            for (queued_topic, _), queue in self._queues.items():
                if queued_topic == topic:
                    queue.put_nowait(self._consumed(published, "", ""))
            if self.event_callback is not None:
                self.event_callback("published", published)
            return published

    async def _subscribe(self, topic: str, consumer_group: str) -> asyncio.Queue[ConsumedEvent]:
        group_key = (topic, consumer_group)
        async with self._lock:
            self._ensure_open()
            queue = self._queues.get(group_key)
            if queue is None:
                queue = asyncio.Queue()
                self._queues[group_key] = queue
                for item in self._logs[topic]:
                    queue.put_nowait(self._consumed(item, consumer_group, ""))
            return queue

    async def _consume(
        self, topic: str, consumer_group: str, consumer_id: str
    ) -> AsyncIterator[ConsumedEvent]:
        queue = await self._subscribe(topic, consumer_group)
        while not self._closed:
            message = await queue.get()
            if self._ack_key(message, consumer_group) in self._acknowledged:
                continue
            claimed = replace(message, consumer_group=consumer_group, consumer_id=consumer_id)
            if self.event_callback is not None:
                self.event_callback("claimed", claimed)
            yield claimed

    def consume(
        self, topic: str, *, consumer_group: str, consumer_id: str
    ) -> AsyncIterator[ConsumedEvent]:
        if not consumer_group or not consumer_id:
            raise ValueError("consumer_group and consumer_id must not be empty")
        return self._consume(topic, consumer_group, consumer_id)

    async def acknowledge(self, message: ConsumedEvent) -> None:
        async with self._lock:
            self._acknowledged.add(self._ack_key(message, message.consumer_group))
        if self.event_callback is not None:
            self.event_callback("acknowledged", message)

    async def retry(self, message: ConsumedEvent, *, reason: str) -> None:
        if not reason:
            raise ValueError("retry reason must not be empty")
        async with self._lock:
            queue = self._queues[(message.topic, message.consumer_group)]
            queue.put_nowait(
                replace(
                    message,
                    event=message.event.next_attempt(),
                    delivery_count=message.delivery_count + 1,
                )
            )

    async def dead_letter(self, message: ConsumedEvent, *, reason: str) -> PublishedEvent:
        event = EventEnvelope(
            EventType.DEAD_LETTERED,
            run_id=message.event.run_id,
            correlation_id=message.event.correlation_id,
            causation_id=message.event.event_id,
            attempt=message.event.attempt,
            payload={
                "source_topic": message.topic,
                "source_event": message.event.to_dict(),
                "reason": reason,
            },
        )
        published = await self.publish(Topic.DLQ, event, key=message.key)
        await self.acknowledge(message)
        return published

    async def close(self) -> None:
        self._closed = True

    def topic_events(self, topic: str) -> tuple[PublishedEvent, ...]:
        return tuple(self._logs[topic])

    def _partition_for(self, key: str) -> int:
        # Python's hash is process-randomized; this small stable hash keeps judge
        # runs reproducible while preserving same-key ordering.
        return sum(key.encode()) % self.partitions

    @staticmethod
    def _consumed(event: PublishedEvent, consumer_group: str, consumer_id: str) -> ConsumedEvent:
        return ConsumedEvent(
            event.topic,
            event.key,
            event.partition,
            event.offset,
            event.event,
            consumer_group,
            consumer_id,
        )

    @staticmethod
    def _ack_key(message: ConsumedEvent, group: str) -> tuple[str, str, int, int]:
        return (message.topic, group, message.partition, message.offset)

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("event bus is closed")
