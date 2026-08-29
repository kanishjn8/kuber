from __future__ import annotations

from rules_engine.models import Permission

MUTATING_VERBS = frozenset({"create", "update", "patch", "delete", "*"})


def permission_risk_signals(permission: Permission) -> tuple[tuple[str, int], ...]:
    """Return deterministic heuristic signals; this is not an industry standard."""

    signals: list[tuple[str, int]] = []
    if permission.verb == "*":
        signals.append(("wildcard verbs", 20))
    if permission.resource == "*" or permission.api_group == "*":
        signals.append(("wildcard resources/API groups", 25))
    if permission.namespace is None:
        signals.append(("cluster-wide scope", 8))
    if permission.source and permission.source.startswith("ClusterRoleBinding/"):
        signals.append(("ClusterRoleBinding grant", 5))
    if permission.resource == "secrets":
        signals.append((f"{permission.verb} secrets", 8 if permission.verb in {"get", "list", "watch", "*"} else 12))
    if permission.verb in MUTATING_VERBS:
        signals.append((f"mutating verb: {permission.verb}", 4))
    if permission.verb in {"delete", "*"}:
        signals.append(("delete capability", 5))
    if permission.resource in {"roles", "clusterroles", "rolebindings", "clusterrolebindings"}:
        signals.append(("RBAC modification capability", 20))
    return tuple(signals)

