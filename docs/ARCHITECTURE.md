# Architecture

Kuber has one engine and two environment adapters. `rules_engine` contains only
deterministic models, RBAC parsing/resolution/authorization, policy generation,
minimization, and risk scoring. It imports no environment or LLM code.
`agent_layer` owns the Inspector, Reducer and Verifier plus the bounded
orchestrator. It sees environments only through `EnvironmentAdapter`.

`judge_layer.SimulatorEnvironment` evaluates normalized `KubeEvent` objects.
`demo_layer.KubernetesEnvironment` applies the same `Policy` through `kubectl`,
runs the owner-supplied smoke command, and derives denied events from structured
workload logs. Thus the control flow and security decisions are shared.

```text
INSPECT → PROPOSE → APPLY → VERIFY
                           │ fail
                           ▼
                      DIAGNOSE → REPAIR → RETRY (bounded)
                           │ pass
                           ▼
                    ACCEPT + REPORT
```

The initial proposal is the narrowest supported policy for observed calls.
Every observed event must already be authorized by the original policy. A
repair is accepted only for a normalized event that the original policy also
authorized. Generated YAML is parsed and resolved again before live apply.

Namespace `None` represents cluster-wide scope. A ClusterRole used by a
RoleBinding receives that binding's namespace; one used by a
ClusterRoleBinding remains cluster-wide. Wildcards remain explicit until
effective-count expansion, so risk remains visible.

