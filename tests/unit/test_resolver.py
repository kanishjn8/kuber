from rules_engine.models import ServiceAccountRef
from rules_engine.rbac.parser import parse_rbac
from rules_engine.rbac.resolver import resolve_effective_policy


def _manifest(binding_kind: str, role_kind: str = "ClusterRole") -> str:
    binding_namespace = "namespace: team-a" if binding_kind == "RoleBinding" else ""
    return f"""
kind: {role_kind}
apiVersion: rbac.authorization.k8s.io/v1
metadata: {{name: reader{", namespace: team-a" if role_kind == "Role" else ""}}}
rules:
  - apiGroups: [""]
    resources: [pods]
    verbs: [get, list]
---
kind: {binding_kind}
apiVersion: rbac.authorization.k8s.io/v1
metadata:
  name: reader-binding
  {binding_namespace}
roleRef: {{apiGroup: rbac.authorization.k8s.io, kind: {role_kind}, name: reader}}
subjects:
  - {{kind: ServiceAccount, name: app, namespace: team-a}}
"""


def test_cluster_role_binding_is_cluster_wide() -> None:
    policy = resolve_effective_policy(
        parse_rbac(_manifest("ClusterRoleBinding")), ServiceAccountRef("app", "team-a")
    )
    assert {item.namespace for item in policy.permissions} == {None}
    assert all(item.source == "ClusterRoleBinding/reader-binding" for item in policy.permissions)


def test_role_binding_scopes_cluster_role_to_namespace() -> None:
    policy = resolve_effective_policy(
        parse_rbac(_manifest("RoleBinding")), ServiceAccountRef("app", "team-a")
    )
    assert {item.namespace for item in policy.permissions} == {"team-a"}


def test_unbound_service_account_gets_no_permissions() -> None:
    policy = resolve_effective_policy(
        parse_rbac(_manifest("ClusterRoleBinding")), ServiceAccountRef("other", "team-a")
    )
    assert policy.permissions == ()
