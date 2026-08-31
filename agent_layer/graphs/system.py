from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from agent_layer.trajectory import TrajectoryEvent, TrajectoryRecorder
from context_layer import (
    IndexedServiceContext,
    ServiceContext,
    ServiceContextIndexer,
    ServiceDiscovery,
    ServiceRegistry,
)
from event_layer import EventBus, EventEnvelope, EventType, Topic


class SystemGraphState(TypedDict, total=False):
    run_id: str
    namespace: str
    services: tuple[ServiceContext, ...]
    contexts: tuple[IndexedServiceContext, ...]
    result_events: tuple[EventEnvelope, ...]
    expected_results: int
    system_passed: bool
    report_path: Path | None
    graph_node: str


@dataclass(frozen=True, slots=True)
class SystemRunResult:
    run_id: str
    namespace: str
    services: tuple[ServiceContext, ...]
    results: tuple[EventEnvelope, ...]
    system_passed: bool
    trajectory_path: Path | None
    report_path: Path | None = None


class SystemOptimizationGraph:
    """Namespace coordinator that dispatches work rather than running it inline."""

    def __init__(
        self,
        *,
        discovery: ServiceDiscovery,
        registry: ServiceRegistry,
        indexer: ServiceContextIndexer,
        event_bus: EventBus,
        cluster: str = "kind-kuber",
        result_timeout_seconds: float = 300,
        trajectory_directory: Path | None = Path("artifacts/trajectories"),
        report_directory: Path | None = None,
        event_callback: Callable[[TrajectoryEvent], None] | None = None,
        system_verifier: Callable[[], bool] | None = None,
        checkpointer: BaseCheckpointSaver[Any] | None = None,
    ) -> None:
        self.discovery = discovery
        self.registry = registry
        self.indexer = indexer
        self.event_bus = event_bus
        self.cluster = cluster
        self.result_timeout_seconds = result_timeout_seconds
        self.trajectory_directory = trajectory_directory
        self.report_directory = report_directory
        self.event_callback = event_callback
        self.system_verifier = system_verifier
        self.checkpointer = checkpointer or InMemorySaver()

    async def run(self, namespace: str, *, run_id: str | None = None) -> SystemRunResult:
        identifier = run_id or uuid4().hex
        recorder = TrajectoryRecorder(identifier, self.trajectory_directory)

        def record(state: SystemGraphState, action: str, reason: str) -> None:
            event = TrajectoryEvent(state["run_id"], "system", "system_graph", action, reason)
            recorder.record(event)
            if self.event_callback is not None:
                self.event_callback(event)

        graph = self._build(record)
        config = {"configurable": {"thread_id": f"system:{identifier}"}}
        final = cast(
            SystemGraphState,
            await graph.ainvoke(
                {"run_id": identifier, "namespace": namespace, "graph_node": "START"},
                config,
            ),
        )
        return SystemRunResult(
            identifier,
            namespace,
            final["services"],
            final["result_events"],
            final["system_passed"],
            recorder.write_summary(),
            final.get("report_path"),
        )

    def _write_report(self, state: SystemGraphState) -> Path | None:
        if self.report_directory is None:
            return None
        self.report_directory.mkdir(parents=True, exist_ok=True)
        path = self.report_directory / f"{state['run_id']}-namespace-report.md"
        rows = []
        for event in sorted(
            state["result_events"], key=lambda item: str(item.payload["workload_id"])
        ):
            value = event.payload
            status = "PASS" if value.get("accepted") else "FAIL"
            rows.append(
                f"| {value['workload_id']} | {value['worker_id']} | "
                f"{value['original_permissions']} → {value['final_permissions']} | "
                f"{value['original_risk']} → {value['final_risk']} | "
                f"{value['tests_passed']}/{value['tests_total']} | "
                f"{value['repairs']} | {status} |"
            )
        status = "PASS" if state["system_passed"] else "FAIL"
        path.write_text(
            f"# Kuber namespace report: {state['namespace']}\n\n"
            f"- Run ID: `{state['run_id']}`\n"
            f"- Services discovered: {len(state['services'])}\n"
            f"- Workload results received: {len(state['result_events'])}\n"
            f"- System verification: **{status}**\n\n"
            "| Service | Worker | Permissions | Risk | Tests | Repairs | Result |\n"
            "|---|---|---:|---:|---:|---:|---|\n" + "\n".join(rows) + "\n",
            encoding="utf-8",
        )
        return path

    def _build(self, record: Callable[[SystemGraphState, str, str], None]) -> Any:
        def discover(state: SystemGraphState) -> SystemGraphState:
            services = self.discovery.discover(state["namespace"])
            record(state, "discover_system", f"discovered {len(services)} workloads dynamically")
            return {"services": services, "graph_node": "DISCOVER_SYSTEM"}

        def build_registry(state: SystemGraphState) -> SystemGraphState:
            for service in state["services"]:
                self.registry.put(service)
            record(state, "build_service_registry", "persisted deterministic service records")
            return {"graph_node": "BUILD_SERVICE_REGISTRY"}

        def index_contexts(state: SystemGraphState) -> SystemGraphState:
            contexts = tuple(self.indexer.index(service).context for service in state["services"])
            record(
                state,
                "index_service_contexts",
                f"indexed {sum(len(item.files) for item in contexts)} service-scoped files",
            )
            return {"contexts": contexts, "graph_node": "INDEX_SERVICE_CONTEXTS"}

        async def dispatch(state: SystemGraphState) -> SystemGraphState:
            by_service = {item.service_id: item for item in state["contexts"]}
            for service in state["services"]:
                context = by_service[service.service_id]
                task_id = f"{state['run_id']}:{service.service_id}"
                event = EventEnvelope(
                    EventType.WORKLOAD_OPTIMIZATION_REQUESTED,
                    run_id=state["run_id"],
                    correlation_id=state["run_id"],
                    payload={
                        "task_id": task_id,
                        "workload_id": service.service_id,
                        "namespace": service.namespace,
                        "deployment": service.deployment_name,
                        "service_account": service.service_account,
                        "repository_ref": f"service://{service.service_id}",
                        "context_ref": context.context_ref,
                        "verification_profile": service.verification_profile,
                    },
                )
                key = f"{self.cluster}:{service.namespace}:{service.service_id}"
                await self.event_bus.publish(Topic.OPTIMIZATION_REQUESTS, event, key=key)
            record(
                state,
                "dispatch_workload_events",
                f"published {len(state['services'])} independently consumable tasks",
            )
            return {
                "expected_results": len(state["services"]),
                "graph_node": "DISPATCH_WORKLOAD_EVENTS",
            }

        async def wait_for_completion(state: SystemGraphState) -> SystemGraphState:
            expected = state["expected_results"]
            results: list[EventEnvelope] = []
            if expected:
                messages = self.event_bus.consume(
                    Topic.OPTIMIZATION_RESULTS,
                    consumer_group=f"kuber-system-{state['run_id']}",
                    consumer_id="system-coordinator",
                )
                async with asyncio.timeout(self.result_timeout_seconds):
                    while len(results) < expected:
                        message = await anext(messages)
                        if message.event.run_id == state["run_id"]:
                            results.append(message.event)
                        await self.event_bus.acknowledge(message)
            record(state, "wait_for_completion_events", f"received {len(results)} durable results")
            return {
                "result_events": tuple(results),
                "graph_node": "WAIT_FOR_COMPLETION_EVENTS",
            }

        def aggregate(state: SystemGraphState) -> SystemGraphState:
            record(state, "aggregate_results", "aggregated results by workload and task")
            return {"graph_node": "AGGREGATE_RESULTS"}

        async def verify_system(state: SystemGraphState) -> SystemGraphState:
            requested = EventEnvelope(
                EventType.SYSTEM_VERIFICATION_REQUESTED,
                run_id=state["run_id"],
                correlation_id=state["run_id"],
                payload={"namespace": state["namespace"]},
            )
            await self.event_bus.publish(
                Topic.SYSTEM_EVENTS, requested, key=f"{self.cluster}:{state['namespace']}"
            )
            workload_passed = len(state["result_events"]) == state["expected_results"] and all(
                bool(event.payload.get("accepted")) for event in state["result_events"]
            )
            end_to_end_passed = (
                await asyncio.to_thread(self.system_verifier)
                if workload_passed and self.system_verifier is not None
                else workload_passed
            )
            passed = workload_passed and end_to_end_passed
            completed = EventEnvelope(
                EventType.SYSTEM_VERIFICATION_COMPLETED,
                run_id=state["run_id"],
                correlation_id=state["run_id"],
                causation_id=requested.event_id,
                payload={
                    "namespace": state["namespace"],
                    "passed": passed,
                    "workload_verification_passed": workload_passed,
                    "end_to_end_passed": end_to_end_passed,
                },
            )
            await self.event_bus.publish(
                Topic.SYSTEM_EVENTS, completed, key=f"{self.cluster}:{state['namespace']}"
            )
            record(
                state,
                "system_verify",
                "all workload verification results passed"
                if passed
                else "system verification failed",
            )
            return {"system_passed": passed, "graph_node": "SYSTEM_VERIFY"}

        def report(state: SystemGraphState) -> SystemGraphState:
            report_path = self._write_report(state)
            reason = (
                f"wrote final namespace report to {report_path}"
                if report_path is not None
                else "final namespace result is ready"
            )
            record(state, "system_report", reason)
            return {"report_path": report_path, "graph_node": "SYSTEM_REPORT"}

        def diagnose_system(state: SystemGraphState) -> SystemGraphState:
            record(
                state,
                "system_diagnosis",
                "one or more workloads require rollback or human review",
            )
            return {"graph_node": "SYSTEM_DIAGNOSIS"}

        def route_system(state: SystemGraphState) -> str:
            return "system_report" if state["system_passed"] else "system_diagnosis"

        builder = StateGraph(SystemGraphState)
        builder.add_node("discover_system", discover)
        builder.add_node("build_service_registry", build_registry)
        builder.add_node("index_service_contexts", index_contexts)
        builder.add_node("dispatch_workload_events", dispatch)
        builder.add_node("wait_for_completion_events", wait_for_completion)
        builder.add_node("aggregate_results", aggregate)
        builder.add_node("system_verify", verify_system)
        builder.add_node("system_report", report)
        builder.add_node("system_diagnosis", diagnose_system)
        builder.add_edge(START, "discover_system")
        builder.add_edge("discover_system", "build_service_registry")
        builder.add_edge("build_service_registry", "index_service_contexts")
        builder.add_edge("index_service_contexts", "dispatch_workload_events")
        builder.add_edge("dispatch_workload_events", "wait_for_completion_events")
        builder.add_edge("wait_for_completion_events", "aggregate_results")
        builder.add_edge("aggregate_results", "system_verify")
        builder.add_conditional_edges("system_verify", route_system)
        builder.add_edge("system_report", END)
        builder.add_edge("system_diagnosis", END)
        return builder.compile(checkpointer=self.checkpointer, name="system-optimization")
