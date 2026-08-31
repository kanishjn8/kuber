# Kubernetes Reference Sandbox

The reference sandbox exists to show Kuber working against **real Kubernetes authorization**.

It is not required for the deterministic judge evaluation and it is not a production deployment template.

## What the sandbox contains

The sandbox creates:

- local `kind-kuber` Kubernetes cluster,
- Kafka in KRaft mode,
- Redis,
- five application services,
- separate ServiceAccounts,
- intentionally broad starting RBAC,
- service-specific smoke tests,
- Kafka consumer workers.

## Why it exists

The deterministic benchmark suite is easy to reproduce, but a simulator cannot prove that Kubernetes itself really rejects a bad policy.

The sandbox demonstrates that.

The most important moment is:

```text
Kuber applies smaller RBAC
        ↓
worker-service runs rare Job flow
        ↓
real Kubernetes API server returns 403
        ↓
Kuber repairs exact missing capability
        ↓
retries
        ↓
service passes
```

## Requirements

- Docker
- kind
- kubectl
- curl
- Python 3.12+
- uv

## Commands

```bash
make sandbox-check
make sandbox-up
make sandbox-status
make sandbox-run
make sandbox-reset
make sandbox-down
```

## What `sandbox-up` does

It:

1. creates or reuses `kind-kuber`,
2. deploys Kafka in KRaft mode,
3. deploys Redis,
4. builds and loads the example service images,
5. deploys the services,
6. creates their ServiceAccounts and starting RBAC,
7. creates Kafka topics,
8. waits for the environment to become ready.

## What `sandbox-run` does

It:

1. resets the known starting policies,
2. restarts/warmups the workloads,
3. intentionally avoids the rare worker Job workflow during warmup,
4. discovers opted-in services,
5. builds service-scoped context,
6. publishes optimization tasks,
7. runs multiple consumers,
8. executes each service's LangGraph workflow,
9. applies smaller policies,
10. runs each service's verification profile,
11. shows real Kubernetes 403 responses when permissions are missing,
12. repairs only the exact missing capabilities,
13. runs final workload and system verification,
14. writes reports and trajectories.

## Example hidden path

The worker service has a rare reconciliation workflow that uses Kubernetes Jobs.

Normal warmup does not exercise it.

During full verification:

```text
jobs:create → 403
restore create
retry

jobs:get → 403
restore get
retry

jobs:delete → 403
restore delete
retry

all tests pass
```

## What Kuber is actually testing

Kuber does not inspect the code and simply declare that a policy looks correct.

It applies the candidate RBAC and triggers the service's owner-defined smoke tests.

The service then makes its normal Kubernetes API calls using its ServiceAccount.

Kubernetes itself decides whether those calls are allowed.

```text
Kuber changes Role/RoleBinding
        ↓
service executes behavior
        ↓
service calls Kubernetes API
        ↓
Kubernetes checks ServiceAccount RBAC
        ↓
ALLOW or 403
```

## Gemini

Gemini is optional.

It may explain a technical 403 in readable language.

It does not:

- authorize a permission,
- decide whether RBAC is valid,
- apply a policy,
- approve the final result.

Leave the API key unset for a fully local deterministic run.

## Safety

The live adapter is restricted to:

```text
context: kind-kuber
namespace label: kuber.dev/sandbox=true
```

If the safety boundary does not match, live mutation must be refused or downgraded to dry-run mode.
