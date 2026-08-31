from __future__ import annotations

from io import StringIO

from rich.console import Console

from agent_layer.graphs import SystemRunResult
from agent_layer.trajectory import TrajectoryEvent
from event_layer import EventEnvelope, EventType
from kuber_cli.system_presenter import SystemPresenter


def test_system_presenter_shows_graph_denial_diagnosis_and_summary() -> None:
    output = StringIO()
    presenter = SystemPresenter(
        Console(file=output, force_terminal=False, width=120), llm_label="deterministic"
    )
    presenter.start()
    presenter.preparation("KUBER_WARMUP worker-service=PASS\nWarmup complete")
    presenter.graph_event(
        TrajectoryEvent(
            "run",
            "kubernetes:kind-kuber/kuber-sandbox:worker-service:live",
            "verifier",
            "verify",
            "2/3 verification tests passed",
            decision="diagnose",
            details={
                "denied_events": [
                    {
                        "api_group": "batch",
                        "resource": "jobs",
                        "verb": "create",
                        "resource_name": "job",
                    }
                ]
            },
        )
    )
    presenter.graph_event(
        TrajectoryEvent(
            "run",
            "environment",
            "reasoner",
            "diagnose_failure",
            "Job creation is required.",
            details={"reasoner": "deterministic"},
        )
    )
    presenter.graph_event(
        TrajectoryEvent("run", "environment", "verifier", "repair_policy", "repair")
    )
    presenter.system_event(
        TrajectoryEvent("run", "system", "system_graph", "system_verify", "passed")
    )
    result_event = EventEnvelope(
        EventType.WORKLOAD_OPTIMIZATION_COMPLETED,
        run_id="run",
        correlation_id="run",
        payload={
            "workload_id": "worker-service",
            "worker_id": "worker-1",
            "original_permissions": 14,
            "final_permissions": 4,
            "original_risk": 42,
            "final_risk": 13,
            "tests_passed": 3,
            "tests_total": 3,
            "repairs": 3,
        },
    )
    presenter.finish(SystemRunResult("run", "kuber-sandbox", (), (result_event,), True, None))

    rendered = output.getvalue()
    for text in (
        "REAL 403",
        "DIAGNOSE_FAILURE",
        "REPAIR_POLICY",
        "SYSTEM_VERIFY",
        "14 → 4",
        "PASS",
    ):
        assert text in rendered
