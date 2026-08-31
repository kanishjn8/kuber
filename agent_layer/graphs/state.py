from __future__ import annotations

from typing import Literal

from typing_extensions import TypedDict

from agent_layer.interfaces import FailureDescription, VerificationResult
from rules_engine.models import KubeEvent, Policy
from rules_engine.risk import RiskAssessment

FailureType = Literal["rbac", "unrelated", "unrecoverable"]


class WorkloadGraphState(TypedDict, total=False):
    """Checkpoint-safe state for one workload optimization task."""

    run_id: str
    task_id: str
    workload_id: str
    service_name: str
    namespace: str
    deployment_name: str
    service_account: str
    repository_ref: str
    context_ref: str
    original_policy: Policy
    current_policy: Policy
    candidate_policy: Policy
    last_known_good_policy: Policy
    effective_permissions: int
    observed_events: tuple[KubeEvent, ...]
    source_evidence: tuple[str, ...]
    original_risk: RiskAssessment
    current_risk: RiskAssessment
    candidate_risk: RiskAssessment
    verification_result: VerificationResult
    failure_type: FailureType | None
    failure_details: FailureDescription | None
    missing_permissions: tuple[KubeEvent, ...]
    reductions_attempted: int
    reductions_accepted: int
    reductions_rejected: int
    retry_count: int
    incorrect_removals: int
    accepted: bool
    graph_node: str
    trajectory_ref: str | None
