from pathlib import Path

from judge_layer.evaluation.runner import run_evaluation
from judge_layer.simulator import load_benchmark
from rules_engine.rbac.authorization import is_authorized


def test_all_benchmarks_have_valid_expected_policies() -> None:
    paths = sorted(
        path
        for path in Path("judge_layer/benchmarks").glob("*/metadata.yaml")
        if not (path.parent / "system.yaml").exists()
    )
    assert len(paths) >= 10
    for metadata in paths:
        case = load_benchmark(metadata.parent)
        assert case.expected_policy is not None
        for test in case.verification_tests:
            assert all(is_authorized(case.expected_policy, event) for event in test.events), (
                case.identifier,
                test.name,
            )


def test_evaluation_writes_real_artifacts(tmp_path: Path, capsys) -> None:
    artifacts = tmp_path / "evaluation"
    output = run_evaluation(Path("judge_layer/benchmarks"), artifacts, tmp_path / "trajectories")
    assert output["kuber"]["functional_successes"] == 14  # type: ignore[index]
    assert output["baseline"]["functional_successes"] < 14  # type: ignore[index]
    assert (artifacts / "results.json").exists()
    assert (artifacts / "results.csv").exists()
    report = (artifacts / "report.md").read_text(encoding="utf-8")
    assert "Validated Risk Reduction" in report
    assert "Baseline permissions" in report
    assert "Kuber VRR" in report
    assert "../trajectories/evaluation-01_config_reader.md" in report
    rendered = capsys.readouterr().out
    assert "KUBER JUDGE" in rendered
    assert "╭" in rendered and "┏" in rendered
    assert "Discovered 14 benchmark cases" in rendered
    assert "Evidence files:" in rendered
    assert "HIDDEN PATH" in rendered
    assert "Observed-only baseline:" in rendered
    assert "Kuber agent flow:" in rendered
    assert "Inspector ->" in rendered
    assert "Reducer   ->" in rendered
    assert "Verifier  ->" in rendered
    assert "DENIED" in rendered
    assert "RESTORE" in rendered
    assert "Generated evidence:" in rendered
