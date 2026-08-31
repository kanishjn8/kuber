import io
import urllib.error

from agent_layer.interfaces import FailureDescription
from agent_layer.llm import FailureReasoner
from rules_engine.models import KubeEvent


class BrokenProvider:
    def complete(self, prompt: str) -> str:
        raise RuntimeError("offline")


class StaticProvider:
    def __init__(self, response: str) -> None:
        self.response = response

    def complete(self, prompt: str) -> str:
        assert "Kubernetes workload verification failure" in prompt
        return self.response


def test_reasoner_is_offline_safe() -> None:
    failure = FailureDescription(
        "lease forbidden",
        (KubeEvent("coordination.k8s.io", "leases", "update", "payments", "leader"),),
        True,
    )
    result = FailureReasoner(BrokenProvider()).explain_with_source(failure)
    assert "update coordination.k8s.io/leases/leader" in result.text
    assert result.source == "deterministic-fallback"
    assert result.error == "RuntimeError: offline"


def test_reasoner_uses_provider_explanation_when_available() -> None:
    failure = FailureDescription("smoke failure")

    result = FailureReasoner(StaticProvider("The lease update was denied.")).explain_with_source(
        failure
    )

    assert result.text == "The lease update was denied."
    assert result.source == "StaticProvider"
    assert result.error is None


def test_reasoner_handles_empty_provider_response() -> None:
    failure = FailureDescription("health endpoint failed")

    result = FailureReasoner(StaticProvider(" ")).explain_with_source(failure)

    assert result.source == "deterministic-fallback"
    assert "health endpoint failed" in result.text
    assert result.error is None


def test_reasoner_without_provider_is_deterministic() -> None:
    failure = FailureDescription("unknown failure")

    assert FailureReasoner().explain(failure) == (
        "Verification failed without a deterministically mapped RBAC denial: unknown failure"
    )


def test_reasoner_sanitizes_http_error() -> None:
    class HttpProvider:
        def complete(self, prompt: str) -> str:
            raise urllib.error.HTTPError(
                "https://example.invalid", 429, "Too Many Requests", {}, io.BytesIO()
            )

    result = FailureReasoner(HttpProvider()).explain_with_source(FailureDescription("limited"))

    assert result.error == "Gemini HTTP 429: Too Many Requests"
    assert "example.invalid" not in result.error


def test_reasoner_sanitizes_connection_error() -> None:
    class OfflineProvider:
        def complete(self, prompt: str) -> str:
            raise urllib.error.URLError("network unavailable")

    result = FailureReasoner(OfflineProvider()).explain_with_source(FailureDescription("offline"))

    assert result.error == "Gemini connection error: network unavailable"
