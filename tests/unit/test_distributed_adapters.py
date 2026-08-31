from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from event_layer import EventEnvelope, EventType
from event_layer.bus import ConsumedEvent
from event_layer.deduplication import RedisDeduplicationStore
from event_layer.kafka import KafkaEventBus
from event_layer.locks import RedisWorkloadLockManager, workload_lock_key
from event_layer.trajectory import EventTrajectoryRecorder


def request() -> EventEnvelope:
    return EventEnvelope(
        EventType.WORKLOAD_OPTIMIZATION_REQUESTED,
        run_id="run",
        correlation_id="run",
        payload={"task_id": "task", "workload_id": "payment-service"},
    )


class FakeProducer:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.started = False
        self.stopped = False
        self.sent: list[tuple[str, bytes, bytes]] = []

    async def start(self) -> None:
        self.started = True

    async def send_and_wait(self, topic: str, value: bytes, *, key: bytes) -> Any:
        self.sent.append((topic, value, key))
        return SimpleNamespace(partition=2, offset=7)

    async def stop(self) -> None:
        self.stopped = True


class FakeConsumer:
    def __init__(self, *topics: str, **kwargs: Any) -> None:
        self.topics = topics
        self.kwargs = kwargs
        self.commits: list[object] = []
        self.stopped = False

    async def start(self) -> None:
        return None

    def __aiter__(self) -> FakeConsumer:
        self._remaining = 1
        return self

    async def __anext__(self) -> Any:
        if not self._remaining:
            raise StopAsyncIteration
        self._remaining = 0
        return SimpleNamespace(
            topic="requests",
            key=b"cluster:namespace:payment-service",
            partition=1,
            offset=4,
            value=request().to_json(),
        )

    async def commit(self, value: object) -> None:
        self.commits.append(value)

    async def stop(self) -> None:
        self.stopped = True


def test_kafka_adapter_serializes_keys_consumes_and_manually_commits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def exercise() -> None:
        module = SimpleNamespace(AIOKafkaProducer=FakeProducer, AIOKafkaConsumer=FakeConsumer)
        stages: list[str] = []
        bus = KafkaEventBus(
            "broker:9092", event_callback=lambda stage, message: stages.append(stage)
        )
        monkeypatch.setattr(bus, "_aiokafka", lambda: module)

        published = await bus.publish(
            "requests", request(), key="cluster:namespace:payment-service"
        )
        assert published.partition == 2 and published.offset == 7
        producer = bus._producer
        assert producer.kwargs["enable_idempotence"] is True
        assert (
            producer.sent[0][1] == request().to_json()
            or EventEnvelope.from_json(producer.sent[0][1]).event_type
            == EventType.WORKLOAD_OPTIMIZATION_REQUESTED
        )

        values = [
            message
            async for message in bus.consume(
                "requests", consumer_group="workers", consumer_id="worker-1"
            )
        ]
        assert len(values) == 1
        # The iterator closes its consumer, so register a fake active consumer
        # to exercise explicit offset+1 commit independently.
        consumer = FakeConsumer()
        bus._consumers[("workers", "worker-1")] = consumer
        await bus.acknowledge(values[0])
        assert consumer.commits
        await bus.close()
        assert stages == ["published", "claimed", "acknowledged"]

    asyncio.run(exercise())


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.closed = False
        self.lock_value = FakeLock()

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, **kwargs: object) -> None:
        self.values[key] = value

    def lock(self, *args: object, **kwargs: object) -> FakeLock:
        return self.lock_value

    async def aclose(self) -> None:
        self.closed = True


class FakeLock:
    def __init__(self) -> None:
        self.allowed = True
        self.released = False

    async def acquire(self) -> bool:
        return self.allowed

    async def release(self) -> None:
        self.released = True


def test_redis_deduplication_locking_and_event_trajectory(tmp_path: Path) -> None:
    async def exercise() -> None:
        redis = FakeRedis()
        dedup = RedisDeduplicationStore("redis://unused")
        dedup._client = redis
        assert await dedup.get("task") is None
        await dedup.put("task", {"accepted": True})
        assert await dedup.get("task") == {"accepted": True}

        locks = RedisWorkloadLockManager("redis://unused")
        locks._client = redis
        async with locks.acquire(workload_lock_key("kind", "sandbox", "payment")):
            pass
        assert redis.lock_value.released
        await locks.close()
        assert redis.closed

        recorder = EventTrajectoryRecorder(tmp_path)
        message = ConsumedEvent("requests", "key", 0, 1, request(), "workers", "worker-1")
        recorder("claimed", message)
        path = tmp_path / "run" / "payment-service-events.jsonl"
        assert '"consumer_id":"worker-1"' in path.read_text(encoding="utf-8")

    asyncio.run(exercise())


def test_redis_lock_timeout_and_lock_key_validation() -> None:
    async def exercise() -> None:
        redis = FakeRedis()
        redis.lock_value.allowed = False
        locks = RedisWorkloadLockManager("redis://unused")
        locks._client = redis
        with pytest.raises(TimeoutError, match="payment"):
            async with locks.acquire("kind:sandbox:payment"):
                pass

    asyncio.run(exercise())
    with pytest.raises(ValueError, match="components"):
        workload_lock_key("kind", "bad:namespace", "payment")
