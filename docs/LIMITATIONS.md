# Limitations and future work

The MVP supports a deliberate subset: Pods, ConfigMaps, Secrets, Services,
Deployments, Jobs and Leases with get/list/watch/create/update/patch/delete.
It does not model subresources, CRDs, non-resource URLs, aggregated
ClusterRoles, admission control, impersonation, authorization webhooks,
service-mesh policy, cloud IAM, arbitrary audit logs, or full API discovery.

The resolver handles ServiceAccount subjects only and ignores other subject
kinds. It does not model escalation/bind/impersonate verbs. List/watch
`resourceNames` field-selector semantics are conservatively denied. Risk scores
are comparative project heuristics, not compliance or production risk ratings.

Live observation is intentionally instrumented inside the demo workload rather
than obtained from generic audit logs. Live demo scripts target one known kind
cluster, one namespace, one workload, and one owner-provided smoke command.
Production mutation is outside scope.

