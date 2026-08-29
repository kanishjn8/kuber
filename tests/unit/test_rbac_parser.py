import pytest

from rules_engine.rbac.parser import RbacParseError, UnsupportedResourceError, parse_rbac


def test_parses_all_supported_rbac_kinds() -> None:
    parsed = parse_rbac(
        """
apiVersion: v1
kind: ServiceAccount
metadata: {name: app, namespace: payments}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata: {name: reader, namespace: payments}
rules:
  - apiGroups: [""]
    resources: [configmaps]
    verbs: [get]
    resourceNames: [app-config]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata: {name: app-reader, namespace: payments}
roleRef: {apiGroup: rbac.authorization.k8s.io, kind: Role, name: reader}
subjects:
  - {kind: ServiceAccount, name: app, namespace: payments}
"""
    )
    assert len(parsed.service_accounts) == 1
    assert parsed.roles[0].rules[0].resource_names == ("app-config",)
    assert parsed.bindings[0].subjects[0].name == "app"


@pytest.mark.parametrize(
    "manifest, error",
    [
        ("kind: Role\nmetadata: {name: x, namespace: n}\nrules: [", RbacParseError),
        ("kind: Deployment\nmetadata: {name: x}", RbacParseError),
        ("kind: Role\nmetadata: {name: x, namespace: n}\nrules: [{apiGroups: [''], resources: [nodes], verbs: [get]}]", UnsupportedResourceError),
    ],
)
def test_rejects_invalid_or_unsupported_input(manifest: str, error: type[Exception]) -> None:
    with pytest.raises(error):
        parse_rbac(manifest)

