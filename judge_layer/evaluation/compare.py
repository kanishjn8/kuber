from __future__ import annotations

from time import perf_counter

from agent_layer.orchestrator import KuberOrchestrator
from judge_layer.baseline import run_observed_only
from judge_layer.evaluation.metrics import SystemCaseMetrics
from judge_layer.simulator import BenchmarkCase, SimulatorEnvironment
from rules_engine.models import Policy
from rules_engine.rbac.canonicalizer import effective_permission_count, expand_policy
from rules_engine.risk import score_policy


def _high_risk_count(policy: Policy) -> int:
    return sum(
        permission.verb == "*"
        or permission.resource == "*"
        or permission.resource == "secrets"
        or permission.verb in {"create", "delete"}
        for permission in policy.permissions
    )


def _metrics(
    initial: Policy,
    final: Policy,
    success: bool,
    runtime: float,
    *,
    incorrect: int = 0,
    repairs: int = 0,
) -> SystemCaseMetrics:
    initial_risk = score_policy(initial).score
    final_risk = score_policy(final).score
    risk_reduction = 100 * (initial_risk - final_risk) / initial_risk if initial_risk else 0.0
    initial_count = effective_permission_count(initial)
    final_count = effective_permission_count(final)
    raw_reduction = 100 * (initial_count - final_count) / initial_count if initial_count else 0.0
    cluster_wide = sum(
        permission.namespace is None for permission in expand_policy(final).permissions
    )
    return SystemCaseMetrics(
        success,
        initial_risk,
        final_risk,
        risk_reduction,
        risk_reduction if success else 0.0,
        raw_reduction,
        initial_count,
        final_count,
        _high_risk_count(final),
        cluster_wide,
        incorrect,
        repairs,
        runtime,
    )


def evaluate_baseline(case: BenchmarkCase) -> tuple[Policy, SystemCaseMetrics]:
    environment = SimulatorEnvironment(case)
    started = perf_counter()
    candidate = run_observed_only(case.initial_policy, case.observed_events)
    environment.apply_policy(candidate)
    result = environment.verify_workload()
    elapsed = perf_counter() - started
    return candidate, _metrics(case.initial_policy, candidate, result.passed, elapsed)


def evaluate_kuber(
    case: BenchmarkCase, orchestrator: KuberOrchestrator
) -> tuple[Policy, SystemCaseMetrics]:
    environment = SimulatorEnvironment(case)
    started = perf_counter()
    result = orchestrator.run(environment, run_id=f"evaluation-{case.identifier}")
    elapsed = perf_counter() - started
    return result.final_policy, _metrics(
        case.initial_policy,
        result.final_policy,
        result.verification.passed and result.accepted,
        elapsed,
        incorrect=result.incorrect_removals,
        repairs=result.repair_iterations,
    )
