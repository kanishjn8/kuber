from __future__ import annotations

from dataclasses import dataclass

from rules_engine.models import KubeEvent, Permission, Policy

RESOURCE_NAME_VERBS = frozenset({"get", "update", "patch", "delete"})


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    allowed: bool
    matching_permission: Permission | None = None
    reason: str = ""


def _matches(permission: Permission, event: KubeEvent) -> bool:
    if permission.api_group not in {"*", event.api_group}:
        return False
    if permission.resource not in {"*", event.resource}:
        return False
    if permission.verb not in {"*", event.verb}:
        return False
    if permission.namespace is not None and permission.namespace != event.namespace:
        return False
    if permission.resource_name is not None:
        # Kubernetes resourceNames does not safely constrain create, list or
        # watch in this normalized model (list/watch would need a name field selector).
        if event.verb not in RESOURCE_NAME_VERBS:
            return False
        if event.resource_name != permission.resource_name:
            return False
    return True


def authorize(policy: Policy, event: KubeEvent) -> AuthorizationDecision:
    for permission in policy.permissions:
        if _matches(permission, event):
            return AuthorizationDecision(True, permission, "matched deterministic RBAC rule")
    return AuthorizationDecision(False, None, "no matching permission")


def is_authorized(policy: Policy, event: KubeEvent) -> bool:
    return authorize(policy, event).allowed

