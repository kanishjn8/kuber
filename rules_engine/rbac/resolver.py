from __future__ import annotations

from rules_engine.models import ParsedRbac, Permission, Policy, ServiceAccountRef


def resolve_effective_policy(parsed: ParsedRbac, service_account: ServiceAccountRef) -> Policy:
    """Resolve Role/ClusterRole bindings for one ServiceAccount.

    A ClusterRole referenced by a RoleBinding is namespace-scoped to the
    binding namespace. A ClusterRoleBinding remains cluster-wide.
    """

    permissions: list[Permission] = []
    for binding in parsed.bindings:
        if service_account not in binding.subjects:
            continue
        role = next(
            (
                candidate
                for candidate in parsed.roles
                if candidate.name == binding.role_name
                and ((binding.role_kind == "ClusterRole" and candidate.cluster_role) or (binding.role_kind == "Role" and not candidate.cluster_role and candidate.namespace == binding.namespace))
            ),
            None,
        )
        if role is None:
            continue
        namespace = None if binding.cluster_binding else binding.namespace
        source = f"{'ClusterRoleBinding' if binding.cluster_binding else 'RoleBinding'}/{binding.name}"
        for rule in role.rules:
            names: tuple[str | None, ...] = rule.resource_names or (None,)
            for group in rule.api_groups:
                for resource in rule.resources:
                    for verb in rule.verbs:
                        for resource_name in names:
                            permissions.append(Permission(group, resource, verb, namespace, resource_name, source))
    return Policy(
        permissions=tuple(permissions),
        name=f"{service_account.name}-effective",
        service_account=service_account.name,
        service_account_namespace=service_account.namespace,
    )

