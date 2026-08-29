from pathlib import Path

from agent_layer.orchestrator import KuberOrchestrator
from judge_layer.baseline import run_observed_only
from judge_layer.simulator import BenchmarkCase, SimulatorEnvironment, VerificationTest, load_benchmark
from rules_engine.models import KubeEvent, Permission, Policy
from rules_engine.rbac.authorization import is_authorized


def test_hidden_path_breaks_baseline_and_is_repaired(tmp_path: Path) -> None:
    case = load_benchmark(Path("judge_layer/benchmarks/07_hidden_path"))
    baseline_environment = SimulatorEnvironment(case)
    baseline_environment.apply_policy(run_observed_only(case.initial_policy, case.observed_events))
    assert not baseline_environment.verify_workload().passed

    environment = SimulatorEnvironment(case)
    result = KuberOrchestrator(trajectory_directory=tmp_path).run(environment, run_id="hidden-path")
    assert result.accepted
    assert result.verification.passed
    assert result.repair_iterations == 1
    assert is_authorized(result.final_policy, KubeEvent("", "configmaps", "list", "payments"))
    assert (tmp_path / "hidden-path.jsonl").exists()
    assert (tmp_path / "hidden-path.md").exists()


def test_unrepairable_failure_restores_original_policy(tmp_path: Path) -> None:
    original = Policy((Permission("", "configmaps", "get", "payments", "app-config"),))
    case = BenchmarkCase(
        "unrepairable",
        "Unrepairable",
        "verification asks for capability absent from original",
        original,
        (KubeEvent("", "configmaps", "get", "payments", "app-config"),),
        (VerificationTest("invalid expectation", (KubeEvent("", "secrets", "get", "payments", "x"),)),),
    )
    environment = SimulatorEnvironment(case)
    result = KuberOrchestrator(trajectory_directory=tmp_path).run(environment)
    assert not result.accepted
    assert result.final_policy == original
    assert environment.get_current_policy() == original

