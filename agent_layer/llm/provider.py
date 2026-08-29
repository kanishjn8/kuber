from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv


class LLMProvider(Protocol):
    def complete(self, prompt: str) -> str: ...


@dataclass(frozen=True, slots=True)
class GeminiProvider:
    """Minimal Gemini REST provider; the core does not depend on a vendor SDK."""

    api_key: str
    model: str = "gemini-2.5-flash"
    api_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    timeout_seconds: int = 20

    def complete(self, prompt: str) -> str:
        model = self.model.removeprefix("models/")
        endpoint = (
            f"{self.api_base_url.rstrip('/')}/models/"
            f"{urllib.parse.quote(model, safe='')}:generateContent"
        )
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(
                {
                    "contents": [
                        {
                            "role": "user",
                            "parts": [{"text": prompt}],
                        }
                    ],
                    "generationConfig": {
                        "temperature": 0.2,
                        "maxOutputTokens": 512,
                    },
                }
            ).encode("utf-8"),
            headers={
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310 - explicitly configured endpoint
            value = json.loads(response.read().decode("utf-8"))
        parts: list[str] = []
        for candidate in value.get("candidates", []):
            content = candidate.get("content", {})
            for part in content.get("parts", []):
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
            if parts:
                break
        if not parts:
            raise ValueError("Gemini response contained no text candidate")
        return "\n".join(parts)


def provider_from_environment() -> LLMProvider | None:
    """Load optional Gemini configuration, preferring existing process values."""

    load_dotenv(dotenv_path=Path(".env"), override=False)
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        timeout = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "20"))
    except ValueError as exc:
        raise ValueError("GEMINI_TIMEOUT_SECONDS must be an integer") from exc
    return GeminiProvider(
        api_key,
        os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        os.getenv(
            "GEMINI_API_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta",
        ),
        timeout,
    )
