from __future__ import annotations

from judge_layer.evaluation import runner


def test_summary_only_argument_disables_detailed_presenter(monkeypatch) -> None:
    calls: list[bool] = []

    def fake_run_evaluation(*, detailed: bool) -> dict[str, object]:
        calls.append(detailed)
        return {}

    monkeypatch.setattr(runner, "run_evaluation", fake_run_evaluation)

    runner.main(["--summary-only"])

    assert calls == [False]
