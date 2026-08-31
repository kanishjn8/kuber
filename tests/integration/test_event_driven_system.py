from __future__ import annotations

import asyncio
from pathlib import Path

from agent_layer.graphs import SystemOptimizationGraph, WorkloadOptimizationGraph
from context_layer import (
    RepositorySource,
    ServiceContext,
    ServiceContextIndexer,
    SQLiteContextStore,
    SQLiteServiceRegistry,
    StaticServiceDiscovery,
)
from event_layer import InMemoryEventBus, InMemoryWorkloadLockManager
from event_layer.contracts import EventEnvelope
from event_layer.worker import OptimizationWorker
from judge_layer.simulator import BenchmarkCase, SimulatorEnvironment, load_benchmark


class SimulatorFactory:
    def __init__(self, cases: dict[str, BenchmarkCase]) -> None:
        self.cases = cases

    def create(self, event: EventEnvelope, context: object) -> SimulatorEnvironment:
        return SimulatorEnvironment(self.cases[str(event.payload["workload_id"])])


def make_service(root: Path, service_id: str) -> ServiceContext:
    service_root = root / service_id
    service_root.mkdir()
    (service_root / "main.py").write_text("# service-scoped fixture\n", encoding="utf-8")
    return ServiceContext(
        service_id=service_id,
        namespace="judge",
        workload_kind="Deployment",
        deployment_name=service_id,
        service_account=f"{service_id}-sa",
        source_repository=RepositorySource(service_id, str(service_root)),
        important_paths=("main.py",),
        verification_profile=service_id,
    )


def test_system_graph_dispatches_two_services_to_independent_workers(tmp_path: Path) -> None:
    async def exercise() -> None:
        cases = {
            "config-reader": load_benchmark(Path("judge_layer/benchmarks/01_config_reader")),
            "hidden-path": load_benchmark(Path("judge_layer/benchmarks/07_hidden_path")),
        }
        services = tuple(make_service(tmp_path, service_id) for service_id in cases)
        database = tmp_path / "system.sqlite"
        registry = SQLiteServiceRegistry(database)
        contexts = SQLiteContextStore(database)
        bus = InMemoryEventBus(partitions=3)
        locks = InMemoryWorkloadLockManager()
        factory = SimulatorFactory(cases)
        workers = [
            OptimizationWorker(
                worker_id=f"worker-{index}",
                event_bus=bus,
                context_store=contexts,
                lock_manager=locks,
                environment_factory=factory,
                graph=WorkloadOptimizationGraph(
                    trajectory_directory=tmp_path / "workload-trajectories"
                ),
                cluster="judge",
            )
            for index in (1, 2)
        ]
        system = SystemOptimizationGraph(
            discovery=StaticServiceDiscovery(services),
            registry=registry,
            indexer=ServiceContextIndexer(contexts),
            event_bus=bus,
            cluster="judge",
            result_timeout_seconds=10,
            trajectory_directory=tmp_path / "system-trajectories",
            report_directory=tmp_path / "reports",
        )

        result, _, _ = await asyncio.gather(
            system.run("judge", run_id="multi-service"),
            workers[0].run_one(),
            workers[1].run_one(),
        )
        assert result.system_passed
        assert {item.payload["workload_id"] for item in result.results} == set(cases)
        assert sum(worker.stats.completed for worker in workers) == 2
        assert result.report_path == tmp_path / "reports/multi-service-namespace-report.md"
        report = result.report_path.read_text(encoding="utf-8")
        assert "Kuber namespace report: judge" in report
        assert "config-reader" in report and "hidden-path" in report
        assert "System verification: **PASS**" in report
        assert registry.list(namespace="judge") == tuple(
            sorted(services, key=lambda x: x.service_id)
        )
        await bus.close()
        registry.close()
        contexts.close()

    asyncio.run(exercise())
