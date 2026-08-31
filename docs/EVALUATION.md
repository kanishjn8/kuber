# Evaluation

## What are we trying to prove?

The question is not:

> "Can Kuber remove a lot of permissions?"

A system can remove almost everything and look impressive while completely breaking the application.

The real question is:

> **Can Kuber remove unnecessary permissions while keeping the workload working?**

## Baseline

Our simple baseline is an **observed-only reducer**.

It looks at Kubernetes API calls seen during normal activity and creates a policy containing only those observed permissions.

Example:

```text
Observed:
- read ConfigMap

Baseline policy:
- read ConfigMap
```

This is simple and reasonable, but it can miss rare behavior.

For example:

```text
Normal activity:
- read ConfigMap

Rare reconciliation flow:
- create Job
- get Job
- delete Job
```

If that rare flow was not observed, the baseline removes those Job permissions and the service breaks later.

## Kuber

Kuber starts from a similarly narrow candidate, but it does not automatically trust it.

It:

```text
creates smaller policy
        ↓
applies it
        ↓
runs owner-defined verification
        ↓
PASS → accept

403 / missing permission
        ↓
restore only the missing permission
        ↓
retry
```

## Benchmark set

The evaluation contains 14 fixed scenarios.

They cover cases such as:

- reading a ConfigMap,
- reading a named Secret,
- Job reconciliation,
- leader election,
- namespace-only permissions,
- named-resource access,
- hidden code paths,
- wildcard removal,
- cluster-to-namespace reduction,
- multi-service execution,
- parallel workers,
- final system verification.

Both the baseline and Kuber receive the **same cases**.

The deterministic evaluation does not require an LLM.

## Main result

The easiest result to understand is functional success:

| | Simple baseline | Kuber |
|---|---:|---:|
| Scenarios that still worked | **4 / 14** | **14 / 14** |

The baseline produced very small policies, but it broke 10 of the 14 scenarios.

Kuber kept all 14 scenarios working.

## Permission reduction

| | Simple baseline | Kuber |
|---|---:|---:|
| Raw permission reduction | 97.5% | 95.3% |

The baseline removes slightly more permissions.

That is **not** a win by itself, because many of those removed permissions were actually needed.

Kuber keeps a small number of additional permissions when verification proves that they are required.

## Verified Risk Reduction

We also use a project metric called **Validated Risk Reduction (VRR)**.

The idea is simple:

> We only count a security improvement if the workload still works.

```text
if all verification tests pass:
    VRR = percentage reduction in the project risk score

if verification fails:
    VRR = 0
```

Results:

| | Simple baseline | Kuber |
|---|---:|---:|
| Validated Risk Reduction | 27.4% | **91.9%** |

The risk score is a project heuristic used for comparison. It is **not** a compliance score or industry standard.

It gives extra weight to broad or dangerous access such as:

- wildcard verbs/resources,
- cluster-wide access,
- ClusterRoleBinding usage,
- Secret access,
- mutation,
- deletion.

## Why this comparison matters

The baseline achieved:

> 97.5% raw permission reduction

but only:

> 4 / 14 scenarios still worked

Kuber achieved:

> 95.3% raw permission reduction

while:

> all 14 / 14 scenarios still worked

So the main result is not that Kuber removes the absolute maximum number of permissions.

The result is:

> **Kuber removes most unnecessary access without accepting a policy that fails the declared workload tests.**

## Challenging case: hidden Job workflow

One benchmark intentionally hides a valid Job reconciliation path from the observed traffic.

Normal evidence sees only a read operation.

The full verification requires:

```text
create Job
get Job
delete Job
```

The observed-only baseline removes these permissions and fails.

Kuber sees the failure, restores only the missing originally allowed capabilities, and verifies again.

## Live Kubernetes validation

The deterministic benchmark suite proves that the logic is reproducible.

The reference sandbox separately proves that the same workflow can operate against real Kubernetes authorization.

In the sandbox, the `worker-service` receives real Kubernetes 403 responses for missing Job permissions.

Kuber repairs them one at a time and retries until all service tests pass.

## What this evaluation does not prove

The evaluation does not claim:

- that Kuber finds every possible future application path,
- that the project risk score is an industry standard,
- that three Kafka workers provide linear scaling,
- that the bundled sandbox adapter is production-ready.

Kuber can only verify behavior covered by the owner-defined verification profile.

## Regenerate results

```bash
make evaluate
```

Generated artifacts are written under:

```text
artifacts/evaluation/
artifacts/trajectories/
```

Results should be regenerated from the current implementation before submission rather than copied manually.
