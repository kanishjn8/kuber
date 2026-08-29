from agent_layer.interfaces import FailureDescription
from agent_layer.llm import FailureReasoner
from rules_engine.models import KubeEvent


class BrokenProvider:
    def complete(self, prompt: str) -> str:
        raise RuntimeError("offline")


def test_reasoner_is_offline_safe() -> None:
    failure = FailureDescription(
        "lease forbidden",
        (KubeEvent("coordination.k8s.io", "leases", "update", "payments", "leader"),),
        True,
    )
    explanation = FailureReasoner(BrokenProvider()).explain(failure)
    assert "update coordination.k8s.io/leases/leader" in explanation

