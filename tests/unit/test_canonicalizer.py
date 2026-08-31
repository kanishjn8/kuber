from rules_engine.models import Permission
from rules_engine.rbac.canonicalizer import expand_permission


def test_wildcard_api_group_does_not_invent_resource_group_combinations() -> None:
    expanded = expand_permission(Permission("*", "configmaps", "get", "payments"))
    assert {(permission.api_group, permission.resource) for permission in expanded} == {
        ("", "configmaps")
    }


def test_full_wildcard_expands_to_the_documented_mvp_catalog() -> None:
    expanded = expand_permission(Permission("*", "*", "*", None))
    assert len(expanded) == 49
