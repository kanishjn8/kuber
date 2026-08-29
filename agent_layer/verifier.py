from __future__ import annotations

from dataclasses import dataclass

from agent_layer.interfaces import EnvironmentAdapter, FailureDescription, VerificationResult
from rules_engine.minimizer import repair_policy
from rules_engine.models import Policy


@dataclass(frozen=True, slots=True)
class VerificationAttempt:
    result: VerificationResult
    failure: FailureDescription | None


class VerifierAgent:
    def verify(self, environment: EnvironmentAdapter, policy: Policy) -> VerificationAttempt:
        environment.apply_policy(policy)
        result = environment.verify_workload()
        failure = None if result.passed else environment.describe_failure(result)
        return VerificationAttempt(result, failure)

    def repair(self, candidate: Policy, failure: FailureDescription, original: Policy) -> Policy:
        if not failure.authorization_denial or not failure.missing_events:
            raise ValueError("failure cannot be repaired deterministically")
        return repair_policy(candidate, failure.missing_events, original)

