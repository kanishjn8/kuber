from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from time import perf_counter
from typing import Protocol, runtime_checkable

from agent_layer.graphs import WorkloadOptimizationGraph
from agent_layer.interfaces import EnvironmentAdapter
from context_layer import ContextStore, IndexedServiceContext
from event_layer.bus import ConsumedEvent, EventBus
from event_layer.contracts import EventEnvelope, EventType
from event_layer.deduplication import DeduplicationStore, InMemoryDeduplicationStore
from event_layer.locks import WorkloadLockManager, workload_lock_key
from event_layer.topics import OPTIMIZATION_CONSUMER_GROUP, Topic
from rules_engine.rbac.canonicalizer import effective_permission_count, expand_policy


@runtime_checkable
class EnvironmentFactory(Protocol):
    def create(
        self, event: EventEnvelope, context: IndexedServiceContext
    ) -> EnvironmentAdapter: ...


@dataclass(slots=True)
class WorkerStats:
    claimed: int = 0
    completed: int = 0
    failed: int = 0
    retried: int = 0
    duplicates: int = 0


class OptimizationWorker:
    """Consumes one task at a time and acknowledges only after durable completion."""

    def __init__(
        self,
        *,
        worker_id: str,
        event_bus: EventBus,
        context_store: ContextStore,
        lock_manager: WorkloadLockManager,
        environment_factory: EnvironmentFactory,
        graph: WorkloadOptimizationGraph,
        cluster: str = "kind-kuber",
        max_delivery_attempts: int = 3,
        deduplication_store: DeduplicationStore | None = None,
    ) -> None:
        self.worker_id = worker_id
        self.event_bus = event_bus
        self.context_store = context_store
        self.lock_manager = lock_manager
        self.environment_factory = environment_factory
        self.graph = graph
        self.cluster = cluster
        self.max_delivery_attempts = max_delivery_attempts
        self.deduplication_store = deduplication_store or InMemoryDeduplicationStore()
        self.stats = WorkerStats()

    async def run(self) -> None:
        async for message in self.event_bus.consume(
            Topic.OPTIMIZATION_REQUESTS,
            consumer_group=OPTIMIZATION_CONSUMER_GROUP,
            consumer_id=self.worker_id,
        ):
            await self.process(message)

    async def run_one(self) -> None:
        messages = self.event_bus.consume(
            Topic.OPTIMIZATION_REQUESTS,
            consumer_group=OPTIMIZATION_CONSUMER_GROUP,
            consumer_id=self.worker_id,
        )
        await self.process(await anext(messages))

    async def process(self, message: ConsumedEvent) -> None:
        event = message.event
        self.stats.claimed += 1
        try:
            task_id, workload_id, namespace, context = self._validate(event)
        except (KeyError, ValueError) as error:
            self.stats.failed += 1
            await self.event_bus.dead_letter(message, reason=f"invalid task: {error}")
            return

        completed_result = await self.deduplication_store.get(task_id)
        if completed_result is not None:
            self.stats.duplicates += 1
            duplicate = EventEnvelope(
                EventType.WORKLOAD_OPTIMIZATION_COMPLETED,
                run_id=event.run_id,
                correlation_id=event.correlation_id,
                causation_id=event.event_id,
                payload=completed_result,
            )
            await self.event_bus.publish(Topic.OPTIMIZATION_RESULTS, duplicate, key=message.key)
            await self.event_bus.acknowledge(message)
            return

        key = workload_lock_key(self.cluster, namespace, workload_id)
        environment: EnvironmentAdapter | None = None
        try:
            async with self.lock_manager.acquire(key):
                environment = self.environment_factory.create(event, context)
                started = perf_counter()
                execution = await asyncio.to_thread(
                    self.graph.run,
                    environment,
                    run_id=event.run_id,
                    task_id=task_id,
                    workload_id=workload_id,
                    context_ref=context.context_ref,
                    repository_ref=str(event.payload["repository_ref"]),
                )
                result_payload = {
                    "task_id": task_id,
                    "workload_id": workload_id,
                    "worker_id": self.worker_id,
                    "accepted": execution.accepted,
                    "repairs": execution.repair_iterations,
                    "original_risk": execution.original_risk.score,
                    "final_risk": execution.final_risk.score,
                    "original_permissions": effective_permission_count(execution.original_policy),
                    "final_permissions": effective_permission_count(execution.final_policy),
                    "high_risk_permissions_remaining": sum(
                        permission.verb == "*"
                        or permission.resource == "*"
                        or permission.resource == "secrets"
                        or permission.verb in {"create", "delete"}
                        for permission in execution.final_policy.permissions
                    ),
                    "cluster_wide_grants_remaining": sum(
                        permission.namespace is None
                        for permission in expand_policy(execution.final_policy).permissions
                    ),
                    "incorrect_removals": execution.incorrect_removals,
                    "tests_passed": execution.verification.tests_passed,
                    "tests_total": execution.verification.tests_total,
                    "processing_seconds": perf_counter() - started,
                }
                result = EventEnvelope(
                    EventType.WORKLOAD_OPTIMIZATION_COMPLETED,
                    run_id=event.run_id,
                    correlation_id=event.correlation_id,
                    causation_id=event.event_id,
                    payload=result_payload,
                )
                # Publishing the durable result follows the final graph checkpoint.
                # Only then is the request offset/queue item acknowledged.
                await self.deduplication_store.put(task_id, result_payload)
                await self.event_bus.publish(Topic.OPTIMIZATION_RESULTS, result, key=message.key)
                await self.event_bus.acknowledge(message)
                self.stats.completed += 1
        except Exception as error:
            if environment is not None:
                with suppress(Exception):
                    environment.restore_policy()
            if event.attempt + 1 < self.max_delivery_attempts:
                self.stats.retried += 1
                await self.event_bus.retry(message, reason=type(error).__name__)
            else:
                self.stats.failed += 1
                await self.event_bus.dead_letter(message, reason=f"{type(error).__name__}: {error}")

    def _validate(self, event: EventEnvelope) -> tuple[str, str, str, IndexedServiceContext]:
        if event.event_type != EventType.WORKLOAD_OPTIMIZATION_REQUESTED:
            raise ValueError(f"unexpected event type {event.event_type}")
        task_id = str(event.payload["task_id"])
        workload_id = str(event.payload["workload_id"])
        namespace = str(event.payload["namespace"])
        context_ref = str(event.payload["context_ref"])
        if not all((task_id, workload_id, namespace, context_ref)):
            raise ValueError("task identifiers must not be empty")
        context = self.context_store.get(context_ref)
        if context is None:
            raise ValueError(f"unknown context_ref {context_ref}")
        if context.service_id != workload_id:
            raise ValueError("context belongs to a different workload")
        return task_id, workload_id, namespace, context
