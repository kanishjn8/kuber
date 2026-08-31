from __future__ import annotations

import asyncio

import pytest

from event_layer import EventEnvelope, EventType, InMemoryEventBus, Topic


def event() -> EventEnvelope:
    return EventEnvelope(
        EventType.WORKLOAD_OPTIMIZATION_REQUESTED,
        run_id="run-1",
        correlation_id="correlation-1",
        payload={"task_id": "task-1", "workload_id": "payment-service"},
    )


def test_event_contract_round_trips_and_rejects_unknown_schema() -> None:
    original = event()
    assert EventEnvelope.from_json(original.to_json()) == original
    assert original.task_id == "task-1"
    assert original.workload_id == "payment-service"

    value = original.to_dict()
    value["schema_version"] = "99"
    with pytest.raises(ValueError, match="unsupported event schema"):
        EventEnvelope.from_dict(value)


def test_consumer_groups_retry_acknowledgement_and_dlq() -> None:
    async def exercise() -> None:
        bus = InMemoryEventBus(partitions=3)
        published = await bus.publish(Topic.OPTIMIZATION_REQUESTS, event(), key="c:n:payment")
        first_group = bus.consume(
            Topic.OPTIMIZATION_REQUESTS, consumer_group="workers", consumer_id="worker-1"
        )
        audit_group = bus.consume(
            Topic.OPTIMIZATION_REQUESTS, consumer_group="audit", consumer_id="audit-1"
        )
        first = await anext(first_group)
        audit = await anext(audit_group)
        assert first.event.event_id == published.event.event_id == audit.event.event_id
        assert first.partition == bus._partition_for("c:n:payment")

        await bus.retry(first, reason="transient")
        retried = await anext(first_group)
        assert retried.delivery_count == 2
        assert retried.event.attempt == 1
        await bus.acknowledge(retried)

        await bus.dead_letter(audit, reason="invalid")
        dlq = bus.topic_events(Topic.DLQ)
        assert len(dlq) == 1
        assert dlq[0].event.event_type == EventType.DEAD_LETTERED
        await bus.close()

    asyncio.run(exercise())


def test_same_key_has_stable_partition_and_empty_key_is_rejected() -> None:
    async def exercise() -> None:
        bus = InMemoryEventBus(partitions=5)
        one = await bus.publish("topic", event(), key="cluster:namespace:service")
        two = await bus.publish("topic", event(), key="cluster:namespace:service")
        assert one.partition == two.partition
        assert (one.offset, two.offset) == (0, 1)
        with pytest.raises(ValueError, match="key"):
            await bus.publish("topic", event(), key="")

    asyncio.run(exercise())
