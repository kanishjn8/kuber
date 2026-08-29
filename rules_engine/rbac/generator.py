from __future__ import annotations

from collections import defaultdict
from typing import Any

import yaml

from rules_engine.models import Permission, Policy


def _rule_key(permission: Permission) -> tuple[str, str, str | None]:
    return permission.api_group, permission.resource, permission.resource_name


def _rules(permissions: list[Permission]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str | None], set[str]] = defaultdict(set)
    for permission in permissions:
        grouped[_rule_key(permission)].add(permission.verb)
    result: list[dict[str, Any]] = []
    for (api_group, resource, resource_name), verbs in sorted(
        grouped.items(), key=lambda item: (item[0][0], item[0][1], item[0][2] or "")
    ):
        rule: dict[str, Any] = {
            "apiGroups": [api_group],
            "resources": [resource],
            "verbs": sorted(verbs),
        }
        if resource_name:
            rule["resourceNames"] = [resource_name]
        result.append(rule)
    return result


def policy_to_documents(policy: Policy) -> list[dict[str, Any]]:
    """Generate valid Role/Binding pairs, separating every policy scope."""

    by_scope: dict[str | None, list[Permission]] = defaultdict(list)
    for permission in policy.permissions:
        by_scope[permission.namespace].append(permission)
    documents: list[dict[str, Any]] = []
    for namespace, permissions in sorted(by_scope.items(), key=lambda item: item[0] or ""):
        cluster = namespace is None
        suffix = "cluster" if cluster else namespace
        role_name = f"{policy.name}-{suffix}"
        role: dict[str, Any] = {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "ClusterRole" if cluster else "Role",
            "metadata": {"name": role_name},
            "rules": _rules(permissions),
        }
        if namespace:
            role["metadata"]["namespace"] = namespace
        binding: dict[str, Any] = {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "ClusterRoleBinding" if cluster else "RoleBinding",
            "metadata": {"name": f"{role_name}-binding"},
            "roleRef": {
                "apiGroup": "rbac.authorization.k8s.io",
                "kind": role["kind"],
                "name": role_name,
            },
            "subjects": [
                {
                    "kind": "ServiceAccount",
                    "name": policy.service_account,
                    "namespace": policy.service_account_namespace,
                }
            ],
        }
        if namespace:
            binding["metadata"]["namespace"] = namespace
        documents.extend((role, binding))
    return documents


def policy_to_yaml(policy: Policy) -> str:
    documents = policy_to_documents(policy)
    return yaml.safe_dump_all(documents, sort_keys=False) if documents else "# Empty policy: no RBAC grants\n"
