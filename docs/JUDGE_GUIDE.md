# Judge guide

The judge path needs Python 3.12+ and uv. It does not inspect kubeconfig or use
Docker, Kubernetes, an LLM, or a cloud account.

```bash
uv sync
make test
make evaluate
```

`make evaluate` loads all directories under `judge_layer/benchmarks`, sends the
same initial policy and observed events to the baseline and Kuber, runs every
declared verification event, calculates metrics, writes artifacts, and prints a
comparison table. A missing benchmark or fewer than ten cases is an error.

Inspect `artifacts/evaluation/results.json` for exact values and
`artifacts/trajectories/evaluation-*.jsonl` for decisions. Delete generated
artifacts at any time; the next evaluation recreates them.

