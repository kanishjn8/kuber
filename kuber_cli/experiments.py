"""Measured experiments required by the architecture specification.

The context experiment is local and deterministic in scope, while its timing is
an observed wall-clock value. The worker experiment records observations from
real Kafka/Kubernetes runs and deliberately makes no scaling claim on its own.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

_SOURCE_SUFFIXES = {".go", ".java", ".js", ".json", ".py", ".sh", ".toml", ".ts", ".yaml", ".yml"}
_SOURCE_NAMES = {"Dockerfile", "Makefile"}
_IGNORED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "artifacts",
    "build",
    "dist",
}


@dataclass(frozen=True, slots=True)
class ContextScanMeasurement:
    mode: str
    services_analyzed: int
    files_inspected: int
    bytes_loaded: int
    latency_seconds: float
    service_sources_present: int
    routing_violations: int
    llm_input_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class ContextRoutingExperiment:
    whole_repository: ContextScanMeasurement
    service_scoped: ContextScanMeasurement
    note: str = "LLM input tokens are not measured because context indexing does not invoke an LLM."


@dataclass(frozen=True, slots=True)
class WorkerScalingTrial:
    worker_count: int
    wall_clock_seconds: float
    workloads_completed: int
    workloads_accepted: int
    failures: int
    retries: int
    throughput_per_second: float
    workers_receiving_tasks: int
    system_passed: bool
    run_id: str


def _source_files(root: Path) -> tuple[Path, ...]:
    return tuple(
        sorted(
            path
            for path in root.rglob("*")
            if path.is_file()
            and not _IGNORED_PARTS.intersection(path.relative_to(root).parts)
            and (path.suffix.lower() in _SOURCE_SUFFIXES or path.name in _SOURCE_NAMES)
        )
    )


def _read_groups(groups: tuple[tuple[Path, ...], ...]) -> tuple[int, int, float]:
    digest = hashlib.sha256()
    files = 0
    byte_count = 0
    started = perf_counter()
    for group in groups:
        for path in group:
            content = path.read_bytes()
            digest.update(content)
            files += 1
            byte_count += len(content)
    # Computing a digest ensures each selected byte is genuinely consumed.
    digest.digest()
    return files, byte_count, perf_counter() - started


def measure_context_routing(repository_root: Path) -> ContextRoutingExperiment:
    """Compare repeated whole-repository reads with service-owned source reads."""

    root = repository_root.resolve()
    service_root = root / "examples/service_catalog"
    service_directories = tuple(sorted(path for path in service_root.iterdir() if path.is_dir()))
    if not service_directories:
        raise ValueError(f"no service repositories found under {service_root}")

    whole_files = _source_files(root)
    scoped_groups = tuple(_source_files(path) for path in service_directories)
    if not whole_files or any(not group for group in scoped_groups):
        raise ValueError("experiment requires source files in every service repository")

    whole_groups = tuple(whole_files for _ in service_directories)
    whole_count, whole_bytes, whole_latency = _read_groups(whole_groups)
    scoped_count, scoped_bytes, scoped_latency = _read_groups(scoped_groups)
    service_count = len(service_directories)

    return ContextRoutingExperiment(
        whole_repository=ContextScanMeasurement(
            mode="whole-repository-per-service",
            services_analyzed=service_count,
            files_inspected=whole_count,
            bytes_loaded=whole_bytes,
            latency_seconds=whole_latency,
            service_sources_present=service_count,
            routing_violations=service_count,
        ),
        service_scoped=ContextScanMeasurement(
            mode="service-scoped",
            services_analyzed=service_count,
            files_inspected=scoped_count,
            bytes_loaded=scoped_bytes,
            latency_seconds=scoped_latency,
            service_sources_present=service_count,
            routing_violations=0,
        ),
    )


def write_context_experiment(
    experiment: ContextRoutingExperiment, directory: Path = Path("artifacts/experiments")
) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "context-routing.json"
    markdown_path = directory / "context-routing.md"
    json_path.write_text(json.dumps(asdict(experiment), indent=2) + "\n", encoding="utf-8")
    whole = experiment.whole_repository
    scoped = experiment.service_scoped
    markdown_path.write_text(
        "# Context-routing experiment\n\n"
        "These are measurements from the current checkout, not embedded benchmark constants.\n\n"
        "| Mode | Services | Files inspected | Bytes loaded | Latency (s) | "
        "Sources present | Routing violations | LLM tokens |\n"
        "|---|---:|---:|---:|---:|---:|---:|---|\n"
        f"| Whole repository per service | {whole.services_analyzed} | "
        f"{whole.files_inspected} | {whole.bytes_loaded} | {whole.latency_seconds:.6f} | "
        f"{whole.service_sources_present} | {whole.routing_violations} | not measured |\n"
        f"| Service scoped | {scoped.services_analyzed} | {scoped.files_inspected} | "
        f"{scoped.bytes_loaded} | {scoped.latency_seconds:.6f} | "
        f"{scoped.service_sources_present} | {scoped.routing_violations} | not measured |\n\n"
        f"{experiment.note}\n",
        encoding="utf-8",
    )
    return json_path, markdown_path


def write_worker_scaling_experiment(
    trials: tuple[WorkerScalingTrial, ...],
    directory: Path = Path("artifacts/experiments"),
) -> tuple[Path, Path]:
    if not trials:
        raise ValueError("at least one measured trial is required")
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "kafka-worker-scaling.json"
    markdown_path = directory / "kafka-worker-scaling.md"
    json_path.write_text(
        json.dumps({"trials": [asdict(trial) for trial in trials]}, indent=2) + "\n",
        encoding="utf-8",
    )
    rows = "\n".join(
        f"| {trial.worker_count} | {trial.wall_clock_seconds:.3f} | "
        f"{trial.workloads_completed} | {trial.workloads_accepted} | {trial.failures} | "
        f"{trial.retries} | {trial.throughput_per_second:.3f} | "
        f"{trial.workers_receiving_tasks} | {'PASS' if trial.system_passed else 'FAIL'} |"
        for trial in trials
    )
    markdown_path.write_text(
        "# Kafka worker-scaling experiment\n\n"
        "Each row is one observed run against the same five-service kind/Kafka sandbox. "
        "The sandbox is reset before every trial. A two-point, single-trial comparison "
        "does not establish linear scaling.\n\n"
        "| Workers | Wall time (s) | Completed | Accepted | Failures | Retries | "
        "Throughput (workloads/s) | Workers used | System |\n"
        "|---:|---:|---:|---:|---:|---:|---:|---:|---|\n"
        f"{rows}\n",
        encoding="utf-8",
    )
    return json_path, markdown_path
