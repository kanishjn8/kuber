from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import yaml

from agent_layer.graphs import SystemOptimizationGraph, WorkloadOptimizationGraph
from context_layer import (
    RepositorySource,
    ServiceContext,
    ServiceContextIndexer,
    SQLiteContextStore,
    SQLiteServiceRegistry,
    StaticServiceDiscovery,
)
from event_layer import (
    EventEnvelope,
    InMemoryDeduplicationStore,
    InMemoryEventBus,
    InMemoryWorkloadLockManager,
)
from event_layer.worker import OptimizationWorker
from judge_layer.evaluation.compare import evaluate_baseline
from judge_layer.evaluation.metrics import SystemCaseMetrics
from judge_layer.simulator import BenchmarkCase, SimulatorEnvironment, load_benchmark


@dataclass(frozen=True, slots=True)
class SystemBenchmark:
    identifier: str
    name: str
    description: str
    cases: tuple[BenchmarkCase, ...]
    workers: int


class _SimulatorFactory:
    def __init__(self, cases: dict[str, BenchmarkCase]) -> None:
        self.cases = cases

    def create(self, event: EventEnvelope, context: object) -> SimulatorEnvironment:
        return SimulatorEnvironment(self.cases[str(event.payload["workload_id"])])


def load_system_benchmark(path: Path, benchmark_root: Path) -> SystemBenchmark:
    metadata = yaml.safe_load((path / "metadata.yaml").read_text(encoding="utf-8"))
    definition = yaml.safe_load((path / "system.yaml").read_text(encoding="utf-8"))
    if not isinstance(metadata, dict) or not isinstance(definition, dict):
        raise ValueError(f"invalid system benchmark in {path}")
    cases = tuple(load_benchmark(benchmark_root / str(item)) for item in definition["cases"])
    return SystemBenchmark(
        path.name,
        str(metadata["name"]),
        str(metadata["description"]),
        cases,
        int(definition.get("workers", 3)),
    )


def _aggregate(values: list[SystemCaseMetrics], *, runtime: float) -> SystemCaseMetrics:
    initial_risk = sum(item.initial_risk for item in values)
    final_risk = sum(item.final_risk for item in values)
    initial_permissions = sum(item.initial_permissions for item in values)
    final_permissions = sum(item.final_permissions for item in values)
    risk_reduction = 100 * (initial_risk - final_risk) / initial_risk if initial_risk else 0.0
    raw_reduction = (
        100 * (initial_permissions - final_permissions) / initial_permissions
        if initial_permissions
        else 0.0
    )
    success = all(item.functional_success for item in values)
    return SystemCaseMetrics(
        functional_success=success,
        initial_risk=initial_risk,
        final_risk=final_risk,
        risk_reduction_percent=risk_reduction,
        validated_risk_reduction=risk_reduction if success else 0.0,
        raw_permission_reduction_percent=raw_reduction,
        initial_permissions=initial_permissions,
        final_permissions=final_permissions,
        high_risk_permissions_remaining=sum(
            item.high_risk_permissions_remaining for item in values
        ),
        cluster_wide_grants_remaining=sum(item.cluster_wide_grants_remaining for item in values),
        incorrect_removals=sum(item.incorrect_removals for item in values),
        repair_iterations=sum(item.repair_iterations for item in values),
        runtime_seconds=runtime,
    )


def evaluate_system_baseline(benchmark: SystemBenchmark) -> SystemCaseMetrics:
    started = perf_counter()
    values = [evaluate_baseline(case)[1] for case in benchmark.cases]
    return _aggregate(values, runtime=perf_counter() - started)


def _metrics_from_events(events: tuple[EventEnvelope, ...], runtime: float) -> SystemCaseMetrics:
    payloads = [event.payload for event in events]
    initial_risk = sum(int(value["original_risk"]) for value in payloads)
    final_risk = sum(int(value["final_risk"]) for value in payloads)
    initial_permissions = sum(int(value["original_permissions"]) for value in payloads)
    final_permissions = sum(int(value["final_permissions"]) for value in payloads)
    success = all(bool(value["accepted"]) for value in payloads)
    risk_reduction = 100 * (initial_risk - final_risk) / initial_risk if initial_risk else 0.0
    raw_reduction = (
        100 * (initial_permissions - final_permissions) / initial_permissions
        if initial_permissions
        else 0.0
    )
    return SystemCaseMetrics(
        success,
        initial_risk,
        final_risk,
        risk_reduction,
        risk_reduction if success else 0.0,
        raw_reduction,
        initial_permissions,
        final_permissions,
        sum(int(value["high_risk_permissions_remaining"]) for value in payloads),
        sum(int(value["cluster_wide_grants_remaining"]) for value in payloads),
        sum(int(value["incorrect_removals"]) for value in payloads),
        sum(int(value["repairs"]) for value in payloads),
        runtime,
    )


async def _evaluate_system_kuber(
    benchmark: SystemBenchmark, trajectory_root: Path
) -> SystemCaseMetrics:
    with TemporaryDirectory(prefix="kuber-judge-") as temporary:
        database = Path(temporary) / "judge.sqlite"
        registry = SQLiteServiceRegistry(database)
        contexts = SQLiteContextStore(database)
        bus = InMemoryEventBus(partitions=max(3, benchmark.workers))
        locks = InMemoryWorkloadLockManager()
        deduplication = InMemoryDeduplicationStore()
        cases = {case.identifier: case for case in benchmark.cases}
        services = tuple(
            ServiceContext(
                service_id=case.identifier,
                namespace=benchmark.identifier,
                workload_kind="Deployment",
                deployment_name=case.identifier,
                service_account=case.initial_policy.service_account,
                source_repository=RepositorySource(
                    case.identifier, str(Path("judge_layer/benchmarks") / case.identifier)
                ),
                important_paths=(
                    "metadata.yaml",
                    "initial-rbac.yaml",
                    "observed-events.json",
                    "verification-tests.yaml",
                ),
                verification_profile=case.identifier,
            )
            for case in benchmark.cases
        )
        workers = [
            OptimizationWorker(
                worker_id=f"judge-worker-{index}",
                event_bus=bus,
                context_store=contexts,
                lock_manager=locks,
                deduplication_store=deduplication,
                environment_factory=_SimulatorFactory(cases),
                graph=WorkloadOptimizationGraph(
                    trajectory_directory=trajectory_root,
                    service_scoped_trajectories=True,
                ),
                cluster="judge",
            )
            for index in range(1, benchmark.workers + 1)
        ]
        system = SystemOptimizationGraph(
            discovery=StaticServiceDiscovery(services),
            registry=registry,
            indexer=ServiceContextIndexer(contexts),
            event_bus=bus,
            cluster="judge",
            result_timeout_seconds=30,
            trajectory_directory=trajectory_root,
        )
        worker_tasks = [asyncio.create_task(worker.run()) for worker in workers]
        started = perf_counter()
        try:
            result = await system.run(
                benchmark.identifier, run_id=f"evaluation-{benchmark.identifier}"
            )
        finally:
            for task in worker_tasks:
                task.cancel()
            await asyncio.gather(*worker_tasks, return_exceptions=True)
            await bus.close()
            registry.close()
            contexts.close()
        return _metrics_from_events(result.results, perf_counter() - started)


def evaluate_system_kuber(benchmark: SystemBenchmark, trajectory_root: Path) -> SystemCaseMetrics:
    return asyncio.run(_evaluate_system_kuber(benchmark, trajectory_root))
