from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

from agent_layer.orchestrator import KuberOrchestrator
from judge_layer.evaluation.compare import evaluate_baseline, evaluate_kuber
from judge_layer.evaluation.metrics import summarize
from judge_layer.evaluation.report import console_table, markdown_report
from judge_layer.simulator import load_benchmark


def run_evaluation(
    benchmark_root: Path = Path("judge_layer/benchmarks"),
    artifact_root: Path = Path("artifacts/evaluation"),
    trajectory_root: Path = Path("artifacts/trajectories"),
) -> dict[str, object]:
    paths = sorted(path for path in benchmark_root.iterdir() if path.is_dir() and (path / "metadata.yaml").exists())
    if len(paths) < 10:
        raise RuntimeError(f"expected at least 10 benchmark cases, found {len(paths)}")
    orchestrator = KuberOrchestrator(trajectory_directory=trajectory_root)
    case_rows: list[dict[str, object]] = []
    baseline_values = []
    kuber_values = []
    for path in paths:
        case = load_benchmark(path)
        _, baseline = evaluate_baseline(case)
        _, kuber = evaluate_kuber(case, orchestrator)
        baseline_values.append(baseline)
        kuber_values.append(kuber)
        case_rows.append({"id": case.identifier, "name": case.name, "baseline": baseline.to_dict(), "kuber": kuber.to_dict()})
    baseline_summary = summarize(baseline_values)
    kuber_summary = summarize(kuber_values)
    output: dict[str, object] = {
        "methodology": {"primary_metric": "Validated Risk Reduction", "risk_score": "Kuber benchmark heuristic v1; not an industry standard"},
        "baseline": baseline_summary.to_dict(),
        "kuber": kuber_summary.to_dict(),
        "cases": case_rows,
    }
    artifact_root.mkdir(parents=True, exist_ok=True)
    (artifact_root / "results.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (artifact_root / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "name", "system", *asdict(baseline_values[0]).keys()])
        writer.writeheader()
        for row in case_rows:
            for system in ("baseline", "kuber"):
                writer.writerow({"id": row["id"], "name": row["name"], "system": system, **row[system]})  # type: ignore[arg-type]
    (artifact_root / "report.md").write_text(markdown_report(baseline_summary, kuber_summary, case_rows), encoding="utf-8")
    print(console_table(baseline_summary, kuber_summary))
    return output


if __name__ == "__main__":
    run_evaluation()

