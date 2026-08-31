from __future__ import annotations

import importlib
from collections.abc import AsyncIterator, Callable
from typing import Any

from event_layer.bus import ConsumedEvent, EventBus, PublishedEvent
from event_layer.contracts import EventEnvelope, EventType
from event_layer.topics import Topic


class KafkaEventBus(EventBus):
    """Kafka transport with keyed records and manual offset commits.

    ``aiokafka`` is imported lazily so judge mode has no Kafka client or broker
    runtime requirement. A message is committed only through ``acknowledge``.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        *,
        client_id: str = "kuber",
        event_callback: Callable[[str, PublishedEvent], None] | None = None,
    ) -> None:
        self.bootstrap_servers = bootstrap_servers
        self.client_id = client_id
        self._producer: Any = None
        self._consumers: dict[tuple[str, str], Any] = {}
        self.event_callback = event_callback

    @staticmethod
    def _aiokafka() -> Any:
        try:
            return importlib.import_module("aiokafka")
        except ModuleNotFoundError as error:
            raise RuntimeError(
                "Kafka support requires the 'distributed' or 'kubernetes' project extra"
            ) from error

    async def _get_producer(self) -> Any:
        if self._producer is None:
            module = self._aiokafka()
            self._producer = module.AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                client_id=self.client_id,
                acks="all",
                enable_idempotence=True,
            )
            await self._producer.start()
        return self._producer

    async def publish(self, topic: str, event: EventEnvelope, *, key: str) -> PublishedEvent:
        if not key:
            raise ValueError("event key must not be empty")
        producer = await self._get_producer()
        metadata = await producer.send_and_wait(topic, event.to_json(), key=key.encode())
        published = PublishedEvent(topic, key, metadata.partition, metadata.offset, event)
        if self.event_callback is not None:
            self.event_callback("published", published)
        return published

    async def _consume(
        self, topic: str, consumer_group: str, consumer_id: str
    ) -> AsyncIterator[ConsumedEvent]:
        module = self._aiokafka()
        consumer = module.AIOKafkaConsumer(
            topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=consumer_group,
            client_id=consumer_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        identity = (consumer_group, consumer_id)
        self._consumers[identity] = consumer
        await consumer.start()
        try:
            async for record in consumer:
                message = ConsumedEvent(
                    record.topic,
                    record.key.decode() if record.key else "",
                    record.partition,
                    record.offset,
                    EventEnvelope.from_json(record.value),
                    consumer_group,
                    consumer_id,
                )
                if self.event_callback is not None:
                    self.event_callback("claimed", message)
                yield message
        finally:
            await consumer.stop()
            self._consumers.pop(identity, None)

    def consume(
        self, topic: str, *, consumer_group: str, consumer_id: str
    ) -> AsyncIterator[ConsumedEvent]:
        return self._consume(topic, consumer_group, consumer_id)

    async def acknowledge(self, message: ConsumedEvent) -> None:
        consumer = self._consumers.get((message.consumer_group, message.consumer_id))
        if consumer is None:
            raise RuntimeError("consumer is not active")
        structs = importlib.import_module("aiokafka.structs")
        partition = structs.TopicPartition(message.topic, message.partition)
        offset = structs.OffsetAndMetadata(message.offset + 1, "")
        await consumer.commit({partition: offset})
        if self.event_callback is not None:
            self.event_callback("acknowledged", message)

    async def retry(self, message: ConsumedEvent, *, reason: str) -> None:
        if not reason:
            raise ValueError("retry reason must not be empty")
        await self.publish(message.topic, message.event.next_attempt(), key=message.key)
        await self.acknowledge(message)

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
        for consumer in tuple(self._consumers.values()):
            await consumer.stop()
        self._consumers.clear()
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None
