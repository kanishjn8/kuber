from __future__ import annotations

from dataclasses import dataclass

from agent_layer.interfaces import EnvironmentAdapter
from rules_engine.minimizer import CandidateReduction, candidate_reductions
from rules_engine.models import KubeEvent, Policy
from rules_engine.risk import RiskAssessment, score_policy


@dataclass(frozen=True, slots=True)
class InspectionResult:
    policy: Policy
    observed: tuple[KubeEvent, ...]
    risk: RiskAssessment
    unused: tuple[CandidateReduction, ...]


class InspectorAgent:
    def inspect(self, environment: EnvironmentAdapter) -> InspectionResult:
        policy = environment.get_current_policy()
        observed = environment.get_observed_usage()
        return InspectionResult(policy, observed, score_policy(policy), candidate_reductions(policy, observed))

