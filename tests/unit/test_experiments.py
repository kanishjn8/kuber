from __future__ import annotations

import json
from pathlib import Path

import pytest

from kuber_cli.experiments import (
    WorkerScalingTrial,
    measure_context_routing,
    write_context_experiment,
    write_worker_scaling_experiment,
)


def test_context_experiment_reads_real_bytes_and_writes_evidence(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    first = repository / "examples/service_catalog" / "first"
    second = repository / "examples/service_catalog" / "second"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    (first / "service.py").write_text("FIRST = True\n", encoding="utf-8")
    (second / "service.py").write_text("SECOND = True\n", encoding="utf-8")
    (repository / "shared.py").write_text("SHARED = True\n", encoding="utf-8")

    experiment = measure_context_routing(repository)

    assert experiment.whole_repository.services_analyzed == 2
    assert experiment.whole_repository.files_inspected == 6
    assert experiment.service_scoped.files_inspected == 2
    assert experiment.whole_repository.bytes_loaded > experiment.service_scoped.bytes_loaded
    assert experiment.whole_repository.routing_violations == 2
    assert experiment.service_scoped.routing_violations == 0
    assert experiment.service_scoped.llm_input_tokens is None

    json_path, markdown_path = write_context_experiment(experiment, tmp_path / "evidence")
    assert (
        json.loads(json_path.read_text(encoding="utf-8"))["service_scoped"]["files_inspected"] == 2
    )
    assert "not measured" in markdown_path.read_text(encoding="utf-8")


def test_context_experiment_rejects_missing_service_sources(tmp_path: Path) -> None:
    (tmp_path / "examples/service_catalog").mkdir(parents=True)
    with pytest.raises(ValueError, match="no service repositories"):
        measure_context_routing(tmp_path)


def test_worker_experiment_writer_preserves_observations(tmp_path: Path) -> None:
    trial = WorkerScalingTrial(
        worker_count=3,
        wall_clock_seconds=2.5,
        workloads_completed=5,
        workloads_accepted=5,
        failures=0,
        retries=1,
        throughput_per_second=2.0,
        workers_receiving_tasks=3,
        system_passed=True,
        run_id="run-1",
    )

    json_path, markdown_path = write_worker_scaling_experiment((trial,), tmp_path)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["trials"][0]["wall_clock_seconds"] == 2.5
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "does not establish linear scaling" in markdown
    assert "| 3 | 2.500 | 5 | 5 | 0 | 1 | 2.000 | 3 | PASS |" in markdown


def test_worker_experiment_writer_requires_observations(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one"):
        write_worker_scaling_experiment((), tmp_path)
