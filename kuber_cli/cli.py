from __future__ import annotations

import asyncio
import json
import subprocess
from contextlib import suppress
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter
from typing import Annotated

import typer

from agent_layer.graphs import SystemOptimizationGraph, SystemRunResult, WorkloadOptimizationGraph
from agent_layer.graphs.checkpoints import SQLiteCheckpointStore
from agent_layer.llm import FailureReasoner, GeminiProvider, provider_from_environment
from context_layer import (
    KubernetesServiceDiscovery,
    ServiceContextIndexer,
    SQLiteContextStore,
    SQLiteServiceRegistry,
)
from event_layer import EventTrajectoryRecorder, KafkaEventBus
from event_layer.deduplication import RedisDeduplicationStore
from event_layer.locks import RedisWorkloadLockManager
from event_layer.worker import OptimizationWorker, WorkerStats
from judge_layer.evaluation.runner import run_evaluation
from kuber_cli.experiments import (
    WorkerScalingTrial,
    measure_context_routing,
    write_context_experiment,
    write_worker_scaling_experiment,
)
from kuber_cli.system_presenter import SystemPresenter
from kubernetes_runtime.adapter import (
    KubernetesEnvironment,
    KubernetesEnvironmentFactory,
    SafetyError,
)
from kubernetes_runtime.runtime import SandboxPortForwards
from rules_engine.minimizer import observed_only_policy
from rules_engine.models import KubeEvent, ServiceAccountRef
from rules_engine.rbac import parse_rbac, policy_to_yaml, resolve_effective_policy
from rules_engine.rbac.canonicalizer import effective_permission_count
from rules_engine.risk import score_policy

app = typer.Typer(help="Kuber: verified least-privilege compilation for Kubernetes workloads.")


@dataclass(frozen=True, slots=True)
class LiveSystemObservation:
    result: SystemRunResult
    worker_stats: tuple[WorkerStats, ...]
    wall_clock_seconds: float


async def _run_system(
    presenter: SystemPresenter | None,
    failure_reasoner: FailureReasoner,
    *,
    worker_count: int = 3,
) -> LiveSystemObservation:
    if worker_count < 1:
        raise ValueError("worker_count must be at least one")
    state_directory = Path("artifacts/state")
    state_directory.mkdir(parents=True, exist_ok=True)
    registry = SQLiteServiceRegistry(state_directory / "services.sqlite")
    contexts = SQLiteContextStore(state_directory / "contexts.sqlite")
    event_recorder = EventTrajectoryRecorder()
    bus = KafkaEventBus("127.0.0.1:19092", event_callback=event_recorder)
    locks = RedisWorkloadLockManager("redis://127.0.0.1:16379/0")
    deduplication = RedisDeduplicationStore("redis://127.0.0.1:16379/0")
    worker_tasks: list[asyncio.Task[None]] = []
    try:
        with SQLiteCheckpointStore(state_directory / "checkpoints.sqlite") as checkpoints:
            workers = [
                OptimizationWorker(
                    worker_id=f"worker-{index}",
                    event_bus=bus,
                    context_store=contexts,
                    lock_manager=locks,
                    deduplication_store=deduplication,
                    environment_factory=KubernetesEnvironmentFactory(),
                    graph=WorkloadOptimizationGraph(
                        trajectory_directory=Path("artifacts/trajectories"),
                        service_scoped_trajectories=True,
                        failure_reasoner=failure_reasoner,
                        event_callback=presenter.graph_event if presenter is not None else None,
                        checkpointer=checkpoints.saver,
                    ),
                )
                for index in range(1, worker_count + 1)
            ]
            worker_tasks = [asyncio.create_task(worker.run()) for worker in workers]

            def verify_end_to_end() -> bool:
                completed = subprocess.run(
                    ("./deploy/kind/scripts/system-smoke.sh",),
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                return completed.returncode == 0 and "KUBER_SYSTEM_SUMMARY=5/5" in completed.stdout

            system = SystemOptimizationGraph(
                discovery=KubernetesServiceDiscovery(repository_root=Path(".")),
                registry=registry,
                indexer=ServiceContextIndexer(contexts),
                event_bus=bus,
                event_callback=presenter.system_event if presenter is not None else None,
                system_verifier=verify_end_to_end,
                result_timeout_seconds=300,
                trajectory_directory=Path("artifacts/trajectories"),
                report_directory=Path("artifacts/runs"),
            )
            started = perf_counter()
            result = await system.run("kuber-sandbox")
            return LiveSystemObservation(
                result=result,
                worker_stats=tuple(replace(worker.stats) for worker in workers),
                wall_clock_seconds=perf_counter() - started,
            )
    finally:
        for task in worker_tasks:
            task.cancel()
        if worker_tasks:
            await asyncio.gather(*worker_tasks, return_exceptions=True)
        with suppress(Exception):
            await bus.close()
        with suppress(Exception):
            await locks.close()
        with suppress(Exception):
            await deduplication.close()
        registry.close()
        contexts.close()


@app.command()
def discover(
    namespace: str = typer.Option("kuber-sandbox", help="Kubernetes namespace to discover."),
    context: str = typer.Option("kind-kuber", help="kubectl context."),
    database: str = typer.Option(
        "artifacts/state/services.sqlite", help="Persistent registry database."
    ),
) -> None:
    """Discover opt-in Kubernetes Deployments and persist the Service Registry."""

    database_path = Path(database)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    registry = SQLiteServiceRegistry(database_path)
    try:
        services = KubernetesServiceDiscovery(repository_root=Path("."), context=context).discover(
            namespace
        )
        for service in services:
            registry.put(service)
        if not services:
            typer.echo("No Deployments opted in with kuber.dev/source-path.")
            return
        for service in services:
            typer.echo(
                f"{service.service_id}: Deployment/{service.deployment_name}, "
                f"ServiceAccount/{service.service_account}, "
                f"source={service.source_repository.local_path}"
            )
        typer.echo(f"Persisted {len(services)} services to {database_path} (context {context}).")
    finally:
        registry.close()


@app.command()
def trajectory(
    run_id: str,
    root: str = typer.Option("artifacts/trajectories", help="Trajectory root."),
) -> None:
    """Print graph and event trajectory locations for a run."""

    trajectory_root = Path(root)
    scoped = trajectory_root / run_id
    paths = sorted(scoped.glob("*.jsonl")) if scoped.is_dir() else []
    legacy = trajectory_root / f"{run_id}.jsonl"
    if legacy.exists():
        paths.append(legacy)
    if not paths:
        raise typer.BadParameter(f"trajectory not found for run {run_id}")
    for path in paths:
        typer.echo(path)


@app.command()
def inspect(manifest: Path, service_account: str, namespace: str) -> None:
    """Resolve and summarize one ServiceAccount's supported effective RBAC."""

    policy = resolve_effective_policy(
        parse_rbac(manifest), ServiceAccountRef(service_account, namespace)
    )
    risk = score_policy(policy)
    typer.echo(f"Effective permissions: {effective_permission_count(policy)}")
    typer.echo(f"Privilege risk score: {risk.score}/100")
    for finding in risk.findings:
        typer.echo(f"+ {finding.reason}: {finding.points} ({finding.occurrences} occurrence(s))")


@app.command()
def minimize(
    manifest: Path,
    events: Path,
    service_account: str,
    namespace: str,
    output: Path = Path("artifacts/policies/candidate.yaml"),
) -> None:
    """Generate an observed-only candidate; it is not accepted without verification."""

    current = resolve_effective_policy(
        parse_rbac(manifest), ServiceAccountRef(service_account, namespace)
    )
    values = json.loads(events.read_text(encoding="utf-8"))
    observed = tuple(KubeEvent.from_dict(value) for value in values)
    candidate = observed_only_policy(current, observed)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(policy_to_yaml(candidate), encoding="utf-8")
    typer.echo(f"Unverified candidate written to {output}")


@app.command()
def evaluate(
    summary_only: bool = typer.Option(False, help="Print only aggregate metrics."),
) -> None:
    """Run the Kubernetes-free benchmark suite and write generated artifacts."""

    run_evaluation(detailed=not summary_only)


@app.command("experiment-context")
def experiment_context(
    repository: Annotated[Path, typer.Option(help="Repository root to measure.")] = Path("."),
    output: Annotated[Path, typer.Option(help="Directory for JSON and Markdown evidence.")] = Path(
        "artifacts/experiments"
    ),
) -> None:
    """Measure whole-repository reads against service-scoped context routing."""

    experiment = measure_context_routing(repository)
    json_path, markdown_path = write_context_experiment(experiment, output)
    whole = experiment.whole_repository
    scoped = experiment.service_scoped
    typer.echo("Context-routing experiment")
    typer.echo(
        f"Whole repository: {whole.files_inspected} files, {whole.bytes_loaded} bytes, "
        f"{whole.latency_seconds:.6f}s"
    )
    typer.echo(
        f"Service scoped:  {scoped.files_inspected} files, {scoped.bytes_loaded} bytes, "
        f"{scoped.latency_seconds:.6f}s"
    )
    typer.echo("LLM tokens: not measured (indexing does not call an LLM)")
    typer.echo(f"Evidence: {json_path} and {markdown_path}")


@app.command("experiment-workers")
def experiment_workers(
    output: Annotated[Path, typer.Option(help="Directory for JSON and Markdown evidence.")] = Path(
        "artifacts/experiments"
    ),
) -> None:
    """Measure one versus three Kafka workers in the guarded live sandbox."""

    try:
        guard = KubernetesEnvironment()
        if guard.dry_run:
            raise SafetyError("kind-kuber with the sandbox namespace label is required")
        trials: list[WorkerScalingTrial] = []
        for worker_count in (1, 3):
            typer.echo(f"Resetting sandbox for {worker_count}-worker trial...")
            subprocess.run(
                ("./deploy/kind/scripts/reset.sh",),
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ("./deploy/kind/scripts/warmup-system.sh",),
                check=True,
                capture_output=True,
                text=True,
            )
            with SandboxPortForwards():
                observation = asyncio.run(
                    _run_system(None, FailureReasoner(None), worker_count=worker_count)
                )
            result = observation.result
            accepted = sum(bool(event.payload.get("accepted")) for event in result.results)
            retries = sum(stats.retried for stats in observation.worker_stats)
            failed_tasks = sum(stats.failed for stats in observation.worker_stats)
            rejected = len(result.results) - accepted
            workers_used = len(
                {
                    str(event.payload["worker_id"])
                    for event in result.results
                    if "worker_id" in event.payload
                }
            )
            trial = WorkerScalingTrial(
                worker_count=worker_count,
                wall_clock_seconds=observation.wall_clock_seconds,
                workloads_completed=len(result.results),
                workloads_accepted=accepted,
                failures=failed_tasks + rejected,
                retries=retries,
                throughput_per_second=(
                    len(result.results) / observation.wall_clock_seconds
                    if observation.wall_clock_seconds
                    else 0.0
                ),
                workers_receiving_tasks=workers_used,
                system_passed=result.system_passed,
                run_id=result.run_id,
            )
            trials.append(trial)
            typer.echo(
                f"{worker_count} worker(s): {trial.wall_clock_seconds:.3f}s, "
                f"{trial.workloads_completed} completed, {trial.failures} failures, "
                f"{trial.retries} retries"
            )
        json_path, markdown_path = write_worker_scaling_experiment(tuple(trials), output)
        typer.echo("No linear-scaling claim is inferred from these two observed trials.")
        typer.echo(f"Evidence: {json_path} and {markdown_path}")
        if not all(trial.system_passed for trial in trials):
            raise typer.Exit(1)
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or str(exc)).strip()
        typer.echo(f"Worker experiment failed: {details}", err=True)
        raise typer.Exit(1) from exc
    except (
        SafetyError,
        FileNotFoundError,
        subprocess.SubprocessError,
        TimeoutError,
        RuntimeError,
        ValueError,
    ) as exc:
        typer.echo(f"Worker experiment unavailable: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command()
def report(path: Path = Path("artifacts/evaluation/report.md")) -> None:
    """Print the latest generated evaluation report."""

    if not path.exists():
        raise typer.BadParameter("report not found; run `kuber evaluate` first")
    typer.echo(path.read_text(encoding="utf-8"))


@app.command()
def optimize() -> None:
    """Optimize the five reference services in the guarded Kubernetes sandbox."""

    try:
        guard = KubernetesEnvironment()
        if guard.dry_run:
            raise SafetyError("kind-kuber with the sandbox namespace label is required")
        provider = provider_from_environment()
        llm_label = (
            f"Gemini enabled ({provider.model})"
            if isinstance(provider, GeminiProvider)
            else "Gemini disabled (no GEMINI_API_KEY); deterministic fallback"
        )
        presenter = SystemPresenter(llm_label=llm_label)
        presenter.start()
        reset = subprocess.run(
            ("./deploy/kind/scripts/reset.sh",),
            check=True,
            capture_output=True,
            text=True,
        )
        warmup = subprocess.run(
            ("./deploy/kind/scripts/warmup-system.sh",),
            check=True,
            capture_output=True,
            text=True,
        )
        presenter.preparation(f"{reset.stdout}\n{warmup.stdout}")
        with SandboxPortForwards():
            observation = asyncio.run(_run_system(presenter, FailureReasoner(provider)))
        result = observation.result
        presenter.finish(result)
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or str(exc)).strip()
        typer.echo(f"Optimization failed: {details}", err=True)
        raise typer.Exit(1) from exc
    except (
        SafetyError,
        FileNotFoundError,
        subprocess.SubprocessError,
        TimeoutError,
        RuntimeError,
        ValueError,
    ) as exc:
        typer.echo(f"Optimization unavailable: {exc}", err=True)
        raise typer.Exit(1) from exc
    if not result.system_passed:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
