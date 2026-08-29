from __future__ import annotations

from rules_engine.models import KubeEvent, Permission, Policy
from rules_engine.rbac.authorization import is_authorized

RESOURCE_NAME_SAFE_VERBS = frozenset({"get", "update", "patch", "delete"})


def event_permission(event: KubeEvent) -> Permission:
    name = event.resource_name if event.verb in RESOURCE_NAME_SAFE_VERBS else None
    return Permission(event.api_group, event.resource, event.verb, event.namespace, name, "Kuber/verified")


def observed_only_policy(current: Policy, observed: tuple[KubeEvent, ...]) -> Policy:
    """Build the narrowest supported policy for observed, currently-authorized calls."""

    unauthorized = [event for event in observed if not is_authorized(current, event)]
    if unauthorized:
        rendered = ", ".join(event.display() for event in unauthorized)
        raise ValueError(f"observed usage is not authorized by the current policy: {rendered}")
    return Policy(
        permissions=tuple(event_permission(event) for event in observed),
        name=f"{current.service_account}-kuber",
        service_account=current.service_account,
        service_account_namespace=current.service_account_namespace,
    )


def repair_policy(candidate: Policy, missing_events: tuple[KubeEvent, ...], original: Policy) -> Policy:
    """Add only denied capabilities that the original policy actually allowed."""

    additions: list[Permission] = []
    for event in missing_events:
        if not is_authorized(original, event):
            raise ValueError(f"refusing to invent permission absent from original policy: {event.display()}")
        additions.append(event_permission(event))
    return candidate.with_permissions([*candidate.permissions, *additions])

