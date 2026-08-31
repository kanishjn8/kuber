from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from time import sleep
from typing import Protocol

from dotenv import load_dotenv


class LLMProvider(Protocol):
    def complete(self, prompt: str) -> str: ...


GEMINI_API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
TRANSIENT_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_REQUEST_ATTEMPTS = 3
_MODEL_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass(frozen=True, slots=True)
class GeminiProvider:
    """Minimal Gemini REST provider for an explicitly configured model."""

    api_key: str
    timeout_seconds: int = 20
    model: str = DEFAULT_GEMINI_MODEL

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError("Gemini API key must not be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("Gemini timeout must be positive")
        normalized_model = self.model.removeprefix("models/").strip()
        if not _MODEL_NAME.fullmatch(normalized_model):
            raise ValueError("Gemini model must be a plain model name")
        object.__setattr__(self, "model", normalized_model)

    @property
    def endpoint(self) -> str:
        return f"{GEMINI_API_ROOT}/models/{self.model}:generateContent"

    def complete(self, prompt: str) -> str:
        request = urllib.request.Request(
            self.endpoint,
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
        response_body: bytes | None = None
        for attempt in range(MAX_REQUEST_ATTEMPTS):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    response_body = response.read()
                break
            except urllib.error.HTTPError as exc:
                if exc.code not in TRANSIENT_HTTP_STATUSES or attempt == MAX_REQUEST_ATTEMPTS - 1:
                    raise
                # Brief bounded backoff improves provider reliability while keeping
                # deterministic fallback latency predictable.
                sleep(0.5 * (2**attempt))
        if response_body is None:  # pragma: no cover - the loop either returns or raises
            raise RuntimeError("Gemini request completed without a response")
        value = json.loads(response_body.decode("utf-8"))
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
        api_key=api_key,
        timeout_seconds=timeout,
        model=os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
    )
