import pytest

from rules_engine.models import KubeEvent, Permission, Policy
from rules_engine.rbac.authorization import is_authorized


def test_wildcards_authorize_supported_event() -> None:
    policy = Policy((Permission("*", "*", "*", None),))
    assert is_authorized(policy, KubeEvent("batch", "jobs", "create", "payments", "job-1"))


def test_namespace_boundary_is_enforced() -> None:
    policy = Policy((Permission("", "pods", "list", "team-a"),))
    assert is_authorized(policy, KubeEvent("", "pods", "list", "team-a"))
    assert not is_authorized(policy, KubeEvent("", "pods", "list", "team-b"))


@pytest.mark.parametrize("verb", ["list", "watch", "create"])
def test_resource_names_do_not_optimize_unsafe_verbs(verb: str) -> None:
    policy = Policy((Permission("", "configmaps", verb, "payments", "app-config"),))
    event = KubeEvent("", "configmaps", verb, "payments", "app-config")
    assert not is_authorized(policy, event)


@pytest.mark.parametrize("verb", ["get", "update", "patch", "delete"])
def test_resource_names_match_named_requests(verb: str) -> None:
    policy = Policy((Permission("", "configmaps", verb, "payments", "app-config"),))
    assert is_authorized(policy, KubeEvent("", "configmaps", verb, "payments", "app-config"))
    assert not is_authorized(policy, KubeEvent("", "configmaps", verb, "payments", "other"))


def test_missing_verb_is_denied() -> None:
    policy = Policy((Permission("", "pods", "get", "payments"),))
    assert not is_authorized(policy, KubeEvent("", "pods", "list", "payments"))

