from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class SystemCaseMetrics:
    functional_success: bool
    initial_risk: int
    final_risk: int
    risk_reduction_percent: float
    validated_risk_reduction: float
    raw_permission_reduction_percent: float
    initial_permissions: int
    final_permissions: int
    high_risk_permissions_remaining: int
    cluster_wide_grants_remaining: int
    incorrect_removals: int
    repair_iterations: int
    runtime_seconds: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class EvaluationSummary:
    cases: int
    functional_successes: int
    functional_success_rate: float
    average_validated_risk_reduction: float
    average_raw_permission_reduction: float
    average_risk_reduction: float
    high_risk_permissions_remaining: int
    cluster_wide_grants_remaining: int
    incorrect_removals: int
    repair_iterations: int
    average_runtime_seconds: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def summarize(values: list[SystemCaseMetrics]) -> EvaluationSummary:
    count = len(values)
    if not count:
        return EvaluationSummary(0, 0, 0.0, 0.0, 0.0, 0.0, 0, 0, 0, 0, 0.0)
    successes = sum(item.functional_success for item in values)
    return EvaluationSummary(
        cases=count,
        functional_successes=successes,
        functional_success_rate=100 * successes / count,
        average_validated_risk_reduction=sum(item.validated_risk_reduction for item in values) / count,
        average_raw_permission_reduction=sum(item.raw_permission_reduction_percent for item in values) / count,
        average_risk_reduction=sum(item.risk_reduction_percent for item in values) / count,
        high_risk_permissions_remaining=sum(item.high_risk_permissions_remaining for item in values),
        cluster_wide_grants_remaining=sum(item.cluster_wide_grants_remaining for item in values),
        incorrect_removals=sum(item.incorrect_removals for item in values),
        repair_iterations=sum(item.repair_iterations for item in values),
        average_runtime_seconds=sum(item.runtime_seconds for item in values) / count,
    )

