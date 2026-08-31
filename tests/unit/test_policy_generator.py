from rules_engine.models import Permission, Policy, ServiceAccountRef
from rules_engine.rbac.generator import policy_to_yaml
from rules_engine.rbac.parser import parse_rbac
from rules_engine.rbac.resolver import resolve_effective_policy


def test_generated_policy_round_trips_without_cross_product_overgrant() -> None:
    policy = Policy(
        (
            Permission("", "pods", "list", "payments"),
            Permission("", "configmaps", "get", "payments", "app-config"),
        ),
        name="payment",
        service_account="app",
        service_account_namespace="payments",
    )
    resolved = resolve_effective_policy(
        parse_rbac(policy_to_yaml(policy)), ServiceAccountRef("app", "payments")
    )
    keys = {item.key() for item in resolved.permissions}
    assert ("", "pods", "list", "payments", None) in keys
    assert ("", "configmaps", "get", "payments", "app-config") in keys
    assert ("", "pods", "get", "payments", None) not in keys


def test_empty_policy_generates_no_grants() -> None:
    assert policy_to_yaml(Policy()).startswith("# Empty policy")
