# Kuber

> **An agentic least-privilege compiler for Kubernetes workloads.**

**Want to evaluate Kuber?** → [Judge guide](docs/JUDGE_GUIDE.md)  
**Want to run the real Kubernetes demo?** → [Demo guide](docs/DEMO_GUIDE.md)  
**Want to understand the system?** → [Architecture](docs/ARCHITECTURE.md)

Kubernetes workload owners often retain broad RBAC because removing a grant
can break a rare but legitimate path. Static or runtime observation shows what
happened, not everything the owner declares must work. Kuber creates a narrow
candidate, applies it in a controlled environment, runs owner-provided tests,
repairs only demonstrated authorization failures, and accepts the result only
after verification passes.

The LLM may propose and explain. **The environment proves.** The complete judge
workflow is deterministic and requires no cluster, Docker, kubeconfig, cloud
account, API key, or network after dependencies are installed.

Optional explanations use Gemini. Copy `.env.example` to `.env`, set
`GEMINI_API_KEY`, and optionally change `GEMINI_MODEL`. Without a key, Kuber
continues with deterministic failure explanations.

## Architecture

```text
                    deterministic core
              ┌──────────────────────────┐
              │ rules_engine             │
              │ parse · resolve · authz  │
              │ minimize · risk · YAML   │
              └────────────▲─────────────┘
                           │
              ┌────────────┴─────────────┐
              │ agent_layer              │
              │ inspect → reduce → verify│
              │ diagnose → repair        │
              └──────▲────────────▲──────┘
                     │ same adapter API
          ┌──────────┘             └──────────┐
  ┌───────┴────────┐                 ┌────────┴─────────┐
  │ Judge simulator│                 │ kind/Kubernetes  │
  │ normalized RBAC│                 │ real API + RBAC  │
  └────────────────┘                 └──────────────────┘
```

Only the environment adapter changes. The simulator models only the supported
authorization decisions; it is not a Kubernetes simulator.

## Judge quickstart

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/):

```bash
uv sync
make test
make evaluate
```

The latest actual local run produced 31 passing tests. Across 10 identical
benchmark inputs, the observed-only baseline preserved all declared behavior in
3 cases; Kuber preserved it in all 10 after 7 repair iterations. Generated
average Validated Risk Reduction was 28.8% for the baseline and 91.3% for
Kuber. Re-run `make evaluate` to regenerate the source-of-truth JSON, CSV,
Markdown report, and JSONL trajectories rather than relying on these snapshot
figures.

## Live demo quickstart

```bash
make demo-check
make demo-up
make demo
make demo-down
```

The demo deploys the source in `workload_src/payment_controller` with a real
ServiceAccount. Its tracked client still performs real Kubernetes calls. A
leader-election path is omitted during warmup and exercised by the full smoke
test so Kubernetes can issue a real 403 and the verifier can repair it.

## Outputs

- `artifacts/evaluation/results.json` and `results.csv`: machine-readable data
- `artifacts/evaluation/report.md`: generated comparison
- `artifacts/trajectories/*.jsonl`: machine-readable agent decisions
- `artifacts/policies/*.yaml`: generated candidates

## Safety boundary

Automatic mutation is enabled only when the context is exactly `kind-kuber`
and namespace `kuber-demo` has `kuber.dev/sandbox=true`. Otherwise the live
adapter defaults to dry-run, writes a proposal, and refuses application. Demo
credentials are fake; kubeconfigs and real secrets are never stored.

## Scope

The MVP covers core Pods, ConfigMaps, Secrets and Services; apps Deployments;
batch Jobs; coordination Leases; seven common verbs; wildcards; namespace
scope; and safe named-resource behavior. It does not claim complete Kubernetes
authorization semantics. See [limitations](docs/LIMITATIONS.md) and the
[security model](docs/SECURITY_MODEL.md).
