from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.base import BaseCheckpointSaver

from agent_layer.graphs import WorkloadOptimizationGraph
from agent_layer.interfaces import EnvironmentAdapter, VerificationResult
from agent_layer.llm import FailureReasoner
from agent_layer.trajectory import TrajectoryEvent
from rules_engine.models import Policy
from rules_engine.risk import RiskAssessment


@dataclass(frozen=True, slots=True)
class KuberRunResult:
    run_id: str
    accepted: bool
    original_policy: Policy
    final_policy: Policy
    original_risk: RiskAssessment
    final_risk: RiskAssessment
    verification: VerificationResult
    repair_iterations: int
    incorrect_removals: int
    trajectory_path: Path | None


class KuberOrchestrator:
    """Compatibility facade backed by the LangGraph workload subgraph."""

    def __init__(
        self,
        *,
        max_repair_iterations: int = 5,
        trajectory_directory: Path | None = Path("artifacts/trajectories"),
        failure_reasoner: FailureReasoner | None = None,
        event_callback: Callable[[TrajectoryEvent], None] | None = None,
        checkpointer: BaseCheckpointSaver[Any] | None = None,
    ) -> None:
        self.graph = WorkloadOptimizationGraph(
            max_repair_iterations=max_repair_iterations,
            trajectory_directory=trajectory_directory,
            failure_reasoner=failure_reasoner,
            event_callback=event_callback,
            checkpointer=checkpointer,
        )

    def run(self, environment: EnvironmentAdapter, *, run_id: str | None = None) -> KuberRunResult:
        execution = self.graph.run(environment, run_id=run_id or uuid4().hex)
        return KuberRunResult(
            execution.run_id,
            execution.accepted,
            execution.original_policy,
            execution.final_policy,
            execution.original_risk,
            execution.final_risk,
            execution.verification,
            execution.repair_iterations,
            execution.incorrect_removals,
            execution.trajectory_path,
        )
