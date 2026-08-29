from pathlib import Path

from judge_layer.evaluation.runner import run_evaluation
from judge_layer.simulator import load_benchmark
from rules_engine.rbac.authorization import is_authorized


def test_all_benchmarks_have_valid_expected_policies() -> None:
    paths = sorted(Path("judge_layer/benchmarks").glob("*/metadata.yaml"))
    assert len(paths) >= 10
    for metadata in paths:
        case = load_benchmark(metadata.parent)
        assert case.expected_policy is not None
        for test in case.verification_tests:
            assert all(is_authorized(case.expected_policy, event) for event in test.events), (case.identifier, test.name)


def test_evaluation_writes_real_artifacts(tmp_path: Path) -> None:
    artifacts = tmp_path / "evaluation"
    output = run_evaluation(Path("judge_layer/benchmarks"), artifacts, tmp_path / "trajectories")
    assert output["kuber"]["functional_successes"] == 10  # type: ignore[index]
    assert output["baseline"]["functional_successes"] < 10  # type: ignore[index]
    assert (artifacts / "results.json").exists()
    assert (artifacts / "results.csv").exists()
    assert "Validated Risk Reduction" in (artifacts / "report.md").read_text(encoding="utf-8")

