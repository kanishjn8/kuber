# Evaluation methodology

The primary metric is **Validated Risk Reduction (VRR)**:

```text
if every verification test passes:
    VRR = 100 × (initial risk - final risk) / initial risk
else:
    VRR = 0
```

The deterministic risk score is a benchmark heuristic, not an industry
standard. It assigns documented points for wildcard verbs/resources,
cluster-wide scope, ClusterRoleBinding use, Secrets, mutation, and deletion,
then caps presentation at 100. Raw effective-permission reduction is reported
separately, as are success, remaining broad grants, incorrect removals, repair
iterations, and runtime.

The observed-only baseline and Kuber receive identical cases. Several
verification files deliberately contain legitimate events absent from observed
traffic. Results are never embedded in evaluation code; `make evaluate`
generates every artifact from the current implementation and data.

