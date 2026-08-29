import pytest

from rules_engine.minimizer import candidate_reductions, observed_only_policy, repair_policy
from rules_engine.models import KubeEvent, Permission, Policy
from rules_engine.rbac.authorization import is_authorized


def test_observed_only_restricts_named_get_but_not_list() -> None:
    current = Policy((Permission("", "*", "*", "payments"),), service_account="app", service_account_namespace="payments")
    observed = (
        KubeEvent("", "configmaps", "get", "payments", "app-config"),
        KubeEvent("", "pods", "list", "payments"),
    )
    candidate = observed_only_policy(current, observed)
    assert is_authorized(candidate, observed[0])
    assert is_authorized(candidate, observed[1])
    named_get = next(item for item in candidate.permissions if item.verb == "get")
    assert named_get.resource_name == "app-config"
    assert next(item for item in candidate.permissions if item.verb == "list").resource_name is None


def test_repair_restores_only_originally_authorized_hidden_path() -> None:
    current = Policy((Permission("", "configmaps", "*", "payments"),))
    candidate = observed_only_policy(current, (KubeEvent("", "configmaps", "get", "payments", "app-config"),))
    hidden = KubeEvent("", "configmaps", "list", "payments")
    repaired = repair_policy(candidate, (hidden,), current)
    assert is_authorized(repaired, hidden)
    with pytest.raises(ValueError, match="refusing to invent"):
        repair_policy(candidate, (KubeEvent("", "secrets", "get", "payments", "x"),), current)


def test_unused_candidate_reductions_are_risk_ordered() -> None:
    current = Policy((Permission("", "pods", "get", "payments"), Permission("*", "*", "*", None)))
    reductions = candidate_reductions(current, ())
    assert reductions[0].risk_value >= reductions[-1].risk_value

