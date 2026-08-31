# Kuber

**Kuber safely removes unnecessary Kubernetes permissions without breaking the application.**

Kubernetes services often collect more permissions than they really need. Removing those permissions by hand is risky, because a permission that looks unused may still be needed by a rare workflow.

Kuber solves this by making a smaller RBAC policy, applying it in a safe sandbox, running the service's own tests, and restoring only the permissions that the tests prove are still required.

## The idea in one example

Imagine a worker service currently has permission to:

- read ConfigMaps
- create Jobs
- get Jobs
- delete Jobs
- list Pods
- change Deployments
- read Secrets

During normal traffic, Kuber may only observe the service reading a ConfigMap.

A simple "observed-only" approach would keep only that permission. But the service may also have a rare reconciliation flow that creates and manages Kubernetes Jobs.

Kuber handles that safely:

```text
Observe normal usage
        ↓
Create a smaller RBAC policy
        ↓
Apply it in the sandbox
        ↓
Run the service's real smoke tests
        ↓
If everything works → keep the policy

If Kubernetes returns 403
        ↓
Find the missing permission
        ↓
Restore only that permission
        ↓
Run the tests again
```

That verification loop is the main idea behind Kuber.

## Who is Kuber for?

Kuber is aimed at platform, DevOps, SRE, and Kubernetes security teams that manage RBAC across many services.

The current problem is simple:

- RBAC policies slowly become too broad.
- Manually auditing them takes time.
- Runtime logs only show what happened recently.
- Rare but valid behavior may be missing from those logs.
- Removing permissions without testing can break production workloads.

Kuber treats least privilege as a **verification problem**, not just a log-analysis problem.

## What happened in our evaluation?

We tested Kuber on 14 fixed scenarios.

The simple baseline only kept **4 of the 14 scenarios working**.

Kuber kept **all 14 working** while still removing most unnecessary access.

| Result | Simple baseline | Kuber |
|---|---:|---:|
| Scenarios that still worked | 4 / 14 | **14 / 14** |
| Raw permission reduction | 97.5% | 95.3% |
| Verified risk reduction | 27.4% | **91.9%** |

Why did the baseline remove slightly more permissions? Because it removed permissions that some rare workflows still needed.

Kuber kept a few extra permissions only when verification proved they were necessary.

> **Removing more permissions is not useful if the application stops working.**

### What does "verified risk reduction" mean?

Kuber uses a simple project risk score for broad Kubernetes permissions.

We only count that risk reduction when the workload's tests still pass.

If the policy breaks the workload, its verified improvement is treated as zero.

The full methodology is in [docs/EVALUATION.md](docs/EVALUATION.md).

## How Kuber works

```text
Kubernetes + source repository
            ↓
     Discover services
            ↓
 Build small context per service
            ↓
          Kafka
     distributes work
      ↙     ↓     ↘
   Worker Worker Worker
      ↓     ↓     ↓
  LangGraph workflow
            ↓
 Deterministic RBAC engine
            ↓
 Apply smaller policy
            ↓
 Run service verification
       ↙           ↘
     PASS          403
      ↓             ↓
    Keep      diagnose + repair
                    ↓
                  retry
```

### What each part does

- **Service discovery** finds opted-in Kubernetes workloads and maps them to their source code.
- **Service-scoped context** means a worker reads only the files for the service it is analyzing instead of repeatedly loading the whole repository.
- **Kafka** distributes independent service-optimization tasks across workers.
- **Redis** is used for coordination such as preventing two workers from changing the same workload at the same time.
- **LangGraph** controls the per-service workflow: inspect → propose → apply → verify → diagnose → repair → retry.
- **Rules engine** performs deterministic RBAC parsing, validation, minimization, and risk scoring.
- **Kubernetes** is the final authority in the live demo: it either allows the workload's API call or returns a real 403.
- **Gemini is optional** and is only used to explain failures in plain language. It never decides whether a policy is allowed.

## What makes Kuber agentic?

Each service is handled by a stateful LangGraph workflow.

The workflow does not just produce one answer. It:

1. gathers evidence,
2. proposes a smaller policy,
3. calls deterministic tools,
4. applies the candidate in a controlled environment,
5. observes the result,
6. changes its next action based on success or failure,
7. repairs the policy when needed,
8. retries until it reaches a verified result or a bounded retry limit.

The environment provides feedback, and that feedback changes the next step.

## Real hidden-path example

The `worker-service` warmup intentionally does **not** run its rare Job reconciliation flow.

Kuber first sees only normal usage and creates a smaller policy.

During full verification:

```text
REAL 403: jobs:create
→ restore create only
→ retry

REAL 403: jobs:get
→ restore get only
→ retry

REAL 403: jobs:delete
→ restore delete only
→ retry

3/3 tests pass
```

This is the key failure mode Kuber was built to handle.

## Important limitation

Kuber does **not** invent application tests.

It verifies the behavior covered by the workload owner's verification profile.

That means Kuber can prove:

> "This smaller policy still supports the behavior we tested."

It cannot prove that every possible future code path has been covered if the owner's tests do not exercise it.

## Quick start

### Deterministic evaluation

This path does not require Docker, Kubernetes, Kafka, Redis, or an LLM key.

```bash
git clone <repository-url> kuber
cd kuber
test -f Makefile && test -d kuber_cli
uv sync --extra kubernetes
make quality
make evaluate
```

Run these commands from the repository root—the directory containing
`Makefile`, `pyproject.toml`, and `kuber_cli/`. The installed command remains
`kuber`; `kuber_cli` is only the internal Python package name.

### Real Kubernetes sandbox

Requirements:

- Docker
- kind
- kubectl
- Python 3.12+
- uv

```bash
make sandbox-check
make sandbox-up
make sandbox-status
make sandbox-run
make sandbox-down
```

The sandbox creates:

- a local `kind-kuber` cluster,
- Kafka in KRaft mode,
- Redis,
- five independently discovered services,
- separate ServiceAccounts and RBAC policies,
- three Kafka consumers,
- real service smoke tests.

## Safety

Kuber is pre-1.0.

The bundled live adapter is intentionally limited to the local reference sandbox.

It may mutate RBAC only when:

- the kubectl context is exactly `kind-kuber`, and
- the namespace is marked with `kuber.dev/sandbox=true`.

Outside that boundary, Kuber stays in dry-run mode.

The bundled adapter should not be treated as production infrastructure.

## Submission material

- [Evaluation](docs/EVALUATION.md)
- [Improvement changelog](docs/IMPROVEMENT_CHANGELOG.md)
- [Reproduction guide](docs/REPRODUCTION.md)
- [Agent trajectories](docs/AGENT_TRAJECTORIES.md)
- [Reference sandbox](docs/DEMO_GUIDE.md)
- [Video script](docs/VIDEO_SCRIPT.md)

## Repository layout

```text
rules_engine/        deterministic RBAC logic
agent_layer/         LangGraph workflows and checkpoints
event_layer/         Kafka events, workers, retries, locks
context_layer/       discovery and service-scoped indexing
kubernetes_runtime/  guarded Kubernetes adapter
judge_layer/         deterministic benchmark evaluation
kuber_cli/            installed `kuber` command and application presentation
deploy/kind/         local sandbox manifests
examples/            reference workloads
docs/                submission documentation
```

## Main lesson

> **Runtime observation shows what a service used. It does not always show everything the service needs.**

Kuber therefore does not trust observation alone.

It proposes a smaller policy, tests it, learns from real failures, repairs only what is necessary, and verifies again.
