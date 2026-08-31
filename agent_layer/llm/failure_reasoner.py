from __future__ import annotations

import json
import urllib.error
from dataclasses import dataclass

from agent_layer.interfaces import FailureDescription
from agent_layer.llm.provider import LLMProvider


@dataclass(frozen=True, slots=True)
class ReasoningExplanation:
    text: str
    source: str
    error: str | None = None


@dataclass(slots=True)
class FailureReasoner:
    provider: LLMProvider | None = None

    def explain(self, failure: FailureDescription) -> str:
        return self.explain_with_source(failure).text

    def explain_with_source(self, failure: FailureDescription) -> ReasoningExplanation:
        if failure.authorization_denial and failure.missing_events:
            capabilities = ", ".join(event.display() for event in failure.missing_events)
            fallback = f"Verification exercised required capabilities missing from the candidate: {capabilities}."
        else:
            fallback = f"Verification failed without a deterministically mapped RBAC denial: {failure.summary}"
        if self.provider is None:
            return ReasoningExplanation(fallback, "deterministic")
        context = {
            "summary": failure.summary,
            "authorization_denial": failure.authorization_denial,
            "missing_events": [event.to_dict() for event in failure.missing_events],
        }
        prompt = (
            "Explain this Kubernetes workload verification failure in at most three sentences. "
            "Do not generate YAML and do not claim a policy is safe. Structured context:\n"
            + json.dumps(context, sort_keys=True)
        )
        try:
            enhanced = self.provider.complete(prompt)
            normalized = enhanced.strip()
            if normalized:
                return ReasoningExplanation(normalized, type(self.provider).__name__)
        except Exception as exc:
            if isinstance(exc, urllib.error.HTTPError):
                error = f"Gemini HTTP {exc.code}: {exc.reason}"
            elif isinstance(exc, urllib.error.URLError):
                error = f"Gemini connection error: {exc.reason}"
            else:
                message = str(exc).replace("\n", " ")[:240]
                error = f"{type(exc).__name__}: {message}" if message else type(exc).__name__
            return ReasoningExplanation(fallback, "deterministic-fallback", error)
        return ReasoningExplanation(fallback, "deterministic-fallback")
