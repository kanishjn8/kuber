from rules_engine.models import Permission, Policy
from rules_engine.risk import score_policy


def test_risk_is_deterministic_explainable_and_capped() -> None:
    broad = Policy((Permission("*", "*", "*", None, source="ClusterRoleBinding/admin"),))
    first = score_policy(broad)
    second = score_policy(broad)
    assert first == second
    assert 0 < first.score <= 100
    assert first.uncapped_score >= first.score
    assert {finding.reason for finding in first.findings} >= {
        "wildcard verbs",
        "wildcard resources/API groups",
        "cluster-wide scope",
    }


def test_narrow_read_is_lower_risk() -> None:
    broad = Policy((Permission("", "secrets", "*", None),))
    narrow = Policy((Permission("", "configmaps", "get", "payments", "app-config"),))
    assert score_policy(narrow).score < score_policy(broad).score
