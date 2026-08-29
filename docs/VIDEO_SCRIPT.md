# Demo video script

1. Show the broad ClusterRoleBinding and explain why copied controller RBAC persists.
2. Run `make evaluate`; compare observed-only failures with verified repair.
3. Run `make demo-up`, then `make demo`; show normalized real API events.
4. Show the reduced Role and real leader-election 403 from Kubernetes.
5. Show the trajectory: diagnose, restore only Lease capability, retry.
6. Show final smoke success, before/after risk, and generated policy.
7. Close with the safety gate and the core insight: verification supplies evidence.

