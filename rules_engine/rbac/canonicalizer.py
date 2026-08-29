from __future__ import annotations

from rules_engine.models import Permission, Policy

SUPPORTED_RESOURCES: dict[str, tuple[str, ...]] = {
    "": ("pods", "configmaps", "secrets", "services"),
    "apps": ("deployments",),
    "batch": ("jobs",),
    "coordination.k8s.io": ("leases",),
}
SUPPORTED_VERBS: tuple[str, ...] = (
    "get",
    "list",
    "watch",
    "create",
    "update",
    "patch",
    "delete",
)


def is_supported_resource(api_group: str, resource: str) -> bool:
    if api_group == "*" or resource == "*":
        return True
    return resource in SUPPORTED_RESOURCES.get(api_group, ())


def expand_permission(permission: Permission) -> tuple[Permission, ...]:
    groups = tuple(SUPPORTED_RESOURCES) if permission.api_group == "*" else (permission.api_group,)
    verbs = SUPPORTED_VERBS if permission.verb == "*" else (permission.verb,)
    expanded: list[Permission] = []
    for group in groups:
        resources = SUPPORTED_RESOURCES.get(group, ()) if permission.resource == "*" else (permission.resource,)
        for resource in resources:
            for verb in verbs:
                expanded.append(
                    Permission(
                        api_group=group,
                        resource=resource,
                        verb=verb,
                        namespace=permission.namespace,
                        resource_name=permission.resource_name,
                        source=permission.source,
                    )
                )
    return tuple(expanded)


def expand_policy(policy: Policy) -> Policy:
    expanded = [item for permission in policy.permissions for item in expand_permission(permission)]
    return policy.with_permissions(expanded)


def effective_permission_count(policy: Policy) -> int:
    return len(expand_policy(policy).permissions)

