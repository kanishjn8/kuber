from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from agent_layer.llm import provider as provider_module
from agent_layer.llm.provider import GeminiProvider, provider_from_environment


class FakeResponse:
    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(
            {
                "candidates": [
                    {"content": {"parts": [{"text": "Lease update is probably required."}]}}
                ]
            }
        ).encode("utf-8")


class EmptyResponse(FakeResponse):
    def read(self) -> bytes:
        return b'{"candidates":[{"content":{"parts":[]}}]}'


def test_gemini_provider_uses_generate_content_request(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: int) -> FakeResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = GeminiProvider("test-key", 7, "gemini-test")
    result = provider.complete("Explain this denial")

    request = captured["request"]
    body = json.loads(request.data.decode("utf-8"))
    assert request.full_url == (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent"
    )
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
        "GEMINI_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / ".env").write_text(
        "GEMINI_API_KEY=local-key\nGEMINI_MODEL=gemini-local\nGEMINI_TIMEOUT_SECONDS=9\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    provider = provider_from_environment()

    assert isinstance(provider, GeminiProvider)
    assert provider.api_key == "local-key"
    assert provider.model == "gemini-local"
    assert provider.timeout_seconds == 9


def test_missing_api_key_disables_optional_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert provider_from_environment() is None


def test_gemini_provider_rejects_response_without_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: EmptyResponse())

    with pytest.raises(ValueError, match="no text candidate"):
        GeminiProvider("test-key").complete("Explain")


def test_invalid_timeout_is_reported_without_making_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "local-key")
    monkeypatch.setenv("GEMINI_TIMEOUT_SECONDS", "later")

    with pytest.raises(ValueError, match="must be an integer"):
        provider_from_environment()


def test_process_environment_takes_precedence_over_dotenv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".env").write_text(
        "GEMINI_API_KEY=file-key\nGEMINI_MODEL=gemini-file\nGEMINI_TIMEOUT_SECONDS=5\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "process-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-process")
    monkeypatch.setenv("GEMINI_TIMEOUT_SECONDS", "11")

    provider = provider_from_environment()

    assert isinstance(provider, GeminiProvider)
    assert provider.api_key == "process-key"
    assert provider.model == "gemini-process"
    assert provider.timeout_seconds == 11


def test_gemini_provider_retries_transient_http_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0
    delays: list[float] = []

    def transient_then_success(*args: object, **kwargs: object) -> FakeResponse:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise urllib.error.HTTPError("https://example.invalid", 503, "Unavailable", {}, None)
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", transient_then_success)
    monkeypatch.setattr(provider_module, "sleep", delays.append)

    result = GeminiProvider("test-key").complete("Explain")

    assert result == "Lease update is probably required."
    assert attempts == 3
    assert delays == [0.5, 1.0]


def test_gemini_provider_does_not_retry_client_error(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    def unauthorized(*args: object, **kwargs: object) -> FakeResponse:
        nonlocal attempts
        attempts += 1
        raise urllib.error.HTTPError("https://example.invalid", 401, "Unauthorized", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", unauthorized)

    with pytest.raises(urllib.error.HTTPError):
        GeminiProvider("test-key").complete("Explain")
    assert attempts == 1


@pytest.mark.parametrize(
    ("api_key", "timeout", "model", "message"),
    [
        ("", 20, "gemini-test", "key must not be empty"),
        ("key", 0, "gemini-test", "timeout must be positive"),
        ("key", 20, "../bad", "plain model name"),
    ],
)
def test_gemini_provider_rejects_invalid_configuration(
    api_key: str, timeout: int, model: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        GeminiProvider(api_key, timeout, model)
