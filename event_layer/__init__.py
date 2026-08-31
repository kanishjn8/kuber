"""Typed event contracts and transport-independent delivery primitives."""

from event_layer.bus import ConsumedEvent, EventBus, InMemoryEventBus, PublishedEvent
from event_layer.contracts import EventEnvelope, EventType
from event_layer.deduplication import InMemoryDeduplicationStore
from event_layer.kafka import KafkaEventBus
from event_layer.locks import InMemoryWorkloadLockManager, workload_lock_key
from event_layer.topics import Topic
from event_layer.trajectory import EventTrajectoryRecorder

__all__ = [
    "ConsumedEvent",
    "EventBus",
    "EventEnvelope",
    "EventTrajectoryRecorder",
    "EventType",
    "InMemoryDeduplicationStore",
    "InMemoryEventBus",
    "InMemoryWorkloadLockManager",
    "KafkaEventBus",
    "PublishedEvent",
    "Topic",
    "workload_lock_key",
]
