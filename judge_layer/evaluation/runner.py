from __future__ import annotations

import csv
import json
from argparse import ArgumentParser
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from agent_layer.orchestrator import KuberOrchestrator
from judge_layer.evaluation.compare import evaluate_baseline, evaluate_kuber
from judge_layer.evaluation.metrics import CaseResultRow, summarize
from judge_layer.evaluation.presenter import JudgeEvaluationPresenter
from judge_layer.evaluation.report import console_table, markdown_report
from judge_layer.evaluation.system_benchmarks import (
    evaluate_system_baseline,
    evaluate_system_kuber,
    load_system_benchmark,
)
from judge_layer.simulator import load_benchmark


def run_evaluation(
    benchmark_root: Path = Path("judge_layer/benchmarks"),
    artifact_root: Path = Path("artifacts/evaluation"),
    trajectory_root: Path = Path("artifacts/trajectories"),
    *,
    detailed: bool = True,
) -> dict[str, object]:
    paths = sorted(
        path
        for path in benchmark_root.iterdir()
        if path.is_dir() and (path / "metadata.yaml").exists()
    )
    if len(paths) < 12:
        raise RuntimeError(f"expected at least 12 benchmark cases, found {len(paths)}")
    presenter = JudgeEvaluationPresenter() if detailed else None
    if presenter is not None:
        presenter.start(len(paths), benchmark_root)
    case_rows: list[CaseResultRow] = []
    baseline_values = []
    kuber_values = []
    for index, path in enumerate(paths, 1):
        if (path / "system.yaml").exists():
            benchmark = load_system_benchmark(path, benchmark_root)
            if presenter is not None:
                presenter.system_case_started(index, len(paths), benchmark)
            baseline = evaluate_system_baseline(benchmark)
            kuber = evaluate_system_kuber(benchmark, trajectory_root)
            if presenter is not None:
                presenter.system_case_finished(baseline, kuber)
            baseline_values.append(baseline)
            kuber_values.append(kuber)
            case_rows.append(
                {
                    "id": benchmark.identifier,
                    "name": benchmark.name,
                    "baseline": baseline.to_dict(),
                    "kuber": kuber.to_dict(),
                }
            )
            continue
        case = load_benchmark(path)
        if presenter is not None:
            presenter.case_started(index, len(paths), path, case)
        baseline_policy, baseline = evaluate_baseline(case)
        if presenter is not None:
            presenter.baseline(case, baseline_policy, baseline)
            presenter.agent_started()
        orchestrator = KuberOrchestrator(
            trajectory_directory=trajectory_root,
            event_callback=presenter.handle_event if presenter is not None else None,
        )
        final_policy, kuber = evaluate_kuber(case, orchestrator)
        if presenter is not None:
            presenter.case_finished(
                kuber,
                final_policy,
                trajectory_root / f"evaluation-{case.identifier}.jsonl",
            )
        baseline_values.append(baseline)
        kuber_values.append(kuber)
        case_rows.append(
            {
                "id": case.identifier,
                "name": case.name,
                "baseline": baseline.to_dict(),
                "kuber": kuber.to_dict(),
            }
        )
    baseline_summary = summarize(baseline_values)
    kuber_summary = summarize(kuber_values)
    output: dict[str, object] = {
        "methodology": {
            "primary_metric": "Validated Risk Reduction",
            "risk_score": "Kuber benchmark heuristic v1; not an industry standard",
        },
        "baseline": baseline_summary.to_dict(),
        "kuber": kuber_summary.to_dict(),
        "cases": case_rows,
    }
    artifact_root.mkdir(parents=True, exist_ok=True)
    (artifact_root / "results.json").write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with (artifact_root / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["id", "name", "system", *asdict(baseline_values[0]).keys()]
        )
        writer.writeheader()
        for row in case_rows:
            for system, metrics in (
                ("baseline", row["baseline"]),
                ("kuber", row["kuber"]),
            ):
                writer.writerow({"id": row["id"], "name": row["name"], "system": system, **metrics})
    (artifact_root / "report.md").write_text(
        markdown_report(baseline_summary, kuber_summary, case_rows), encoding="utf-8"
    )
    summary = console_table(baseline_summary, kuber_summary)
    if presenter is not None:
        presenter.finish(summary, artifact_root)
    else:
        print(summary)
    return output


def main(arguments: Sequence[str] | None = None) -> None:
    parser = ArgumentParser(description="Run Kuber's deterministic benchmark evaluation.")
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="print only aggregate metrics; artifacts and trajectories are still generated",
    )
    options = parser.parse_args(arguments)
    run_evaluation(detailed=not options.summary_only)


if __name__ == "__main__":
    main()
