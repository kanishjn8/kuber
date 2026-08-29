from __future__ import annotations

import json
from dataclasses import dataclass

from agent_layer.interfaces import FailureDescription
from agent_layer.llm.provider import LLMProvider


@dataclass(slots=True)
class FailureReasoner:
    provider: LLMProvider | None = None

    def explain(self, failure: FailureDescription) -> str:
        if failure.authorization_denial and failure.missing_events:
            capabilities = ", ".join(event.display() for event in failure.missing_events)
            fallback = f"Verification exercised required capabilities missing from the candidate: {capabilities}."
        else:
            fallback = f"Verification failed without a deterministically mapped RBAC denial: {failure.summary}"
        if self.provider is None:
            return fallback
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
            return enhanced or fallback
        except Exception:
            return fallback

