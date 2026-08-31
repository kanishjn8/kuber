from __future__ import annotations

from time import perf_counter

from agent_layer.interfaces import FailureDescription, VerificationResult
from judge_layer.simulator.workload_runner import BenchmarkCase
from rules_engine.models import KubeEvent, Policy
from rules_engine.rbac.authorization import is_authorized


class SimulatorEnvironment:
    """A narrow RBAC behavior simulator, deliberately not a Kubernetes simulator."""

    def __init__(self, case: BenchmarkCase) -> None:
        self.case = case
        self._original_policy = case.initial_policy
        self._current_policy = case.initial_policy

    @property
    def name(self) -> str:
        return f"simulator:{self.case.identifier}"

    def get_current_policy(self) -> Policy:
        return self._current_policy

    def get_observed_usage(self) -> tuple[KubeEvent, ...]:
        return self.case.observed_events

    def apply_policy(self, policy: Policy) -> None:
        self._current_policy = policy

    def verify_workload(self) -> VerificationResult:
        started = perf_counter()
        denied: list[KubeEvent] = []
        passed = 0
        for test in self.case.verification_tests:
            test_denials = [
                event for event in test.events if not is_authorized(self._current_policy, event)
            ]
            if test_denials:
                denied.extend(test_denials)
            else:
                passed += 1
        unique = {event: None for event in denied}
        stderr = "\n".join(f"403 Forbidden: {event.display()}" for event in unique)
        return VerificationResult(
            passed=not denied,
            tests_passed=passed,
            tests_total=len(self.case.verification_tests),
            denied_events=tuple(unique),
            stderr=stderr,
            duration_seconds=perf_counter() - started,
        )

    def restore_policy(self) -> None:
        self._current_policy = self._original_policy

    def describe_failure(self, result: VerificationResult) -> FailureDescription:
        if result.denied_events:
            return FailureDescription(
                summary=f"{len(result.denied_events)} required API capability/capabilities denied",
                missing_events=result.denied_events,
                authorization_denial=True,
            )
        return FailureDescription(result.stderr or "verification failed without an RBAC denial")
