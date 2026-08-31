# Reproduction Guide

This guide is for someone starting from a clean environment.

Kuber has two execution paths:

1. **Deterministic evaluation** — easiest way to reproduce the main result.
2. **Real Kubernetes sandbox** — shows the same idea using a local Kubernetes cluster.

---

# 1. Deterministic evaluation

This path does **not** require:

- Docker
- Kubernetes
- Kafka
- Redis
- an LLM API key

## Requirements

- Python 3.12+
- `uv`
- Git

## Setup

```bash
git clone <repository-url> kuber
cd kuber
test -f Makefile && test -d kuber_cli
uv sync --extra kubernetes
```

## Verify the project

```bash
make quality
make build
```

## Run the evaluation

```bash
make evaluate
```

The evaluation runs the same benchmark cases through:

- the simple observed-only baseline,
- Kuber.

### Expected high-level result

With the current fixtures:

```text
Simple baseline:
4 / 14 scenarios remain functional

Kuber:
14 / 14 scenarios remain functional
```

The exact generated numbers should be read from the current evaluation artifacts rather than copied manually.

Generated output is written under:

```text
artifacts/evaluation/
artifacts/trajectories/
```

---

# 2. Context-routing experiment

Run:

```bash
make experiment-context
```

This compares:

```text
whole-repository loading
vs
service-scoped context
```

The goal is to show why workers should receive only the code/context relevant to their assigned service.

---

# 3. Real Kubernetes sandbox

This path demonstrates:

- real Kubernetes workloads,
- real ServiceAccounts,
- real RBAC changes,
- Kafka task distribution,
- Redis coordination,
- LangGraph repair loops,
- real Kubernetes 403 responses.

## Requirements

- Docker
- kind
- kubectl
- curl
- Python 3.12+
- uv

## Check prerequisites

```bash
make sandbox-check
```

## Start the sandbox

```bash
make sandbox-up
```

This creates a local disposable environment containing:

- `kind-kuber`,
- Kafka in KRaft mode,
- Redis,
- five source-mapped services,
- separate ServiceAccounts and RBAC policies.

## Check status

```bash
make sandbox-status
```

## Run Kuber

```bash
make sandbox-run
```

During the run you should see:

```text
service discovery
→ service-scoped context
→ Kafka task distribution
→ worker LangGraph execution
→ smaller RBAC policy
→ verification
→ real 403 on the hidden worker path
→ targeted repair
→ retry
→ final PASS
```

## Run the worker experiment

```bash
make experiment-workers
```

This compares one worker and three workers.

The project does not claim linear scaling from this small experiment.

## Shut down

```bash
make sandbox-down
```

---

# 4. Optional Gemini explanations

Gemini is **not required** for the deterministic evaluation.

Without an API key, Kuber uses local deterministic explanations.

To test Gemini:

```bash
cp .env.example .env
```

Add the required key/model values, then:

```bash
make test-llm
```

Do not enable external LLM diagnostics for cluster-derived data unless your data policy allows it.

---

# Approximate runtime and cost

Record the final values from the machine used for submission immediately before submitting.

Suggested format:

```text
Deterministic evaluation:
Runtime: ~1.2 seconds
External API cost: $0

Sandbox run:
Runtime: ~16 seconds
External API cost without Gemini: $0
External API cost with Gemini: $0 on the current Gemini free tier
```

---

# Safety boundary

The bundled live adapter is intentionally restricted.

It may mutate RBAC only when:

```text
kubectl context = kind-kuber
namespace label = kuber.dev/sandbox=true
```

Otherwise it should remain in dry-run mode.

The reference sandbox is validation infrastructure, not a production deployment template.
