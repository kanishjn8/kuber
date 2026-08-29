# Judge layer

This layer runs Kuber without Kubernetes. Each benchmark contains initial RBAC,
observed normalized events, owner-declared verification tests, an expected
minimum policy, and metadata. The simulator answers only whether the supported
RBAC policy authorizes each event.

Run from the repository root with `make evaluate`. See
[`docs/EVALUATION.md`](../docs/EVALUATION.md) for metric definitions.

