from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from agent_layer.llm.provider import GeminiProvider, provider_from_environment


class FakeResponse:
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "Lease update is probably required."}
                            ]
                        }
                    }
                ]
            }
        ).encode("utf-8")


def test_gemini_provider_uses_generate_content_request(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: int) -> FakeResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = GeminiProvider("test-key", "gemini-test", "https://gemini.invalid/v1beta", 7)
    result = provider.complete("Explain this denial")

    request = captured["request"]
    body = json.loads(request.data.decode("utf-8"))
    assert request.full_url == "https://gemini.invalid/v1beta/models/gemini-test:generateContent"
    assert request.get_header("X-goog-api-key") == "test-key"
    assert body["contents"][0]["parts"][0]["text"] == "Explain this denial"
    assert captured["timeout"] == 7
    assert result == "Lease update is probably required."


def test_provider_loads_gemini_configuration_from_dotenv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for name in (
        "GEMINI_API_KEY",
        "GEMINI_MODEL",
        "GEMINI_API_BASE_URL",
        "GEMINI_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / ".env").write_text(
        "GEMINI_API_KEY=local-key\n"
        "GEMINI_MODEL=gemini-local\n"
        "GEMINI_API_BASE_URL=https://local.invalid/v1beta\n"
        "GEMINI_TIMEOUT_SECONDS=9\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    provider = provider_from_environment()

    assert isinstance(provider, GeminiProvider)
    assert provider.api_key == "local-key"
    assert provider.model == "gemini-local"
    assert provider.api_base_url == "https://local.invalid/v1beta"
    assert provider.timeout_seconds == 9


def test_missing_api_key_disables_optional_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert provider_from_environment() is None

