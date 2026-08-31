from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from agent_layer.graphs.state import FailureType, WorkloadGraphState
from agent_layer.interfaces import EnvironmentAdapter, VerificationResult
from agent_layer.llm import FailureReasoner
from agent_layer.reducer import ReducerAgent
from agent_layer.trajectory import TrajectoryEvent, TrajectoryRecorder
from agent_layer.verifier import VerifierAgent
from rules_engine.models import KubeEvent, Policy
from rules_engine.rbac.authorization import is_authorized
from rules_engine.rbac.canonicalizer import effective_permission_count
from rules_engine.risk import RiskAssessment, score_policy


@dataclass(frozen=True, slots=True)
class WorkloadExecution:
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


class WorkloadOptimizationGraph:
    """Reusable, bounded LangGraph subgraph for one workload.

    Environment mutations remain behind ``EnvironmentAdapter``. LangGraph owns
    workflow state and routing, while deterministic agents own RBAC decisions.
    """

    def __init__(
        self,
        *,
        max_repair_iterations: int = 5,
        trajectory_directory: Path | None = Path("artifacts/trajectories"),
        failure_reasoner: FailureReasoner | None = None,
        event_callback: Callable[[TrajectoryEvent], None] | None = None,
        checkpointer: BaseCheckpointSaver[Any] | None = None,
        service_scoped_trajectories: bool = False,
    ) -> None:
        if max_repair_iterations < 0:
            raise ValueError("max_repair_iterations must be non-negative")
        self.max_repair_iterations = max_repair_iterations
        self.trajectory_directory = trajectory_directory
        self.failure_reasoner = failure_reasoner or FailureReasoner()
        self.event_callback = event_callback
        self.checkpointer = checkpointer or InMemorySaver()
        self.service_scoped_trajectories = service_scoped_trajectories
        self.reducer = ReducerAgent()
        self.verifier = VerifierAgent()

    def run(
        self,
        environment: EnvironmentAdapter,
        *,
        run_id: str,
        task_id: str | None = None,
        workload_id: str | None = None,
        context_ref: str = "",
        repository_ref: str = "",
    ) -> WorkloadExecution:
        identifier = workload_id or environment.name
        trajectory_directory = self.trajectory_directory
        if trajectory_directory is not None and self.service_scoped_trajectories:
            trajectory_directory = trajectory_directory / run_id
        recorder = TrajectoryRecorder(
            run_id,
            trajectory_directory,
            file_stem=identifier if self.service_scoped_trajectories else None,
        )

        def record(event: TrajectoryEvent) -> None:
            recorder.record(event)
            if self.event_callback is not None:
                self.event_callback(event)

        graph = self._build(environment, record)
        initial: WorkloadGraphState = {
            "run_id": run_id,
            "task_id": task_id or run_id,
            "workload_id": identifier,
            "service_name": identifier,
            "context_ref": context_ref,
            "repository_ref": repository_ref,
            "retry_count": 0,
            "incorrect_removals": 0,
            "reductions_attempted": 0,
            "reductions_accepted": 0,
            "reductions_rejected": 0,
            "accepted": False,
            "graph_node": "START",
        }
        config = {"configurable": {"thread_id": f"{run_id}:{identifier}"}}
        final = cast(WorkloadGraphState, graph.invoke(initial, config))
        trajectory_path = recorder.write_summary()
        original = final["original_policy"]
        policy = final["current_policy"] if final["accepted"] else original
        return WorkloadExecution(
            run_id=run_id,
            accepted=final["accepted"],
            original_policy=original,
            final_policy=policy,
            original_risk=final["original_risk"],
            final_risk=score_policy(policy),
            verification=final["verification_result"],
            repair_iterations=final["retry_count"],
            incorrect_removals=final["incorrect_removals"],
            trajectory_path=trajectory_path,
        )

    def _build(
        self,
        environment: EnvironmentAdapter,
        record: Callable[[TrajectoryEvent], None],
    ) -> Any:
        def emit(
            state: WorkloadGraphState,
            agent: str,
            action: str,
            reason: str,
            *,
            decision: str | None = None,
            details: dict[str, Any] | None = None,
        ) -> None:
            record(
                TrajectoryEvent(
                    state["run_id"],
                    environment.name,
                    agent,
                    action,
                    reason,
                    decision=decision,
                    retry_count=state.get("retry_count", 0),
                    details=details or {},
                )
            )

        def load_context(state: WorkloadGraphState) -> WorkloadGraphState:
            emit(
                state,
                "orchestrator",
                "load_service_context",
                "loaded compact service-scoped context reference",
                details={
                    "context_ref": state.get("context_ref", ""),
                    "repository_ref": state.get("repository_ref", ""),
                },
            )
            return {"graph_node": "LOAD_SERVICE_CONTEXT"}

        def inspect(state: WorkloadGraphState) -> WorkloadGraphState:
            policy = environment.get_current_policy()
            risk = score_policy(policy)
            emit(
                state,
                "inspector",
                "inspect",
                "resolved policy and deterministic risk",
                details={
                    "permissions": effective_permission_count(policy),
                    "risk": risk.score,
                    "risk_uncapped": risk.uncapped_score,
                    "risk_findings": [
                        {"reason": finding.reason, "points": finding.points}
                        for finding in risk.findings
                    ],
                },
            )
            return {
                "original_policy": policy,
                "current_policy": policy,
                "last_known_good_policy": policy,
                "original_risk": risk,
                "current_risk": risk,
                "effective_permissions": effective_permission_count(policy),
                "namespace": policy.service_account_namespace,
                "service_account": policy.service_account,
                "graph_node": "INSPECT_RBAC",
            }

        def gather(state: WorkloadGraphState) -> WorkloadGraphState:
            observed = environment.get_observed_usage()
            emit(
                state,
                "inspector",
                "gather_evidence",
                f"gathered {len(observed)} normalized Kubernetes calls",
                details={"observed_events": [event.to_dict() for event in observed]},
            )
            return {"observed_events": observed, "graph_node": "GATHER_EVIDENCE"}

        def generate(state: WorkloadGraphState) -> WorkloadGraphState:
            original = state["original_policy"]
            candidate = self.reducer.propose(original, state["observed_events"])
            risk = score_policy(candidate)
            emit(
                state,
                "reducer",
                "propose_policy",
                "narrowest supported policy for observed calls; verification still required",
                details={
                    "permissions": effective_permission_count(candidate),
                    "removed_permissions": effective_permission_count(original)
                    - effective_permission_count(candidate),
                    "risk": risk.score,
                    "candidate_permissions": [item.display() for item in candidate.permissions],
                },
            )
            return {
                "candidate_policy": candidate,
                "candidate_risk": risk,
                "reductions_attempted": state.get("reductions_attempted", 0) + 1,
                "graph_node": "GENERATE_CANDIDATE",
            }

        def validate(state: WorkloadGraphState) -> WorkloadGraphState:
            candidate_events = (
                KubeEvent(
                    permission.api_group,
                    permission.resource,
                    permission.verb,
                    permission.namespace,
                    permission.resource_name,
                )
                for permission in state["candidate_policy"].permissions
            )
            if not all(
                is_authorized(state["original_policy"], event) for event in candidate_events
            ):
                raise ValueError("candidate contains a capability absent from the original policy")
            emit(
                state,
                "rules_engine",
                "validate_candidate",
                "candidate is normalized and constrained to original capabilities",
            )
            return {"graph_node": "VALIDATE_CANDIDATE"}

        def apply(state: WorkloadGraphState) -> WorkloadGraphState:
            candidate = state["candidate_policy"]
            environment.apply_policy(candidate)
            emit(
                state,
                "verifier",
                "apply_policy",
                "applied deterministic candidate in the controlled environment",
                details={
                    "attempt": state.get("retry_count", 0) + 1,
                    "permissions": effective_permission_count(candidate),
                    "risk": score_policy(candidate).score,
                },
            )
            return {"current_policy": candidate, "graph_node": "APPLY_CANDIDATE"}

        def verify(state: WorkloadGraphState) -> WorkloadGraphState:
            result = environment.verify_workload()
            failure = None if result.passed else environment.describe_failure(result)
            failure_type: FailureType | None = None
            if failure is not None:
                failure_type = "rbac" if failure.authorization_denial else "unrelated"
            emit(
                state,
                "verifier",
                "verify",
                f"{result.tests_passed}/{result.tests_total} verification tests passed",
                decision="accept" if result.passed else "diagnose",
                details={
                    "denied_events": [event.to_dict() for event in result.denied_events],
                    "tests_passed": result.tests_passed,
                    "tests_total": result.tests_total,
                    "duration_seconds": result.duration_seconds,
                    "test_output": result.stdout.strip(),
                },
            )
            return {
                "verification_result": result,
                "failure_details": failure,
                "failure_type": failure_type,
                "missing_permissions": failure.missing_events if failure else (),
                "graph_node": "VERIFY",
            }

        def route_verification(state: WorkloadGraphState) -> str:
            if state["verification_result"].passed:
                return "check_more_reductions"
            if (
                state.get("failure_type") == "rbac"
                and state["retry_count"] < self.max_repair_iterations
            ):
                return "diagnose_failure"
            return "restore_last_known_good"

        def check_more(state: WorkloadGraphState) -> WorkloadGraphState:
            emit(
                state,
                "orchestrator",
                "check_more_reductions",
                "observed-only candidate is already the narrowest supported candidate",
                decision="final_verify",
            )
            return {"graph_node": "CHECK_MORE_REDUCTIONS"}

        def final_verify(state: WorkloadGraphState) -> WorkloadGraphState:
            emit(
                state,
                "verifier",
                "final_verify",
                "declared verification passed for the retained candidate",
                decision="accept",
            )
            return {"accepted": True, "failure_type": None, "graph_node": "FINAL_VERIFY"}

        def diagnose(state: WorkloadGraphState) -> WorkloadGraphState:
            failure = state["failure_details"]
            assert failure is not None
            explanation = self.failure_reasoner.explain_with_source(failure)
            emit(
                state,
                "reasoner",
                "diagnose_failure",
                explanation.text,
                decision="repair",
                details={"reasoner": explanation.source, "reasoner_error": explanation.error},
            )
            return {"graph_node": "DIAGNOSE_FAILURE"}

        def repair(state: WorkloadGraphState) -> WorkloadGraphState:
            failure = state["failure_details"]
            assert failure is not None
            candidate = state["candidate_policy"]
            try:
                repaired = self.verifier.repair(candidate, failure, state["original_policy"])
            except ValueError:
                return {"failure_type": "unrecoverable", "graph_node": "REPAIR_POLICY"}
            additions = len(repaired.permissions) - len(candidate.permissions)
            if additions <= 0:
                return {"failure_type": "unrecoverable", "graph_node": "REPAIR_POLICY"}
            retry_count = state["retry_count"] + 1
            emit(
                state,
                "verifier",
                "repair_policy",
                "restored only denied capabilities allowed by the original policy",
                decision="retry",
                details={
                    "restored": [event.to_dict() for event in failure.missing_events],
                    "permissions_after_repair": effective_permission_count(repaired),
                    "risk_after_repair": score_policy(repaired).score,
                },
            )
            return {
                "candidate_policy": repaired,
                "candidate_risk": score_policy(repaired),
                "retry_count": retry_count,
                "incorrect_removals": state["incorrect_removals"] + additions,
                "graph_node": "REPAIR_POLICY",
            }

        def route_repair(state: WorkloadGraphState) -> str:
            return (
                "validate_candidate"
                if state.get("failure_type") != "unrecoverable"
                else "restore_last_known_good"
            )

        def restore(state: WorkloadGraphState) -> WorkloadGraphState:
            environment.restore_policy()
            emit(
                state,
                "orchestrator",
                "restore_policy",
                "candidate did not pass declared verification",
                decision="reject",
            )
            return {
                "current_policy": state["last_known_good_policy"],
                "accepted": False,
                "reductions_rejected": state.get("reductions_rejected", 0) + 1,
                "graph_node": "RESTORE_LAST_KNOWN_GOOD",
            }

        def human_review(state: WorkloadGraphState) -> WorkloadGraphState:
            emit(
                state,
                "orchestrator",
                "human_review",
                "automatic repair was unsafe or exhausted; original policy restored",
                decision="review",
            )
            return {"graph_node": "HUMAN_REVIEW"}

        def finalize(state: WorkloadGraphState) -> WorkloadGraphState:
            accepted = state.get("accepted", False)
            policy = state["current_policy"]
            emit(
                state,
                "orchestrator",
                "finalize",
                "verified candidate retained" if accepted else "last-known-good policy retained",
                decision="accept" if accepted else "reject",
                details={
                    "permissions": effective_permission_count(policy),
                    "risk": score_policy(policy).score,
                    "final_permissions": [item.display() for item in policy.permissions],
                },
            )
            return {
                "current_risk": score_policy(policy),
                "reductions_accepted": 1 if accepted else 0,
                "graph_node": "FINALIZE_WORKLOAD",
            }

        def publish_result(state: WorkloadGraphState) -> WorkloadGraphState:
            emit(
                state,
                "orchestrator",
                "publish_result_event",
                "durable worker may now publish the result and acknowledge its task",
            )
            return {"graph_node": "PUBLISH_RESULT_EVENT"}

        builder = StateGraph(WorkloadGraphState)
        nodes = {
            "load_service_context": load_context,
            "inspect_rbac": inspect,
            "gather_evidence": gather,
            "generate_candidate": generate,
            "validate_candidate": validate,
            "apply_candidate": apply,
            "verify": verify,
            "check_more_reductions": check_more,
            "final_verify": final_verify,
            "diagnose_failure": diagnose,
            "repair_policy": repair,
            "restore_last_known_good": restore,
            "human_review": human_review,
            "finalize_workload": finalize,
            "publish_result_event": publish_result,
        }
        for name, node in nodes.items():
            builder.add_node(name, node)
        builder.add_edge(START, "load_service_context")
        builder.add_edge("load_service_context", "inspect_rbac")
        builder.add_edge("inspect_rbac", "gather_evidence")
        builder.add_edge("gather_evidence", "generate_candidate")
        builder.add_edge("generate_candidate", "validate_candidate")
        builder.add_edge("validate_candidate", "apply_candidate")
        builder.add_edge("apply_candidate", "verify")
        builder.add_conditional_edges("verify", route_verification)
        builder.add_edge("check_more_reductions", "final_verify")
        builder.add_edge("final_verify", "finalize_workload")
        builder.add_edge("diagnose_failure", "repair_policy")
        builder.add_conditional_edges("repair_policy", route_repair)
        builder.add_edge("restore_last_known_good", "human_review")
        builder.add_edge("human_review", "finalize_workload")
        builder.add_edge("finalize_workload", "publish_result_event")
        builder.add_edge("publish_result_event", END)
        return builder.compile(checkpointer=self.checkpointer, name="workload-optimization")
