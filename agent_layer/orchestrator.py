from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from agent_layer.inspector import InspectionResult, InspectorAgent
from agent_layer.interfaces import EnvironmentAdapter, VerificationResult
from agent_layer.llm import FailureReasoner
from agent_layer.reducer import ReducerAgent
from agent_layer.trajectory import TrajectoryEvent, TrajectoryRecorder
from agent_layer.verifier import VerifierAgent
from rules_engine.models import Policy
from rules_engine.risk import RiskAssessment, score_policy


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
    def __init__(self, *, max_repair_iterations: int = 5, trajectory_directory: Path | None = Path("artifacts/trajectories"), failure_reasoner: FailureReasoner | None = None) -> None:
        if max_repair_iterations < 0:
            raise ValueError("max_repair_iterations must be non-negative")
        self.max_repair_iterations = max_repair_iterations
        self.trajectory_directory = trajectory_directory
        self.inspector = InspectorAgent()
        self.reducer = ReducerAgent()
        self.verifier = VerifierAgent()
        self.failure_reasoner = failure_reasoner or FailureReasoner()

    def run(self, environment: EnvironmentAdapter, *, run_id: str | None = None) -> KuberRunResult:
        identifier = run_id or uuid4().hex
        recorder = TrajectoryRecorder(identifier, self.trajectory_directory)
        inspection: InspectionResult = self.inspector.inspect(environment)
        original = inspection.policy
        recorder.record(TrajectoryEvent(identifier, environment.name, "inspector", "inspect", "resolved policy, observed usage, and deterministic risk", details={"permissions": len(original.permissions), "risk": inspection.risk.score, "observed_events": len(inspection.observed)}))
        candidate = self.reducer.propose(original, inspection.observed)
        recorder.record(TrajectoryEvent(identifier, environment.name, "reducer", "propose_policy", "narrowest supported policy for observed calls; verification still required", details={"permissions": len(candidate.permissions), "risk": score_policy(candidate).score}))

        repairs = 0
        incorrect_removals = 0
        last_result: VerificationResult | None = None
        accepted = False
        while repairs <= self.max_repair_iterations:
            attempt = self.verifier.verify(environment, candidate)
            last_result = attempt.result
            recorder.record(TrajectoryEvent(identifier, environment.name, "verifier", "verify", f"{attempt.result.tests_passed}/{attempt.result.tests_total} verification tests passed", decision="accept" if attempt.result.passed else "diagnose", retry_count=repairs, details={"denied_events": [event.to_dict() for event in attempt.result.denied_events]}))
            if attempt.result.passed:
                accepted = True
                break
            if attempt.failure is None or repairs == self.max_repair_iterations:
                break
            try:
                repaired = self.verifier.repair(candidate, attempt.failure, original)
            except ValueError:
                break
            new_permissions = len(repaired.permissions) - len(candidate.permissions)
            if new_permissions <= 0:
                break
            incorrect_removals += new_permissions
            repairs += 1
            candidate = repaired
            recorder.record(TrajectoryEvent(identifier, environment.name, "verifier", "repair_policy", self.failure_reasoner.explain(attempt.failure), decision="retry", retry_count=repairs, details={"restored": [event.to_dict() for event in attempt.failure.missing_events]}))


        if not accepted:
            environment.restore_policy()
            final_policy = original
            recorder.record(TrajectoryEvent(identifier, environment.name, "orchestrator", "restore_policy", "candidate did not pass declared verification", decision="reject"))
            if last_result is None:
                last_result = environment.verify_workload()
        else:
            final_policy = candidate
            recorder.record(TrajectoryEvent(identifier, environment.name, "orchestrator", "finalize", "verified candidate retained", decision="accept"))
        trajectory_path = recorder.write_summary()
        assert last_result is not None
        return KuberRunResult(identifier, accepted, original, final_policy, inspection.risk, score_policy(final_policy), last_result, repairs, incorrect_removals, trajectory_path)
